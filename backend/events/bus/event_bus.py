from __future__ import annotations

from collections import defaultdict
import threading
from typing import Any, Callable, Dict, Optional

from backend.events.adapters.legacy_event_adapter import adapt_legacy_event
from backend.events.bus.event_bus_support import (
    LegacyDictEventTracker,
    dispatch_async_handler,
    event_key,
    handle_dispatch_failure,
    log_dead_letter,
    stats_snapshot,
)
from backend.utils.logger import logger


def subscribe(event_type: str):
    """Decorator for declarative event subscription."""
    def wrapper(func: Callable):
        func._event_type = event_type.value if hasattr(event_type, "value") else event_type
        return func
    return wrapper


class EventBus:
    _instance = None

    def __new__(cls, is_singleton: bool = True, allow_legacy_dict_events: Optional[bool] = None):
        if not is_singleton:
            instance = super().__new__(cls)
            instance._initialized = False
            return instance
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, is_singleton: bool = True, allow_legacy_dict_events: Optional[bool] = None):
        if self._initialized:
            return
        if allow_legacy_dict_events is None:
            try:
                from backend.utils import config
                allow_legacy_dict_events = bool(getattr(config, "EVENTBUS_ALLOW_LEGACY_DICT_EVENTS", False))
            except Exception:
                allow_legacy_dict_events = False
        self._subscribers = defaultdict(list)
        self._global_subscribers = []
        self._global_subscriber_keys = {}
        self._allow_legacy_dict_events = bool(allow_legacy_dict_events)
        self._legacy_tracker = LegacyDictEventTracker()
        self._sequence_counter = 0
        self._lock = threading.RLock()
        self._system_error_guard = threading.local()
        self._dead_letter_count = 0
        self._initialized = True

    def register_handlers(self, handler_instance: Any):
        """Automatically registers all methods decorated with @subscribe."""
        for attr in dir(handler_instance):
            method = getattr(handler_instance, attr)
            if hasattr(method, "_event_type"):
                is_async = getattr(method, "_is_async", False)
                self.subscribe(method._event_type, method, is_async=is_async)

    def subscribe(self, event_type: str, handler: Callable, is_async: bool = False):
        key = event_type.value if hasattr(event_type, "value") else event_type
        with self._lock:
            if not any(h[0] is handler for h in self._subscribers[key]):
                self._subscribers[key].append((handler, is_async))

    def subscribe_all(self, handler: Callable, key: Optional[str] = None, replace: bool = False, is_async: bool = False):
        """Register a global subscriber."""
        with self._lock:
            if key:
                old_entry = self._global_subscriber_keys.get(key)
                if old_entry and old_entry[0] is handler:
                    return
                if old_entry is not None and (replace or old_entry in self._global_subscribers):
                    self._global_subscribers = [
                        item for item in self._global_subscribers if item[0] is not old_entry[0]
                    ]
                self._global_subscriber_keys[key] = (handler, is_async)

            if not any(h[0] is handler for h in self._global_subscribers):
                self._global_subscribers.append((handler, is_async))

    def publish_from_legacy(self, event: dict):
        legacy_key = self._event_key(event)
        source = event.get("source", "unknown")
        if not self._allow_legacy_dict_events:
            self._record_dead_letter(
                {"type": legacy_key},
                "event_ingress",
                TypeError("legacy dict events are disabled"),
            )
            logger.error(
                "[EventBus] rejected legacy dict event: type=%s source=%s",
                legacy_key, source,
            )
            return

        if self._legacy_tracker.record(legacy_key, source, self._lock):
            logger.warning(
                "[EventBus] legacy dict event published: type=%s source=%s",
                legacy_key, source,
            )
        adapted = adapt_legacy_event(event)
        if adapted is None:
            self._record_dead_letter({"type": legacy_key}, "event_ingress", ValueError("legacy event missing type"))
            return
        self.publish(adapted)

    def publish(self, event: Any):
        """
        Unified publication portal.
        Dispatches events to specific and global subscribers.
        """
        from backend.events.models.base_event import BaseEvent
        if not isinstance(event, BaseEvent):
            if isinstance(event, dict):
                raise TypeError("Internal EventBus accepts BaseEvent only. Use publish_from_legacy for dict events.")
            raise TypeError(f"Internal EventBus accepts BaseEvent only, got {type(event).__name__}")

        key = self._event_key(event)
        with self._lock:
            self._sequence_counter += 1
            handlers = list(self._subscribers.get(key, []))
            global_handlers = list(self._global_subscribers)

        for handler, is_async in handlers + global_handlers:
            if is_async:
                self._dispatch_async(handler, event)
            else:
                self._safe_execute(handler, event)

    def _dispatch_async(self, handler: Callable, event: Any):
        """Offloads execution to the background AsyncRuntime."""
        dispatch_async_handler(handler, event, self._safe_execute)

    def _safe_execute(self, handler: Callable, event: Any):
        """Executes handler with basic error protection."""
        try:
            handler(event)
        except Exception as exc:
            handle_dispatch_failure(
                event=event,
                handler=handler,
                exc=exc,
                publish_system_error=self.publish,
                record_dead_letter=self._record_dead_letter,
                system_error_guard=self._system_error_guard,
            )

    def _event_key(self, event: Any) -> str:
        return event_key(event)

    def _is_system_error(self, event: Any) -> bool:
        return self._event_key(event) == "SYSTEM_ERROR"

    def _record_dead_letter(self, event: Any, handler_name: str, exc: Exception):
        with self._lock:
            self._dead_letter_count += 1
        log_dead_letter(event, handler_name, exc)

    def emit(self, event_type, data=None):
        from backend.events.models.base_event import BaseEvent

        self.publish(BaseEvent.create(event_type=str(event_type), source="event_bus.emit", payload=data or {}))

    def stats(self) -> Dict[str, Any]:
        """Return observability counters without exposing handler internals."""
        with self._lock:
            return stats_snapshot(
                sequence_counter=self._sequence_counter,
                subscribers=self._subscribers,
                global_subscribers=self._global_subscribers,
                global_subscriber_keys=self._global_subscriber_keys,
                dead_letter_count=self._dead_letter_count,
                allow_legacy_dict_events=self._allow_legacy_dict_events,
                legacy_stats=self._legacy_tracker.stats(),
            )

    def reset_for_tests(self) -> None:
        """Reset subscribers and diagnostics for isolated unit tests."""
        with self._lock:
            self._subscribers.clear()
            self._global_subscribers.clear()
            self._global_subscriber_keys.clear()
            self._legacy_tracker.reset()
            self._sequence_counter = 0
            self._dead_letter_count = 0


# Canonical Singleton
bus = EventBus()
