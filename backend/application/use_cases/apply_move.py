from backend.events.bus.event_bus import bus
from backend.events.event_types import EventType

class ApplyMoveUseCase:
    """
    [Domain Action] Apply Move Use Case.
    Responsibility: Validates and applies a move to the system state.
    """
    def __init__(self, state_manager):
        self.state_manager = state_manager

    async def execute(self, move_payload: dict, trace_id: str = None):
        """
        Executes the move application logic.
        Publishes a MOVE_APPLIED event to the bus, which will be
        picked up by the StateManager for the authoritative update.
        """
        from backend.events.models.base_event import BaseEvent

        event = BaseEvent.create(
            event_type=EventType.MOVE_APPLIED,
            source="apply_move_use_case",
            payload=move_payload,
            trace_id=trace_id
        )

        # Dispatch via the global bus (StateManager is already subscribed)
        bus.publish(event)

        return self.state_manager.current
