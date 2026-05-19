from collections import defaultdict
from typing import Callable, Any, List, Dict, Optional
import asyncio
import threading
import time
from backend.utils.logger import logger

def subscribe(event_type: str):
    """Decorator for declarative event subscription."""
    def wrapper(func: Callable):
        func._event_type = event_type.value if hasattr(event_type, 'value') else event_type
        return func
    return wrapper

class EventBus:
    _instance = None

    def __new__(cls, is_singleton: bool = True):
        if not is_singleton:
            instance = super().__new__(cls)
            instance._initialized = False
            return instance
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, is_singleton: bool = True):
        if self._initialized: return
        self._subscribers = defaultdict(list) # List[Tuple[Callable, bool]] (handler, is_async)
        self._global_subscribers = [] # List[Tuple[Callable, bool]]
        self._global_subscriber_keys = {}
        self._legacy_dict_warnings = set()
        self._legacy_dict_event_count = 0
        self._legacy_dict_event_types = defaultdict(int)
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
                # Check for async marker from decorator
                is_async = getattr(method, "_is_async", False)
                self.subscribe(method._event_type, method, is_async=is_async)

    def subscribe(self, event_type: str, handler: Callable, is_async: bool = False):
        key = event_type.value if hasattr(event_type, 'value') else event_type
        with self._lock:
            # Check if already subscribed to avoid duplicates
            if not any(h[0] is handler for h in self._subscribers[key]):
                self._subscribers[key].append((handler, is_async))

    def subscribe_all(self, handler: Callable, key: Optional[str] = None, replace: bool = False, is_async: bool = False):
        """
        Register a global subscriber.
        """
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

    def publish(self, event: Any):
        """
        Unified publication portal.
        Dispatches events to specific and global subscribers.
        """
        key = self._event_key(event)
        if isinstance(event, dict):
            source = event.get("source", "unknown")
            warning_key = (key, source)
            with self._lock:
                self._legacy_dict_event_count += 1
                self._legacy_dict_event_types[key] += 1
                should_warn = warning_key not in self._legacy_dict_warnings
                if should_warn:
                    self._legacy_dict_warnings.add(warning_key)
            if should_warn:
                logger.warning(
                    "[EventBus] legacy dict event published: type=%s source=%s",
                    key, source
                )
        with self._lock:
            self._sequence_counter += 1
            handlers = list(self._subscribers.get(key, []))
            global_handlers = list(self._global_subscribers)

        # Combine handlers to avoid code duplication
        all_handlers = handlers + global_handlers

        for handler, is_async in all_handlers:
            if is_async:
                self._dispatch_async(handler, event)
            else:
                self._safe_execute(handler, event)

    def _dispatch_async(self, handler: Callable, event: Any):
        """Offloads execution to the background AsyncRuntime."""
        try:
            from backend.application.container import container
            runtime = container.get("runtime")
            loop = container.get("loop")

            if not runtime or not loop or not loop.is_running():
                self._safe_execute(handler, event)
                return

            if asyncio.iscoroutinefunction(handler):
                runtime.run_task(handler(event))
            else:
                # Use call_soon_threadsafe to ensure sequential execution on the background loop
                # instead of concurrent execution in a thread pool executor.
                loop.call_soon_threadsafe(self._safe_execute, handler, event)
        except Exception as e:
            logger.debug(f"[EventBus] Async dispatch failed for {handler}: {e}")
            self._safe_execute(handler, event)

    def _safe_execute(self, handler: Callable, event: Any):
        """Executes handler with basic error protection."""
        try:
            handler(event)
        except Exception as e:
            handler_name = getattr(handler, "__name__", repr(handler))
            logger.error(f"[EventBus] Dispatch Error in {handler_name}: {e}", exc_info=True)

            # Broadcast system error event to allow UI/Services to react.
            try:
                from backend.events.event_types import EventType
                from backend.events.models.base_event import BaseEvent
                error_payload = {
                    "handler": handler_name,
                    "error": str(e),
                    "event_type": self._event_key(event)
                }
                if self._is_system_error(event) or getattr(self._system_error_guard, "active", False):
                    self._record_dead_letter(event, handler_name, e)
                    return
                try:
                    self._system_error_guard.active = True
                    self.publish(BaseEvent.create(
                        event_type=EventType.SYSTEM_ERROR,
                        source="event_bus",
                        payload=error_payload,
                    ))
                finally:
                    self._system_error_guard.active = False
            except Exception:
                logger.error("[EventBus] Failed to publish SYSTEM_ERROR", exc_info=True)

    def _event_key(self, event: Any) -> str:
        if hasattr(event, "event_type"):
            key = getattr(event, "event_type")
        elif isinstance(event, dict):
            key = event.get("type") or event.get("event_type") or "unknown"
        elif hasattr(event, "type"):
            key = getattr(event, "type")
        else:
            key = "unknown"
        return str(key.value if hasattr(key, "value") else key)

    def _is_system_error(self, event: Any) -> bool:
        return self._event_key(event) == "SYSTEM_ERROR"

    def _record_dead_letter(self, event: Any, handler_name: str, exc: Exception):
        with self._lock:
            self._dead_letter_count += 1
        logger.error(
            "[EventBus] Dead-lettered event type=%s handler=%s error=%s",
            self._event_key(event),
            handler_name,
            exc,
        )

    def emit(self, event_type, data=None):
        self.publish({"type": event_type, "payload": data or {}})

    def stats(self) -> Dict[str, Any]:
        """Return observability counters without exposing handler internals."""
        with self._lock:
            return {
                "sequence": self._sequence_counter,
                "event_types": len(self._subscribers),
                "specific_subscribers": sum(len(items) for items in self._subscribers.values()),
                "global_subscribers": len(self._global_subscribers),
                "keyed_global_subscribers": len(self._global_subscriber_keys),
                "dead_letters": self._dead_letter_count,
                "legacy_dict_events": self._legacy_dict_event_count,
                "legacy_dict_event_types": dict(self._legacy_dict_event_types),
            }

    def reset_for_tests(self) -> None:
        """Reset subscribers and diagnostics for isolated unit tests."""
        with self._lock:
            self._subscribers.clear()
            self._global_subscribers.clear()
            self._global_subscriber_keys.clear()
            self._legacy_dict_warnings.clear()
            self._legacy_dict_event_count = 0
            self._legacy_dict_event_types.clear()
            self._sequence_counter = 0
            self._dead_letter_count = 0

# Canonical Singleton
bus = EventBus()
