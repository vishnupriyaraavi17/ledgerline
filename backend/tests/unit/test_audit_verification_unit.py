import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock
import pytest

from backend.app.models.audit import AuditEvent, AuditChainHead
from backend.app.services.audit import audit_service
from backend.app.repositories.audit import AuditRepository
from backend.app.schemas.audit import TamperFailureType


def make_mock_event(
    seq: int,
    prev_hash: str,
    event_type: str = "financial.deposit",
    payload: dict = None,
    created_at: datetime = None,
    tampered_current_hash: str = None,
) -> AuditEvent:
    if payload is None:
        payload = {"amount": "100.00"}
    if created_at is None:
        created_at = datetime(2026, 11, 7, 12, 0, seq, 0, tzinfo=timezone.utc)

    real_hash, _ = AuditRepository.compute_event_hash(
        sequence_number=seq,
        prev_hash=prev_hash,
        event_type=event_type,
        actor_id=None,
        actor_role=None,
        entity_type="transaction",
        entity_id=f"TXN-{seq}",
        payload=payload,
        created_at=created_at,
    )

    return AuditEvent(
        id=uuid.uuid4(),
        sequence_number=seq,
        event_type=event_type,
        actor_id=None,
        actor_role=None,
        entity_type="transaction",
        entity_id=f"TXN-{seq}",
        payload=payload,
        prev_hash=prev_hash,
        current_hash=tampered_current_hash or real_hash,
        created_at=created_at,
    )


def test_verify_healthy_chain_succeeds():
    db = MagicMock()

    # Build 3 valid linked events
    e1 = make_mock_event(1, "0" * 64)
    e2 = make_mock_event(2, e1.current_hash)
    e3 = make_mock_event(3, e2.current_hash)

    head = AuditChainHead(id=1, sequence_number=3, current_hash=e3.current_hash, updated_at=e3.created_at)

    db.execute.return_value.mappings.return_value.one.return_value = {
        "sequence_number": 3,
        "current_hash": e3.current_hash,
    }
    db.scalars.return_value = [e1, e2, e3]

    res = audit_service.verify_chain(db)
    assert res.is_valid is True
    assert res.total_events == 3
    assert res.head_sequence == 3
    assert res.head_hash == e3.current_hash
    assert res.tamper_details is None


def test_verify_detects_hash_mismatch():
    db = MagicMock()

    e1 = make_mock_event(1, "0" * 64)
    # Tamper with e1 payload without recalculating current_hash
    tampered_e1 = AuditEvent(
        id=e1.id,
        sequence_number=e1.sequence_number,
        event_type=e1.event_type,
        actor_id=e1.actor_id,
        actor_role=e1.actor_role,
        entity_type=e1.entity_type,
        entity_id=e1.entity_id,
        payload={"amount": "999.00"},  # Tampered
        prev_hash=e1.prev_hash,
        current_hash=e1.current_hash,  # Old hash!
        created_at=e1.created_at,
    )

    db.execute.return_value.mappings.return_value.one.return_value = {
        "sequence_number": 1,
        "current_hash": e1.current_hash,
    }
    db.scalars.return_value = [tampered_e1]

    res = audit_service.verify_chain(db)
    assert res.is_valid is False
    assert res.tamper_details is not None
    assert res.tamper_details.failure_type == TamperFailureType.HASH_MISMATCH
    assert res.tamper_details.sequence_number == 1


def test_verify_detects_broken_chain():
    db = MagicMock()

    e1 = make_mock_event(1, "0" * 64)
    # e2 has a forged or invalid prev_hash
    forged_prev_hash = "f" * 64
    e2 = make_mock_event(2, forged_prev_hash)

    db.execute.return_value.mappings.return_value.one.return_value = {
        "sequence_number": 2,
        "current_hash": e2.current_hash,
    }
    db.scalars.return_value = [e1, e2]

    res = audit_service.verify_chain(db)
    assert res.is_valid is False
    assert res.tamper_details is not None
    assert res.tamper_details.failure_type == TamperFailureType.BROKEN_CHAIN
    assert res.tamper_details.sequence_number == 2


def test_verify_detects_sequence_gap():
    db = MagicMock()

    e1 = make_mock_event(1, "0" * 64)
    # Event 2 was deleted, so e3 with sequence 3 appears next
    e3 = make_mock_event(3, e1.current_hash)

    db.execute.return_value.mappings.return_value.one.return_value = {
        "sequence_number": 3,
        "current_hash": e3.current_hash,
    }
    db.scalars.return_value = [e1, e3]

    res = audit_service.verify_chain(db)
    assert res.is_valid is False
    assert res.tamper_details is not None
    assert res.tamper_details.failure_type == TamperFailureType.SEQUENCE_GAP
    assert res.tamper_details.sequence_number == 2


def test_verify_detects_head_desync():
    db = MagicMock()

    e1 = make_mock_event(1, "0" * 64)
    # Head sequence is 2, but only 1 event exists
    db.execute.return_value.mappings.return_value.one.return_value = {
        "sequence_number": 2,
        "current_hash": e1.current_hash,
    }
    db.scalars.return_value = [e1]

    res = audit_service.verify_chain(db)
    assert res.is_valid is False
    assert res.tamper_details is not None
    assert res.tamper_details.failure_type == TamperFailureType.HEAD_DESYNC
