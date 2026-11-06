import uuid
from decimal import Decimal
from typing import List, Tuple
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from backend.app.models.ledger import LedgerEntry, EntryType


class LedgerRepository:
    """
    Data access layer for Ledger entities.
    Strictly read-only for application runtime role.
    """

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
