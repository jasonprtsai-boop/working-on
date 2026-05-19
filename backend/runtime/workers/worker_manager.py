import logging
import threading
import asyncio
import inspect
from typing import Dict, Any, Optional

logger = logging.getLogger("WorkerManager")

class WorkerManager:
    """
    [Industrial Authority] Background Task Lifecycle Controller.
    Responsible for starting, stopping, and monitoring all background workers.
    Ensures graceful shutdown and prevents zombie threads.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._workers = {}
                cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized: return
        self._initialized = True
        self._async_tasks = []
        logger.info("WorkerManager initialized.")

    def register_worker(self, name: str, worker_instance: Any):
        with self._lock:
            self._workers[name] = worker_instance

    async def start_task(self, coro):
        """Starts an asyncio task and tracks it for shutdown."""
        task = asyncio.create_task(coro)
        self._async_tasks.append(task)
        return task

    def start_all(self):
        from backend.application.container import container
        runtime = container.get("runtime")
        if not runtime:
            logger.error("AsyncRuntime not found in container. Cannot start workers.")
            return

        for name, worker in self._workers.items():
            if hasattr(worker, "start"):
                try:
                    started = worker.start()
                    if inspect.isawaitable(started):
                        runtime.run_task(started)
                except Exception:
                    logger.exception(f"Failed to start worker: {name}")

    async def shutdown(self):
        """Graceful shutdown for both threads and async tasks."""
        logger.info("Shutting down...")
        # 1. Stop threads
        for name, worker in self._workers.items():
            if hasattr(worker, "stop"):
                try:
                    stopped = worker.stop()
                    if inspect.isawaitable(stopped):
                        await stopped
                except Exception:
                    logger.exception(f"Failed to stop worker: {name}")

        # 2. Cancel async tasks
        for task in self._async_tasks:
            task.cancel()

        if self._async_tasks:
            await asyncio.gather(*self._async_tasks, return_exceptions=True)
            self._async_tasks.clear()
        logger.info("Shutdown complete.")

    def shutdown_sync(self, runtime: Optional[Any] = None, timeout: float = 5.0):
        """Run shutdown from synchronous teardown hooks without losing async stops."""
        async def _shutdown():
            await self.shutdown()

        loop = getattr(runtime, "_loop", None) if runtime else None
        if loop and loop.is_running():
            future = runtime.run_task(_shutdown())
            return future.result(timeout=timeout)

        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop and running_loop.is_running():
            return running_loop.create_task(_shutdown())

        return asyncio.run(_shutdown())

    def list_workers(self) -> Dict[str, str]:
        """List current workers and their status (if available)."""
        return {name: (getattr(worker, "status", "unknown")) for name, worker in self._workers.items()}

    def status_snapshot(self) -> Dict[str, Dict[str, Any]]:
        """Structured worker state for diagnostics and health endpoints."""
        snapshot: Dict[str, Dict[str, Any]] = {}
        for name, worker in self._workers.items():
            task = getattr(worker, "_task", None)
            thread = getattr(worker, "_thread", None)
            snapshot[name] = {
                "status": getattr(worker, "status", "running" if getattr(worker, "is_running", False) else "unknown"),
                "is_running": bool(getattr(worker, "is_running", False)),
                "task_done": bool(task.done()) if task is not None and hasattr(task, "done") else None,
                "thread_alive": bool(thread.is_alive()) if thread is not None and hasattr(thread, "is_alive") else None,
                "last_error": getattr(worker, "last_error", None),
            }
            if hasattr(worker, "stats"):
                try:
                    snapshot[name]["stats"] = worker.stats()
                except Exception as exc:
                    snapshot[name]["stats_error"] = str(exc)
        return snapshot

# Canonical Singleton
worker_manager = WorkerManager()
