import secrets
import string
import uuid
from decimal import Decimal
from typing import List, Optional, Tuple
from sqlalchemy import select, func, distinct
from sqlalchemy.orm import Session, selectinload

from backend.app.models.ledger import (
    LedgerTransaction,
    LedgerEntry,
    EntryType,
    TransactionType,
)


class LedgerRepository:
    """
    Data access layer for Ledger entities.
    Supports atomic double-entry posting and read-only journal queries.
    """

    @staticmethod
    def generate_unique_reference(db: Session) -> str:
        """
        Generate a unique transaction reference matching 'TXN-[A-Z0-9]{12}'.
        """
        alphabet = string.ascii_uppercase + string.digits
        for _ in range(20):
            suffix = "".join(secrets.choice(alphabet) for _ in range(12))
            candidate = f"TXN-{suffix}"
            existing = db.scalar(
                select(LedgerTransaction.id).where(LedgerTransaction.reference == candidate)
            )
            if not existing:
                return candidate
        raise RuntimeError("Unable to generate unique transaction reference after multiple attempts")

    @staticmethod
    def create_transaction_with_entries(
        db: Session,
        reference: str,
        transaction_type: TransactionType,
        description: str,
        debit_account_id: uuid.UUID,
        credit_account_id: uuid.UUID,
        amount: Decimal,
    ) -> LedgerTransaction:
        """
        Atomically post a balanced double-entry transaction.
        Entry 1: Debit leg on debit_account_id.
        Entry 2: Credit leg on credit_account_id.
        Flushes to trigger database balance sync and constraint checks.
        """
        txn_id = uuid.uuid4()
        txn = LedgerTransaction(
            id=txn_id,
            reference=reference,
            transaction_type=transaction_type,
            description=description,
        )
        db.add(txn)

        entry_debit = LedgerEntry(
            id=uuid.uuid4(),
            transaction_id=txn_id,
            account_id=debit_account_id,
            entry_type=EntryType.DEBIT,
            amount=amount,
            sequence=1,
        )
        entry_credit = LedgerEntry(
            id=uuid.uuid4(),
            transaction_id=txn_id,
            account_id=credit_account_id,
            entry_type=EntryType.CREDIT,
            amount=amount,
            sequence=2,
        )
        db.add(entry_debit)
        db.add(entry_credit)

        # Flush to execute triggers inside the active transaction
        db.flush()
        return txn

    @staticmethod
    def get_transaction_by_reference(
        db: Session, reference: str
    ) -> Optional[LedgerTransaction]:
        return db.scalar(
            select(LedgerTransaction)
            .options(selectinload(LedgerTransaction.entries))
            .where(LedgerTransaction.reference == reference.strip())
        )

    @staticmethod
    def get_transaction_by_id(
        db: Session, txn_id: uuid.UUID
    ) -> Optional[LedgerTransaction]:
        return db.scalar(
            select(LedgerTransaction)
            .options(selectinload(LedgerTransaction.entries))
            .where(LedgerTransaction.id == txn_id)
        )

    @staticmethod
    def list_transactions_for_accounts(
        db: Session, account_ids: List[uuid.UUID], skip: int = 0, limit: int = 50
    ) -> Tuple[List[LedgerTransaction], int]:
        if not account_ids:
            return [], 0

        # Subquery finding distinct transaction IDs involving the specified accounts
        matching_txn_ids_stmt = (
            select(distinct(LedgerEntry.transaction_id))
            .where(LedgerEntry.account_id.in_(account_ids))
        )

        total = db.scalar(
            select(func.count()).select_from(
                matching_txn_ids_stmt.subquery()
            )
        ) or 0

        stmt = (
            select(LedgerTransaction)
            .options(selectinload(LedgerTransaction.entries))
            .where(LedgerTransaction.id.in_(matching_txn_ids_stmt))
            .order_by(LedgerTransaction.posted_at.desc())
            .offset(skip)
            .limit(limit)
        )
        items = list(db.scalars(stmt).all())
        return items, total

    @staticmethod
    def list_all_transactions(
        db: Session, skip: int = 0, limit: int = 50
    ) -> Tuple[List[LedgerTransaction], int]:
        total = db.scalar(select(func.count()).select_from(LedgerTransaction)) or 0
        stmt = (
            select(LedgerTransaction)
            .options(selectinload(LedgerTransaction.entries))
            .order_by(LedgerTransaction.posted_at.desc())
            .offset(skip)
            .limit(limit)
        )
        items = list(db.scalars(stmt).all())
        return items, total

    @staticmethod
    def list_entries_by_account(
        db: Session, account_id: uuid.UUID, skip: int = 0, limit: int = 50
    ) -> Tuple[List[LedgerEntry], int]:
        total = db.scalar(
            select(func.count())
            .select_from(LedgerEntry)
            .where(LedgerEntry.account_id == account_id)
        ) or 0
        stmt = (
            select(LedgerEntry)
            .where(LedgerEntry.account_id == account_id)
            .order_by(LedgerEntry.created_at.asc(), LedgerEntry.sequence.asc())
            .offset(skip)
            .limit(limit)
        )
        items = list(db.scalars(stmt).all())
        return items, total

    @staticmethod
    def get_account_ledger_sum(db: Session, account_id: uuid.UUID) -> Decimal:
        """
        Compute read-only sum of ledger entries for an account.
        """
        credits = db.scalar(
            select(func.coalesce(func.sum(LedgerEntry.amount), Decimal("0.00")))
            .where(
                LedgerEntry.account_id == account_id,
                LedgerEntry.entry_type == EntryType.CREDIT,
            )
        ) or Decimal("0.00")

        debits = db.scalar(
            select(func.coalesce(func.sum(LedgerEntry.amount), Decimal("0.00")))
            .where(
                LedgerEntry.account_id == account_id,
                LedgerEntry.entry_type == EntryType.DEBIT,
            )
        ) or Decimal("0.00")

        return credits - debits


ledger_repository = LedgerRepository()
