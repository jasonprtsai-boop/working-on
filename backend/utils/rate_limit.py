from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass


@dataclass
class RateLimitExceeded(Exception):
    retry_after_seconds: int


class FixedWindowRateLimiter:
    def __init__(self, *, max_buckets: int = 10000):
        self._lock = threading.RLock()
        self._buckets: dict[str, tuple[float, int]] = {}
        self._max_buckets = max(1, int(max_buckets))
        self._last_prune = 0.0

    def check(self, key: str, limit: int, window_seconds: float = 60.0) -> None:
        if limit <= 0:
            return

        now = time.monotonic()
        window_seconds = max(1.0, float(window_seconds))
        with self._lock:
            self._prune_expired(now, window_seconds)
            window_start, count = self._buckets.get(key, (now, 0))
            if now - window_start >= window_seconds:
                window_start, count = now, 0

            if count >= limit:
                retry_after = max(1, math.ceil(window_seconds - (now - window_start)))
                raise RateLimitExceeded(retry_after_seconds=retry_after)

            self._buckets[key] = (window_start, count + 1)
            if len(self._buckets) > self._max_buckets:
                self._prune_oldest(len(self._buckets) - self._max_buckets)

    def _prune_expired(self, now: float, window_seconds: float) -> None:
        if now - self._last_prune < min(window_seconds, 60.0):
            return
        expired_before = now - window_seconds
        self._buckets = {
            key: value for key, value in self._buckets.items()
            if value[0] >= expired_before
        }
        self._last_prune = now

    def _prune_oldest(self, count: int) -> None:
        if count <= 0:
            return
        oldest_keys = sorted(self._buckets, key=lambda item: self._buckets[item][0])[:count]
        for key in oldest_keys:
            self._buckets.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._buckets.clear()
            self._last_prune = 0.0

    def bucket_count(self) -> int:
        with self._lock:
            return len(self._buckets)


rate_limiter = FixedWindowRateLimiter()
