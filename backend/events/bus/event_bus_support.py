from __future__ import annotations

from collections import defaultdict
import asyncio
from typing import Any, Callable, Dict

from backend.utils.logger import logger


def event_key(event: Any) -> str:
    if hasattr(event, "event_type"):
        key = getattr(event, "event_type")
    elif isinstance(event, dict):
        key = event.get("type") or event.get("event_type") or "unknown"
    elif hasattr(event, "type"):
        key = getattr(event, "type")
    else:
        key = "unknown"
    return str(key.value if hasattr(key, "value") else key)


def handler_name(handler: Callable) -> str:
    return getattr(handler, "__name__", repr(handler))


class LegacyDictEventTracker:
    def __init__(self):
        self._warnings = set()
        self._count = 0
        self._event_types = defaultdict(int)

    def record(self, legacy_key: str, source: str, lock) -> bool:
        warning_key = (legacy_key, source)
        with lock:
            self._count += 1
            self._event_types[legacy_key] += 1
            should_warn = warning_key not in self._warnings
            if should_warn:
                self._warnings.add(warning_key)
            return should_warn

    def stats(self) -> dict:
        return {
            "legacy_dict_events": self._count,
            "legacy_dict_event_types": dict(self._event_types),
        }

    def reset(self) -> None:
        self._warnings.clear()
        self._count = 0
        self._event_types.clear()


def dispatch_async_handler(handler: Callable, event: Any, safe_execute: Callable[[Callable, Any], None]) -> None:
    try:
        from backend.application.container import container
        runtime = container.get("runtime")
        loop = container.get("loop")

        if not runtime or not loop or not loop.is_running():
            safe_execute(handler, event)
            return

        if asyncio.iscoroutinefunction(handler):
            runtime.run_task(handler(event))
        else:
            loop.call_soon_threadsafe(safe_execute, handler, event)
    except Exception as exc:
        logger.warning("[EventBus] Async dispatch failed for %s: %s", handler, exc, exc_info=True)
        safe_execute(handler, event)


def handle_dispatch_failure(
    *,
    event: Any,
    handler: Callable,
    exc: Exception,
    publish_system_error: Callable[[Any], None],
    record_dead_letter: Callable[[Any, str, Exception], None],
    system_error_guard,
) -> None:
    name = handler_name(handler)
    logger.error("[EventBus] Dispatch Error in %s: %s", name, exc, exc_info=True)
    try:
        from backend.events.event_types import EventType
        from backend.events.models.base_event import BaseEvent

        error_payload = {
            "handler": name,
            "error": str(exc),
            "event_type": event_key(event),
        }
        if event_key(event) == "SYSTEM_ERROR" or getattr(system_error_guard, "active", False):
            record_dead_letter(event, name, exc)
            return
        try:
            system_error_guard.active = True
            publish_system_error(BaseEvent.create(
                event_type=EventType.SYSTEM_ERROR,
                source="event_bus",
                payload=error_payload,
            ))
        finally:
            system_error_guard.active = False
    except Exception:
        logger.error("[EventBus] Failed to publish SYSTEM_ERROR", exc_info=True)


def log_dead_letter(event: Any, handler: str, exc: Exception) -> None:
    logger.error(
        "[EventBus] Dead-lettered event type=%s handler=%s error=%s",
        event_key(event),
        handler,
        exc,
    )


def stats_snapshot(
    *,
    sequence_counter: int,
    subscribers,
    global_subscribers,
    global_subscriber_keys,
    dead_letter_count: int,
    allow_legacy_dict_events: bool,
    legacy_stats: dict,
) -> Dict[str, Any]:
    snapshot = {
        "sequence": sequence_counter,
        "event_types": len(subscribers),
        "specific_subscribers": sum(len(items) for items in subscribers.values()),
        "global_subscribers": len(global_subscribers),
        "keyed_global_subscribers": len(global_subscriber_keys),
        "dead_letters": dead_letter_count,
        "legacy_dict_enabled": allow_legacy_dict_events,
    }
    snapshot.update(legacy_stats)
    return snapshot
