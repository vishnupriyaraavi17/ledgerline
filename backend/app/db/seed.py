import sys
import secrets
from pathlib import Path
from sqlalchemy.orm import Session

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.config import settings
from backend.app.db.session import SessionLocal
from backend.app.models.user import User, UserRole
from backend.app.schemas.user import UserCreate
from backend.app.services.auth import auth_service
from backend.app.repositories.user import user_repository


def seed_development_accounts(db: Session):
    """
    Seeds three baseline development accounts (Admin, Account Holder, Auditor).
    Strictly blocked in production environments.
    Passwords are sourced from environment variables or cryptographically generated.
    """
    if settings.ENVIRONMENT.lower() == "production":
        print("[ABORT] Database seeding is strictly disabled in production environments.")
        return

    print("--- LedgerLine Development Account Seeding ---")

    accounts_to_seed = [
        {
            "username": "admin",
            "email": "admin@ledgerline.internal",
            "role": UserRole.ADMIN,
            "env_pass": settings.SEED_ADMIN_PASSWORD,
        },
        {
            "username": "holder",
            "email": "holder@ledgerline.internal",
            "role": UserRole.ACCOUNT_HOLDER,
            "env_pass": settings.SEED_HOLDER_PASSWORD,
        },
        {
            "username": "auditor",
            "email": "auditor@ledgerline.internal",
            "role": UserRole.AUDITOR,
            "env_pass": settings.SEED_AUDITOR_PASSWORD,
        },
    ]

    for acc in accounts_to_seed:
        existing = user_repository.get_by_username(db, acc["username"])
        if existing:
            print(f"[*] Account '{acc['username']}' already exists ({acc['role'].value}). Skipping.")
            continue

        password = acc["env_pass"] or f"{secrets.token_urlsafe(12)}!9A"
        user_in = UserCreate(
            username=acc["username"],
            email=acc["email"],
            password=password,
            role=acc["role"],
        )
        created = auth_service.create_user(db, user_in)
        print(f"[+] Provisioned {acc['role'].value.upper()}:")
        print(f"    Username: {created.username}")
        print(f"    Email:    {created.email}")
        print(f"    Password: {password}")
        print(f"    User ID:  {created.id}")

    print("--- Seeding Complete ---")


if __name__ == "__main__":
    with SessionLocal() as db_session:
        seed_development_accounts(db_session)
