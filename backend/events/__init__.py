"""Canonical public surface for the backend event system."""

from backend.events.bus.event_bus import bus  # noqa: F401
from backend.events.event_types import EventType  # noqa: F401
from backend.events.models.base_event import BaseEvent  # noqa: F401

try:  # pragma: no cover
    from backend.events.event_factory import EventFactory  # noqa: F401
except Exception:  # pragma: no cover
    EventFactory = None  # type: ignore

__all__ = ["bus", "EventType", "BaseEvent", "EventFactory"]
