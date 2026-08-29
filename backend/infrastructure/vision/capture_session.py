from __future__ import annotations

import threading
import time
import uuid
from typing import Any

from backend.events.bus.event_bus import bus
from backend.events.event_types import EventType
from backend.events.models.base_event import BaseEvent
from backend.utils import config
from backend.utils.logger import logger


class VisionCaptureSession:
    """Controls operator-triggered vision recognition rounds."""

    def __init__(self):
        self._lock = threading.RLock()
        self._active = False
        self._session_id = ""
        self._trace_id = ""
        self._source = ""
        self._started_at = None
        self._completed_at = None
        self._interval_sec = self._default_interval_sec()
        self._timeout_sec = self._default_timeout_sec()
        self._attempts = 0
        self._processed_count = 0
        self._last_capture_at = None
        self._last_processed_at = None
        self._last_error = None
        self._last_reason = "idle"
        self._last_result: dict[str, Any] = {}

    def start(
        self,
        *,
        source: str = "operator",
        trace_id: str | None = None,
        interval_sec: float | None = None,
        timeout_sec: float | None = None,
    ) -> dict[str, Any]:
        now = time.time()
        with self._lock:
            self._active = True
            self._session_id = str(uuid.uuid4())
            self._trace_id = str(trace_id or self._session_id)
            self._source = str(source or "operator")
            self._started_at = now
            self._completed_at = None
            self._interval_sec = self._coerce_interval(interval_sec)
            self._timeout_sec = self._coerce_timeout(timeout_sec)
            self._attempts = 0
            self._processed_count = 0
            self._last_capture_at = None
            self._last_processed_at = None
            self._last_error = None
            self._last_reason = "active"
            self._last_result = {}
            logger.info(
                "[VisionCaptureSession] started id=%s interval=%.2fs timeout=%.2fs source=%s",
                self._session_id,
                self._interval_sec,
                self._timeout_sec,
                self._source,
            )
            return self._snapshot_locked(now=now)

    def stop(self, reason: str = "operator_stopped", result: dict[str, Any] | None = None) -> dict[str, Any]:
        now = time.time()
        with self._lock:
            if not self._active:
                return self._snapshot_locked(now=now)
            self._complete_locked(reason=reason, result=result, now=now)
            return self._snapshot_locked(now=now)

    def tick(self, *, now: float | None = None) -> tuple[str, dict[str, Any] | None]:
        current = time.time() if now is None else float(now)
        with self._lock:
            if not self._active:
                return "idle", None

            if self._timed_out_locked(current):
                self._complete_locked(reason="timeout", now=current)
                return "expired", self._snapshot_locked(now=current)

            if self._last_capture_at is not None:
                elapsed = current - float(self._last_capture_at)
                if elapsed < self._interval_sec:
                    return "waiting", None

            self._attempts += 1
            self._last_capture_at = current
            self._last_error = None
            return "capture", self._snapshot_locked(now=current)

    def mark_frame_unavailable(self) -> dict[str, Any]:
        now = time.time()
        with self._lock:
            self._last_error = "frame_unavailable"
            return self._snapshot_locked(now=now)

    def mark_processed(self, *, latency_ms: float | None = None) -> dict[str, Any]:
        now = time.time()
        with self._lock:
            self._processed_count += 1
            self._last_processed_at = now
            if latency_ms is not None:
                self._last_result = {**self._last_result, "latency_ms": float(latency_ms)}
            return self._snapshot_locked(now=now)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._snapshot_locked(now=time.time())

    def vision_payload(self) -> dict[str, Any]:
        snapshot = self.snapshot()
        status = "CAPTURING" if snapshot["active"] else self._status_for_reason(snapshot.get("last_reason"))
        return {
            "status": status,
            "capture_active": bool(snapshot["active"]),
            "capture_session": snapshot,
        }

    def publish_status(self, *, source: str = "vision_capture_session", toast: str | None = None, level: str = "info") -> None:
        payload = {"vision": self.vision_payload()}
        try:
            bus.publish(BaseEvent.create(
                event_type=EventType.DIAGNOSTICS_UPDATED,
                source=source,
                payload=payload,
            ))
            if toast:
                bus.publish(BaseEvent.create(
                    event_type=EventType.UI_TOAST,
                    source=source,
                    payload={"text": toast, "level": level},
                ))
        except Exception:
            logger.debug("[VisionCaptureSession] failed to publish status", exc_info=True)

    def is_active(self) -> bool:
        with self._lock:
            return bool(self._active)

    def _complete_locked(self, *, reason: str, result: dict[str, Any] | None = None, now: float | None = None) -> None:
        current = time.time() if now is None else float(now)
        self._active = False
        self._completed_at = current
        self._last_reason = str(reason or "completed")
        self._last_result = dict(result or self._last_result or {})
        logger.info(
            "[VisionCaptureSession] stopped id=%s reason=%s attempts=%s processed=%s",
            self._session_id,
            self._last_reason,
            self._attempts,
            self._processed_count,
        )

    def _timed_out_locked(self, now: float) -> bool:
        if self._timeout_sec <= 0 or self._started_at is None:
            return False
        return now - float(self._started_at) >= self._timeout_sec

    def _snapshot_locked(self, *, now: float) -> dict[str, Any]:
        started_at = self._started_at
        completed_at = self._completed_at
        elapsed = max(0.0, now - float(started_at)) if started_at else 0.0
        return {
            "active": bool(self._active),
            "session_id": self._session_id,
            "trace_id": self._trace_id,
            "source": self._source,
            "started_at": started_at,
            "completed_at": completed_at,
            "elapsed_sec": round(elapsed, 3),
            "interval_sec": round(float(self._interval_sec), 3),
            "timeout_sec": round(float(self._timeout_sec), 3),
            "attempts": int(self._attempts),
            "processed_count": int(self._processed_count),
            "last_capture_at": self._last_capture_at,
            "last_processed_at": self._last_processed_at,
            "last_error": self._last_error,
            "last_reason": self._last_reason,
            "last_result": dict(self._last_result),
            "next_capture_in_sec": self._next_capture_in_locked(now),
        }

    def _next_capture_in_locked(self, now: float) -> float | None:
        if not self._active:
            return None
        if self._last_capture_at is None:
            return 0.0
        return round(max(0.0, self._interval_sec - (now - float(self._last_capture_at))), 3)

    def _coerce_interval(self, value: float | None) -> float:
        return self._bounded_float(value, self._default_interval_sec(), minimum=0.25, maximum=30.0)

    def _coerce_timeout(self, value: float | None) -> float:
        return self._bounded_float(value, self._default_timeout_sec(), minimum=2.0, maximum=300.0)

    def _bounded_float(self, value: float | None, default: float, *, minimum: float, maximum: float) -> float:
        try:
            numeric = float(default if value is None else value)
        except (TypeError, ValueError):
            numeric = default
        return max(minimum, min(maximum, numeric))

    def _default_interval_sec(self) -> float:
        return float(getattr(config, "VISION_USER_CAPTURE_INTERVAL_SEC", 2.0))

    def _default_timeout_sec(self) -> float:
        return float(getattr(config, "VISION_USER_CAPTURE_TIMEOUT_SEC", 30.0))

    def _status_for_reason(self, reason: str | None) -> str:
        if reason == "stable_vision_result":
            return "CAPTURE_COMPLETE"
        if reason == "timeout":
            return "CAPTURE_TIMEOUT"
        if reason == "operator_stopped":
            return "CAPTURE_STOPPED"
        return "CAPTURE_IDLE"


vision_capture_session = VisionCaptureSession()
