import uuid
from decimal import Decimal
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from sqlalchemy import select, func, text, and_, case
from sqlalchemy.orm import Session

from backend.app.models.account import Account, AccountType
from backend.app.models.ledger import (
    LedgerTransaction,
    LedgerEntry,
    EntryType,
    TransactionType,
)


class StatementRepository:
    """
    Data access layer for Account Statements.
    Executes under a consistent PostgreSQL REPEATABLE READ READ ONLY snapshot.
    Ensures deterministic ordering and exact paise decimal precision.
    """

    @staticmethod
    def get_account_under_snapshot(db: Session, account_id: uuid.UUID) -> Optional[Account]:
        """
        Fetch account entity ensuring REPEATABLE READ snapshot consistency.
        """
        return db.scalar(select(Account).where(Account.id == account_id))

    @staticmethod
    def compute_opening_balance(
        db: Session, account_id: uuid.UUID, start_date: datetime
    ) -> Decimal:
        """
        Compute opening balance at start_date from genesis:
        Sum of credits minus sum of debits for entries where created_at < start_date.
        Strictly applies to customer accounts (normal balance = CREDIT).
        """
        stmt = (
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (LedgerEntry.entry_type == EntryType.CREDIT, LedgerEntry.amount),
                            (LedgerEntry.entry_type == EntryType.DEBIT, -LedgerEntry.amount),
                            else_=Decimal("0.00"),
                        )
                    ),
                    Decimal("0.00"),
                )
            )
            .where(
                LedgerEntry.account_id == account_id,
                LedgerEntry.created_at < start_date,
            )
        )
        opening_bal = db.scalar(stmt)
        return opening_bal if opening_bal is not None else Decimal("0.00")

    @staticmethod
    def fetch_period_entries(
        db: Session, account_id: uuid.UUID, start_date: datetime, end_date: datetime
    ) -> List[Tuple[LedgerEntry, LedgerTransaction]]:
        """
        Fetch all ledger entries and transaction headers for the account in [start_date, end_date).
        Deterministically ordered by created_at ASC, sequence ASC, id ASC.
        """
        stmt = (
            select(LedgerEntry, LedgerTransaction)
            .join(LedgerTransaction, LedgerEntry.transaction_id == LedgerTransaction.id)
            .where(
                LedgerEntry.account_id == account_id,
                LedgerEntry.created_at >= start_date,
                LedgerEntry.created_at < end_date,
            )
            .order_by(
                LedgerEntry.created_at.asc(),
                LedgerEntry.sequence.asc(),
                LedgerEntry.id.asc(),
            )
        )
        return list(db.execute(stmt).all())

    @staticmethod
    def resolve_counterparties(
        db: Session,
        entries: List[Tuple[LedgerEntry, LedgerTransaction]],
        account_id: uuid.UUID,
    ) -> Dict[uuid.UUID, Tuple[Optional[str], Optional[str]]]:
        """
        Resolve counterparty account number and name for each transaction in the period.
        Returns a mapping of transaction_id -> (counterparty_account_number, counterparty_name).
        """
        txn_ids = list({e[0].transaction_id for e in entries})
        if not txn_ids:
            return {}

        # Sibling query: find ledger entries for same txn_id where account_id != account_id
        sibling_stmt = (
            select(
                LedgerEntry.transaction_id,
                Account.account_number,
                Account.name,
            )
            .join(Account, LedgerEntry.account_id == Account.id)
            .where(
                LedgerEntry.transaction_id.in_(txn_ids),
                LedgerEntry.account_id != account_id,
            )
        )
        mapping = {}
        for row in db.execute(sibling_stmt).all():
            mapping[row[0]] = (row[1], row[2])
        return mapping


statement_repository = StatementRepository()
