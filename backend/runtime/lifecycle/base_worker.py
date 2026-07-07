import asyncio
import logging
import time
from abc import ABC, abstractmethod

logger = logging.getLogger("BaseWorker")

class BaseWorker(ABC):
    """
    [Runtime Layer] Base class for all industrial background workers.
    Ensures consistent lifecycle management and health reporting.
    """
    def __init__(self, name: str):
        self.name = name
        self.is_running = False
        self._task: asyncio.Task = None
        self.status = "IDLE"
        self.last_error = None
        self.started_at = None
        self.stopped_at = None
        self.failure_count = 0

    @abstractmethod
    async def run(self):
        """Main execution loop for the worker."""
        pass

    async def start(self):
        if self.is_running:
            return
        self.is_running = True
        self.status = "STARTING"
        self.started_at = time.time()
        self.stopped_at = None
        logger.info(f"[Worker:{self.name}] Starting...")
        self._task = asyncio.create_task(self._run_guarded())
        self.status = "RUNNING"

    async def _run_guarded(self):
        try:
            await self.run()
            if self.is_running and self.status not in {"STOPPING", "STOPPED"}:
                self.status = "STOPPED"
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.failure_count += 1
            self.last_error = str(exc)
            self.status = "FAILED"
            self.is_running = False
            logger.error(f"[Worker:{self.name}] Fatal error: {exc}", exc_info=True)
            self._publish_worker_failure(exc)
        finally:
            if self.status != "RUNNING":
                self.is_running = False
            self.stopped_at = time.time()

    async def stop(self):
        if not self.is_running:
            return
        self.is_running = False
        self.status = "STOPPING"
        logger.info(f"[Worker:{self.name}] Stopping...")
        if self._task:
            self._task.cancel()
            await asyncio.sleep(0)
            if not self._task.done():
                self.last_error = "stop_pending_cancel"
                logger.debug(f"[Worker:{self.name}] Stop requested; task left for runtime cancellation.")
            self._task = None
        self.status = "STOPPED"
        self.stopped_at = time.time()
        logger.info(f"[Worker:{self.name}] Stopped.")

    def request_stop(self):
        """Thread-safe best-effort stop signal for process teardown hooks."""
        self.is_running = False
        self.status = "STOPPING"
        task = self._task
        if task and hasattr(task, "cancel"):
            try:
                loop = task.get_loop() if hasattr(task, "get_loop") else None
                if loop and loop.is_running():
                    loop.call_soon_threadsafe(task.cancel)
                else:
                    task.cancel()
            except Exception:
                logger.debug(f"[Worker:{self.name}] request_stop cancellation degraded.", exc_info=True)
        self._task = None
        self.status = "STOPPED"
        self.stopped_at = time.time()

    async def healthcheck(self) -> bool:
        """Returns True if the worker is healthy."""
        return self.is_running and (self._task is not None and not self._task.done())

    def stats(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "is_running": self.is_running,
            "last_error": self.last_error,
            "failure_count": self.failure_count,
            "started_at": self.started_at,
            "stopped_at": self.stopped_at,
        }

    def _publish_worker_failure(self, exc: Exception) -> None:
        try:
            from backend.events.bus.event_bus import bus
            from backend.events.event_types import EventType
            from backend.events.models.base_event import BaseEvent

            bus.publish(BaseEvent.create(
                event_type=EventType.DIAGNOSTICS_UPDATED,
                source="base_worker",
                payload={
                    "workers": {
                        self.name: {
                            "status": self.status,
                            "last_error": self.last_error,
                            "failure_count": self.failure_count,
                        }
                    },
                    "worker_failure": {
                        "name": self.name,
                        "error": str(exc),
                    },
                },
            ))
        except Exception:
            logger.debug("[Worker:%s] Failed to publish worker failure diagnostics.", self.name, exc_info=True)
