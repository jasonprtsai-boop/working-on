from queue import Queue
from .robot_command import RobotCommand
from typing import Optional

class RobotQueue:
    """
    Deprecated legacy queue for robotic movement commands.

    RobotFacade.execute_move() is the active v1 command authority. This queue is
    retained for E-Stop cleanup compatibility and should not gain new consumers.
    """
    DEPRECATED_ACTIVE_CONSUMER = False

    def __init__(self):
        self.queue = Queue()

    def enqueue(self, command: RobotCommand):
        self.queue.put(command)

    def dequeue(self, timeout_sec: float = 0.2) -> Optional[RobotCommand]:
        try:
            return self.queue.get(timeout=float(timeout_sec))
        except Exception:
            return None

    def clear(self) -> int:
        """Best-effort clear of queued commands. Returns number removed."""
        removed = 0
        while True:
            try:
                self.queue.get_nowait()
                removed += 1
            except Exception:
                break
        return removed

# Global Instance
robot_queue = RobotQueue()
