"""Bootstrap reducer wiring kept separate from the runtime startup flow."""

from backend.events.event_types import EventType
from backend.state.reducers.engine_reducer import EngineReducer
from backend.state.reducers.move_reducer import MoveReducer
from backend.state.reducers.robot_reducer import RobotReducer
from backend.state.reducers.system_reducer import SystemReducer
from backend.state.store.manager.reducer_registry import reducer_registry


def register_bootstrap_reducers() -> None:
    """Register EventBus reducers used by the application bootstrap."""
    reducer_registry.register(EventType.VISION_MOVE_DETECTED, MoveReducer)
    reducer_registry.register(EventType.MOVE_APPLIED, MoveReducer)
    reducer_registry.register(EventType.GAME_PLAYER_MOVE, MoveReducer)
    reducer_registry.register(EventType.ENGINE_ANALYSIS_COMPLETED, EngineReducer)
    reducer_registry.register(EventType.ROBOT_MOVE_STARTED, RobotReducer)
    reducer_registry.register(EventType.ROBOT_MOVE_COMPLETED, RobotReducer)
    reducer_registry.register(EventType.ROBOT_STATUS_UPDATED, RobotReducer)
    reducer_registry.register(EventType.SYSTEM_RESET, SystemReducer)
    reducer_registry.register(EventType.SYSTEM_ERROR, SystemReducer)
    reducer_registry.register(EventType.DIAGNOSTICS_UPDATED, SystemReducer)
