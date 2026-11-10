import uuid
from fastapi.testclient import TestClient
import pytest
from unittest.mock import MagicMock
from redis.exceptions import ConnectionError

from backend.app.security.rate_limiter import registration_limiter
from backend.app.core.redis import set_redis_client, get_redis_client


def test_registration_distributed_rate_limiting_with_forwarded_headers(client: TestClient):
    """
    Verifies that requests from a specific client IP (via X-Forwarded-For)
    are tracked and limited independently by the Redis rate limiter.
    """
    orig_limit = registration_limiter.requests_limit
    orig_window = registration_limiter.window_seconds
    registration_limiter.requests_limit = 2
    registration_limiter.window_seconds = 60

    client_ip_a = "198.51.100.1"
    client_ip_b = "198.51.100.2"

    try:
        # Client A sends 2 requests (allowed)
        for _ in range(2):
            uid = uuid.uuid4().hex[:6]
            res = client.post(
                "/api/v1/auth/register",
                headers={"x-forwarded-for": client_ip_a},
                json={"username": f"user_a_{uid}", "email": f"user_a_{uid}@example.com", "password": "SecurePassword123!"},
            )
            assert res.status_code == 201

        # Client A 3rd request -> blocked (429)
        blocked_a = client.post(
            "/api/v1/auth/register",
            headers={"x-forwarded-for": client_ip_a},
            json={"username": "blocked_a", "email": "blocked_a@example.com", "password": "SecurePassword123!"},
        )
        assert blocked_a.status_code == 429
        assert "Retry-After" in blocked_a.headers

        # Client B sends a request -> should be admitted (distinct IP tracking)
        uid_b = uuid.uuid4().hex[:6]
        res_b = client.post(
            "/api/v1/auth/register",
            headers={"x-forwarded-for": client_ip_b},
            json={"username": f"user_b_{uid_b}", "email": f"user_b_{uid_b}@example.com", "password": "SecurePassword123!"},
        )
        assert res_b.status_code == 201
    finally:
        registration_limiter.requests_limit = orig_limit
        registration_limiter.window_seconds = orig_window


def test_registration_fails_closed_when_redis_offline(client: TestClient):
    """
    Verifies that when Redis is offline or throws an error,
    the registration endpoint returns HTTP 503 and does NOT bypass rate limiting.
    """
    failing_redis = MagicMock()
    failing_redis.eval.side_effect = ConnectionError("Redis server unreachable")

    original_client = get_redis_client()
    set_redis_client(failing_redis)

    try:
        res = client.post(
            "/api/v1/auth/register",
            json={"username": "test_offline", "email": "offline@example.com", "password": "SecurePassword123!"},
        )
        assert res.status_code == 503
        data = res.json()
        assert "Registration service temporarily unavailable due to rate limiter outage" in data["detail"]
        assert "Retry-After" in res.headers
    finally:
        set_redis_client(original_client)
