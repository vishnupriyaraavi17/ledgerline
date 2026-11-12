from datetime import timedelta
import pytest
import jwt
from backend.app.security.tokens import create_access_token, decode_access_token
from backend.app.core.config import settings


def test_create_and_decode_access_token():
    payload = {
        "sub": "498b4448-b5ab-40ab-9a28-c7b9347860db",
        "username": "admin",
        "email": "admin@ledgerline.internal",
        "role": "admin",
    }
    token = create_access_token(payload)
    assert isinstance(token, str)
    assert len(token.split(".")) == 3

    decoded = decode_access_token(token)
    assert decoded["sub"] == payload["sub"]
    assert decoded["username"] == "admin"
    assert decoded["email"] == "admin@ledgerline.internal"
    assert decoded["role"] == "admin"
    assert "exp" in decoded
    assert "iat" in decoded


def test_expired_token_raises_expired_signature_error():
    payload = {"sub": "user-123"}
    # Token expired 10 minutes ago
    expired_token = create_access_token(payload, expires_delta=timedelta(minutes=-10))

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(expired_token)


def test_tampered_token_signature_fails():
    payload = {"sub": "user-123", "role": "account_holder"}
    token = create_access_token(payload)

    parts = token.split(".")
    # Tamper with the payload part
    tampered_token = f"{parts[0]}.eyJhZG1pbiI6IHRydWV9.{parts[2]}"

    with pytest.raises(jwt.PyJWTError):
        decode_access_token(tampered_token)


def test_token_with_wrong_secret_fails():
    payload = {"sub": "user-123"}
    foreign_token = jwt.encode(payload, "a" * 32, algorithm="HS256")

    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(foreign_token)


def test_create_and_decode_refresh_token():
    payload = {
        "sub": "498b4448-b5ab-40ab-9a28-c7b9347860db",
        "role": "admin",
        "jti": "random-uuid-1234",
    }
    from backend.app.security.tokens import create_refresh_token, decode_refresh_token
    token = create_refresh_token(payload)
    assert isinstance(token, str)

    decoded = decode_refresh_token(token)
    assert decoded["sub"] == payload["sub"]
    assert decoded["role"] == "admin"
    assert decoded["jti"] == "random-uuid-1234"
    assert decoded["type"] == "refresh"


def test_access_token_rejected_by_decode_refresh_token():
    from backend.app.security.tokens import create_access_token, decode_refresh_token
    access_token = create_access_token({"sub": "user-123", "role": "admin"})

    with pytest.raises(jwt.InvalidTokenError, match="Token is not a valid refresh token"):
        decode_refresh_token(access_token)


def test_expired_refresh_token_fails():
    from backend.app.security.tokens import create_refresh_token, decode_refresh_token
    expired = create_refresh_token({"sub": "user-123", "role": "admin"}, expires_delta=timedelta(days=-1))

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_refresh_token(expired)
