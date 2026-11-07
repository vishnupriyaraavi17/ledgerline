import logging
import uuid
from decimal import Decimal
from typing import List, Optional, Tuple
from datetime import datetime
from sqlalchemy import select, or_, and_, desc
from sqlalchemy.orm import Session

from backend.app.db.session import SessionLocal
from backend.app.models.refusal import RefusedOperation
from backend.app.models.account import Account

logger = logging.getLogger(__name__)


class RefusalRepository:
    """
    Data access layer for refused and unsuccessful financial operations.
    Supports isolated autonomous persistence and statement history queries.
    """

    @staticmethod
    def record_refusal(
        user_id: uuid.UUID,
        operation_type: str,
        account_id: Optional[uuid.UUID],
        counterparty_account_id: Optional[uuid.UUID],
        amount: Optional[Decimal],
        refusal_reason: str,
        error_message: str,
        idempotency_key_hash: Optional[str] = None,
    ) -> Optional[uuid.UUID]:
        """
        Record a refused financial operation in an independent database session.
        Accepts safe primitive values only (no attached ORM objects).
        Fail-safe: errors in refusal logging are caught and logged without suppressing exceptions.
        """
        session: Session = SessionLocal()
        try:
            refusal = RefusedOperation(
                id=uuid.uuid4(),
                user_id=user_id,
                account_id=account_id,
                counterparty_account_id=counterparty_account_id,
                operation_type=operation_type,
                amount=amount,
                currency="INR",
                refusal_reason=refusal_reason,
                error_message=error_message,
                idempotency_key_hash=idempotency_key_hash,
            )
            session.add(refusal)
            session.commit()
            return refusal.id
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to persist refused operation record: {e}", exc_info=True)
            return None
        finally:
            session.close()

    @staticmethod
    def list_refusals_for_account(
        db: Session,
        account_id: uuid.UUID,
        start_date: datetime,
        end_date: datetime,
    ) -> List[Tuple[RefusedOperation, bool, Optional[str]]]:
        """
        Query refused operations where the account was either primary (account_id)
        or counterparty (counterparty_account_id) in interval [start_date, end_date).
        Returns a list of tuples: (RefusedOperation, is_source, counterparty_account_number).
        Deduplicates self-transfers where account_id == counterparty_account_id.
        """
        stmt = (
            select(RefusedOperation)
            .where(
                or_(
                    RefusedOperation.account_id == account_id,
                    RefusedOperation.counterparty_account_id == account_id,
                ),
                RefusedOperation.created_at >= start_date,
                RefusedOperation.created_at < end_date,
            )
            .order_by(desc(RefusedOperation.created_at), desc(RefusedOperation.id))
        )
        records = list(db.scalars(stmt).all())

        # Collect unique counterparty account IDs needing number lookups
        counterparty_ids = set()
        for rec in records:
            if rec.account_id == account_id and rec.counterparty_account_id:
                counterparty_ids.add(rec.counterparty_account_id)
            elif rec.counterparty_account_id == account_id and rec.account_id:
                counterparty_ids.add(rec.account_id)

        acc_num_map = {}
        if counterparty_ids:
            acc_stmt = select(Account.id, Account.account_number).where(Account.id.in_(counterparty_ids))
            for a_id, a_num in db.execute(acc_stmt).all():
                acc_num_map[a_id] = a_num

        results = []
        seen_ids = set()
        for rec in records:
            if rec.id in seen_ids:
                continue
            seen_ids.add(rec.id)

            is_source = (rec.account_id == account_id)
            c_num = None
            if is_source and rec.counterparty_account_id:
                c_num = acc_num_map.get(rec.counterparty_account_id)
            elif not is_source and rec.account_id:
                c_num = acc_num_map.get(rec.account_id)

            results.append((rec, is_source, c_num))

        return results


refusal_repository = RefusalRepository()
