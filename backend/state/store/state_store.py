from backend.state.store.manager.state_manager import state_manager
from backend.state.store.models.system_state import SystemState

class StateStore:
    """
    [Architectural Authority] Unified Entry Point for State Access.
    Replaces the God Object GameState facade.
    Provides typed, read-only access to sub-states and dispatches mutations.
    """
    def __init__(self):
        self._manager = state_manager

    @property
    def game(self):
        return self._manager.current.game

    @property
    def engine(self):
        return self._manager.current.engine

    @property
    def robot(self):
        return self._manager.current.robot

    @property
    def vision(self):
        return self._manager.current.vision

    @property
    def health(self):
        return {
            "fps": self._manager.current.fps,
            "cpu_percent": self._manager.current.cpu_percent,
            "memory_mb": self._manager.current.memory_mb
        }

    @property
    def current(self) -> SystemState:
        """Access the full immutable system state."""
        return self._manager.current

    def dispatch(self, event):
        """Unified portal for state mutations via Event Objects."""
        self._manager.dispatch(event)

    def to_dict(self):
        """Standard serialization for frontend sync."""
        return self._manager.current.to_dict()

# Single Source of Truth Entry Point
state_store = StateStore()
