import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.app.models.audit import AuditEvent, AuditChainHead
from backend.app.repositories.audit import audit_repository, AuditRepository
from backend.app.schemas.audit import (
    VerificationResult,
    TamperDetail,
    TamperFailureType,
    AuditListResponse,
    AuditEventResponse,
    AuditHeadResponse,
)


class AuditService:
    @staticmethod
    def verify_chain(db: Session) -> VerificationResult:
        """
        Performs full mathematical verification of the cryptographic audit chain:
        1. Acquires SELECT ... FOR SHARE on audit_chain_head (preventing concurrent writes)
        2. Streams all events from genesis to head in ascending sequence order
        3. Validates sequence continuity, parent pointer linkage, and SHA-256 payload integrity
        4. Asserts final event matches committed audit_chain_head
        """
        # 1. Acquire shared lock on chain head via SECURITY DEFINER function
        head_row = db.execute(
            text("SELECT sequence_number, current_hash FROM public.lock_audit_chain_head_for_share()")
        ).mappings().one()
        head_seq = head_row["sequence_number"]
        head_hash = head_row["current_hash"]

        verified_at = datetime.now(timezone.utc)

        # 2. Genesis empty check
        if head_seq == 0:
            first_event = db.scalar(select(AuditEvent).limit(1))
            if first_event is not None:
                return VerificationResult(
                    is_valid=False,
                    total_events=0,
                    verified_at=verified_at,
                    head_sequence=head_seq,
                    head_hash=head_hash,
                    tamper_details=TamperDetail(
                        failure_type=TamperFailureType.HEAD_DESYNC,
                        sequence_number=first_event.sequence_number,
                        event_id=str(first_event.id),
                        expected_value="0",
                        actual_value=str(first_event.sequence_number),
                        message="Chain head indicates 0 events, but events exist in audit_events.",
                    ),
                )
            return VerificationResult(
                is_valid=True,
                total_events=0,
                verified_at=verified_at,
                head_sequence=head_seq,
                head_hash=head_hash,
            )

        # 3. Stream all events from sequence 1 to head
        expected_seq = 1
        expected_prev_hash = "0" * 64
        total_verified = 0

        # Stream ordered events using yield_per for memory efficiency
        stmt = select(AuditEvent).order_by(AuditEvent.sequence_number.asc()).execution_options(yield_per=500)
        events_stream = db.scalars(stmt)

        for event in events_stream:
            # Check Sequence Continuity
            if event.sequence_number != expected_seq:
                return VerificationResult(
                    is_valid=False,
                    total_events=total_verified,
                    verified_at=verified_at,
                    head_sequence=head_seq,
                    head_hash=head_hash,
                    tamper_details=TamperDetail(
                        failure_type=TamperFailureType.SEQUENCE_GAP,
                        sequence_number=expected_seq,
                        event_id=str(event.id),
                        expected_value=str(expected_seq),
                        actual_value=str(event.sequence_number),
                        message=f"Sequence gap detected: expected sequence #{expected_seq}, but found #{event.sequence_number}.",
                    ),
                )

            # Check Parent Hash Linkage
            if event.prev_hash != expected_prev_hash:
                return VerificationResult(
                    is_valid=False,
                    total_events=total_verified,
                    verified_at=verified_at,
                    head_sequence=head_seq,
                    head_hash=head_hash,
                    tamper_details=TamperDetail(
                        failure_type=TamperFailureType.BROKEN_CHAIN,
                        sequence_number=event.sequence_number,
                        event_id=str(event.id),
                        expected_value=expected_prev_hash,
                        actual_value=event.prev_hash,
                        message=f"Broken hash pointer at sequence #{event.sequence_number}: previous hash does not match predecessor digest.",
                    ),
                )

            # Check Canonical Content Integrity
            computed_hash, _ = AuditRepository.compute_event_hash(
                sequence_number=event.sequence_number,
                prev_hash=event.prev_hash,
                event_type=event.event_type,
                actor_id=event.actor_id,
                actor_role=event.actor_role,
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                payload=event.payload,
                created_at=event.created_at,
            )

            if event.current_hash != computed_hash:
                return VerificationResult(
                    is_valid=False,
                    total_events=total_verified,
                    verified_at=verified_at,
                    head_sequence=head_seq,
                    head_hash=head_hash,
                    tamper_details=TamperDetail(
                        failure_type=TamperFailureType.HASH_MISMATCH,
                        sequence_number=event.sequence_number,
                        event_id=str(event.id),
                        expected_value=computed_hash,
                        actual_value=event.current_hash,
                        message=f"Content hash mismatch at sequence #{event.sequence_number}: stored hash differs from canonical serialization.",
                    ),
                )

            expected_prev_hash = event.current_hash
            expected_seq += 1
            total_verified += 1

        # 4. Check Head Synchronization
        last_seq = expected_seq - 1
        if head_seq != last_seq or head_hash != expected_prev_hash:
            return VerificationResult(
                is_valid=False,
                total_events=total_verified,
                verified_at=verified_at,
                head_sequence=head_seq,
                head_hash=head_hash,
                tamper_details=TamperDetail(
                    failure_type=TamperFailureType.HEAD_DESYNC,
                    sequence_number=head_seq,
                    expected_value=f"seq={last_seq}, hash={expected_prev_hash}",
                    actual_value=f"seq={head_seq}, hash={head_hash}",
                    message="Audit chain head is desynchronized from the final event in the chain.",
                ),
            )

        return VerificationResult(
            is_valid=True,
            total_events=total_verified,
            verified_at=verified_at,
            head_sequence=head_seq,
            head_hash=head_hash,
        )

    @staticmethod
    def list_events(
        db: Session,
        event_type: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        actor_id: Optional[uuid.UUID] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> AuditListResponse:
        events, total = audit_repository.list_events(
            db=db,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor_id,
            limit=limit,
            offset=offset,
        )
        return AuditListResponse(
            items=[AuditEventResponse.model_validate(e) for e in events],
            total=total,
            limit=limit,
            offset=offset,
        )

    @staticmethod
    def get_head(db: Session) -> AuditHeadResponse:
        head = audit_repository.get_head(db)
        return AuditHeadResponse.model_validate(head)


audit_service = AuditService()
