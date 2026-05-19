from __future__ import annotations

import copy
import threading
import time
from typing import Any


class IdempotencyStore:
    def __init__(self, *, clock=time.time):
        self._clock = clock
        self._records: dict[str, tuple[float, dict[str, Any], int]] = {}
        self._lock = threading.RLock()

    def get(self, key: str | None) -> tuple[dict[str, Any], int] | None:
        if not key:
            return None
        now = self._clock()
        with self._lock:
            self._purge_expired_locked(now)
            record = self._records.get(str(key))
            if not record:
                return None
            _expires_at, payload, status = record
            return copy.deepcopy(payload), status

    def save(self, key: str | None, payload: dict[str, Any], status: int = 200, *, ttl_seconds: int = 300) -> None:
        if not key:
            return
        expires_at = self._clock() + max(1, int(ttl_seconds or 300))
        with self._lock:
            self._purge_expired_locked(self._clock())
            self._records[str(key)] = (expires_at, copy.deepcopy(payload), int(status))

    def clear(self) -> None:
        with self._lock:
            self._records.clear()

    def _purge_expired_locked(self, now: float) -> None:
        expired = [key for key, (expires_at, _payload, _status) in self._records.items() if expires_at <= now]
        for key in expired:
            self._records.pop(key, None)


idempotency_store = IdempotencyStore()
