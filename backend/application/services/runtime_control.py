from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Dict, Optional

from backend.events.bus.event_bus import bus
from backend.events.event_types import EventType
from backend.events.models.base_event import BaseEvent
from backend.runtime.workers.engine_worker import engine_worker
from backend.utils import config
from backend.utils.logger import logger


AI_MODES = {
    "companionship": {"label": "陪伴模式", "depth": 6},
    "training": {"label": "訓練模式", "depth": 10},
    "demo": {"label": "展示模式", "depth": 18},
    "adaptive": {"label": "自適應模式", "depth": 8},
}


class RuntimeControl:
    """Small runtime control surface for console-only experiment controls."""

    def __init__(self):
        self._lock = threading.RLock()
        self.safe_mode = True
        self.ai_mode = self._normalize_ai_mode(getattr(config, "AI_MODE_DEFAULT", "companionship"))
        self.engine_depth = int(AI_MODES[self.ai_mode]["depth"])
        engine_worker.depth_on_change = self.engine_depth
        engine_worker.depth_on_idle = self.engine_depth
        self.participant_id = ""
        self.session_id: Optional[str] = None
        self.session_started_at: Optional[float] = None
        self.session_ended_at: Optional[float] = None
        self.session_record_filename = ""
        self.session_record_path = ""
        self.session_record_status = ""
        self.session_record_error = ""
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
                "ai_mode": self.ai_mode,
                "ai_mode_label": AI_MODES.get(self.ai_mode, AI_MODES["companionship"])["label"],
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
                    "record_filename": self.session_record_filename,
                    "record_path": self.session_record_path,
                    "record_status": self.session_record_status,
                    "record_error": self.session_record_error,
                },
            }

    def frontend_ui_payload(self) -> Dict[str, Any]:
        snap = self.snapshot()
        session = snap["session"]
        return {
            "safe_mode": snap["safe_mode"],
            "ai_mode": snap["ai_mode"],
            "ai_mode_label": snap["ai_mode_label"],
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
            "record_filename": session["record_filename"],
            "record_path": session["record_path"],
            "record_status": session["record_status"],
        }

    def set_engine_depth(self, depth: int) -> Dict[str, Any]:
        depth_value = max(1, min(60, int(depth)))
        with self._lock:
            self.engine_depth = depth_value
            self.ai_mode = self._mode_from_depth(depth_value) or "custom"
            engine_worker.depth_on_change = depth_value
            engine_worker.depth_on_idle = depth_value

        self._publish_snapshot("AI depth updated.", "success", extra_engine={"depth": depth_value})
        return self.snapshot()

    def set_ai_mode(self, mode: str) -> Dict[str, Any]:
        normalized = self._normalize_ai_mode(mode)
        depth_value = self._depth_for_mode(normalized)
        with self._lock:
            self.ai_mode = normalized
            self.engine_depth = depth_value
            engine_worker.depth_on_change = depth_value
            engine_worker.depth_on_idle = depth_value

        label = AI_MODES[normalized]["label"]
        self._publish_snapshot(f"AI mode updated: {label}.", "success", extra_engine={"depth": depth_value})
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
            self.session_record_filename = ""
            self.session_record_path = ""
            self.session_record_status = ""
            self.session_record_error = ""
            self._last_step_at = now
            self.move_records = []

        self._publish_snapshot("Session started.", "success", event_name="SESSION_STARTED")
        return self.snapshot()

    def end_session(self) -> Dict[str, Any]:
        should_export = False
        session_id = None
        started_at = None
        with self._lock:
            if self.session_id and not self.session_ended_at:
                self.session_ended_at = time.time()
                should_export = bool(getattr(config, "AUTO_EXPORT_SESSION_RECORD", True))
                session_id = self.session_id
                started_at = self.session_started_at
                if should_export:
                    self.session_record_status = "pending"
                    self.session_record_error = ""
            snapshot = self.snapshot()

        self._publish_snapshot("Session ended.", "info", event_name="SESSION_ENDED")
        if should_export and session_id:
            snapshot = self._export_session_record(session_id, started_at)
        return snapshot

    def _export_session_record(self, session_id: str, started_at: Optional[float]) -> Dict[str, Any]:
        try:
            delay = min(0.75, max(0.05, float(getattr(config, "PERSISTENCE_FLUSH_INTERVAL_SEC", 0.25)) * 2))
            time.sleep(delay)
            result = self._save_session_record(session_id, started_at)
            with self._lock:
                self.session_record_filename = result.filename
                self.session_record_path = result.path
                self.session_record_status = "saved"
                self.session_record_error = ""
                snapshot = self.snapshot()
            self._publish_snapshot("Session record saved.", "success", event_name="SESSION_RECORD_SAVED")
            return snapshot
        except Exception as exc:
            logger.warning("[RuntimeControl] session record export failed: %s", exc, exc_info=True)
            with self._lock:
                self.session_record_status = "failed"
                self.session_record_error = str(exc)
                snapshot = self.snapshot()
            self._publish_snapshot("Session record export failed.", "warning", event_name="SESSION_RECORD_FAILED")
            return snapshot

    def _save_session_record(self, session_id: str, started_at: Optional[float]):
        from backend.utils.serialization.excel_report_service import export_session_record

        return export_session_record(session_id=session_id, started_at=started_at)

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
            self._apply_adaptive_depth_locked()

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

    def _apply_adaptive_depth_locked(self) -> None:
        if self.ai_mode != "adaptive" or not self.move_records:
            return
        recent = self.move_records[-4:]
        elapsed_values = [float(item.get("elapsed_sec", 0.0) or 0.0) for item in recent]
        average_elapsed = sum(elapsed_values) / len(elapsed_values)
        depth_value = self.engine_depth
        if average_elapsed < 15.0:
            depth_value = min(14, depth_value + 1)
        elif average_elapsed > 45.0:
            depth_value = max(4, depth_value - 1)
        if depth_value == self.engine_depth:
            return
        self.engine_depth = depth_value
        engine_worker.depth_on_change = depth_value
        engine_worker.depth_on_idle = depth_value

    @staticmethod
    def _difficulty_label(depth: int) -> str:
        depth_value = int(depth)
        for mode in AI_MODES.values():
            if int(mode["depth"]) == depth_value:
                return str(mode["label"])
        return f"自訂 Depth {depth_value}"

    @staticmethod
    def _normalize_ai_mode(mode: str) -> str:
        normalized = str(mode or "").strip().lower().replace("-", "_")
        aliases = {
            "companion": "companionship",
            "care": "companionship",
            "陪伴": "companionship",
            "train": "training",
            "訓練": "training",
            "show": "demo",
            "展示": "demo",
            "auto": "adaptive",
            "adaptive_mode": "adaptive",
            "自適應": "adaptive",
        }
        normalized = aliases.get(normalized, normalized)
        if normalized not in AI_MODES:
            return "companionship"
        return normalized

    @staticmethod
    def _depth_for_mode(mode: str) -> int:
        return int(AI_MODES.get(mode, AI_MODES["companionship"])["depth"])

    @staticmethod
    def _mode_from_depth(depth: int) -> Optional[str]:
        depth_value = int(depth)
        for key, value in AI_MODES.items():
            if int(value["depth"]) == depth_value:
                return key
        return None


runtime_control = RuntimeControl()
