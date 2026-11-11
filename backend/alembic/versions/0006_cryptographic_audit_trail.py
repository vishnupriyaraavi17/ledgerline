"""cryptographic audit trail

Revision ID: 0006_cryptographic_audit_trail
Revises: 0005_idempotency_records
Create Date: 2026-11-07 12:20:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

from backend.app.core.config import settings

# revision identifiers, used by Alembic.
revision: str = '0006_cryptographic_audit_trail'
down_revision: Union[str, None] = '0005_idempotency_records'
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

    # 2. Pre-Flight Safeguard 1: Assert strict schema public access privileges
    public_has_create = conn.execute(
        sa.text("SELECT has_schema_privilege('public', 'public', 'CREATE')")
    ).scalar()
    if public_has_create:
        raise RuntimeError(
            "Pre-flight role verification failed: PUBLIC must not hold CREATE privilege on schema public."
        )

    app_has_create = conn.execute(
        sa.text("SELECT has_schema_privilege(:app_user, 'public', 'CREATE')"),
        {"app_user": app_user},
    ).scalar()
    if app_has_create:
        raise RuntimeError(
            f"Pre-flight role verification failed: Runtime role '{app_user}' must not hold CREATE privilege on schema public."
        )

    owner_has_create = conn.execute(
        sa.text("SELECT has_schema_privilege('ledgerline_owner', 'public', 'CREATE')")
    ).scalar()
    owner_has_usage = conn.execute(
        sa.text("SELECT has_schema_privilege('ledgerline_owner', 'public', 'USAGE')")
    ).scalar()
    if not (owner_has_create and owner_has_usage):
        raise RuntimeError(
            "Pre-flight role verification failed: Migration role 'ledgerline_owner' must hold USAGE and CREATE on schema public."
        )

    # 3. Create public.audit_chain_head Table and Seed Genesis Row
    op.execute("""
    CREATE TABLE public.audit_chain_head (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        sequence_number BIGINT NOT NULL,
        current_hash CHAR(64) NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
        CONSTRAINT chk_head_sequence_non_negative CHECK (sequence_number >= 0),
        CONSTRAINT chk_head_current_hash_format CHECK (current_hash ~ '^[0-9a-f]{64}$')
    );
    """)

    op.execute("""
    INSERT INTO public.audit_chain_head (id, sequence_number, current_hash, updated_at)
    VALUES (1, 0, '0000000000000000000000000000000000000000000000000000000000000000', now());
    """)

    # 4. Create public.audit_events Table
    op.execute("""
    CREATE TABLE public.audit_events (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        sequence_number BIGINT NOT NULL UNIQUE,
        event_type VARCHAR(64) NOT NULL,
        actor_id UUID NULL REFERENCES public.users(id) ON DELETE RESTRICT,
        actor_role VARCHAR(32) NULL,
        entity_type VARCHAR(64) NOT NULL,
        entity_id VARCHAR(128) NOT NULL,
        payload JSONB NOT NULL,
        prev_hash CHAR(64) NOT NULL,
        current_hash CHAR(64) NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        CONSTRAINT chk_audit_sequence_positive CHECK (sequence_number > 0),
        CONSTRAINT chk_audit_prev_hash_format CHECK (prev_hash ~ '^[0-9a-f]{64}$'),
        CONSTRAINT chk_audit_current_hash_format CHECK (current_hash ~ '^[0-9a-f]{64}$')
    );
    """)

    # 5. Create Secondary Indexes
    op.execute("CREATE INDEX ix_audit_events_event_type ON public.audit_events(event_type);")
    op.execute("CREATE INDEX ix_audit_events_entity ON public.audit_events(entity_type, entity_id);")
    op.execute("CREATE INDEX ix_audit_events_actor_id ON public.audit_events(actor_id);")
    op.execute("CREATE INDEX ix_audit_events_created_at ON public.audit_events(created_at);")
    op.execute("CREATE INDEX ix_audit_events_current_hash ON public.audit_events(current_hash);")

    # 6. Engine Immutability Triggers
    op.execute("""
    CREATE OR REPLACE FUNCTION public.prevent_audit_events_modification()
    RETURNS TRIGGER
    LANGUAGE plpgsql
    SET search_path = pg_catalog, public, pg_temp
    AS $$
    BEGIN
        RAISE EXCEPTION 'Audit trail records are strictly immutable. Action % on audit_events is prohibited.', TG_OP;
    END;
    $$;
    """)

    op.execute("""
    CREATE TRIGGER trg_protect_audit_events_row
    BEFORE UPDATE OR DELETE ON public.audit_events
    FOR EACH ROW EXECUTE FUNCTION public.prevent_audit_events_modification();
    """)

    op.execute("""
    CREATE TRIGGER trg_protect_audit_events_truncate
    BEFORE TRUNCATE ON public.audit_events
    FOR EACH STATEMENT EXECUTE FUNCTION public.prevent_audit_events_modification();
    """)

    op.execute("""
    CREATE OR REPLACE FUNCTION public.prevent_audit_chain_head_modification()
    RETURNS TRIGGER
    LANGUAGE plpgsql
    SET search_path = pg_catalog, public, pg_temp
    AS $$
    BEGIN
        RAISE EXCEPTION 'The audit chain head cannot be inserted or deleted.';
    END;
    $$;
    """)

    op.execute("""
    CREATE TRIGGER trg_protect_audit_chain_head_row
    BEFORE INSERT OR DELETE ON public.audit_chain_head
    FOR EACH ROW EXECUTE FUNCTION public.prevent_audit_chain_head_modification();
    """)

    # 7. SECURITY DEFINER Functions for Controlled Locking & Appends
    op.execute("""
    CREATE OR REPLACE FUNCTION public.acquire_audit_chain_head()
    RETURNS TABLE (
        sequence_number bigint,
        current_hash text
    )
    LANGUAGE plpgsql
    SECURITY DEFINER
    SET search_path = pg_catalog, public, pg_temp
    AS $$
    BEGIN
        RETURN QUERY
        SELECT h.sequence_number, h.current_hash::text
        FROM public.audit_chain_head h
        WHERE h.id = 1
        FOR UPDATE;
    END;
    $$;
    """)

    op.execute("""
    CREATE OR REPLACE FUNCTION public.lock_audit_chain_head_for_share()
    RETURNS TABLE (
        sequence_number bigint,
        current_hash text
    )
    LANGUAGE plpgsql
    SECURITY DEFINER
    SET search_path = pg_catalog, public, pg_temp
    AS $$
    BEGIN
        RETURN QUERY
        SELECT h.sequence_number, h.current_hash::text
        FROM public.audit_chain_head h
        WHERE h.id = 1
        FOR SHARE;
    END;
    $$;
    """)

    op.execute("""
    CREATE OR REPLACE FUNCTION public.append_audit_event(
        p_event_type text,
        p_actor_id uuid,
        p_actor_role text,
        p_entity_type text,
        p_entity_id text,
        p_payload jsonb,
        p_timestamp timestamptz,
        p_expected_prev_hash text,
        p_expected_sequence bigint,
        p_current_hash text
    )
    RETURNS TABLE (
        event_id uuid,
        sequence_number bigint,
        prev_hash text,
        current_hash text
    )
    LANGUAGE plpgsql
    SECURITY DEFINER
    SET search_path = pg_catalog, public, pg_temp
    AS $$
    DECLARE
        v_head_seq bigint;
        v_head_hash text;
        v_event_id uuid;
    BEGIN
        -- 1. Exclusively lock the singleton head row
        SELECT h.sequence_number, h.current_hash
        INTO v_head_seq, v_head_hash
        FROM public.audit_chain_head h
        WHERE h.id = 1
        FOR UPDATE;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Audit chain head is uninitialized';
        END IF;

        -- 2. Validate chain continuity and expected sequence
        IF p_expected_prev_hash <> v_head_hash THEN
            RAISE EXCEPTION 'Audit chain conflict: expected previous hash % does not match current head hash %',
                p_expected_prev_hash, v_head_hash;
        END IF;

        IF p_expected_sequence <> (v_head_seq + 1) THEN
            RAISE EXCEPTION 'Audit sequence conflict: expected sequence % but next sequence must be %',
                p_expected_sequence, (v_head_seq + 1);
        END IF;

        -- 3. Insert the new immutable audit event
        INSERT INTO public.audit_events (
            sequence_number,
            event_type,
            actor_id,
            actor_role,
            entity_type,
            entity_id,
            payload,
            prev_hash,
            current_hash,
            created_at
        ) VALUES (
            p_expected_sequence,
            p_event_type,
            p_actor_id,
            p_actor_role,
            p_entity_type,
            p_entity_id,
            p_payload,
            v_head_hash,
            p_current_hash,
            p_timestamp
        ) RETURNING id INTO v_event_id;

        -- 4. Atomically advance the head pointer
        UPDATE public.audit_chain_head
        SET sequence_number = p_expected_sequence,
            current_hash = p_current_hash,
            updated_at = p_timestamp
        WHERE id = 1;

        RETURN QUERY SELECT v_event_id, p_expected_sequence, v_head_hash, p_current_hash;
    END;
    $$;
    """)

    # 8. Permissions: Revoke direct modifications from PUBLIC and ledgerline_app
    op.execute("REVOKE ALL ON TABLE public.audit_events FROM PUBLIC, ledgerline_app;")
    op.execute("REVOKE ALL ON TABLE public.audit_chain_head FROM PUBLIC, ledgerline_app;")
    op.execute(
        "REVOKE ALL ON FUNCTION public.append_audit_event("
        "text, uuid, text, text, text, jsonb, timestamptz, text, bigint, text"
        ") FROM PUBLIC;"
    )
    op.execute("REVOKE ALL ON FUNCTION public.acquire_audit_chain_head() FROM PUBLIC;")
    op.execute("REVOKE ALL ON FUNCTION public.lock_audit_chain_head_for_share() FROM PUBLIC;")

    # 9. Grant Minimal Permissions to Application Runtime Role
    op.execute(f"GRANT SELECT ON TABLE public.audit_events TO {app_user};")
    op.execute(f"GRANT SELECT ON TABLE public.audit_chain_head TO {app_user};")
    op.execute(
        f"GRANT EXECUTE ON FUNCTION public.append_audit_event("
        f"text, uuid, text, text, text, jsonb, timestamptz, text, bigint, text"
        f") TO {app_user};"
    )
    op.execute(f"GRANT EXECUTE ON FUNCTION public.acquire_audit_chain_head() TO {app_user};")
    op.execute(f"GRANT EXECUTE ON FUNCTION public.lock_audit_chain_head_for_share() TO {app_user};")


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
    op.execute(
        f"REVOKE ALL ON FUNCTION public.append_audit_event("
        f"text, uuid, text, text, text, jsonb, timestamptz, text, bigint, text"
        f") FROM {app_user};"
    )
    op.execute(f"REVOKE ALL ON TABLE public.audit_events FROM {app_user};")
    op.execute(f"REVOKE ALL ON TABLE public.audit_chain_head FROM {app_user};")

    # 3. Drop Triggers and Functions
    op.execute("DROP TRIGGER IF EXISTS trg_protect_audit_chain_head_row ON public.audit_chain_head;")
    op.execute("DROP FUNCTION IF EXISTS public.prevent_audit_chain_head_modification();")

    op.execute("DROP TRIGGER IF EXISTS trg_protect_audit_events_truncate ON public.audit_events;")
    op.execute("DROP TRIGGER IF EXISTS trg_protect_audit_events_row ON public.audit_events;")
    op.execute("DROP FUNCTION IF EXISTS public.prevent_audit_events_modification();")

    op.execute(
        "DROP FUNCTION IF EXISTS public.append_audit_event("
        "text, uuid, text, text, text, jsonb, timestamptz, text, bigint, text"
        ");"
    )
    op.execute("DROP FUNCTION IF EXISTS public.acquire_audit_chain_head();")
    op.execute("DROP FUNCTION IF EXISTS public.lock_audit_chain_head_for_share();")

    # 4. Drop Tables
    op.execute("DROP TABLE IF EXISTS public.audit_events CASCADE;")
    op.execute("DROP TABLE IF EXISTS public.audit_chain_head CASCADE;")
