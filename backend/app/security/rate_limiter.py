import logging
import time
import uuid
from typing import Optional
from fastapi import HTTPException, Request, status
import redis
from redis.exceptions import ConnectionError, RedisError, TimeoutError

from backend.app.core.redis import get_redis_client

logger = logging.getLogger(__name__)

# Atomic sliding-window rate limiter evaluated inside Redis via Lua
SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member_id = ARGV[4]

local window_start = now - window

-- 1. Remove entries outside the current sliding window
redis.call('ZREMRANGEBYSCORE', key, '-inf', '(' .. window_start)

-- 2. Count current active requests in window
local current_count = redis.call('ZCARD', key)

if current_count < limit then
    -- 3. Record new request timestamp with unique member ID
    redis.call('ZADD', key, now, member_id)
    -- Set TTL to prevent unbounded memory growth
    redis.call('EXPIRE', key, math.ceil(window) + 2)
    local remaining = limit - current_count - 1
    return {1, remaining, 0}
else
    -- 4. Exceeded: calculate Retry-After based on oldest record in window
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry_after = 1
    if #oldest >= 2 then
        local oldest_score = tonumber(oldest[2])
        local wait_time = math.ceil(oldest_score + window - now)
        if wait_time > 1 then
            retry_after = wait_time
        end
    end
    return {0, 0, retry_after}
end
"""


def get_client_ip(request: Request) -> str:
    """
    Safely resolves client IP address.
    Checks X-Forwarded-For and X-Real-IP when behind reverse proxies,
    falling back to request.client.host.
    """
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        # Standard X-Forwarded-For: client, proxy1, proxy2 ...
        first_ip = forwarded_for.split(",")[0].strip()
        if first_ip:
            return first_ip

    real_ip = request.headers.get("x-real-ip")
    if real_ip and real_ip.strip():
        return real_ip.strip()

    if request.client and request.client.host:
        return request.client.host

    return "unknown"


class RedisRateLimiter:
    """
    Distributed sliding-window rate limiter backed by Redis.
    Uses atomic Lua script execution to prevent race conditions across concurrent processes.
    Fails closed (HTTP 503) if Redis is unavailable to prevent rate-limiting bypass.
    """

    def __init__(
        self,
        requests_limit: int = 10,
        window_seconds: int = 60,
        prefix: str = "register",
        redis_client: Optional[redis.Redis] = None,
    ):
        self.requests_limit = requests_limit
        self.window_seconds = window_seconds
        self.prefix = prefix
        self._redis_client = redis_client
        self._lua_script = None

    @property
    def client(self) -> redis.Redis:
        if self._redis_client is not None:
            return self._redis_client
        return get_redis_client()

    def __call__(self, request: Request) -> None:
        self.check(request)

    def check(self, request: Request) -> None:
        client_ip = get_client_ip(request)
        key = f"ratelimit:{self.prefix}:{client_ip}"
        now = time.time()
        member_id = f"{now}:{uuid.uuid4().hex}"

        try:
            r = self.client
            # Evaluate atomic Lua script
            result = r.eval(
                SLIDING_WINDOW_LUA,
                1,
                key,
                now,
                self.window_seconds,
                self.requests_limit,
                member_id,
            )
        except (RedisError, ConnectionError, TimeoutError, OSError) as exc:
            # Security fail-closed guard: Never silently bypass rate limiting or fall back to in-memory
            logger.error(f"Rate limiting check failed due to Redis outage: {type(exc).__name__}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Registration service temporarily unavailable due to rate limiter outage. Please try again later.",
                headers={"Retry-After": "30"},
            )

        allowed, remaining, retry_after = result[0], result[1], result[2]

        if not allowed:
            retry_seconds = max(1, int(retry_after))
            logger.warning(
                f"Rate limit exceeded for IP '{client_ip}' on prefix '{self.prefix}'. "
                f"Limit: {self.requests_limit}/{self.window_seconds}s. Retry-After: {retry_seconds}s."
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many registration attempts. Please try again later.",
                headers={"Retry-After": str(retry_seconds)},
            )

    def reset(self, ip: Optional[str] = None) -> None:
        """
        Clears rate limit keys for a specific IP or all keys for this prefix.
        Primarily utilized in automated testing suites.
        """
        try:
            r = self.client
            if ip:
                r.delete(f"ratelimit:{self.prefix}:{ip}")
            else:
                pattern = f"ratelimit:{self.prefix}:*"
                keys = r.keys(pattern)
                if keys:
                    r.delete(*keys)
        except Exception as exc:
            logger.warning(f"Error resetting rate limit keys: {type(exc).__name__}")


# Canonical registration limiter: 10 attempts per 60 seconds
registration_limiter = RedisRateLimiter(
    requests_limit=10,
    window_seconds=60,
    prefix="register",
)
