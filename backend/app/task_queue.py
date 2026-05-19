from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable, List

from backend.utils.logger import logger


@dataclass(frozen=True)
class ClearHook:
    key: str
    hook: Callable[[], None]
    kind: str = "work"


class TaskQueueRegistry:
    """
    Registry of "clear hooks" for in-flight background work.

    This project has multiple domain queues (engine/robot/etc.) that may or may not
    be instantiated in a given deployment. The E-Stop chain calls `clear()` to
    best-effort cancel pending work.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._clear_hooks: List[ClearHook] = []

    def register_clear_hook(self, hook: Callable[[], None], *, key: str | None = None, kind: str = "work") -> None:
        hook_key = key or f"{getattr(hook, '__module__', '')}.{getattr(hook, '__qualname__', repr(hook))}"
        with self._lock:
            if any(item.key == hook_key for item in self._clear_hooks):
                return
            self._clear_hooks.append(ClearHook(key=hook_key, hook=hook, kind=kind))

    def clear(self, *, include_observers: bool = False) -> None:
        with self._lock:
            hooks = [
                item for item in self._clear_hooks
                if include_observers or item.kind != "observer"
            ]

        failures = 0
        for item in hooks:
            try:
                item.hook()
            except Exception as e:
                failures += 1
                logger.error(f"[task_queue] clear hook failed for {item.key}: {e}")

        if hooks:
            logger.info(f"[task_queue] Cleared {len(hooks)} hook(s) with {failures} failure(s).")

    def hook_count(self, *, include_observers: bool = True) -> int:
        with self._lock:
            if include_observers:
                return len(self._clear_hooks)
            return sum(1 for item in self._clear_hooks if item.kind != "observer")


# Global singleton (import-safe)
task_queue = TaskQueueRegistry()
