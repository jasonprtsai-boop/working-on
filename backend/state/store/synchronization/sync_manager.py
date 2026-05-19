from backend.state.store.manager.state_manager import state_manager
from backend.events.bus.event_bus import bus
from backend.events.event_types import EventType
from backend.events.models.base_event import BaseEvent

class SyncManager:
    """Manages push-based synchronization to external interfaces (SocketIO, UI)."""

    def __init__(self, socket_gateway=None):
        self.gateway = socket_gateway
        self._setup_subscriptions()

    def _setup_subscriptions(self):
        """Reacts to STATE_UPDATED to push to frontend."""
        bus.subscribe(EventType.STATE_UPDATED, self._on_state_updated)

    def _on_state_updated(self, event: BaseEvent):
        if self.gateway:
            # Pushing the standardized state dictionary to the frontend room
            self.gateway.emit_event("STATE_SYNC", event.payload)

    def force_sync(self, trace_id="sync"):
        """Manually triggers a full state broadcast."""
        bus.publish(BaseEvent.create(
            event_type=EventType.STATE_UPDATED,
            source="sync_manager",
            payload=state_manager.current.to_dict(),
            trace_id=trace_id
        ))

# Global helper
sync_manager = SyncManager()
