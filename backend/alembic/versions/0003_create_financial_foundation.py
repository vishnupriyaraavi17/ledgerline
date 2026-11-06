"""create financial foundation

Revision ID: 0003_create_financial_foundation
Revises: 0002_create_users_table
Create Date: 2026-11-06 18:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from backend.app.core.config import settings

# revision identifiers, used by Alembic.
revision: str = '0003_create_financial_foundation'
down_revision: Union[str, None] = '0002_create_users_table'
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
            f"rolsuper={rolsuper}, rolcreaterole={rolcreaterole}, rolcreatedb={rolcreatedb}, "
            f"rolinherit={rolinherit}, rolreplication={rolreplication}, rolbypassrls={rolbypassrls}. "
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

    # 2. Enums
    op.execute(
        "CREATE TYPE account_type_enum AS ENUM ('customer_checking', 'customer_savings', 'system_reserve', 'internal_clearing');"
    )
    op.execute(
        "CREATE TYPE account_status_enum AS ENUM ('active', 'frozen', 'closed');"
    )
    op.execute(
        "CREATE TYPE entry_type_enum AS ENUM ('debit', 'credit');"
    )
    op.execute(
        "CREATE TYPE transaction_type_enum AS ENUM ('transfer', 'adjustment', 'settlement');"
    )

    # 3. Create Tables
    # Table: accounts
    op.create_table(
        'accounts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('account_number', sa.String(length=32), nullable=False),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=True),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('account_type', postgresql.ENUM('customer_checking', 'customer_savings', 'system_reserve', 'internal_clearing', name='account_type_enum', create_type=False), nullable=False),
        sa.Column('currency', sa.String(length=3), server_default='INR', nullable=False),
        sa.Column('balance', sa.Numeric(precision=20, scale=2), server_default=sa.text('0.00'), nullable=False),
        sa.Column('status', postgresql.ENUM('active', 'frozen', 'closed', name='account_status_enum', create_type=False), server_default='active', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "account_type NOT IN ('customer_checking', 'customer_savings') OR balance >= 0",
            name='chk_customer_balance_non_negative'
        ),
        sa.CheckConstraint(
            "account_number ~ '^ACC-[A-Z0-9]{8}$'",
            name='chk_account_number_format'
        ),
        sa.CheckConstraint(
            "currency = 'INR'",
            name='chk_account_currency'
        ),
    )
    op.create_index(op.f('ix_accounts_id'), 'accounts', ['id'], unique=False)
    op.create_index(op.f('ix_accounts_account_number'), 'accounts', ['account_number'], unique=True)
    op.create_index(op.f('ix_accounts_owner_id'), 'accounts', ['owner_id'], unique=False)
    op.create_index(op.f('ix_accounts_account_type'), 'accounts', ['account_type'], unique=False)
    op.create_index(op.f('ix_accounts_status'), 'accounts', ['status'], unique=False)

    # Table: ledger_transactions
    op.create_table(
        'ledger_transactions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('reference', sa.String(length=64), nullable=False),
        sa.Column('transaction_type', postgresql.ENUM('transfer', 'adjustment', 'settlement', name='transaction_type_enum', create_type=False), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=False),
        sa.Column('posted_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(op.f('ix_ledger_transactions_id'), 'ledger_transactions', ['id'], unique=False)
    op.create_index(op.f('ix_ledger_transactions_reference'), 'ledger_transactions', ['reference'], unique=True)
    op.create_index(op.f('ix_ledger_transactions_transaction_type'), 'ledger_transactions', ['transaction_type'], unique=False)
    op.create_index(op.f('ix_ledger_transactions_posted_at'), 'ledger_transactions', ['posted_at'], unique=False)

    # Table: ledger_entries
    op.create_table(
        'ledger_entries',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('transaction_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('ledger_transactions.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('account_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('accounts.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('entry_type', postgresql.ENUM('debit', 'credit', name='entry_type_enum', create_type=False), nullable=False),
        sa.Column('amount', sa.Numeric(precision=20, scale=2), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "amount > 0",
            name='chk_ledger_entry_amount_positive'
        ),
    )
    op.create_index(op.f('ix_ledger_entries_id'), 'ledger_entries', ['id'], unique=False)
    op.create_index(op.f('ix_ledger_entries_transaction_id'), 'ledger_entries', ['transaction_id'], unique=False)
    op.create_index(op.f('ix_ledger_entries_account_id'), 'ledger_entries', ['account_id'], unique=False)
    op.create_index(op.f('ix_ledger_entries_entry_type'), 'ledger_entries', ['entry_type'], unique=False)
    op.create_index(op.f('ix_ledger_entries_created_at'), 'ledger_entries', ['created_at'], unique=False)

    # 4. Triggers and Functions
    # System account creation guard trigger
    op.execute("""
    CREATE OR REPLACE FUNCTION enforce_account_creation_permissions()
    RETURNS TRIGGER AS $$
    BEGIN
        -- Guard 1: System account types
        IF NEW.account_type IN ('system_reserve', 'internal_clearing') THEN
            IF current_user NOT IN ('ledgerline_owner', 'postgres') THEN
                RAISE EXCEPTION 'Permission denied: System account types can only be provisioned by the migration owner role.';
            END IF;
        END IF;

        -- Guard 2: Reserved system account number pattern ACC-SYSTEM[0-9]{2}
        IF NEW.account_number ~ '^ACC-SYSTEM[0-9]{2}$' THEN
            IF current_user NOT IN ('ledgerline_owner', 'postgres') THEN
                RAISE EXCEPTION 'Permission denied: Reserved system account numbers (ACC-SYSTEM[0-9]{2}) can only be provisioned by the migration owner role.';
            END IF;
        END IF;

        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)

    op.execute("""
    CREATE TRIGGER trg_enforce_account_creation_permissions
    BEFORE INSERT ON accounts
    FOR EACH ROW EXECUTE FUNCTION enforce_account_creation_permissions();
    """)

    # Ledger immutability function and triggers
    op.execute("""
    CREATE OR REPLACE FUNCTION prevent_ledger_modification()
    RETURNS TRIGGER AS $$
    BEGIN
        RAISE EXCEPTION 'Ledger records are strictly immutable. UPDATE, DELETE, and TRUNCATE operations are forbidden.';
    END;
    $$ LANGUAGE plpgsql;
    """)

    op.execute("""
    CREATE TRIGGER trg_protect_ledger_entries_row
    BEFORE UPDATE OR DELETE ON ledger_entries
    FOR EACH ROW EXECUTE FUNCTION prevent_ledger_modification();
    """)

    op.execute("""
    CREATE TRIGGER trg_protect_ledger_transactions_row
    BEFORE UPDATE OR DELETE ON ledger_transactions
    FOR EACH ROW EXECUTE FUNCTION prevent_ledger_modification();
    """)

    op.execute("""
    CREATE TRIGGER trg_protect_ledger_entries_truncate
    BEFORE TRUNCATE ON ledger_entries
    FOR EACH STATEMENT EXECUTE FUNCTION prevent_ledger_modification();
    """)

    op.execute("""
    CREATE TRIGGER trg_protect_ledger_transactions_truncate
    BEFORE TRUNCATE ON ledger_transactions
    FOR EACH STATEMENT EXECUTE FUNCTION prevent_ledger_modification();
    """)

    # 5. Revoke broad table-level privileges and grant restricted privileges
    # Accounts table
    op.execute(f"REVOKE ALL ON TABLE accounts FROM PUBLIC;")
    op.execute(f"REVOKE ALL ON TABLE accounts FROM {app_user};")
    op.execute(f"GRANT SELECT ON TABLE accounts TO {app_user};")
    op.execute(
        f"GRANT INSERT (id, account_number, owner_id, name, account_type, currency, status, created_at, updated_at) "
        f"ON TABLE accounts TO {app_user};"
    )
    op.execute(
        f"GRANT UPDATE (status, updated_at) "
        f"ON TABLE accounts TO {app_user};"
    )

    # Ledger tables
    op.execute(f"REVOKE ALL ON TABLE ledger_transactions FROM PUBLIC;")
    op.execute(f"REVOKE ALL ON TABLE ledger_transactions FROM {app_user};")
    op.execute(f"GRANT SELECT ON TABLE ledger_transactions TO {app_user};")

    op.execute(f"REVOKE ALL ON TABLE ledger_entries FROM PUBLIC;")
    op.execute(f"REVOKE ALL ON TABLE ledger_entries FROM {app_user};")
    op.execute(f"GRANT SELECT ON TABLE ledger_entries TO {app_user};")

    # 6. Seed Root System Reserve Account (ACC-SYSTEM01)
    op.execute("""
    INSERT INTO accounts (id, account_number, owner_id, name, account_type, currency, balance, status, created_at, updated_at)
    VALUES (gen_random_uuid(), 'ACC-SYSTEM01', NULL, 'System Reserve', 'system_reserve', 'INR', 0.00, 'active', now(), now())
    ON CONFLICT (account_number) DO NOTHING;
    """)


