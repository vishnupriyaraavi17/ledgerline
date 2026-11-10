import concurrent.futures
import time
from unittest.mock import MagicMock
import fakeredis
from fastapi import HTTPException, Request, status
import pytest
from redis.exceptions import ConnectionError, RedisError, TimeoutError

from backend.app.security.rate_limiter import (
    RedisRateLimiter,
    get_client_ip,
)


def create_mock_request(
    client_ip: str = "192.168.1.100",
    headers: dict = None,
) -> Request:
    """Helper to construct dummy Request with specified client and headers."""
    scope = {
        "type": "http",
        "client": (client_ip, 50000),
        "headers": [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in (headers or {}).items()] if isinstance(headers, dict) else [],
    }
    return Request(scope)


def test_rate_limiter_allowed_within_limit():
    """Verifies that requests within the allowed threshold (e.g. 5) pass cleanly."""
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    limiter = RedisRateLimiter(requests_limit=5, window_seconds=60, prefix="test_allow", redis_client=fake_redis)

    req = create_mock_request("10.0.0.1")
    for _ in range(5):
        # Should not raise
        limiter.check(req)


def test_rate_limiter_blocks_when_limit_exceeded_with_retry_after():
    """Verifies that exceeding the limit raises HTTP 429 with Retry-After header."""
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    limiter = RedisRateLimiter(requests_limit=3, window_seconds=30, prefix="test_exceed", redis_client=fake_redis)

    req = create_mock_request("10.0.0.2")
    for _ in range(3):
        limiter.check(req)

    # 4th request must be rejected
    with pytest.raises(HTTPException) as exc_info:
        limiter.check(req)

    assert exc_info.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert "Too many registration attempts" in exc_info.value.detail
    assert "Retry-After" in exc_info.value.headers
    retry_after = int(exc_info.value.headers["Retry-After"])
    assert 1 <= retry_after <= 30


def test_rate_limiter_sliding_window_expiry():
    """Verifies that requests outside the sliding window expire and permit new requests."""
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    # 2 requests per 2 seconds
    limiter = RedisRateLimiter(requests_limit=2, window_seconds=2, prefix="test_expire", redis_client=fake_redis)

    req = create_mock_request("10.0.0.3")
    limiter.check(req)
    limiter.check(req)

    with pytest.raises(HTTPException) as exc_info:
        limiter.check(req)
    assert exc_info.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    # Wait for the sliding window to clear
    time.sleep(2.1)

    # Should now succeed again
    limiter.check(req)


def test_rate_limiter_concurrent_requests_atomic_safety():
    """
    Spawns 20 concurrent threads attempting to consume a limit of 5.
    Guarantees exactly 5 succeed and 15 are blocked with HTTP 429,
    proving race condition resistance through atomic Lua execution.
    """
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    limiter = RedisRateLimiter(requests_limit=5, window_seconds=60, prefix="test_concurrency", redis_client=fake_redis)

    req = create_mock_request("10.0.0.4")

    successes = 0
    rejections = 0

    def attempt_request():
        nonlocal successes, rejections
        try:
            limiter.check(req)
            return True
        except HTTPException as exc:
            if exc.status_code == 429:
                return False
            raise

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(attempt_request) for _ in range(20)]
        for f in concurrent.futures.as_completed(futures):
            if f.result() is True:
                successes += 1
            else:
                rejections += 1

    assert successes == 5
    assert rejections == 15


def test_rate_limiter_client_ip_resolution_and_forwarded_headers():
    """Tests safe IP resolution from various headers and direct connections."""
    # 1. Direct host
    req1 = create_mock_request("192.168.1.50")
    assert get_client_ip(req1) == "192.168.1.50"

    # 2. X-Forwarded-For with multiple proxies (leftmost is original client)
    req2 = create_mock_request(
        "127.0.0.1",
        headers={"x-forwarded-for": "203.0.113.195, 70.41.3.18, 150.172.238.178"},
    )
    assert get_client_ip(req2) == "203.0.113.195"

    # 3. X-Real-IP fallback
    req3 = create_mock_request(
        "127.0.0.1",
        headers={"x-real-ip": "198.51.100.42"},
    )
    assert get_client_ip(req3) == "198.51.100.42"

    # 4. Unknown when client and headers are absent
    req4 = Request({"type": "http", "headers": []})
    assert get_client_ip(req4) == "unknown"


def test_rate_limiter_redis_unavailability_fails_closed():
    """
    CRITICAL SECURITY TEST:
    Verifies that when Redis experiences an outage, the rate limiter fails CLOSED:
    it raises HTTP 503 and does NOT silently bypass rate limiting or allow unauthorized flooding.
    """
    mock_failing_redis = MagicMock()
    mock_failing_redis.eval.side_effect = ConnectionError("Could not connect to Redis at 127.0.0.1:6379")

    limiter = RedisRateLimiter(requests_limit=10, window_seconds=60, prefix="test_fail_closed", redis_client=mock_failing_redis)
    req = create_mock_request("10.0.0.5")

    with pytest.raises(HTTPException) as exc_info:
        limiter.check(req)

    assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert "Registration service temporarily unavailable due to rate limiter outage" in exc_info.value.detail
    assert "Retry-After" in exc_info.value.headers
    # Verify no raw redis connection details/passwords leaked in error message
    assert "127.0.0.1:6379" not in exc_info.value.detail


def test_rate_limiter_reset():
    """Verifies reset cleans up redis keys."""
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    limiter = RedisRateLimiter(requests_limit=1, window_seconds=60, prefix="test_reset", redis_client=fake_redis)

    req = create_mock_request("10.0.0.6")
    limiter.check(req)

    with pytest.raises(HTTPException):
        limiter.check(req)

    # Reset keys for this IP
    limiter.reset("10.0.0.6")

    # Should now pass
    limiter.check(req)
