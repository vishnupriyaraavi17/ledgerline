import pytest
from fastapi import HTTPException
from backend.app.api.v1.endpoints.transfers import validate_idempotency_key


def test_validate_idempotency_key_valid():
    """
    Valid ASCII keys between 8 and 128 characters without whitespace are accepted.
    """
    key = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    assert validate_idempotency_key(key) == key

    short_valid = "12345678"
    assert validate_idempotency_key(short_valid) == short_valid

    long_valid = "x" * 128
    assert validate_idempotency_key(long_valid) == long_valid


def test_validate_idempotency_key_missing_or_empty():
    """
    Missing, None, or whitespace-only keys raise HTTP 400 Bad Request.
    """
    with pytest.raises(HTTPException) as exc_none:
        validate_idempotency_key(None)
    assert exc_none.value.status_code == 400
    assert "required" in exc_none.value.detail

    with pytest.raises(HTTPException) as exc_empty:
        validate_idempotency_key("")
    assert exc_empty.value.status_code == 400

    with pytest.raises(HTTPException) as exc_ws:
        validate_idempotency_key("   ")
    assert exc_ws.value.status_code == 400


def test_validate_idempotency_key_length_boundaries():
    """
    Keys shorter than 8 characters or longer than 128 characters raise HTTP 400.
    """
    with pytest.raises(HTTPException) as exc_short:
        validate_idempotency_key("1234567")
    assert exc_short.value.status_code == 400
    assert "between 8 and 128" in exc_short.value.detail

    with pytest.raises(HTTPException) as exc_long:
        validate_idempotency_key("a" * 129)
    assert exc_long.value.status_code == 400
    assert "between 8 and 128" in exc_long.value.detail


def test_validate_idempotency_key_invalid_characters():
    """
    Keys with spaces, newlines, control characters, or non-ASCII characters raise HTTP 400.
    """
    with pytest.raises(HTTPException) as exc_space:
        validate_idempotency_key("validkey with spaces")
    assert exc_space.value.status_code == 400
    assert "printable ASCII" in exc_space.value.detail

    with pytest.raises(HTTPException) as exc_unicode:
        validate_idempotency_key("idempotency-key-₹-100")
    assert exc_unicode.value.status_code == 400
    assert "printable ASCII" in exc_unicode.value.detail

    with pytest.raises(HTTPException) as exc_ctrl:
        validate_idempotency_key("validkey\x00nullbyte")
    assert exc_ctrl.value.status_code == 400
