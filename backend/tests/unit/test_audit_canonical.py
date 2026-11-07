import uuid
from datetime import datetime, timezone
from decimal import Decimal
import pytest

from backend.app.repositories.audit import (
    canonicalize_payload,
    normalize_timestamp,
    AuditRepository,
)


def test_canonical_serialization_deterministic_key_ordering():
    account_id = uuid.uuid4()
    payload_a = {
        "z_field": "last",
        "a_field": "first",
        "nested": {"beta": 2, "alpha": 1},
        "account_id": account_id,
    }
    payload_b = {
        "account_id": account_id,
        "nested": {"alpha": 1, "beta": 2},
        "a_field": "first",
        "z_field": "last",
    }

    norm_a = canonicalize_payload(payload_a)
    norm_b = canonicalize_payload(payload_b)

    dt = datetime(2026, 11, 7, 12, 0, 0, 123456, tzinfo=timezone.utc)
    hash_a, _ = AuditRepository.compute_event_hash(
        sequence_number=1,
        prev_hash="0" * 64,
        event_type="test.event",
        actor_id=None,
        actor_role=None,
        entity_type="test",
        entity_id="123",
        payload=norm_a,
        created_at=dt,
    )
    hash_b, _ = AuditRepository.compute_event_hash(
        sequence_number=1,
        prev_hash="0" * 64,
        event_type="test.event",
        actor_id=None,
        actor_role=None,
        entity_type="test",
        entity_id="123",
        payload=norm_b,
        created_at=dt,
    )

    assert hash_a == hash_b
    assert len(hash_a) == 64


def test_canonical_serialization_nested_structures():
    payload = {
        "list_field": [3, 1, 2],
        "nested_dict": {"x": Decimal("10.50"), "y": None},
        "flag_true": True,
        "flag_false": False,
    }
    normalized = canonicalize_payload(payload)

    # Lists preserve order
    assert normalized["list_field"] == [3, 1, 2]
    # Nested Decimal is stringified to 2 decimals
    assert normalized["nested_dict"]["x"] == "10.50"
    # None is preserved as None
    assert normalized["nested_dict"]["y"] is None
    # Booleans are preserved
    assert normalized["flag_true"] is True
    assert normalized["flag_false"] is False


def test_canonical_serialization_decimal_precision():
    payload_1 = {"amount": Decimal("100")}
    payload_2 = {"amount": Decimal("100.00")}

    norm_1 = canonicalize_payload(payload_1)
    norm_2 = canonicalize_payload(payload_2)

    assert norm_1["amount"] == "100.00"
    assert norm_2["amount"] == "100.00"
    assert norm_1 == norm_2


def test_canonical_serialization_whitespace_sensitive():
    dt = datetime(2026, 11, 7, 12, 0, 0, 0, tzinfo=timezone.utc)
    payload_1 = {"memo": "Payment"}
    payload_2 = {"memo": "Payment "}
    payload_3 = {"memo": " Payment"}

    h1, _ = AuditRepository.compute_event_hash(1, "0" * 64, "t", None, None, "e", "1", payload_1, dt)
    h2, _ = AuditRepository.compute_event_hash(1, "0" * 64, "t", None, None, "e", "1", payload_2, dt)
    h3, _ = AuditRepository.compute_event_hash(1, "0" * 64, "t", None, None, "e", "1", payload_3, dt)

    assert h1 != h2
    assert h1 != h3
    assert h2 != h3


def test_canonical_serialization_microsecond_timestamp():
    dt1 = datetime(2026, 11, 7, 12, 0, 0, 123456, tzinfo=timezone.utc)
    dt2 = datetime(2026, 11, 7, 12, 0, 0, 123457, tzinfo=timezone.utc)

    ts1 = normalize_timestamp(dt1)
    ts2 = normalize_timestamp(dt2)

    assert ts1 == "2026-11-07T12:00:00.123456Z"
    assert ts2 == "2026-11-07T12:00:00.123457Z"
    assert ts1 != ts2


def test_canonical_serialization_rejects_naive_timestamp():
    naive_dt = datetime(2026, 11, 7, 12, 0, 0)
    with pytest.raises(ValueError, match="Timezone-naive timestamps are strictly prohibited"):
        normalize_timestamp(naive_dt)

    with pytest.raises(ValueError, match="Timezone-naive timestamps are strictly prohibited"):
        AuditRepository.append_event(
            db=None,  # type: ignore
            event_type="test",
            actor_id=None,
            actor_role=None,
            entity_type="test",
            entity_id="1",
            payload={},
            timestamp=naive_dt,
        )


def test_audit_hash_chain_genesis_formula():
    dt = datetime(2026, 11, 7, 0, 0, 0, 0, tzinfo=timezone.utc)
    genesis_prev_hash = "0" * 64

    h1, _ = AuditRepository.compute_event_hash(
        sequence_number=1,
        prev_hash=genesis_prev_hash,
        event_type="test.genesis",
        actor_id=None,
        actor_role=None,
        entity_type="system",
        entity_id="0",
        payload={"msg": "first"},
        created_at=dt,
    )

    assert len(h1) == 64
    assert h1 != genesis_prev_hash
