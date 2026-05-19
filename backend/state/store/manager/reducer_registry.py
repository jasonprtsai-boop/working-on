from typing import Dict, Callable, Any, Type
from backend.events.event_types import EventType

class ReducerRegistry:
    """
    [State Governance] Registry for mapping EventTypes to functional reducers.
    Allows for decoupled state transitions without circular dependencies.
    """
    def __init__(self):
        self._reducers: Dict[str, Any] = {}

    def register(self, event_type: Any, reducer: Any):
        key = event_type.value if hasattr(event_type, "value") else event_type
        self._reducers[key] = reducer

    def get_reducer(self, event_type: Any) -> Any:
        key = event_type.value if hasattr(event_type, "value") else event_type
        return self._reducers.get(key)

reducer_registry = ReducerRegistry()
