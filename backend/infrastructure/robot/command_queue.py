import queue
import logging
from backend.utils import config

logger = logging.getLogger("RobotCommandQueue")

class RobotCommandQueue:
    def __init__(self):
        self._queue = queue.Queue(maxsize=max(1, int(getattr(config, "ROBOT_COMMAND_QUEUE_SIZE", 200))))

    def enqueue(self, command):
        try:
            self._queue.put_nowait(command)
            return True
        except queue.Full:
            logger.warning("[RobotCommandQueue] command dropped because queue is full")
            return False

    def dequeue(self):
        try:
            return self._queue.get(block=False)
        except queue.Empty:
            return None

    def clear(self):
        with self._queue.mutex:
            self._queue.queue.clear()

    def qsize(self):
        return self._queue.qsize()
