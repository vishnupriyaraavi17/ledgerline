import argparse
from datetime import datetime, timezone
from decimal import Decimal
import os
from pathlib import Path
import subprocess
import sys
import uuid

# Force utf-8 encoding on standard output for Windows console compatibility
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure repository root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session
from alembic.config import Config
from alembic import command

from backend.app.core.config import settings
from backend.app.db.seed import seed_development_accounts
from backend.app.models.user import User
from backend.app.models.account import Account, AccountType
from backend.app.schemas.account import AccountCreate
from backend.app.schemas.transfer import DepositRequest, TransferRequest
from backend.app.services.account import account_service
from backend.app.services.transfer import transfer_service
from backend.app.services.audit import audit_service


def find_pg_binary(name: str) -> str:
    """Locate PostgreSQL binary (e.g. pg_dump, pg_restore)."""
    # Check default install path on Windows first
    default_win_path = Path(r"C:\Program Files\PostgreSQL\17\bin") / f"{name}.exe"
    if default_win_path.exists():
        return str(default_win_path)

    # Check PATH
    import shutil
    binary_path = shutil.which(name)
    if binary_path:
        return binary_path

    raise FileNotFoundError(f"Could not locate '{name}' executable in PATH or standard installation directories.")


def execute_backup() -> Path:
    """Executes pg_dump and validates the archive with pg_restore --list."""
    backups_dir = PROJECT_ROOT / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_file = backups_dir / f"ledgerline_backup_{timestamp}.dump"

    pg_dump_bin = find_pg_binary("pg_dump")
    pg_restore_bin = find_pg_binary("pg_restore")

    print(f"[*] Step 1: Creating backup using pg_dump: {backup_file.name} ...")

    env = os.environ.copy()
    if settings.MIGRATION_POSTGRES_PASSWORD:
        env["PGPASSWORD"] = settings.MIGRATION_POSTGRES_PASSWORD

    dump_cmd = [
        pg_dump_bin,
        "-h", settings.POSTGRES_SERVER,
        "-p", str(settings.POSTGRES_PORT),
        "-U", settings.MIGRATION_POSTGRES_USER,
        "-F", "c",
        "-b",
        "-v",
        "-f", str(backup_file),
        settings.POSTGRES_DB,
    ]

    res = subprocess.run(dump_cmd, env=env, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"pg_dump failed (exit code {res.returncode}):\n{res.stderr}")

    if not backup_file.exists() or backup_file.stat().st_size == 0:
        raise RuntimeError(f"Backup file was not created or is empty: {backup_file}")

    print(f"[+] pg_dump succeeded ({backup_file.stat().st_size} bytes).")

    # Validate archive readability
    print("[*] Validating backup archive readability via pg_restore --list ...")
    restore_cmd = [
        pg_restore_bin,
        "--list",
        str(backup_file),
    ]
    res_restore = subprocess.run(restore_cmd, capture_output=True, text=True)
    if res_restore.returncode != 0:
        raise RuntimeError(f"pg_restore archive validation failed (exit code {res_restore.returncode}):\n{res_restore.stderr}")

    # Confirm core table presence in archive table of contents
    toc = res_restore.stdout
    required_tables = ["accounts", "users", "ledger_transactions", "audit_events"]
    for tbl in required_tables:
        if tbl not in toc:
            raise RuntimeError(f"Archive validation warning: Expected table '{tbl}' not found in archive TOC.")

    print("[+] Archive TOC verified successfully via pg_restore --list.")
    return backup_file


