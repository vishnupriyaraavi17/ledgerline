"""financial operations

Revision ID: 0004_financial_operations
Revises: 0003_create_financial_foundation
Create Date: 2026-11-07 10:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

from backend.app.core.config import settings

# revision identifiers, used by Alembic.
revision: str = '0004_financial_operations'
down_revision: Union[str, None] = '0003_create_financial_foundation'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Alembic Pre-Flight Role Verification (Fails Closed)
    current_user = conn.execute(sa.text("SELECT current_user")).scalar()
    if current_user != "ledgerline_owner":
        raise RuntimeError(
            f"Pre-flight role verification failed: Alembic migration must execute as 'ledgerline_owner', "
            f"but current_user is '{current_user}'"
        )

    app_user = settings.RUNTIME_POSTGRES_USER
    if app_user != "ledgerline_app":
        raise RuntimeError(
            f"Pre-flight role verification failed: Expected canonical runtime user 'ledgerline_app', got '{app_user}'"
        )

    role_row = conn.execute(
        sa.text(
            "SELECT rolsuper, rolcreaterole, rolcreatedb, rolinherit, rolreplication, rolbypassrls "
            "FROM pg_roles WHERE rolname = :rolname"
        ),
        {"rolname": app_user},
    ).fetchone()

    if role_row is None:
        raise RuntimeError(
            f"Pre-flight role verification failed: Runtime role '{app_user}' does not exist in pg_roles"
        )

    rolsuper, rolcreaterole, rolcreatedb, rolinherit, rolreplication, rolbypassrls = role_row
    if any([rolsuper, rolcreaterole, rolcreatedb, rolinherit, rolreplication, rolbypassrls]):
        raise RuntimeError(
            f"Pre-flight role verification failed: Runtime role '{app_user}' has invalid privileged attributes: "
            f"All 6 security attributes must be strictly False."
        )

    membership_count = conn.execute(
        sa.text(
            "SELECT count(*) FROM pg_auth_members WHERE member = (SELECT oid FROM pg_roles WHERE rolname = :rolname)"
        ),
        {"rolname": app_user},
    ).scalar()

    if membership_count != 0:
        raise RuntimeError(
            f"Pre-flight role verification failed: Runtime role '{app_user}' has {membership_count} role memberships in pg_auth_members. "
            f"Zero memberships are required for complete role isolation."
        )

    # 2. Securely Provision ACC-SYSTEM02 (Internal Clearing Transit Account)
    op.execute("""
    INSERT INTO public.accounts (id, account_number, owner_id, name, account_type, currency, balance, status, created_at, updated_at)
    VALUES (gen_random_uuid(), 'ACC-SYSTEM02', NULL, 'Internal Clearing', 'internal_clearing', 'INR', 0.00, 'active', now(), now())
    ON CONFLICT (account_number) DO NOTHING;
    """)

    # 3. Grant INSERT Privileges on Ledger Tables to Application Runtime Role
    op.execute(
        f"GRANT INSERT (id, reference, transaction_type, description, posted_at) "
        f"ON TABLE public.ledger_transactions TO {app_user};"
    )
    op.execute(
        f"GRANT INSERT (id, transaction_id, account_id, entry_type, amount, sequence, created_at) "
        f"ON TABLE public.ledger_entries TO {app_user};"
    )

    # 4. Hardened Balance Synchronization Function (SECURITY DEFINER)
    # search_path: pg_catalog first, then public, pg_temp. Object references schema-qualified.
    op.execute("""
    CREATE OR REPLACE FUNCTION public.sync_account_balance_from_ledger_entry()
    RETURNS TRIGGER
    LANGUAGE plpgsql
    SECURITY DEFINER
    SET search_path = pg_catalog, public, pg_temp
    AS $$
    DECLARE
        v_acc_type public.account_type_enum;
    BEGIN
        SELECT account_type INTO v_acc_type
        FROM public.accounts
        WHERE id = NEW.account_id;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Target account % not found for ledger entry %', NEW.account_id, NEW.id
            USING ERRCODE = '23503';
        END IF;

        -- Apply balance update based on normal balance classification
        IF v_acc_type IN ('customer_checking', 'customer_savings', 'system_reserve') THEN
            -- Normal balance: CREDIT. Credit increments, Debit decrements.
            IF NEW.entry_type = 'credit' THEN
                UPDATE public.accounts
                SET balance = balance + NEW.amount,
                    updated_at = clock_timestamp()
                WHERE id = NEW.account_id;
            ELSIF NEW.entry_type = 'debit' THEN
                UPDATE public.accounts
                SET balance = balance - NEW.amount,
                    updated_at = clock_timestamp()
                WHERE id = NEW.account_id;
            END IF;
        ELSIF v_acc_type = 'internal_clearing' THEN
            -- Normal balance: DEBIT. Debit increments, Credit decrements.
            IF NEW.entry_type = 'debit' THEN
                UPDATE public.accounts
                SET balance = balance + NEW.amount,
                    updated_at = clock_timestamp()
                WHERE id = NEW.account_id;
            ELSIF NEW.entry_type = 'credit' THEN
                UPDATE public.accounts
                SET balance = balance - NEW.amount,
                    updated_at = clock_timestamp()
                WHERE id = NEW.account_id;
            END IF;
        END IF;

        RETURN NEW;
    END;
    $$;
    """)

    # Restrict execution: Revoke from PUBLIC, grant only to necessary roles
    op.execute("REVOKE ALL ON FUNCTION public.sync_account_balance_from_ledger_entry() FROM PUBLIC;")
    op.execute(f"GRANT EXECUTE ON FUNCTION public.sync_account_balance_from_ledger_entry() TO {app_user}, ledgerline_owner;")

    op.execute("""
    CREATE TRIGGER trg_sync_account_balance
    AFTER INSERT ON public.ledger_entries
    FOR EACH ROW EXECUTE FUNCTION public.sync_account_balance_from_ledger_entry();
    """)

    # 5. Hardened Deferred Zero-Sum Balance Constraint Trigger
    op.execute("""
    CREATE OR REPLACE FUNCTION public.verify_transaction_balanced()
    RETURNS TRIGGER
    LANGUAGE plpgsql
    SET search_path = pg_catalog, public, pg_temp
    AS $$
    DECLARE
        v_diff numeric(20, 2);
    BEGIN
        SELECT coalesce(sum(CASE WHEN entry_type = 'debit' THEN amount ELSE -amount END), 0)
        INTO v_diff
        FROM public.ledger_entries
        WHERE transaction_id = NEW.transaction_id;

        IF v_diff <> 0 THEN
            RAISE EXCEPTION 'Unbalanced transaction: debits and credits do not balance (delta: %) for transaction %',
                v_diff, NEW.transaction_id
            USING ERRCODE = '23514';
        END IF;

        RETURN NEW;
    END;
    $$;
    """)

    op.execute("REVOKE ALL ON FUNCTION public.verify_transaction_balanced() FROM PUBLIC;")
    op.execute(f"GRANT EXECUTE ON FUNCTION public.verify_transaction_balanced() TO {app_user}, ledgerline_owner;")

    op.execute("""
    CREATE CONSTRAINT TRIGGER trg_verify_transaction_balanced
    AFTER INSERT ON public.ledger_entries
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION public.verify_transaction_balanced();
    """)

    # 6. Safeguard 1: Database-Level Rejection of Empty Transactions (Deferred Constraint Trigger)
    op.execute("""
    CREATE OR REPLACE FUNCTION public.verify_transaction_has_entries()
    RETURNS TRIGGER
    LANGUAGE plpgsql
    SET search_path = pg_catalog, public, pg_temp
    AS $$
    DECLARE
        v_entry_count integer;
    BEGIN
        SELECT count(*) INTO v_entry_count
        FROM public.ledger_entries
        WHERE transaction_id = NEW.id;

        IF v_entry_count = 0 THEN
            RAISE EXCEPTION 'Transaction % has zero ledger entries and cannot be committed', NEW.id
            USING ERRCODE = '23514';
        END IF;

        RETURN NEW;
    END;
    $$;
    """)

    op.execute("REVOKE ALL ON FUNCTION public.verify_transaction_has_entries() FROM PUBLIC;")
    op.execute(f"GRANT EXECUTE ON FUNCTION public.verify_transaction_has_entries() TO {app_user}, ledgerline_owner;")

    op.execute("""
    CREATE CONSTRAINT TRIGGER trg_verify_transaction_not_empty
    AFTER INSERT ON public.ledger_transactions
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION public.verify_transaction_has_entries();
    """)


def downgrade() -> None:
    app_user = settings.RUNTIME_POSTGRES_USER

    # 1. Drop Constraint Triggers & Functions
    op.execute("DROP TRIGGER IF EXISTS trg_verify_transaction_not_empty ON public.ledger_transactions;")
    op.execute("DROP FUNCTION IF EXISTS public.verify_transaction_has_entries();")

    op.execute("DROP TRIGGER IF EXISTS trg_verify_transaction_balanced ON public.ledger_entries;")
    op.execute("DROP FUNCTION IF EXISTS public.verify_transaction_balanced();")

    op.execute("DROP TRIGGER IF EXISTS trg_sync_account_balance ON public.ledger_entries;")
    op.execute("DROP FUNCTION IF EXISTS public.sync_account_balance_from_ledger_entry();")

    # 2. Revoke INSERT Privileges from Runtime Role
    op.execute(f"REVOKE INSERT ON TABLE public.ledger_entries FROM {app_user};")
    op.execute(f"REVOKE INSERT ON TABLE public.ledger_transactions FROM {app_user};")

    # 3. Clean up seeded ACC-SYSTEM02 if unreferenced
    op.execute("""
    DELETE FROM public.accounts
    WHERE account_number = 'ACC-SYSTEM02'
      AND NOT EXISTS (SELECT 1 FROM public.ledger_entries WHERE account_id = accounts.id);
    """)

