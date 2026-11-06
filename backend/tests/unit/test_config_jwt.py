import pytest
from pydantic import ValidationError
from backend.app.core.config import Settings


def test_jwt_secret_validation_rejects_empty():
    with pytest.raises(ValidationError) as exc_info:
        Settings(JWT_SECRET_KEY="")
    errors = exc_info.value.errors()
    assert any("JWT_SECRET_KEY" in str(e) for e in errors)


def test_jwt_secret_validation_rejects_short_secret():
    with pytest.raises(ValidationError) as exc_info:
        Settings(JWT_SECRET_KEY="short-secret-key-too-weak")
    errors = exc_info.value.errors()
    assert any("at least 32 characters" in str(e) for e in errors)


def test_jwt_secret_validation_accepts_valid_length():
    valid_secret = "a" * 32
    s = Settings(JWT_SECRET_KEY=valid_secret)
    assert s.JWT_SECRET_KEY == valid_secret