def reset_and_seed_demo():
    """Safely resets the development database and seeds clean demo data."""
    # Target validation
    m_url = make_url(settings.MIGRATION_DATABASE_URI)
    r_url = make_url(settings.SQLALCHEMY_DATABASE_URI)

    if m_url.database != "ledgerline" or r_url.database != "ledgerline":
        raise RuntimeError(f"Destructive reset blocked: Target database must be 'ledgerline', got '{m_url.database}'")

    if m_url.host not in ("127.0.0.1", "localhost"):
        raise RuntimeError(f"Destructive reset blocked: Target host must be local (127.0.0.1/localhost), got '{m_url.host}'")

    if r_url.host not in ("127.0.0.1", "localhost"):
        raise RuntimeError(f"Destructive reset blocked: Target host must be local (127.0.0.1/localhost), got '{r_url.host}'")

    # 1. Execute and validate backup
    backup_file = execute_backup()
    print(f"[+] Verified backup retained at: {backup_file}")

    # 2. Reset schema public using ledgerline_owner
    print("[*] Step 2: Resetting schema public as ledgerline_owner ...")
    owner_engine = create_engine(settings.MIGRATION_DATABASE_URI)
    with owner_engine.connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT").execute(
            text(
                "DROP SCHEMA IF EXISTS public CASCADE; "
                "CREATE SCHEMA public AUTHORIZATION ledgerline_owner; "
                "GRANT ALL ON SCHEMA public TO ledgerline_owner; "
                "GRANT USAGE ON SCHEMA public TO ledgerline_app;"
            )
        )
    owner_engine.dispose()
    print("[+] Schema public recreated cleanly.")

    # 3. Apply Alembic migrations through head
    print("[*] Step 3: Applying Alembic migrations through 0007_statements_refusals ...")
    alembic_ini_path = str(PROJECT_ROOT / "backend" / "alembic.ini")
    alembic_cfg = Config(alembic_ini_path)
    alembic_cfg.set_main_option("sqlalchemy.url", settings.MIGRATION_DATABASE_URI)
    command.upgrade(alembic_cfg, "head")
    print("[+] All migrations applied successfully.")

    # Grant application runtime role DML permissions on users table (consistent with scripts/setup_roles.sql)
    owner_engine = create_engine(settings.MIGRATION_DATABASE_URI)
    with owner_engine.connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT").execute(
            text("GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.users TO ledgerline_app;")
        )
    owner_engine.dispose()
    print("[+] Granted users table DML privileges to ledgerline_app.")

    # 4. Seed baseline development accounts using runtime role (ledgerline_app)
    print("[*] Step 4: Seeding baseline users (admin, holder, auditor) as ledgerline_app ...")
    app_engine = create_engine(settings.SQLALCHEMY_DATABASE_URI)
    with Session(app_engine) as session:
        seed_development_accounts(session)

    # 5. Provision 2 clean customer accounts for holder initialized at 0.00
    print("[*] Step 5: Provisioning customer accounts for 'holder' ...")
    with Session(app_engine) as session:
        holder_user = session.query(User).filter(User.username == "holder").one()

        # Checking account
        checking_in = AccountCreate(
            name="Primary Checking",
            account_type=AccountType.CUSTOMER_CHECKING,
            currency="INR",
        )
        checking_acc = account_service.create_account(session, holder_user, checking_in)
        print(f"[+] Created Account: {checking_acc.account_number} ({checking_acc.name}) - Balance: INR {checking_acc.balance}")

        # Savings account
        savings_in = AccountCreate(
            name="High-Yield Savings",
            account_type=AccountType.CUSTOMER_SAVINGS,
            currency="INR",
        )
        savings_acc = account_service.create_account(session, holder_user, savings_in)
        print(f"[+] Created Account: {savings_acc.account_number} ({savings_acc.name}) - Balance: INR {savings_acc.balance}")

        checking_id = checking_acc.id
        savings_id = savings_acc.id

    # 6. Fund accounts exclusively via transfer_service.deposit() with idempotency keys
    print("[*] Step 6: Executing genuine double-entry settlements via transfer_service ...")
    with Session(app_engine) as session:
        holder_user = session.query(User).filter(User.username == "holder").one()

        # Deposit 1: ₹50,000.00 to checking
        dep1 = DepositRequest(
            account_id=checking_id,
            amount=Decimal("50000.00"),
            description="Payroll Direct Deposit",
        )
        res1, _ = transfer_service.deposit(
            db=session,
            current_user=holder_user,
            req=dep1,
            idempotency_key=f"demo-seed-dep-chk-{uuid.uuid4().hex[:8]}",
        )
        print(f"[+] Deposited INR 50,000.00 to Primary Checking (Ref: {res1['reference']})")

        # Deposit 2: ₹100,000.00 to savings
        dep2 = DepositRequest(
            account_id=savings_id,
            amount=Decimal("100000.00"),
            description="Initial Savings Transfer",
        )
        res2, _ = transfer_service.deposit(
            db=session,
            current_user=holder_user,
            req=dep2,
            idempotency_key=f"demo-seed-dep-sav-{uuid.uuid4().hex[:8]}",
        )
        print(f"[+] Deposited INR 100,000.00 to High-Yield Savings (Ref: {res2['reference']})")

        # Transfer: ₹10,000.00 from checking to savings
        xfer = TransferRequest(
            source_account_id=checking_id,
            destination_account_id=savings_id,
            amount=Decimal("10000.00"),
            description="Emergency Fund Contribution",
        )
        res3, _ = transfer_service.transfer(
            db=session,
            current_user=holder_user,
            req=xfer,
            idempotency_key=f"demo-seed-xfer-{uuid.uuid4().hex[:8]}",
        )
        print(f"[+] Transferred INR 10,000.00 Checking -> Savings (Ref: {res3['reference']})")

    # 7. Verification of audit chain and money conservation
    print("[*] Step 7: Verifying cryptographic audit chain and balance conservation ...")
    with Session(app_engine) as session:
        ver_result = audit_service.verify_chain(session)
        print(f"[+] Audit Chain Verification: valid={ver_result.is_valid}, total_events={ver_result.total_events}, head_seq={ver_result.head_sequence}")
        if not ver_result.is_valid:
            raise RuntimeError(f"Audit chain verification failed after demo seeding! Tamper details: {ver_result.tamper_details}")

        # Confirm account balances
        acc1 = session.query(Account).filter(Account.id == checking_id).one()
        acc2 = session.query(Account).filter(Account.id == savings_id).one()
        print(f"[+] Final Balances: Primary Checking = INR {acc1.balance}, High-Yield Savings = INR {acc2.balance}")

    app_engine.dispose()
    print("\n=== Demo Database Reset & Seeding Completed Successfully ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Safely reset and seed the LedgerLine demo database.")
    parser.add_argument(
        "--confirm-destructive-reset",
        action="store_true",
        help="Mandatory confirmation flag required to execute the destructive schema reset.",
    )
    args = parser.parse_args()

    if not args.confirm_destructive_reset:
        print("[ABORT] Missing required confirmation argument.")
        print("To safely reset and seed the demo database, you must explicitly supply:")
        print("  python backend/app/db/reset_demo.py --confirm-destructive-reset")
        sys.exit(1)

    reset_and_seed_demo()
