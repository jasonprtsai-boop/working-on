import json
import os
import threading
import time
from typing import List, Dict, Any
from backend.events.bus.event_bus import bus
from backend.events.event_types import EventType
from backend.utils.logger import logger
from backend.utils import config

class ReplayManager:
    """
    [Observability Layer] Game Session Recorder.
    Captures state snapshots to allow post-game analysis and step-by-step replay.
    """
    def __init__(self, storage_dir: str = "backend/data/replays"):
        self.storage_dir = storage_dir
        self.current_session: List[Dict[str, Any]] = []
        self.session_id = None
        self.max_session_events = max(1, int(getattr(config, "REPLAY_MAX_SESSION_EVENTS", 1000)))
        self.save_every_n_events = max(1, int(getattr(config, "REPLAY_SAVE_EVERY_N_EVENTS", 10)))
        self.retention_files = max(1, int(getattr(config, "REPLAY_RETENTION_FILES", 20)))
        self._events_since_save = 0
        self._lock = threading.RLock()

        if not os.path.exists(self.storage_dir):
            os.makedirs(self.storage_dir, exist_ok=True)

    def start(self):
        # Record every state update to build the history
        bus.subscribe(EventType.STATE_UPDATED, self.on_state_updated, is_async=True)
        bus.subscribe(EventType.SYSTEM_RESET, self.on_reset, is_async=True)
        self.session_id = f"session_{int(time.time())}"
        logger.info(f"[ReplayManager] Recording started: {self.session_id}")

    def on_state_updated(self, event):
        # We store the state to build a replayable timeline
        snapshot = {
            "timestamp": getattr(event, "timestamp", time.time()),
            "trace_id": getattr(event, "trace_id", None),
            "state": getattr(event, "payload", {})
        }
        with self._lock:
            self.current_session.append(snapshot)
            if len(self.current_session) > self.max_session_events:
                del self.current_session[:len(self.current_session) - self.max_session_events]
            self._events_since_save += 1
            should_save = self._events_since_save >= self.save_every_n_events
            if should_save:
                self._events_since_save = 0

        # Auto-save every 10 moves for durability
        if should_save:
            self._save_session()

    def on_reset(self, event):
        self._save_session()
        with self._lock:
            self.current_session = []
            self._events_since_save = 0
            self.session_id = f"session_{int(time.time())}"

    def _save_session(self):
        with self._lock:
            if not self.current_session:
                return
            session_id = self.session_id or f"session_{int(time.time())}"
            self.session_id = session_id
            history = list(self.current_session)

        filepath = os.path.join(self.storage_dir, f"{session_id}.json")
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump({
                    "session_id": session_id,
                    "recorded_at": time.time(),
                    "history": history
                }, f, indent=2)
            self._prune_old_sessions()
        except Exception as e:
            logger.error(f"[ReplayManager] Save failed: {e}")

    def _prune_old_sessions(self):
        try:
            files = [
                os.path.join(self.storage_dir, name)
                for name in os.listdir(self.storage_dir)
                if name.startswith("session_") and name.endswith(".json")
            ]
            files.sort(key=lambda path: os.path.getmtime(path), reverse=True)
            for path in files[self.retention_files:]:
                try:
                    os.remove(path)
                except OSError:
                    logger.debug(f"[ReplayManager] failed to prune replay file: {path}", exc_info=True)
        except Exception:
            logger.debug("[ReplayManager] replay retention check failed", exc_info=True)

replay_manager = ReplayManager()
