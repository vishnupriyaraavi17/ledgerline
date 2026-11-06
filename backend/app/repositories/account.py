import secrets
import string
import uuid
from typing import Optional, List, Tuple
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from backend.app.models.account import Account, AccountType, AccountStatus


class AccountRepository:
    """
    Data access layer for Account entities.
    """

    @staticmethod
    def generate_unique_account_number(db: Session) -> str:
        """
        Generate a unique customer account number matching 'ACC-[A-Z0-9]{8}'.
        Explicitly excludes the reserved 'SYSTEM' prefix to avoid collision
        with reserved system accounts (e.g. ACC-SYSTEM01).
        """
        alphabet = string.ascii_uppercase + string.digits
        for _ in range(20):
            suffix = "".join(secrets.choice(alphabet) for _ in range(8))
            # Disallow reserved prefix
            if suffix.startswith("SYSTEM"):
                continue
            candidate = f"ACC-{suffix}"
            existing = db.scalar(select(Account.id).where(Account.account_number == candidate))
            if not existing:
                return candidate
        raise RuntimeError("Unable to generate unique account number after multiple attempts")

    @staticmethod
    def create_account(
        db: Session,
        name: str,
        account_type: AccountType,
        owner_id: Optional[uuid.UUID] = None,
        currency: str = "INR",
    ) -> Account:
        """
        Create a new customer account.
        NOTE: 'balance' is intentionally omitted to let PostgreSQL's database-side
        'DEFAULT 0.00' populate the balance, complying strictly with column-level
        privileges granted to the runtime role.
        """
        account_number = AccountRepository.generate_unique_account_number(db)
        account = Account(
            id=uuid.uuid4(),
            account_number=account_number,
            owner_id=owner_id,
            name=name,
            account_type=account_type,
            currency=currency,
            status=AccountStatus.ACTIVE,
        )
        db.add(account)
        db.commit()
        db.refresh(account)
        return account

    @staticmethod
    def get_by_id(db: Session, account_id: uuid.UUID) -> Optional[Account]:
        return db.scalar(select(Account).where(Account.id == account_id))

    @staticmethod
    def get_by_number(db: Session, account_number: str) -> Optional[Account]:
        return db.scalar(select(Account).where(Account.account_number == account_number.strip()))

    @staticmethod
    def list_accounts_by_owner(
        db: Session, owner_id: uuid.UUID, skip: int = 0, limit: int = 50
    ) -> Tuple[List[Account], int]:
        total = db.scalar(
            select(func.count()).select_from(Account).where(Account.owner_id == owner_id)
        ) or 0
        stmt = (
            select(Account)
            .where(Account.owner_id == owner_id)
            .order_by(Account.created_at.asc())
            .offset(skip)
            .limit(limit)
        )
        items = list(db.scalars(stmt).all())
        return items, total

    @staticmethod
    def list_all_accounts(
        db: Session, skip: int = 0, limit: int = 50
    ) -> Tuple[List[Account], int]:
        total = db.scalar(select(func.count()).select_from(Account)) or 0
        stmt = select(Account).order_by(Account.created_at.asc()).offset(skip).limit(limit)
        items = list(db.scalars(stmt).all())
        return items, total

    @staticmethod
    def update_status(
        db: Session, account: Account, new_status: AccountStatus
    ) -> Account:
        account.status = new_status
        db.commit()
        db.refresh(account)
        return account


account_repository = AccountRepository()
