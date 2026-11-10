import time
from collections import defaultdict
from threading import Lock
from typing import Dict, List
from fastapi import HTTPException, Request, status


class InMemoryRateLimiter:
    """
    Thread-safe in-memory sliding-window rate limiter for sensitive endpoints.
    Protects registration and authentication endpoints from abuse.
    """

    def __init__(self, requests_limit: int = 5, window_seconds: int = 300):
        self.requests_limit = requests_limit
        self.window_seconds = window_seconds
        self._records: Dict[str, List[float]] = defaultdict(list)
        self._lock = Lock()

    def __call__(self, request: Request) -> None:
        self.check(request)

    def check(self, request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window_start = now - self.window_seconds

        with self._lock:
            # Filter timestamps to within the current sliding window
            valid_timestamps = [ts for ts in self._records[client_ip] if ts > window_start]
            if len(valid_timestamps) >= self.requests_limit:
                retry_after = int(valid_timestamps[0] + self.window_seconds - now) + 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many registration attempts. Please try again later.",
                    headers={"Retry-After": str(max(1, retry_after))},
                )
            valid_timestamps.append(now)
            self._records[client_ip] = valid_timestamps

    def reset(self) -> None:
        """Reset all rate limit tracking (primarily for test suites)."""
        with self._lock:
            self._records.clear()


registration_limiter = InMemoryRateLimiter(requests_limit=10, window_seconds=60)
