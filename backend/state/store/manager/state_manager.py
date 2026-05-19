import threading
import copy
from typing import List, Dict, Any
from backend.state.store.models.system_state import SystemState
from backend.events.bus.event_bus import bus
from backend.events.event_types import EventType
from backend.events.models.base_event import BaseEvent
from backend.state.reducers.move_reducer import MoveReducer
from backend.utils.logger import logger

class StateManager:
    """
    [State Governance Authority]
    The only entity allowed to trigger state transitions.
    Enforces functional updates, locking, and reactive broadcasting.
    """
    def __init__(self):
        self._state = SystemState()
        self._lock = threading.Lock()
        self._history: List[SystemState] = []
        self._max_history = 50
        self._execution_lock = False # To prevent infinite AI loops

    @property
    def current(self) -> SystemState:
        """Returns the current immutable state."""
        return self._state

    def dispatch(self, event: Any):
        """
        Standardized entry point for all state mutations.
        Functional Flow: Dispatch -> Reduce -> Validate -> Commit -> Sync
        """
        # Accept dict events from legacy producers, but only mutate state for known EventType values.
        if isinstance(event, dict) and not hasattr(event, "event_type"):
            raw_type = event.get("event_type") or event.get("type")
            if isinstance(raw_type, str) and raw_type in {e.value for e in EventType}:
                event = BaseEvent.create(
                    event_type=EventType(raw_type),
                    source=event.get("source", "dict_event"),
                    payload=event.get("payload") or {},
                    trace_id=event.get("trace_id"),
                )
            else:
                return

        # Ignore self-emitted state snapshots to prevent deadlocks/feedback loops.
        if hasattr(event, "event_type"):
            et0 = event.event_type.value if hasattr(event.event_type, "value") else event.event_type
            if et0 == EventType.STATE_UPDATED.value:
                return

        snapshot = None
        with self._lock:
            try:
                # 1. Map Event to Reducer via Global Registry (DIP)
                from backend.state.store.manager.reducer_registry import reducer_registry
                reducer = reducer_registry.get_reducer(event.event_type)

                if not reducer:
                    return

                new_state = reducer.reduce(self._state, event)

                # No-op guard: do not broadcast if nothing changed.
                if new_state is self._state:
                    return

                # 2. Validation (Optional but recommended)
                if not self._validate(new_state):
                    logger.warning(
                        "[StateManager] rejected invalid state mutation from %s",
                        event.event_type,
                    )
                    return

                # 3. Commit and Snapshot
                self._history.append(self._state)
                if len(self._history) > self._max_history:
                    self._history.pop(0)

                self._state = new_state
                snapshot = self._state

            except Exception as e:
                logger.error(f"[StateManager] Mutation Error: {e}", exc_info=True)

        # 4. Reactive Synchronization (Outside the lock to prevent deadlock)
        if snapshot:
            self._broadcast_change(snapshot)

    def _validate(self, state: SystemState) -> bool:
        """Ensures state integrity before committing."""
        try:
            from backend.state.store.validators.fen_validator import FENValidator
            fen = getattr(state.game, "fen", "")
            if not FENValidator.validate(fen):
                logger.warning("[StateManager] invalid FEN rejected: %s", fen)
                return False
        except Exception as exc:
            logger.warning("[StateManager] FEN validator failed: %s", exc, exc_info=True)
            return False
        return True

    def _broadcast_change(self, state: SystemState):
        """Publishes the STATE_UPDATED event for all reactive subscribers."""
        bus.publish(BaseEvent.create(
            event_type=EventType.STATE_UPDATED,
            source="state_manager",
            payload=state.to_dict(),
            trace_id=state.trace_id
        ))

# Canonical Global Authority
state_manager = StateManager()
