import hashlib
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, NamedTuple, Optional, Tuple
from sqlalchemy import select, text, func, and_
from sqlalchemy.orm import Session

from backend.app.models.audit import AuditEvent, AuditChainHead


def canonicalize_payload(val: Any) -> Any:
    """
    Recursively normalizes payload elements to guarantee 100% deterministic
    canonical JSON serialization:
    - Dicts: Keys sorted alphabetically
    - Lists/Tuples: Preserved in order, elements normalized recursively
    - Decimal: Formatted as exact fixed 2-decimal string (paise precision)
    - float: Converted via Decimal to fixed 2-decimal string
    - UUID: Lowercase 36-character canonical string
    - None: Preserved as None (serializes to JSON null)
    - bool/int: Preserved as native types
    - str: Preserved with exact internal, leading, and trailing whitespace
    """
    if isinstance(val, dict):
        return {str(k): canonicalize_payload(v) for k, v in sorted(val.items())}
    elif isinstance(val, (list, tuple)):
        return [canonicalize_payload(item) for item in val]
    elif isinstance(val, Decimal):
        return str(val.quantize(Decimal("0.01")))
    elif isinstance(val, float):
        return str(Decimal(str(val)).quantize(Decimal("0.01")))
    elif isinstance(val, uuid.UUID):
        return str(val).lower()
    elif val is None:
        return None
    elif isinstance(val, bool):
        return val
    elif isinstance(val, int):
        return val
    elif isinstance(val, str):
        return val
    else:
        return str(val)


def normalize_timestamp(dt: datetime) -> str:
    """
    Normalizes a datetime object to UTC ISO-8601 with exact microsecond resolution:
    YYYY-MM-DDTHH:MM:SS.ffffffZ
    Matches PostgreSQL TIMESTAMPTZ storage bit-for-bit.
    Fails closed if given a timezone-naive timestamp.
    """
    if dt.tzinfo is None:
        raise ValueError("Timezone-naive timestamps are strictly prohibited in audit records.")
    utc_dt = dt.astimezone(timezone.utc)
    return utc_dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class AuditAppendResult(NamedTuple):
    event_id: uuid.UUID
    sequence_number: int
    prev_hash: str
    current_hash: str


class AuditRepository:
    """
    Repository for cryptographic audit trail data access:
    - Universal Stage 3 locking on audit_chain_head
    - Deterministic SHA-256 canonical event hashing
    - Controlled insertion via PostgreSQL SECURITY DEFINER append_audit_event()
    - Zero post-lock queries prior to commit
    """

    @staticmethod
    def compute_event_hash(
        sequence_number: int,
        prev_hash: str,
        event_type: str,
        actor_id: Optional[uuid.UUID],
        actor_role: Optional[str],
        entity_type: str,
        entity_id: str,
        payload: Dict[str, Any],
        created_at: datetime,
    ) -> Tuple[str, Dict[str, Any]]:
        canonical_payload = canonicalize_payload(payload)
        canonical_dict = {
            "actor_id": str(actor_id).lower() if actor_id else None,
            "actor_role": str(actor_role) if actor_role else None,
            "created_at": normalize_timestamp(created_at),
            "entity_id": str(entity_id),
            "entity_type": str(entity_type),
            "event_type": str(event_type),
            "payload": canonical_payload,
            "prev_hash": str(prev_hash),
            "sequence_number": int(sequence_number),
        }
        canonical_json = json.dumps(canonical_dict, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
        return digest, canonical_payload

    @staticmethod
    def append_event(
        db: Session,
        event_type: str,
        actor_id: Optional[uuid.UUID],
        actor_role: Optional[str],
        entity_type: str,
        entity_id: str,
        payload: Dict[str, Any],
        timestamp: Optional[datetime] = None,
    ) -> AuditAppendResult:
        """
        Appends an immutable audit event to the cryptographic chain:
        1. Acquires Stage 3 lock on audit_chain_head (SELECT ... FOR UPDATE)
        2. Computes canonical payload and SHA-256 hash
        3. Calls SECURITY DEFINER append_audit_event() with explicit JSONB binding
        4. Returns AuditAppendResult directly with zero post-lock queries
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        elif timestamp.tzinfo is None:
            raise ValueError("Timezone-naive timestamps are strictly prohibited in audit records.")

        # Stage 3 Lock: Exclusively lock and read current head via SECURITY DEFINER function
        head_row = db.execute(
            text("SELECT sequence_number, current_hash FROM public.acquire_audit_chain_head()")
        ).mappings().one()

        expected_seq = head_row["sequence_number"] + 1
        expected_prev_hash = head_row["current_hash"]

        # Canonicalize payload and calculate SHA-256 digest
        current_hash, canonical_payload = AuditRepository.compute_event_hash(
            sequence_number=expected_seq,
            prev_hash=expected_prev_hash,
            event_type=event_type,
            actor_id=actor_id,
            actor_role=actor_role,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
            created_at=timestamp,
        )

        payload_json_str = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":"))

        # Explicitly invoke SECURITY DEFINER append_audit_event with JSONB cast
        stmt = text("""
            SELECT event_id, sequence_number, prev_hash, current_hash
            FROM public.append_audit_event(
                :event_type,
                :actor_id,
                :actor_role,
                :entity_type,
                :entity_id,
                CAST(:payload AS jsonb),
                :timestamp,
                :expected_prev_hash,
                :expected_sequence,
                :current_hash
            )
        """)

        row = db.execute(
            stmt,
            {
                "event_type": event_type,
                "actor_id": actor_id,
                "actor_role": actor_role,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "payload": payload_json_str,
                "timestamp": timestamp,
                "expected_prev_hash": expected_prev_hash,
                "expected_sequence": expected_seq,
                "current_hash": current_hash,
            },
        ).mappings().one()

        # Zero post-lock queries! Return function result directly.
        return AuditAppendResult(
            event_id=row["event_id"],
            sequence_number=row["sequence_number"],
            prev_hash=row["prev_hash"],
            current_hash=row["current_hash"],
        )

    @staticmethod
    def get_head(db: Session) -> AuditChainHead:
        return db.execute(
            select(AuditChainHead).where(AuditChainHead.id == 1)
        ).scalar_one()

    @staticmethod
    def list_events(
        db: Session,
        event_type: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        actor_id: Optional[uuid.UUID] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[AuditEvent], int]:
        query = select(AuditEvent)
        filters = []

        if event_type:
            filters.append(AuditEvent.event_type == event_type)
        if entity_type:
            filters.append(AuditEvent.entity_type == entity_type)
        if entity_id:
            filters.append(AuditEvent.entity_id == entity_id)
        if actor_id:
            filters.append(AuditEvent.actor_id == actor_id)

        if filters:
            query = query.where(and_(*filters))

        total_count = db.scalar(
            select(func.count()).select_from(query.subquery())
        ) or 0

        items = db.scalars(
            query.order_by(AuditEvent.sequence_number.desc())
            .limit(limit)
            .offset(offset)
        ).all()

        return list(items), total_count


audit_repository = AuditRepository()
