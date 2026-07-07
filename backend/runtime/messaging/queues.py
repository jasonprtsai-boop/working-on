from __future__ import annotations

import asyncio
import time
from typing import Any
from collections import defaultdict
from enum import Enum

class QueuePolicy(str, Enum):
    LATEST_ONLY = "latest-only"
    BOUNDED = "bounded"
    BOUNDED_WITH_WARNING = "bounded-with-warning"

class ManagedAsyncQueue(asyncio.Queue):
    def __init__(self, manager: "AsyncQueueManager", name: str, maxsize: int):
        super().__init__(maxsize=maxsize)
        self._manager = manager
        self._managed_name = name
        self._suppress_get_record = False

    async def get(self):
        self._suppress_get_record = True
        try:
            item = await super().get()
        finally:
            self._suppress_get_record = False
        self._manager._record_get(self._managed_name)
        return item

    def get_nowait(self):
        item = super().get_nowait()
        if not self._suppress_get_record:
            self._manager._record_get(self._managed_name)
        return item

    def drop_oldest_nowait(self):
        return super().get_nowait()


class AsyncQueueManager:
    """
    [Runtime Layer] Centralized Queue Manager for Industrial Pipeline.
    Enforces 'Latest Frame Overwrite' to prevent latency buildup.
    """
    def __init__(self):
        self._frame_queue = None
        self._detect_queue = None
        self._robot_queue = None
        self._queue_names = {}
        self._queue_policies = {}
        self._drop_counts = defaultdict(int)
        self._put_counts = defaultdict(int)
        self._get_counts = defaultdict(int)
        self._last_put_at = defaultdict(float)
        self._last_get_at = defaultdict(float)
        self._last_drop_at = defaultdict(float)
        self._max_observed_size = defaultdict(int)
        self._blocked_after_sec = 5.0

    def _queue(self, name: str, maxsize: int) -> asyncio.Queue:
        return ManagedAsyncQueue(self, name=name, maxsize=maxsize)

    def _register(self, name: str, queue: asyncio.Queue, policy: QueuePolicy) -> asyncio.Queue:
        self._queue_names[id(queue)] = name
        self._queue_policies[name] = policy.value if isinstance(policy, QueuePolicy) else policy
        return queue

    @property
    def frame_queue(self) -> asyncio.Queue:
        # maxsize=1 ensures we always process the freshest frame.
        if self._frame_queue is None:
            self._frame_queue = self._register("frame", self._queue("frame", maxsize=1), QueuePolicy.LATEST_ONLY)
        return self._frame_queue

    @property
    def detect_queue(self) -> asyncio.Queue:
        if self._detect_queue is None:
            self._detect_queue = self._register("detect", self._queue("detect", maxsize=1), QueuePolicy.LATEST_ONLY)
        return self._detect_queue

    @property
    def robot_queue(self) -> asyncio.Queue:
        if self._robot_queue is None:
            self._robot_queue = self._register("robot", self._queue("robot", maxsize=10), QueuePolicy.BOUNDED)
        return self._robot_queue

    async def put_latest(self, queue: asyncio.Queue, item: Any):
        """Standard industrial 'Drop Oldest' logic."""
        name = self._queue_names.get(id(queue), "unknown")
        if queue.full():
            try:
                if hasattr(queue, "drop_oldest_nowait"):
                    queue.drop_oldest_nowait()
                else:
                    queue.get_nowait()
                self._drop_counts[name] += 1
                self._last_drop_at[name] = time.time()
            except asyncio.QueueEmpty:
                pass
        await queue.put(item)
        self._record_put(name, queue)

    def _record_put(self, name: str, queue: asyncio.Queue) -> None:
        self._put_counts[name] += 1
        self._last_put_at[name] = time.time()
        self._max_observed_size[name] = max(int(self._max_observed_size.get(name, 0)), queue.qsize())

    def _record_get(self, name: str) -> None:
        self._get_counts[name] += 1
        self._last_get_at[name] = time.time()

    def stats(self) -> dict:
        now = time.time()

        def queue_state(name: str, queue: asyncio.Queue | None) -> dict:
            last_put_at = float(self._last_put_at.get(name, 0.0) or 0.0)
            age_sec = max(0.0, now - last_put_at) if last_put_at else 0.0
            if queue is None:
                return {
                    "initialized": False,
                    "size": 0,
                    "maxsize": 0,
                    "full": False,
                    "empty": True,
                    "policy": self._queue_policies.get(name, "unknown"),
                    "dropped_oldest": int(self._drop_counts.get(name, 0)),
                    "put_count": int(self._put_counts.get(name, 0)),
                    "get_count": int(self._get_counts.get(name, 0)),
                    "last_put_at": last_put_at,
                    "last_get_at": float(self._last_get_at.get(name, 0.0) or 0.0),
                    "last_drop_at": float(self._last_drop_at.get(name, 0.0) or 0.0),
                    "age_sec": age_sec,
                    "consumer_idle_sec": 0.0,
                    "utilization": 0.0,
                    "max_observed_size": int(self._max_observed_size.get(name, 0)),
                    "blocked": False,
                    "blocked_reason": None,
                    "status": "idle",
                }
            size = queue.qsize()
            full = queue.full()
            last_get_at = float(self._last_get_at.get(name, 0.0) or 0.0)
            consumer_idle_sec = max(0.0, now - last_get_at) if last_get_at else age_sec
            stale_item = bool(size > 0 and last_put_at and age_sec >= self._blocked_after_sec)
            blocked = bool(full or stale_item)
            blocked_reason = "full" if full else ("stale_item" if stale_item else None)
            maxsize = int(queue.maxsize or 0)
            utilization = (float(size) / float(maxsize)) if maxsize else 0.0
            dropped = int(self._drop_counts.get(name, 0))
            status = "blocked" if blocked else ("warning" if dropped else ("processing" if size else "idle"))
            return {
                "initialized": True,
                "size": size,
                "maxsize": maxsize,
                "full": full,
                "empty": queue.empty(),
                "policy": self._queue_policies.get(name, "unknown"),
                "dropped_oldest": dropped,
                "put_count": int(self._put_counts.get(name, 0)),
                "get_count": int(self._get_counts.get(name, 0)),
                "last_put_at": last_put_at,
                "last_get_at": last_get_at,
                "last_drop_at": float(self._last_drop_at.get(name, 0.0) or 0.0),
                "age_sec": age_sec,
                "consumer_idle_sec": consumer_idle_sec,
                "utilization": round(utilization, 4),
                "max_observed_size": int(self._max_observed_size.get(name, 0)),
                "blocked": blocked,
                "blocked_reason": blocked_reason,
                "status": status,
            }

        return {
            "frame": queue_state("frame", self._frame_queue),
            "detect": queue_state("detect", self._detect_queue),
            "robot": queue_state("robot", self._robot_queue),
        }

queue_manager = AsyncQueueManager()
