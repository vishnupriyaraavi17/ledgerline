from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import jwt
from backend.app.core.config import settings


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Creates a signed HS256 JWT access token.
    """
    to_encode = data.copy()
    now = datetime.now(timezone.utc)

    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({
        "exp": expire,
        "iat": now,
    })

    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def decode_access_token(token: str) -> Dict[str, Any]:
    """
    Decodes and validates the signature and expiration of an access token.
    Raises jwt.PyJWTError on invalid, tampered, or expired tokens.
    """
    payload = jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM]
    )
    return payload


def create_refresh_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Creates a signed HS256 JWT refresh token scoped strictly with type='refresh'.
    """
    to_encode = data.copy()
    now = datetime.now(timezone.utc)

    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode.update({
        "exp": expire,
        "iat": now,
        "type": "refresh",
    })

    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def decode_refresh_token(token: str) -> Dict[str, Any]:
    """
    Decodes and validates a refresh token.
    Strictly asserts that token type equals 'refresh'.
    Raises jwt.PyJWTError on invalid, tampered, expired, or non-refresh tokens.
    """
    payload = jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM]
    )
    if payload.get("type") != "refresh":
        raise jwt.InvalidTokenError("Token is not a valid refresh token")
    return payload
