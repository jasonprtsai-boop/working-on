from __future__ import annotations

import threading
import time
from typing import Optional

from backend.application.container import container
from backend.events.bus.event_bus import bus
from backend.events.event_types import EventType
from backend.utils.logger import logger


class RobotStatusWorker:
    """
    Periodically emits `ROBOT.STATUS_UPDATED` contract events.

    This keeps the frontend aware of connection/busy/error state even when no robot moves occur.
    """

    def __init__(self, interval_sec: float = 1.0):
        self.interval_sec = float(interval_sec)
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="RobotStatusWorker")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)

    def _run(self):
        while not self._stop.is_set():
            try:
                robot = container.get("robot")
                status = {}
                if robot and hasattr(robot, "get_status"):
                    status = robot.get_status() or {}
                from backend.events.models.base_event import BaseEvent
                bus.publish(BaseEvent.create(
                    event_type=EventType.ROBOT_STATUS_UPDATED,
                    source="robot_status_worker",
                    payload=status
                ))
            except Exception as e:
                logger.debug(f"[RobotStatusWorker] failed to emit status: {e}", exc_info=True)
            time.sleep(self.interval_sec)


robot_status_worker = RobotStatusWorker()
