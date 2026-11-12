"""
scripts/provision_admin.py
Initial production Administrator provisioning script for LedgerLine.
"""
import getpass
import sys
import uuid
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker

from backend.app.models.user import User, UserRole
from backend.app.repositories.audit import audit_repository
from backend.app.repositories.user import user_repository
from backend.app.security.passwords import hash_password

# Verified production database name from render.yaml line 21
EXPECTED_DATABASE_NAME = "neondb"
EXPECTED_ROLE_NAME = "ledgerline_app"


class ProvisioningAbort(Exception):
    """Controlled abort exception to guarantee immediate session rollback."""
    pass


def verify_client_tls(db_session) -> bool:
    """
    Verifies that the underlying client driver socket actively encrypts traffic via TLS.
    Directly queries libpq's PQsslInUse via Psycopg 3's pgconn.ssl_in_use.
    """
    conn_fairy = db_session.connection().connection
    raw_conn = (
        getattr(conn_fairy, "driver_connection", None)
        or getattr(conn_fairy, "dbapi_connection", None)
        or conn_fairy
    )

    # 1. Psycopg 3 libpq PGconn wrapper
    pgconn = getattr(raw_conn, "pgconn", None)
    if pgconn is not None and hasattr(pgconn, "ssl_in_use"):
        val = pgconn.ssl_in_use
        return bool(val() if callable(val) else val)

    # 2. Psycopg 2 / DBAPI info interface
    info = getattr(raw_conn, "info", None)
    if info is not None and hasattr(info, "ssl_in_use"):
        val = info.ssl_in_use
        return bool(val() if callable(val) else val)

    # 3. Direct driver property
    if hasattr(raw_conn, "ssl_in_use"):
        val = raw_conn.ssl_in_use
        return bool(val() if callable(val) else val)

    return False


def main() -> None:
    print("=======================================================")
    print("   LedgerLine: Initial Production Admin Provisioning   ")
    print("=======================================================\n")

    # 1. Collect Neon Connection URI privately via hidden prompt
    db_uri = getpass.getpass("Paste Neon Database URL for application runtime role (input hidden): ").strip()
    if not db_uri:
        print("[ABORTED] Database connection URI is required.")
        sys.exit(1)

    # Normalize driver scheme for SQLAlchemy 2 + Psycopg 3
    if db_uri.startswith("postgres://"):
        db_uri = "postgresql+psycopg://" + db_uri[len("postgres://"):]
    elif db_uri.startswith("postgresql://"):
        db_uri = "postgresql+psycopg://" + db_uri[len("postgresql://"):]

    # Parse and validate connection configuration before connecting
    try:
        parsed_url = make_url(db_uri)
    except Exception:
        print("[ABORTED] Invalid database URL format.")
        sys.exit(1)

    # Pre-connect Guard: Enforce runtime role and TLS query parameter
    if parsed_url.username != EXPECTED_ROLE_NAME:
        print("[ABORTED] Unauthorized database role. Only the application runtime role is permitted.")
        sys.exit(1)

    ssl_mode = parsed_url.query.get("sslmode", "")
    if ssl_mode not in ("require", "verify-ca", "verify-full"):
        print("[ABORTED] TLS is mandatory for Neon. The connection URI must include '?sslmode=require'.")
        sys.exit(1)

    # 2. Collect Administrator Credentials securely
    username = input("Enter Admin username: ").strip()
    email = input("Enter Admin email: ").strip()
    password = getpass.getpass("Enter Admin password (min 8 characters, input hidden): ")

    if not username or not email:
        print("[ABORTED] Username and email cannot be empty.")
        sys.exit(1)

    if len(password) < 8:
        print("[ABORTED] Password must be at least 8 characters long.")
        sys.exit(1)

    # Create dedicated engine with explicit TLS driver enforcement
    engine = create_engine(
        db_uri,
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": 10,
            "sslmode": ssl_mode,
        }
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    exit_code = 0
    failure_message = None
    provisioned_summary = None

    try:
        with SessionLocal() as db:
            try:
                # Post-connect Guard 1: Verify authenticated role and database
                current_user, current_db = db.execute(
                    text("SELECT current_user, current_database()")
                ).one()

                if current_user != EXPECTED_ROLE_NAME:
                    raise ProvisioningAbort(
                        "Connected session role does not match the required application runtime role."
                    )

                if current_db != EXPECTED_DATABASE_NAME:
                    raise ProvisioningAbort(
                        "Connected database does not match the expected production database."
                    )

                # Post-connect Guard 2: Verify active TLS encryption on client driver socket
                if not verify_client_tls(db):
                    raise ProvisioningAbort("Live connection is not encrypted via TLS.")

                # Guard 3: Initial Admin Guard - Abort if ANY Admin exists
                existing_admin = db.scalar(
                    select(User).where(User.role == UserRole.ADMIN).limit(1)
                )
                if existing_admin:
                    raise ProvisioningAbort(
                        "An Administrator account already exists. Initial provisioning is locked."
                    )

                # Guard 4: Collision checks (Username and Email)
                if user_repository.get_by_username(db, username):
                    raise ProvisioningAbort("The requested username is already registered. No changes made.")

                if user_repository.get_by_email(db, email):
                    raise ProvisioningAbort("The requested email is already registered. No changes made.")

                # Step 1: Hash password using production Argon2id configuration
                hashed_pw = hash_password(password)

                # Step 2: Instantiate User and stage with db.flush() (no commit)
                admin_id = uuid.uuid4()
                new_user = User(
                    id=admin_id,
                    username=username,
                    email=email,
                    hashed_password=hashed_pw,
                    role=UserRole.ADMIN,
                    is_active=True,
                )
                db.add(new_user)
                db.flush()

                # Step 3: Append cryptographic audit event (does not commit internally)
                audit_repository.append_event(
                    db=db,
                    event_type="security.user_registered",
                    actor_id=None,
                    actor_role=None,
                    entity_type="user",
                    entity_id=str(new_user.id),
                    payload={
                        "user_id": str(new_user.id),
                        "username": new_user.username,
                        "email": new_user.email,
                        "role": new_user.role.value,
                    },
                )

                # Step 4: Single explicit commit of both User row and Audit event
                db.commit()
                db.refresh(new_user)

                provisioned_summary = (
                    "\n[SUCCESS] Production Administrator provisioned atomically.\n"
                    f"User ID : {new_user.id}\n"
                    f"Role    : {new_user.role.value}"
                )

            except ProvisioningAbort as abort_err:
                db.rollback()
                exit_code = 1
                failure_message = f"\n[ABORTED] {abort_err}"
            except Exception as e:
                db.rollback()
                exit_code = 1
                failure_message = f"\n[ERROR] Provisioning failed ({type(e).__name__}). Transaction cleanly rolled back."
    finally:
        engine.dispose()

    # Process exit strictly outside the active SQLAlchemy session and after engine disposal
    if exit_code != 0:
        if failure_message:
            print(failure_message)
        sys.exit(exit_code)

    if provisioned_summary:
        print(provisioned_summary)


if __name__ == "__main__":
    main()
