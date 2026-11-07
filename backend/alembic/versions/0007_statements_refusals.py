"""statements and refused operations

Revision ID: 0007_statements_refusals
Revises: 0006_cryptographic_audit_trail
Create Date: 2026-11-07 18:05:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from backend.app.core.config import settings

# revision identifiers, used by Alembic.
revision: str = '0007_statements_refusals'
down_revision: Union[str, None] = '0006_cryptographic_audit_trail'
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
            f"Pre-flight role verification failed: Runtime role '{app_user}' has memberships in other roles ({membership_count})"
        )

    # 2. Create Table: public.refused_operations
    op.create_table(
        'refused_operations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('account_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('accounts.id', ondelete='RESTRICT'), nullable=True),
        sa.Column('counterparty_account_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('accounts.id', ondelete='RESTRICT'), nullable=True),
        sa.Column('operation_type', sa.String(length=32), nullable=False),
        sa.Column('amount', sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column('currency', sa.String(length=3), server_default='INR', nullable=False),
        sa.Column('refusal_reason', sa.String(length=64), nullable=False),
        sa.Column('error_message', sa.String(length=255), nullable=False),
        sa.Column('idempotency_key_hash', sa.CHAR(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('clock_timestamp()'), nullable=False),
        sa.CheckConstraint(
            "operation_type IN ('deposit', 'withdraw', 'transfer')",
            name='chk_refused_operation_type',
        ),
        sa.CheckConstraint(
            "amount IS NULL OR amount > 0",
            name='chk_refused_amount_positive',
        ),
        sa.CheckConstraint(
            "currency = 'INR'",
            name='chk_refused_currency',
        ),
    )

    # 3. Create Indexes
    op.create_index('ix_refused_operations_account_date', 'refused_operations', ['account_id', 'created_at'], unique=False)
    op.create_index('ix_refused_operations_counterparty_date', 'refused_operations', ['counterparty_account_id', 'created_at'], unique=False)
    op.create_index('ix_refused_operations_user_id', 'refused_operations', ['user_id'], unique=False)
    op.create_index('ix_refused_operations_created_at', 'refused_operations', ['created_at'], unique=False)

    # 4. Immutability Triggers
    op.execute("""
    CREATE OR REPLACE FUNCTION public.prevent_refused_operations_modification()
    RETURNS TRIGGER
    LANGUAGE plpgsql
    AS $$
    BEGIN
        RAISE EXCEPTION 'Refused operation records are strictly immutable and cannot be modified or deleted'
        USING ERRCODE = '55000';
    END;
    $$;
    """)

    op.execute("""
    CREATE TRIGGER trg_protect_refused_operations_row
    BEFORE UPDATE OR DELETE ON public.refused_operations
    FOR EACH ROW
    EXECUTE FUNCTION public.prevent_refused_operations_modification();
    """)

    op.execute("""
    CREATE TRIGGER trg_protect_refused_operations_truncate
    BEFORE TRUNCATE ON public.refused_operations
    FOR EACH STATEMENT
    EXECUTE FUNCTION public.prevent_refused_operations_modification();
    """)

    # 5. Grant Least-Privilege Permissions to Application Runtime Role
    op.execute(f"GRANT SELECT, INSERT ON TABLE public.refused_operations TO {app_user};")


def downgrade() -> None:
    conn = op.get_bind()

    # 1. Role verification
    current_user = conn.execute(sa.text("SELECT current_user")).scalar()
    if current_user != "ledgerline_owner":
        raise RuntimeError(
            f"Pre-flight role verification failed: Alembic downgrade must execute as 'ledgerline_owner', "
            f"but current_user is '{current_user}'"
        )

    app_user = settings.RUNTIME_POSTGRES_USER

    # 2. Revoke Grants
    op.execute(f"REVOKE ALL ON TABLE public.refused_operations FROM {app_user};")

    # 3. Drop Triggers and Function
    op.execute("DROP TRIGGER IF EXISTS trg_protect_refused_operations_truncate ON public.refused_operations;")
    op.execute("DROP TRIGGER IF EXISTS trg_protect_refused_operations_row ON public.refused_operations;")
    op.execute("DROP FUNCTION IF EXISTS public.prevent_refused_operations_modification();")

    # 4. Drop Table
    op.execute("DROP TABLE IF EXISTS public.refused_operations CASCADE;")
