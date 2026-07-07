import time
from typing import Any, Dict, List, Optional

from backend.utils.logger import logger


REPLAY_STATE_EVENT_TYPES = ("STATE_UPDATE", "STATE_UPDATED", "GAME.STATE_APPLIED")


class ReplayManager:
    """
    Compatibility facade for replay data.

    Replay is now sourced from the durable SQLite EventStore through
    backend.interfaces.api.replay_routes. This class intentionally avoids a
    second JSON recording path so there is only one replay authority.
    """

    def __init__(self):
        self.session_id = None

    def start(self):
        self.session_id = self.session_id or f"session_{int(time.time())}"
        logger.info("[ReplayManager] SQLite EventStore replay facade ready: %s", self.session_id)

    def on_state_updated(self, _event):
        return None

    def on_reset(self, _event):
        self.session_id = f"session_{int(time.time())}"

    def list_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        return list(self._event_store().list_sessions(limit=limit, event_types=REPLAY_STATE_EVENT_TYPES))

    def load_session(self, session_id: Optional[str] = None, limit: int = 500, offset: int = 0) -> List[Dict[str, Any]]:
        return list(
            self._event_store().load_replay(
                session_id=session_id,
                limit=limit,
                offset=offset,
                event_types=REPLAY_STATE_EVENT_TYPES,
            )
        )

    @staticmethod
    def _event_store():
        from backend.events.store.event_store import event_store

        return event_store


replay_manager = ReplayManager()
