"""idempotency records

Revision ID: 0005_idempotency_records
Revises: 0004_financial_operations
Create Date: 2026-11-07 11:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

from backend.app.core.config import settings

# revision identifiers, used by Alembic.
revision: str = '0005_idempotency_records'
down_revision: Union[str, None] = '0004_financial_operations'
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

    # 2. Create public.idempotency_records Table
    op.execute("""
    CREATE TABLE public.idempotency_records (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
        idempotency_key VARCHAR(128) NOT NULL,
        operation_type VARCHAR(32) NOT NULL,
        request_hash VARCHAR(64) NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'processing',
        response_status_code INTEGER NULL,
        response_body TEXT NULL,
        transaction_id UUID NULL REFERENCES public.ledger_transactions(id) ON DELETE RESTRICT,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
        CONSTRAINT uq_idempotency_user_key UNIQUE (user_id, idempotency_key),
        CONSTRAINT chk_idempotency_status CHECK (status IN ('processing', 'completed', 'failed'))
    );
    """)

    # 3. Create Secondary Indexes
    # Note: uq_idempotency_user_key automatically provisions the unique index on (user_id, idempotency_key).
    op.execute("CREATE INDEX ix_idempotency_records_created_at ON public.idempotency_records (created_at);")
    op.execute("CREATE INDEX ix_idempotency_records_transaction_id ON public.idempotency_records (transaction_id);")

    # 4. Grant SELECT, INSERT, UPDATE Privileges to Application Runtime Role
    # Permanent retention: DELETE is strictly withheld from ledgerline_app.
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE ON TABLE public.idempotency_records TO {app_user};"
    )


def downgrade() -> None:
    app_user = settings.RUNTIME_POSTGRES_USER

    # 1. Revoke privileges
    op.execute(f"REVOKE ALL ON TABLE public.idempotency_records FROM {app_user};")

    # 2. Drop table
    op.execute("DROP TABLE IF EXISTS public.idempotency_records CASCADE;")
