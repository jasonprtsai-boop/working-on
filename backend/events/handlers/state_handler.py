class StateHandler:
    def __init__(self, game_state, event_bus):
        self.game_state = game_state
        self.bus = event_bus

    def handle_event(self, event):
        """Authoritative state transition entry point."""
        # 1. State reduction
        self.game_state.reduce(event)

        # 2. Re-publish board update if state changed significantly
        from backend.events.event_types import EventType
        if event.event_type in [EventType.VISION_MOVE_DETECTED, EventType.MOVE_APPLIED]:
             update_event = self.game_state.create_board_updated_event(
                 correlation_id=event.correlation_id
             )
             self.bus.publish(update_event)

    def handle_vision_move(self, event):
        # Legacy support/specific mapping
        self.handle_event(event)
