import time
from typing import Any, Optional

from backend.events.bus.event_bus import bus
from backend.events.event_types import EventType
from backend.events.models.base_event import BaseEvent
from backend.state.store.state_store import state_store as game_state
from backend.state.store.models.game_state import SystemPhase
from backend.observability.error_reporter import publish_error_diagnostic
from backend.utils.logger import logger


class GameService:
    """
    Application-level game coordinator.

    Notes:
    - Current production flow is primarily driven by `socket_handler.py` + EventBus.
    - This service remains import-safe for UI actions and simulation workflows.
    """

    def __init__(self, vision_service=None, ai_service=None, robot=None, components=None):
        self.vision = vision_service
        self.ai = ai_service
        self.robot = robot
        self.components = components or {}

        self.is_paused = False
        self.pending_ai_move: Optional[dict] = None
        self.pending_ai_timestamp = 0.0

    async def run_vision_cycle(self) -> Optional[str]:
        if not self.vision:
            bus.publish(BaseEvent.create(
                event_type=EventType.UI_TOAST,
                payload={"text": "Vision service is unavailable.", "level": "warning"},
                source="game_service",
            ))
            return None

        try:
            fen, confidence = self.vision.get_current_fen()
        except Exception as exc:
            logger.warning("[GameService] vision cycle failed", exc_info=True)
            publish_error_diagnostic(
                source="game_service",
                module="vision",
                code="vision_cycle_failed",
                message=str(exc),
                severity="warning",
                status="warning",
                recoverable=True,
            )
            bus.publish(BaseEvent.create(
                event_type=EventType.UI_TOAST,
                payload={"text": "Vision cycle failed.", "level": "error"},
                source="game_service",
            ))
            return None

        if fen:
            bus.publish(BaseEvent.create(
                event_type=EventType.VISION_BOARD_DETECTED,
                payload={"fen": fen, "confidence": confidence},
                source="game_service",
            ))

        return fen

    async def handle_action(self, data: Any):
        action_type = data if isinstance(data, str) else (data.get("type") if isinstance(data, dict) else None)
        action_value = None if isinstance(data, str) else (data.get("value") if isinstance(data, dict) else None)

        if not action_type:
            return

        if action_type == "START":
            self.is_paused = False
            bus.publish(BaseEvent.create(
                event_type=EventType.GAME_START,
                payload={"phase": "playing"},
                source="game_service",
            ))
            return

        if action_type == "PAUSE":
            self.is_paused = True
            bus.publish(BaseEvent.create(
                event_type=EventType.GAME_PAUSE,
                payload={"phase": "paused"},
                source="game_service",
            ))
            return

        if action_type == "RESET":
            self.is_paused = False
            self.pending_ai_move = None
            bus.publish(BaseEvent.create(
                event_type=EventType.SYSTEM_RESET,
                payload={},
                source="game_service",
            ))
            bus.publish(BaseEvent.create(
                event_type=EventType.GAME_RESET,
                payload={"phase": SystemPhase.IDLE.value},
                source="game_service",
            ))
            bus.publish(BaseEvent.create(
                event_type=EventType.UI_TOAST,
                payload={"text": "Game state reset.", "level": "info"},
                source="game_service",
            ))
            return

        if action_type == "UNDO":
            bus.publish(BaseEvent.create(
                event_type=EventType.GAME_UNDO,
                payload={"source_action": "UNDO"},
                source="game_service",
            ))
            bus.publish(BaseEvent.create(
                event_type=EventType.UI_TOAST,
                payload={"text": "Undo applied.", "level": "success"},
                source="game_service",
            ))
            return

        if action_type in ("SYNC", "SYNC_VISION"):
            await self.run_vision_cycle()
            bus.publish(BaseEvent.create(
                event_type=EventType.UI_TOAST,
                payload={"text": "Vision sync requested.", "level": "info"},
                source="game_service",
            ))
            return

        if action_type == "EMERGENCY_STOP":
            from backend.application.services.estop import estop

            reason = "Manual Emergency Stop"
            if isinstance(data, dict):
                reason = data.get("reason") or reason
            estop.trigger(reason=reason)
            return

        if action_type == "CLEAR_EMERGENCY":
            from backend.application.services.estop import estop

            estop.reset()
            self.is_paused = False
            bus.publish(BaseEvent.create(
                event_type=EventType.SYSTEM_RESET,
                payload={},
                source="game_service",
            ))
            bus.publish(BaseEvent.create(
                event_type=EventType.UI_TOAST,
                payload={"text": "Emergency stop cleared.", "level": "success"},
                source="game_service",
            ))
            return

        if action_type == "SET_DIFFICULTY":
            try:
                if self.ai and hasattr(self.ai, "set_difficulty"):
                    self.ai.set_difficulty(action_value)
                    bus.publish(BaseEvent.create(
                        event_type=EventType.UI_TOAST,
                        payload={"text": "Difficulty updated.", "level": "info"},
                        source="game_service",
                    ))
            except Exception as exc:
                logger.warning("[GameService] set_difficulty failed", exc_info=True)
                publish_error_diagnostic(
                    source="game_service",
                    module="engine",
                    code="set_difficulty_failed",
                    message=str(exc),
                    severity="warning",
                    status="warning",
                    recoverable=True,
                    details={"value": action_value},
                )
            return

        bus.publish(BaseEvent.create(
            event_type=EventType.UI_TOAST,
            payload={"text": f"Unknown action: {action_type}", "level": "warning"},
            source="game_service",
        ))

    def _should_trigger_ai(self) -> bool:
        try:
            snap = game_state.to_dict()
            turn = (snap.get("game") or {}).get("current_turn")
        except Exception as exc:
            logger.warning("[GameService] AI trigger check failed", exc_info=True)
            publish_error_diagnostic(
                source="game_service",
                module="engine",
                code="ai_trigger_check_failed",
                message=str(exc),
                severity="warning",
                status="warning",
                recoverable=True,
                throttle_seconds=30.0,
            )
            return False
        return (turn == "black") and bool(self.ai) and (not self.is_paused)

    async def check_timeouts(self):
        if self.pending_ai_move and self.pending_ai_timestamp > 0 and time.time() - self.pending_ai_timestamp > 10:
            logger.warning("[GameService] AI approval timeout")
            self.pending_ai_move = None
            self.pending_ai_timestamp = 0.0


game_service = GameService()
