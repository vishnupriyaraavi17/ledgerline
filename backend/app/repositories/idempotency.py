import hashlib
import json
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.app.models.idempotency import IdempotencyRecord


class IdempotencyRepository:
    """
    Repository for PostgreSQL database-backed idempotency management:
    - Deterministic SHA-256 canonical request fingerprinting
    - Atomic processing record reservation via INSERT ... ON CONFLICT DO NOTHING
    - Pessimistic row locking for concurrent requests via SELECT ... FOR UPDATE
    - Permanent completed record tracking
    """

    @staticmethod
    def compute_canonical_fingerprint(operation_type: str, payload_data: Dict[str, Any]) -> str:
        """
        Computes a deterministic SHA-256 digest from canonical JSON serialization.
        Ensures exact decimal formatting, key sorting, and whitespace-sensitive value preservation
        while eliminating extraneous structural JSON formatting whitespace.
        """
        canonical_dict = {"operation": operation_type}
        for k, v in sorted(payload_data.items()):
            if isinstance(v, Decimal):
                # Normalize to 2 decimal places (paise precision)
                canonical_dict[k] = str(v.quantize(Decimal("0.01")))
            elif isinstance(v, uuid.UUID):
                canonical_dict[k] = str(v)
            elif v is None:
                canonical_dict[k] = ""
            else:
                canonical_dict[k] = str(v)

        canonical_json = json.dumps(canonical_dict, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    @staticmethod
    def try_create_processing_record(
        db: Session,
        user_id: uuid.UUID,
        idempotency_key: str,
        operation_type: str,
        request_hash: str,
    ) -> Optional[IdempotencyRecord]:
        """
        Attempts to atomically reserve the idempotency key in 'processing' status.
        Uses INSERT ... ON CONFLICT (user_id, idempotency_key) DO NOTHING.
        Returns the IdempotencyRecord if reserved by this transaction, or None if conflict.
        """
        stmt = (
            insert(IdempotencyRecord)
            .values(
                user_id=user_id,
                idempotency_key=idempotency_key,
                operation_type=operation_type,
                request_hash=request_hash,
                status="processing",
            )
            .on_conflict_do_nothing(
                index_elements=["user_id", "idempotency_key"]
            )
            .returning(IdempotencyRecord.id)
        )
        inserted_id = db.execute(stmt).scalar_one_or_none()
        if inserted_id:
            # Flushes to ensure the row exists in the transaction
            return db.get(IdempotencyRecord, inserted_id)
        return None

    @staticmethod
    def get_locked_record(
        db: Session,
        user_id: uuid.UUID,
        idempotency_key: str,
    ) -> Optional[IdempotencyRecord]:
        """
        Acquires a pessimistic row-level lock on the existing idempotency record:
        SELECT ... WHERE user_id=:u AND idempotency_key=:k FOR UPDATE.
        Blocks until any concurrent transaction holding the lock commits or rolls back.
        """
        stmt = (
            select(IdempotencyRecord)
            .where(
                IdempotencyRecord.user_id == user_id,
                IdempotencyRecord.idempotency_key == idempotency_key,
            )
            .with_for_update()
        )
        return db.scalar(stmt)

    @staticmethod
    def mark_completed(
        db: Session,
        record: IdempotencyRecord,
        transaction_id: uuid.UUID,
        status_code: int,
        response_body: str,
    ) -> None:
        """
        Marks the idempotency record as completed with cached response body and status code.
        """
        record.status = "completed"
        record.transaction_id = transaction_id
        record.response_status_code = status_code
        record.response_body = response_body
        record.updated_at = datetime.now(timezone.utc)


idempotency_repository = IdempotencyRepository()
