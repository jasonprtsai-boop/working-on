import asyncio
import logging
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

    @abstractmethod
    async def run(self):
        """Main execution loop for the worker."""
        pass

    async def start(self):
        if self.is_running:
            return
        self.is_running = True
        logger.info(f"[Worker:{self.name}] Starting...")
        self._task = asyncio.create_task(self.run())

    async def stop(self):
        if not self.is_running:
            return
        self.is_running = False
        logger.info(f"[Worker:{self.name}] Stopping...")
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(f"[Worker:{self.name}] Stopped.")

    async def healthcheck(self) -> bool:
        """Returns True if the worker is healthy."""
        return self.is_running and (self._task is not None and not self._task.done())