def downgrade() -> None:
    app_user = settings.RUNTIME_POSTGRES_USER

    # 1. Revoke privileges
    op.execute(f"REVOKE ALL ON TABLE ledger_entries FROM {app_user};")
    op.execute(f"REVOKE ALL ON TABLE ledger_transactions FROM {app_user};")
    op.execute(f"REVOKE ALL ON TABLE accounts FROM {app_user};")

    # 2. Drop triggers
    op.execute("DROP TRIGGER IF EXISTS trg_protect_ledger_entries_row ON ledger_entries;")
    op.execute("DROP TRIGGER IF EXISTS trg_protect_ledger_entries_truncate ON ledger_entries;")
    op.execute("DROP TRIGGER IF EXISTS trg_protect_ledger_transactions_row ON ledger_transactions;")
    op.execute("DROP TRIGGER IF EXISTS trg_protect_ledger_transactions_truncate ON ledger_transactions;")
    op.execute("DROP TRIGGER IF EXISTS trg_enforce_account_creation_permissions ON accounts;")

    # 3. Drop trigger functions
    op.execute("DROP FUNCTION IF EXISTS prevent_ledger_modification();")
    op.execute("DROP FUNCTION IF EXISTS enforce_account_creation_permissions();")

    # 4. Drop tables in exact reverse dependency order
    op.drop_index(op.f('ix_ledger_entries_created_at'), table_name='ledger_entries')
    op.drop_index(op.f('ix_ledger_entries_entry_type'), table_name='ledger_entries')
    op.drop_index(op.f('ix_ledger_entries_account_id'), table_name='ledger_entries')
    op.drop_index(op.f('ix_ledger_entries_transaction_id'), table_name='ledger_entries')
    op.drop_index(op.f('ix_ledger_entries_id'), table_name='ledger_entries')
    op.drop_table('ledger_entries')

    op.drop_index(op.f('ix_ledger_transactions_posted_at'), table_name='ledger_transactions')
    op.drop_index(op.f('ix_ledger_transactions_transaction_type'), table_name='ledger_transactions')
    op.drop_index(op.f('ix_ledger_transactions_reference'), table_name='ledger_transactions')
    op.drop_index(op.f('ix_ledger_transactions_id'), table_name='ledger_transactions')
    op.drop_table('ledger_transactions')

    op.drop_index(op.f('ix_accounts_status'), table_name='accounts')
    op.drop_index(op.f('ix_accounts_account_type'), table_name='accounts')
    op.drop_index(op.f('ix_accounts_owner_id'), table_name='accounts')
    op.drop_index(op.f('ix_accounts_account_number'), table_name='accounts')
    op.drop_index(op.f('ix_accounts_id'), table_name='accounts')
    op.drop_table('accounts')

    # 5. Drop enum types explicitly without CASCADE
    op.execute("DROP TYPE IF EXISTS transaction_type_enum;")
    op.execute("DROP TYPE IF EXISTS entry_type_enum;")
    op.execute("DROP TYPE IF EXISTS account_status_enum;")
    op.execute("DROP TYPE IF EXISTS account_type_enum;")
