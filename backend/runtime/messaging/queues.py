import asyncio
from typing import Any

class AsyncQueueManager:
    """
    [Runtime Layer] Centralized Queue Manager for Industrial Pipeline.
    Enforces 'Latest Frame Overwrite' to prevent latency buildup.
    """
    def __init__(self):
        self._frame_queue = None
        self._detect_queue = None
        self._robot_queue = None

    @staticmethod
    def _queue(maxsize: int) -> asyncio.Queue:
        return asyncio.Queue(maxsize=maxsize)

    @property
    def frame_queue(self) -> asyncio.Queue:
        # maxsize=1 ensures we always process the freshest frame.
        if self._frame_queue is None:
            self._frame_queue = self._queue(maxsize=1)
        return self._frame_queue

    @property
    def detect_queue(self) -> asyncio.Queue:
        if self._detect_queue is None:
            self._detect_queue = self._queue(maxsize=1)
        return self._detect_queue

    @property
    def robot_queue(self) -> asyncio.Queue:
        if self._robot_queue is None:
            self._robot_queue = self._queue(maxsize=10)
        return self._robot_queue

    async def put_latest(self, queue: asyncio.Queue, item: Any):
        """Standard industrial 'Drop Oldest' logic."""
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        await queue.put(item)

queue_manager = AsyncQueueManager()
