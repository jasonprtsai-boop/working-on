from backend.events.bus.event_bus import bus

class MoveHistory:
    """Manages the historical event log (Subscriber)."""
    def __init__(self):
        self.events = []
        self.version = 0
        # Auto-subscribe to all authoritative domains
        bus.subscribe("GAME.MOVE_APPLIED", self._on_event)
        bus.subscribe("ENGINE.BESTMOVE_RECEIVED", self._on_event)

    def _on_event(self, event):
        """Internal callback to store events in history."""
        self.events.append(event.to_dict())
        self.version += 1

    def get_recent(self, limit=20):
        return self.events[-limit:]

    def to_dict(self):
        return {
            "version": self.version,
            "event_history": self.get_recent()
        }
