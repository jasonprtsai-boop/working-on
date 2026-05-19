import asyncio
import time
from backend.runtime.lifecycle.base_worker import BaseWorker
from backend.events.bus.event_bus import bus
from backend.events.event_types import EventType
from backend.events.models.base_event import BaseEvent
from backend.utils.logger import logger

class RobotWatchdog(BaseWorker):
    """
    [Runtime Layer] Robot Watchdog
    監控機械手臂通訊狀態，若長時間無回應則發送警報。
    """
    def __init__(self, timeout_sec: float = 10.0):
        super().__init__("RobotWatchdog")
        self.timeout = timeout_sec
        self.last_heartbeat = time.time()
        self.is_healthy = True

    def start_monitoring(self):
        """Subscribe to robot status updates to reset the watchdog."""
        bus.subscribe(EventType.ROBOT_STATUS_UPDATED, self._on_status)
        bus.subscribe(EventType.ROBOT_MOVE_STARTED, self._on_status)

    def _on_status(self, event: BaseEvent):
        self.last_heartbeat = time.time()
        if not self.is_healthy:
            logger.info("[Watchdog] Robot communication restored.")
            self.is_healthy = True

    async def run(self):
        logger.info("[RobotWatchdog] Monitoring started.")
        while self.is_running:
            try:
                idle_time = time.time() - self.last_heartbeat

                if idle_time > self.timeout and self.is_healthy:
                    logger.error(f"[Watchdog] Robot silent for {idle_time:.1f}s. Possible connection loss.")
                    self.is_healthy = False

                    bus.publish(BaseEvent.create(
                        event_type=EventType.DIAGNOSTICS_UPDATED,
                        source="robot_watchdog",
                        payload={"robot_health": "DISCONNECTED", "idle_time": idle_time}
                    ))

                await asyncio.sleep(2.0)
            except Exception as e:
                logger.error(f"[RobotWatchdog] Loop error: {e}")
                await asyncio.sleep(5.0)

robot_watchdog = RobotWatchdog()
