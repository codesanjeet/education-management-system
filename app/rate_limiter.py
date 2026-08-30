

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable

from fastapi import HTTPException, Request, status


class RateLimiter:
    """
    Sliding-window rate limiter.

    Parameters
    ----------
    max_calls       : maximum number of calls allowed per key in the window
    window_seconds  : length of the sliding window in seconds
    key_func        : callable(Request) → str  — how to derive a bucket key
                      defaults to IP address
    """

    def __init__(
        self,
        max_calls: int,
        window_seconds: int,
        key_func: Callable[[Request], str] | None = None,
    ) -> None:
        if max_calls < 1:
            raise ValueError("max_calls must be >= 1")
        if window_seconds < 1:
            raise ValueError("window_seconds must be >= 1")

        self.max_calls      = max_calls
        self.window_seconds = window_seconds
        self.key_func       = key_func or _default_key

        # {key: deque of call timestamps (float, monotonic)}
        self._buckets: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    # ── Public API ─────────────────────────────────────────────────────────────

    def check(self, request: Request, key: str | None = None) -> None:
        """
        Record a call and raise HTTP 429 if the rate limit is exceeded.

        Parameters
        ----------
        request : FastAPI Request object (used to derive the key when key=None)
        key     : explicit bucket key — pass current_user.id (as str) for
                  per-user limiting instead of per-IP limiting
        """
        bucket_key = key if key is not None else self.key_func(request)
        now        = time.monotonic()
        cutoff     = now - self.window_seconds

        with self._lock:
            dq = self._buckets.get(bucket_key)
            if dq is None:
                dq = deque()
                self._buckets[bucket_key] = dq

            # Evict timestamps outside the window
            while dq and dq[0] <= cutoff:
                dq.popleft()

            if len(dq) >= self.max_calls:
                # Calculate how many seconds until the oldest call falls out
                retry_after = max(1, int(dq[0] - cutoff) + 1)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=(
                        f"Rate limit exceeded: {self.max_calls} requests "
                        f"per {self.window_seconds}s. "
                        f"Retry after {retry_after}s."
                    ),
                    headers={"Retry-After": str(retry_after)},
                )

            dq.append(now)

            # Opportunistic full cleanup: remove keys whose deques are empty
            # (only when bucket count is large to avoid doing it every call)
            if len(self._buckets) > 1000:
                self._buckets = {k: v for k, v in self._buckets.items() if v}

    def is_allowed(self, request: Request, key: str | None = None) -> bool:
        """
        Non-raising variant — returns False instead of raising 429.
        Useful for conditional logic; does NOT record the call.
        """
        bucket_key = key if key is not None else self.key_func(request)
        now        = time.monotonic()
        cutoff     = now - self.window_seconds

        with self._lock:
            dq = self._buckets.get(bucket_key)
            if dq is None:
                return True
            # Count without mutating
            count = sum(1 for ts in dq if ts > cutoff)
            return count < self.max_calls


# ── Default key extractor ──────────────────────────────────────────────────────

def _default_key(request: Request) -> str:
    """
    Use X-Forwarded-For (first hop) when behind a reverse proxy,
    otherwise fall back to the direct client IP.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def user_id_key(user_id: int | str) -> str:
    """
    Convenience helper: build a per-user key to pass as key= in check().

    Example
    -------
        upload_limiter.check(request, key=user_id_key(current_user.id))
    """
    return f"uid:{user_id}"