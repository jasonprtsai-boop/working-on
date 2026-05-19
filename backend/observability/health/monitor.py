import threading
import time
from typing import Dict

import psutil

from backend.events.bus.event_bus import bus
from backend.events.event_types import EventType
from backend.events.models.base_event import BaseEvent
from backend.utils.logger import logger


class HealthMonitor:
    def __init__(self, interval_sec: float = 2.0):
        self.interval_sec = float(interval_sec)
        self._thread = None
        self._stop = threading.Event()

    def snapshot(self) -> Dict[str, float]:
        proc = psutil.Process()
        return {
            "cpu_percent": float(psutil.cpu_percent(interval=None)),
            "memory_mb": float(proc.memory_info().rss / (1024 * 1024)),
            "threads": float(proc.num_threads()),
        }

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="HealthMonitor")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread and threading.current_thread() is not self._thread:
            self._thread.join(timeout=1.0)

    def _run(self):
        while not self._stop.is_set():
            try:
                bus.publish(BaseEvent.create(
                    event_type=EventType.DIAGNOSTICS_UPDATED,
                    source="health_monitor",
                    payload={"health": self.snapshot()},
                ))
            except Exception:
                logger.debug("[HealthMonitor] publish failed", exc_info=True)
            time.sleep(self.interval_sec)


health_monitor = HealthMonitor()
