-- scripts/setup_roles.sql
-- Executed once by PostgreSQL superuser / DBA during database bootstrap:
--   psql -U postgres -d ledgerline -f scripts/setup_roles.sql
-- Passwords ingested directly from environment variables (no CLI flags, no hardcoding)

\set ON_ERROR_STOP on

-- 1. Ingest credentials from process environment variables into psql variables
\getenv owner_pw MIGRATION_POSTGRES_PASSWORD
\getenv app_pw POSTGRES_PASSWORD

-- 2. Wrap configuration parameters and execution block in an explicit transaction
BEGIN;

-- Store credentials in transaction-scoped session parameters (evaluated outside dollar-quotes)
SELECT set_config('ledgerline.owner_pw', :'owner_pw', true);
SELECT set_config('ledgerline.app_pw', :'app_pw', true);

-- 3. Execute idempotent role provisioning and isolation block
DO $$
DECLARE
    v_owner_role text := 'ledgerline_owner';
    v_app_role text := 'ledgerline_app';
    v_owner_pw text := current_setting('ledgerline.owner_pw', true);
    v_app_pw text := current_setting('ledgerline.app_pw', true);
    r RECORD;
BEGIN
    -- Validate credentials are present before executing role DDL
    IF v_owner_pw IS NULL OR v_owner_pw = '' THEN
        RAISE EXCEPTION 'MIGRATION_POSTGRES_PASSWORD environment variable is missing or empty.';
    END IF;
    IF v_app_pw IS NULL OR v_app_pw = '' THEN
        RAISE EXCEPTION 'POSTGRES_PASSWORD environment variable is missing or empty.';
    END IF;

    -- 1. Create or update Migration Owner Role (ledgerline_owner) with all 6 security restrictions
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = v_owner_role) THEN
        EXECUTE format(
            'CREATE ROLE %I WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD %L',
            v_owner_role, v_owner_pw
        );
    ELSE
        EXECUTE format(
            'ALTER ROLE %I WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD %L',
            v_owner_role, v_owner_pw
        );
    END IF;

    -- 2. Create or update Application Runtime Role (ledgerline_app) with all 6 security restrictions
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = v_app_role) THEN
        EXECUTE format(
            'CREATE ROLE %I WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD %L',
            v_app_role, v_app_pw
        );
    ELSE
        EXECUTE format(
            'ALTER ROLE %I WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD %L',
            v_app_role, v_app_pw
        );
    END IF;

    -- 3. Complete Role Isolation: Dynamically revoke ALL role memberships from runtime role
    FOR r IN (
        SELECT roleid::regrole::text AS rolename
        FROM pg_auth_members
        WHERE member = v_app_role::regrole
    ) LOOP
        EXECUTE format('REVOKE %I FROM %I', r.rolename, v_app_role);
    END LOOP;

    -- 4. Schema Usage and Ownership
    EXECUTE format('REVOKE ALL ON SCHEMA public FROM %I, PUBLIC', v_app_role);
    EXECUTE format('GRANT CONNECT ON DATABASE ledgerline TO %I, %I', v_owner_role, v_app_role);
    EXECUTE format('GRANT USAGE ON SCHEMA public TO %I, %I', v_owner_role, v_app_role);
    EXECUTE format('ALTER SCHEMA public OWNER TO %I', v_owner_role);
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'ledgerline_user') THEN
        EXECUTE format('REASSIGN OWNED BY %I TO %I', 'ledgerline_user', v_owner_role);
    END IF;
    EXECUTE format('GRANT ALL ON ALL TABLES IN SCHEMA public TO %I', v_owner_role);
    IF EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'users') THEN
        EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE users TO %I', v_app_role);
    END IF;

    -- 5. Immediately clear sensitive session parameters from memory
    PERFORM set_config('ledgerline.owner_pw', '', true);
    PERFORM set_config('ledgerline.app_pw', '', true);
END $$;

COMMIT;
