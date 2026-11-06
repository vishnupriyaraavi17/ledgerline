import pytest
from backend.app.security.passwords import (
    hash_password,
    verify_password,
    is_argon2_hash,
)


def test_hash_password_produces_argon2id():
    raw = "MySuperSecretPass123!"
    hashed = hash_password(raw)
    assert hashed.startswith("$argon2id$")
    assert is_argon2_hash(hashed) is True


def test_verify_password_correct():
    raw = "ValidPassword_2026!"
    hashed = hash_password(raw)
    assert verify_password(raw, hashed) is True


def test_verify_password_incorrect():
    raw = "CorrectPassword_123!"
    wrong = "WrongPassword_999!"
    hashed = hash_password(raw)
    assert verify_password(wrong, hashed) is False


def test_hash_password_is_salted_and_randomized():
    raw = "SamePasswordTwice"
    hash1 = hash_password(raw)
    hash2 = hash_password(raw)
    assert hash1 != hash2
    assert verify_password(raw, hash1) is True
    assert verify_password(raw, hash2) is True


def test_verify_password_handles_malformed_hash_gracefully():
    assert verify_password("test", "not_a_valid_argon2_hash") is False
    assert verify_password("test", "") is False
    assert verify_password("test", "$pbkdf2$invalid") is False
