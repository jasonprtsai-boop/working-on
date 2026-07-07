import copy
import dataclasses
import threading
from typing import List, Dict, Any, Optional
from backend.state.store.models.system_state import SystemState
from backend.events.bus.event_bus import bus
from backend.events.event_types import EventType
from backend.events.models.base_event import BaseEvent
from backend.events.adapters.legacy_event_adapter import adapt_legacy_event
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

    def dispatch(self, event: BaseEvent):
        """
        Standardized entry point for all state mutations.
        Functional Flow: Dispatch -> Reduce -> Validate -> Commit -> Sync
        """
        if not isinstance(event, BaseEvent):
            return

        # Ignore self-emitted state snapshots to prevent deadlocks/feedback loops.
        et0 = event.event_type.value if hasattr(event.event_type, "value") else event.event_type
        if et0 == EventType.STATE_UPDATED.value:
            return

        if isinstance(et0, str) and et0 not in {e.value for e in EventType}:
            return

        snapshot = None
        with self._lock:
            try:
                if et0 == EventType.GAME_UNDO.value:
                    snapshot = self._undo_last_game_mutation(event)
                else:
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

    def _undo_last_game_mutation(self, event: BaseEvent) -> Optional[SystemState]:
        current = self._state
        while self._history:
            candidate = self._history.pop()
            if (
                candidate.game.fen != current.game.fen
                or candidate.game.move_history != current.game.move_history
                or candidate.game.current_turn != current.game.current_turn
            ):
                restored = dataclasses.replace(candidate, trace_id=event.trace_id)
                self._state = restored
                return restored
        return None

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
