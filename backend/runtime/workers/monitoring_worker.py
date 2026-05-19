import asyncio
import psutil
import time
from backend.runtime.lifecycle.base_worker import BaseWorker
from backend.events.bus.event_bus import bus
from backend.events.models.base_event import BaseEvent
from backend.events.event_types import EventType
from backend.utils.logger import logger

class MonitoringWorker(BaseWorker):
    """
    [Runtime Layer] System Health & Metrics Monitor.
    Periodically collects CPU, Memory, and Event Throughput metrics.
    """
    def __init__(self, interval_sec: float = 2.0):
        super().__init__("Monitoring")
        self.interval = interval_sec
        self.process = psutil.Process()

    async def run(self):
        logger.info("[MonitoringWorker] Started.")
        while self.is_running:
            try:
                # 1. Collect Hardware Metrics
                cpu_percent = psutil.cpu_percent()
                memory_info = self.process.memory_info()
                memory_mb = memory_info.rss / (1024 * 1024)

                # 2. Publish Diagnostics Event
                bus.publish(BaseEvent.create(
                    event_type=EventType.DIAGNOSTICS_UPDATED,
                    source="monitoring_worker",
                    payload={
                        "fps": 0.0,
                        "cpu_percent": cpu_percent,
                        "memory_mb": memory_mb,
                        "health": {
                            "fps": 0.0,
                            "cpu_percent": cpu_percent,
                            "memory_mb": memory_mb,
                            "timestamp": time.time()
                        }
                    }
                ))

                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[MonitoringWorker] Error: {e}")
                await asyncio.sleep(5.0)

monitoring_worker = MonitoringWorker()
