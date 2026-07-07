import asyncio
import threading
import logging
from typing import Optional, Coroutine, Any, Dict

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
                cls._instance._futures = set()
                cls._instance._submitted_count = 0
                cls._instance._completed_count = 0
                cls._instance._failed_count = 0
                cls._instance._cancelled_count = 0
                cls._instance._last_error = None
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
            try:
                self._loop.run_until_complete(self._loop.shutdown_asyncgens())
                if hasattr(self._loop, "shutdown_default_executor"):
                    self._loop.run_until_complete(self._loop.shutdown_default_executor())
            except Exception:
                logger.debug("AsyncRuntime loop shutdown cleanup degraded.", exc_info=True)
            finally:
                self._loop.close()
                logger.debug("Background asyncio loop closed.")

    def run_task(self, coro: Coroutine, name: Optional[str] = None):
        """Submit a coroutine to the background loop from any thread."""
        if self._loop is None or not self._loop.is_running():
            raise RuntimeError("AsyncRuntime loop not started.")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        with self._lock:
            self._submitted_count += 1
            self._futures.add(future)
        future.add_done_callback(lambda done: self._observe_future(done, name=name))
        return future

    def _observe_future(self, future, name: Optional[str] = None) -> None:
        with self._lock:
            self._futures.discard(future)
            self._completed_count += 1

        label = name or "background_task"
        try:
            if future.cancelled():
                with self._lock:
                    self._cancelled_count += 1
                return
            exc = future.exception()
        except Exception as exc:
            with self._lock:
                self._failed_count += 1
                self._last_error = str(exc)
            logger.warning(
                "[AsyncRuntime] failed to inspect task result for %s: %s",
                label,
                exc,
                exc_info=(type(exc), exc, exc.__traceback__),
            )
            return

        if exc is not None:
            with self._lock:
                self._failed_count += 1
                self._last_error = str(exc)
            logger.error(
                "[AsyncRuntime] task failed: %s: %s",
                label,
                exc,
                exc_info=(type(exc), exc, exc.__traceback__),
            )

    def stats(self) -> Dict[str, Any]:
        thread_alive = bool(self._thread and self._thread.is_alive())
        loop_running = bool(self._loop and self._loop.is_running())
        with self._lock:
            return {
                "thread_alive": thread_alive,
                "loop_running": loop_running,
                "submitted": self._submitted_count,
                "completed": self._completed_count,
                "failed": self._failed_count,
                "cancelled": self._cancelled_count,
                "pending": len(self._futures),
                "last_error": self._last_error,
            }

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
            loop = self._loop
            thread = self._thread

        if loop and loop.is_running():
            if thread is not threading.current_thread():
                try:
                    future = asyncio.run_coroutine_threadsafe(_cancel_pending_tasks(), loop)
                    future.result(timeout=2.0)
                except Exception:
                    logger.debug("AsyncRuntime pending task cancellation degraded.", exc_info=True)
            loop.call_soon_threadsafe(loop.stop)

        if thread and thread is not threading.current_thread():
            thread.join(timeout=2.0)

        with self._lock:
            self._futures.clear()
            if self._thread is thread:
                self._thread = None
            if self._loop is loop:
                self._loop = None
        logger.info("AsyncRuntime stopped.")

# Global Singleton
runtime = AsyncRuntime()
