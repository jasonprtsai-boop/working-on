from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Dict, Optional

from backend.events.bus.event_bus import bus
from backend.events.event_types import EventType
from backend.events.models.base_event import BaseEvent
from backend.runtime.workers.engine_worker import engine_worker


class RuntimeControl:
    """Small runtime control surface for console-only experiment controls."""

    def __init__(self):
        self._lock = threading.RLock()
        self.safe_mode = True
        self.engine_depth = int(getattr(engine_worker, "depth_on_change", 12) or 12)
        self.participant_id = ""
        self.session_id: Optional[str] = None
        self.session_started_at: Optional[float] = None
        self.session_ended_at: Optional[float] = None
        self._last_step_at: Optional[float] = None
        self.move_records: list[dict[str, Any]] = []
        bus.subscribe(EventType.MOVE_APPLIED, self._on_move_applied)

    @property
    def active_session_id(self) -> Optional[str]:
        with self._lock:
            if self.session_id and self.session_started_at and not self.session_ended_at:
                return self.session_id
            return None

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            active = bool(self.session_id and self.session_started_at and not self.session_ended_at)
            now = time.time()
            duration = 0.0
            if self.session_started_at:
                end_at = now if active else (self.session_ended_at or now)
                duration = max(0.0, end_at - self.session_started_at)

            return {
                "safe_mode": self.safe_mode,
                "engine_depth": self.engine_depth,
                "ai_difficulty": self._difficulty_label(self.engine_depth),
                "session": {
                    "session_id": self.session_id or "",
                    "participant_id": self.participant_id,
                    "active": active,
                    "started_at": self.session_started_at,
                    "ended_at": self.session_ended_at,
                    "duration_sec": round(duration, 3),
                    "move_count": len(self.move_records),
                    "latest_move": self.move_records[-1] if self.move_records else None,
                },
            }

    def frontend_ui_payload(self) -> Dict[str, Any]:
        snap = self.snapshot()
        session = snap["session"]
        return {
            "safe_mode": snap["safe_mode"],
            "ai_difficulty": snap["ai_difficulty"],
            "engine_depth": snap["engine_depth"],
            "participant_id": session["participant_id"],
            "session_id": session["session_id"],
            "session_active": session["active"],
            "session_started_at": session["started_at"],
            "session_ended_at": session["ended_at"],
            "session_time_sec": session["duration_sec"],
            "move_count": session["move_count"],
            "latest_step": session["latest_move"],
        }

    def set_engine_depth(self, depth: int) -> Dict[str, Any]:
        depth_value = max(1, min(60, int(depth)))
        with self._lock:
            self.engine_depth = depth_value
            engine_worker.depth_on_change = depth_value
            engine_worker.depth_on_idle = depth_value

        self._publish_snapshot("AI depth updated.", "success", extra_engine={"depth": depth_value})
        return self.snapshot()

    def set_safe_mode(self, enabled: bool) -> Dict[str, Any]:
        with self._lock:
            self.safe_mode = bool(enabled)

        self._publish_snapshot("Safe Mode updated.", "success")
        return self.snapshot()

    def start_session(self, participant_id: str = "") -> Dict[str, Any]:
        now = time.time()
        clean_participant = str(participant_id or "").strip()[:64]
        session_id = f"session_{time.strftime('%Y%m%d_%H%M%S', time.localtime(now))}_{uuid.uuid4().hex[:6]}"
        with self._lock:
            self.session_id = session_id
            self.participant_id = clean_participant
            self.session_started_at = now
            self.session_ended_at = None
            self._last_step_at = now
            self.move_records = []

        self._publish_snapshot("Session started.", "success", event_name="SESSION_STARTED")
        return self.snapshot()

    def end_session(self) -> Dict[str, Any]:
        with self._lock:
            if self.session_id and not self.session_ended_at:
                self.session_ended_at = time.time()
            snapshot = self.snapshot()

        self._publish_snapshot("Session ended.", "info", event_name="SESSION_ENDED")
        return snapshot

    def _on_move_applied(self, event: BaseEvent):
        with self._lock:
            if not self.active_session_id:
                return
            now = time.time()
            elapsed = now - (self._last_step_at or self.session_started_at or now)
            self._last_step_at = now
            record = {
                "index": len(self.move_records) + 1,
                "move": event.payload.get("move") or event.payload.get("notation") or event.payload,
                "trace_id": event.trace_id,
                "timestamp": now,
                "elapsed_sec": round(max(0.0, elapsed), 3),
            }
            self.move_records.append(record)

        self._publish_snapshot("Move timing recorded.", "info", event_name="SESSION_MOVE_RECORDED")

    def _publish_snapshot(
        self,
        text: str,
        level: str,
        *,
        event_name: str = "RUNTIME_CONTROL_UPDATED",
        extra_engine: Optional[Dict[str, Any]] = None,
    ):
        snap = self.snapshot()
        payload = {
            "ui": self.frontend_ui_payload(),
            "runtime_control": snap,
            "session": snap["session"],
            "event": event_name,
        }
        if extra_engine:
            payload["engine"] = dict(extra_engine)
        session_id = snap["session"].get("session_id") or None
        bus.publish(BaseEvent.create(
            event_type=EventType.DIAGNOSTICS_UPDATED,
            source="runtime_control",
            payload=payload,
            metadata={"session_id": session_id} if session_id else None,
        ))
        bus.publish(BaseEvent.create(
            event_type=EventType.UI_TOAST,
            source="runtime_control",
            payload={"text": text, "level": level, "source": "runtime_control"},
            metadata={"session_id": session_id} if session_id else None,
        ))

    @staticmethod
    def _difficulty_label(depth: int) -> str:
        return f"Depth {int(depth)}"


runtime_control = RuntimeControl()
