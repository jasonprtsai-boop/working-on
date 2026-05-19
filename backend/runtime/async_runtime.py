import asyncio
import threading
import logging
from typing import Optional, Coroutine

logger = logging.getLogger("AsyncRuntime")

class AsyncRuntime:
    """
    [Production Architecture] Unified Asyncio Event Loop Manager.
    Responsibility: Managing a dedicated background thread for all async tasks.
    Ensures thread-safe task submission and graceful lifecycle management.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._loop: Optional[asyncio.AbstractEventLoop] = None
                cls._instance._thread: Optional[threading.Thread] = None
                cls._instance._stop_event = threading.Event()
        return cls._instance

    def start(self):
        """Initializes the background event loop and its manager thread."""
        with self._lock:
            if self._thread and self._thread.is_alive():
                return

            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, name="AsyncRuntimeThread", daemon=True)
            self._thread.start()

            # Wait for loop to be ready
            import time
            timeout = 5.0
            start_time = time.time()
            while self._loop is None or not self._loop.is_running():
                if time.time() - start_time > timeout:
                    raise RuntimeError("AsyncRuntime failed to start within timeout.")
                time.sleep(0.1)

            logger.info("AsyncRuntime background loop is running.")

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        logger.debug("Starting background asyncio loop...")
        try:
            self._loop.run_forever()
        finally:
            self._loop.close()
            logger.debug("Background asyncio loop closed.")

    def run_task(self, coro: Coroutine):
        """Submit a coroutine to the background loop from any thread."""
        if self._loop is None or not self._loop.is_running():
            raise RuntimeError("AsyncRuntime loop not started.")
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def stop(self):
        """Gracefully stop the background loop and wait for the thread to exit."""
        async def _cancel_pending_tasks():
            current = asyncio.current_task()
            pending = [
                task for task in asyncio.all_tasks()
                if task is not current and not task.done()
            ]
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

        with self._lock:
            if self._loop and self._loop.is_running():
                if self._thread is not threading.current_thread():
                    try:
                        future = asyncio.run_coroutine_threadsafe(_cancel_pending_tasks(), self._loop)
                        future.result(timeout=2.0)
                    except Exception:
                        logger.debug("AsyncRuntime pending task cancellation degraded.", exc_info=True)
                self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread:
                self._thread.join(timeout=2.0)
            self._thread = None
            self._loop = None
            logger.info("AsyncRuntime stopped.")

# Global Singleton
runtime = AsyncRuntime()
