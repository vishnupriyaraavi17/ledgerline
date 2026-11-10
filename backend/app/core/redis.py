import logging
import os
import sys
from threading import Lock
from typing import Optional, Tuple
import redis
from redis.exceptions import ConnectionError, RedisError, TimeoutError

from backend.app.core.config import settings

logger = logging.getLogger(__name__)

_redis_client: Optional[redis.Redis] = None
_redis_pool: Optional[redis.ConnectionPool] = None
_test_redis_client: Optional[redis.Redis] = None
_lock = Lock()


def get_redis_client() -> redis.Redis:
    """
    Returns the thread-safe singleton Redis client.
    Lazily creates the connection pool if not already initialized.
    Under automated test runners (pytest), provides an isolated in-memory fakeredis client
    if an active connection is not explicitly injected.
    """
    global _redis_client, _redis_pool, _test_redis_client
    if _redis_client is not None:
        return _redis_client

    with _lock:
        if _redis_client is not None:
            return _redis_client

        if _test_redis_client is not None:
            _redis_client = _test_redis_client
            return _redis_client

        # If running inside pytest test suite, ensure hermetic in-memory execution
        if "pytest" in sys.modules or os.environ.get("PYTEST_CURRENT_TEST"):
            try:
                import fakeredis
                _redis_client = fakeredis.FakeRedis(decode_responses=True)
                _test_redis_client = _redis_client
                return _redis_client
            except ImportError:
                pass

        logger.info(f"Initializing Redis connection pool to {settings.safe_redis_info}")
        _redis_pool = redis.ConnectionPool.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_timeout=2.0,
            socket_connect_timeout=2.0,
            max_connections=50,
        )
        _redis_client = redis.Redis(connection_pool=_redis_pool)
        return _redis_client


def init_redis() -> Optional[redis.Redis]:
    """
    Explicit lifecycle initialization for application startup.
    Creates connection pool and performs an initial connectivity verification.
    """
    client = get_redis_client()
    try:
        client.ping()
        logger.info(f"[+] Redis connection verified successfully ({settings.safe_redis_info}).")
    except (RedisError, ConnectionError, TimeoutError, OSError) as exc:
        logger.warning(
            f"[-] Redis connection failed during startup initialization ({settings.safe_redis_info}): {type(exc).__name__}. "
            "Application will boot; readiness probe will report degraded status until Redis becomes available."
        )
    return client


def close_redis() -> None:
    """
    Explicit lifecycle shutdown to cleanly disconnect and close Redis connection pools.
    """
    global _redis_client, _redis_pool
    with _lock:
        if _redis_client is not None:
            try:
                _redis_client.close()
            except Exception as exc:
                logger.warning(f"Error closing Redis client: {type(exc).__name__}")
            _redis_client = None

        if _redis_pool is not None:
            try:
                _redis_pool.disconnect()
            except Exception as exc:
                logger.warning(f"Error disconnecting Redis pool: {type(exc).__name__}")
            _redis_pool = None
    logger.info("[-] Redis connections closed.")


def ping_redis(timeout: float = 2.0) -> Tuple[bool, str]:
    """
    Bounded Redis ping check for health and readiness probes.
    Returns (is_connected: bool, sanitized_details: str).
    Guarantees that credentials, connection strings, or internal traces are never exposed.
    """
    try:
        client = get_redis_client()
        alive = bool(client.ping())
        if alive:
            return True, "Redis connection responsive"
        return False, "Redis ping returned unexpected response"
    except (TimeoutError, ConnectionError) as exc:
        logger.error(f"Redis probe failed: {type(exc).__name__}")
        return False, "Redis connection unavailable or timed out"
    except (RedisError, OSError) as exc:
        logger.error(f"Redis probe error: {type(exc).__name__}")
        return False, "Redis service communication failure"
    except Exception as exc:
        logger.error(f"Unexpected Redis check error: {type(exc).__name__}")
        return False, "Internal Redis health check failure"


def set_redis_client(client: Optional[redis.Redis]) -> None:
    """
    Overrides the active Redis client (primarily for test suite isolation e.g. fakeredis or mocks).
    """
    global _redis_client, _test_redis_client
    with _lock:
        _redis_client = client
        _test_redis_client = client
