import threading
import time
from backend.events.bus.event_bus import bus
from backend.events.event_types import EventType
from backend.events.models.base_event import BaseEvent
from backend.infrastructure.robot.queue.robot_queue import robot_queue
from backend.utils.logger import logger

class RobotWorker:
    """
    Deprecated legacy worker.

    The active v1 actuation authority is RobotFacade.execute_move(). This class
    remains importable for compatibility, but is not registered by WorkerManager.
    """
    DEPRECATED_ACTIVE_CONSUMER = False
    def __init__(self, controller=None):
        self.controller = controller
        self._stop = threading.Event()
        self._thread = None
        self.status = "IDLE"

    def start(self):
        """Start the background execution thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="RobotWorker")
        self._thread.start()
        self.status = "RUNNING"
        logger.info("[RobotWorker] Thread started.")

    def stop(self):
        """Gracefully stop the background thread."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self.status = "STOPPED"
        logger.info("[RobotWorker] Thread stopped.")

    def _run(self):
        while not self._stop.is_set():
            command = robot_queue.dequeue(timeout_sec=0.2)
            if not command:
                continue

            try:
                self.status = "BUSY"
                command.status = "EXECUTING"
                # Simulate physical movement
                logger.info(f"[RobotWorker] Executing: {command.move} (Trace: {command.trace_id})")

                # In real app: self.controller.move(command.move)
                time.sleep(1.0)

                command.status = "COMPLETED"
                bus.publish(BaseEvent.create(
                    event_type=EventType.ROBOT_MOVE_COMPLETED,
                    source="robot_worker",
                    payload={"move": command.move, "status": "SUCCESS"},
                    trace_id=command.trace_id
                ))
            except Exception as e:
                logger.error(f"[RobotWorker] Execution Error: {e}", exc_info=True)
                command.status = "FAILED"
                bus.publish(BaseEvent.create(
                    event_type=EventType.ROBOT_MOVE_COMPLETED,
                    source="robot_worker",
                    payload={"move": command.move, "status": "FAILED", "error": str(e)},
                    trace_id=command.trace_id
                ))
            finally:
                self.status = "RUNNING"

# Initialized via WorkerManager later
robot_worker = RobotWorker()
