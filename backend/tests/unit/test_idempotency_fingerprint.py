import uuid
from decimal import Decimal
from backend.app.repositories.idempotency import idempotency_repository


def test_canonical_fingerprint_deterministic_key_ordering():
    """
    Asserts dictionary keys are sorted deterministically so key insertion order
    does not alter the generated SHA-256 digest.
    """
    account_id = uuid.uuid4()
    payload_a = {
        "account_id": account_id,
        "amount": Decimal("250.00"),
        "description": "Salary payment",
    }
    payload_b = {
        "description": "Salary payment",
        "amount": Decimal("250.00"),
        "account_id": account_id,
    }

    hash_a = idempotency_repository.compute_canonical_fingerprint("deposit", payload_a)
    hash_b = idempotency_repository.compute_canonical_fingerprint("deposit", payload_b)

    assert hash_a == hash_b
    assert len(hash_a) == 64


def test_canonical_fingerprint_decimal_paise_normalization():
    """
    Asserts exact Decimal paise normalization (Decimal("100") and Decimal("100.00")
    normalize to the same quantized string representation).
    """
    account_id = uuid.uuid4()
    payload_1 = {"account_id": account_id, "amount": Decimal("100")}
    payload_2 = {"account_id": account_id, "amount": Decimal("100.00")}

    hash_1 = idempotency_repository.compute_canonical_fingerprint("deposit", payload_1)
    hash_2 = idempotency_repository.compute_canonical_fingerprint("deposit", payload_2)

    assert hash_1 == hash_2


def test_canonical_fingerprint_amount_difference_detection():
    """
    Asserts a 1-paise difference produces a completely distinct hash.
    """
    account_id = uuid.uuid4()
    payload_1 = {"account_id": account_id, "amount": Decimal("100.00")}
    payload_2 = {"account_id": account_id, "amount": Decimal("100.01")}

    hash_1 = idempotency_repository.compute_canonical_fingerprint("deposit", payload_1)
    hash_2 = idempotency_repository.compute_canonical_fingerprint("deposit", payload_2)

    assert hash_1 != hash_2


def test_canonical_fingerprint_operation_type_difference():
    """
    Asserts identical payload with different operation types produce different hashes.
    """
    account_id = uuid.uuid4()
    payload = {"account_id": account_id, "amount": Decimal("100.00")}

    hash_dep = idempotency_repository.compute_canonical_fingerprint("deposit", payload)
    hash_wd = idempotency_repository.compute_canonical_fingerprint("withdraw", payload)

    assert hash_dep != hash_wd


def test_canonical_fingerprint_description_whitespace_sensitivity():
    """
    Asserts differences in memo or whitespace produce different hashes
    (e.g., 'Payment' and 'Payment ' produce distinct SHA-256 digests).
    """
    account_id = uuid.uuid4()
    payload_1 = {"account_id": account_id, "amount": Decimal("100.00"), "description": "Payment"}
    payload_2 = {"account_id": account_id, "amount": Decimal("100.00"), "description": "Payment "}
    payload_3 = {"account_id": account_id, "amount": Decimal("100.00"), "description": " Payment"}

    hash_1 = idempotency_repository.compute_canonical_fingerprint("deposit", payload_1)
    hash_2 = idempotency_repository.compute_canonical_fingerprint("deposit", payload_2)
    hash_3 = idempotency_repository.compute_canonical_fingerprint("deposit", payload_3)

    assert hash_1 != hash_2
    assert hash_1 != hash_3
    assert hash_2 != hash_3
