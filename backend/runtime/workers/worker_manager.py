import logging
import threading
import asyncio
import inspect
import concurrent.futures
from typing import Dict, Any, Optional
from backend.runtime.lifecycle.worker_protocol import WorkerProtocol

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
                cls._instance._workers: Dict[str, WorkerProtocol] = {}
                cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized: return
        self._initialized = True
        self._async_tasks = []
        logger.info("WorkerManager initialized.")

    def register_worker(self, name: str, worker_instance: WorkerProtocol):
        with self._lock:
            self._workers[name] = worker_instance

    async def start_task(self, coro):
        """Starts an asyncio task and tracks it for shutdown."""
        task = asyncio.create_task(coro)
        self._async_tasks.append(task)
        return task

    def start_all(self) -> Dict[str, Dict[str, Any]]:
        from backend.application.container import container
        runtime = container.get("runtime")
        results: Dict[str, Dict[str, Any]] = {}
        if not runtime:
            logger.error("AsyncRuntime not found in container. Cannot start workers.")
            return {"_runtime": {"started": False, "error": "AsyncRuntime not found"}}

        for name, worker in self._workers.items():
            result = {"started": False, "error": None}
            if hasattr(worker, "start"):
                try:
                    started = worker.start()
                    if inspect.isawaitable(started):
                        future = runtime.run_task(started, name=f"worker_start:{name}")
                        if hasattr(future, "result"):
                            future.result(timeout=2.0)
                    snapshot = self._worker_snapshot(worker)
                    result["started"] = self._worker_is_started(snapshot)
                    result["status"] = snapshot.get("status")
                    result["task_done"] = snapshot.get("task_done")
                    result["thread_alive"] = snapshot.get("thread_alive")
                except Exception:
                    logger.exception(f"Failed to start worker: {name}")
                    result["error"] = "start_failed"
                    try:
                        worker.last_error = "start_failed"
                    except Exception:
                        pass
            else:
                result["error"] = "missing_start"
            results[name] = result
        return results

    async def shutdown(self):
        """Graceful shutdown for both threads and async tasks."""
        logger.info("Shutting down...")
        # 1. Stop threads
        for name, worker in self._workers.items():
            if hasattr(worker, "stop"):
                try:
                    stopped = worker.stop()
                    if inspect.isawaitable(stopped):
                        await asyncio.wait_for(stopped, timeout=3.0)
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
        runtime_thread = getattr(runtime, "_thread", None) if runtime else None
        if loop and loop.is_running() and runtime_thread is not threading.current_thread():
            return self._shutdown_sync_via_runtime(runtime, timeout=timeout)
        if loop and loop.is_running():
            return loop.create_task(_shutdown())

        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop and running_loop.is_running():
            return running_loop.create_task(_shutdown())

        return asyncio.run(_shutdown())

    def _shutdown_sync_via_runtime(self, runtime: Any, timeout: float = 5.0) -> Dict[str, Any]:
        """Stop workers from a non-runtime thread with per-worker diagnostics."""
        results: Dict[str, Any] = {"completed": True, "workers": {}}
        per_worker_timeout = max(1.0, min(5.0, float(timeout)))

        for name, worker in list(self._workers.items()):
            result = {"stopped": False, "error": None}
            if not hasattr(worker, "stop"):
                result["stopped"] = True
                results["workers"][name] = result
                continue
            try:
                if hasattr(worker, "request_stop"):
                    worker.request_stop()
                    stopped = None
                else:
                    stopped = worker.stop()
                if inspect.isawaitable(stopped):
                    future = runtime.run_task(stopped, name=f"worker_stop:{name}")
                    future.result(timeout=per_worker_timeout)
                snapshot = self._worker_snapshot(worker)
                result["stopped"] = not bool(snapshot.get("is_running"))
                result["status"] = snapshot.get("status")
                result["task_done"] = snapshot.get("task_done")
                result["thread_alive"] = snapshot.get("thread_alive")
                result["last_error"] = snapshot.get("last_error")
            except concurrent.futures.TimeoutError:
                results["completed"] = False
                result["error"] = "stop_timeout"
                logger.warning("[WorkerManager] Worker stop timed out: %s", name)
            except Exception as exc:
                results["completed"] = False
                result["error"] = str(exc)
                logger.exception("[WorkerManager] Failed to stop worker: %s", name)
            results["workers"][name] = result

        try:
            future = runtime.run_task(self._cancel_tracked_async_tasks(), name="worker_manager.cancel_tracked")
            future.result(timeout=max(1.0, min(2.0, float(timeout))))
        except Exception as exc:
            results["completed"] = False
            results["tracked_tasks_error"] = str(exc)
            logger.debug("[WorkerManager] tracked async task cancellation degraded.", exc_info=True)

        logger.info("Shutdown complete.")
        return results

    async def _cancel_tracked_async_tasks(self):
        for task in self._async_tasks:
            task.cancel()
        if self._async_tasks:
            await asyncio.gather(*self._async_tasks, return_exceptions=True)
            self._async_tasks.clear()

    def list_workers(self) -> Dict[str, str]:
        """List current workers and their status (if available)."""
        return {name: (getattr(worker, "status", "unknown")) for name, worker in self._workers.items()}

    def status_snapshot(self) -> Dict[str, Dict[str, Any]]:
        """Structured worker state for diagnostics and health endpoints."""
        snapshot: Dict[str, Dict[str, Any]] = {}
        for name, worker in self._workers.items():
            snapshot[name] = self._worker_snapshot(worker)
            if hasattr(worker, "stats"):
                try:
                    snapshot[name]["stats"] = worker.stats()
                except Exception as exc:
                    snapshot[name]["stats_error"] = str(exc)
        return snapshot

    def runtime_snapshot(self, runtime: Optional[Any] = None) -> Dict[str, Any]:
        """Return background runtime health without exposing loop internals."""
        if runtime is None:
            try:
                from backend.application.container import container
                runtime = container.get("runtime")
            except Exception:
                runtime = None
        if runtime and hasattr(runtime, "stats"):
            try:
                return runtime.stats()
            except Exception as exc:
                return {"error": str(exc)}
        return {"available": False}

    def _worker_snapshot(self, worker: Any) -> Dict[str, Any]:
        task = getattr(worker, "_task", None)
        thread = getattr(worker, "_thread", None)
        task_done = bool(task.done()) if task is not None and hasattr(task, "done") else None
        task_cancelled = self._future_cancelled(task)
        task_error = self._future_error(task) if task_done else None
        thread_alive = bool(thread.is_alive()) if thread is not None and hasattr(thread, "is_alive") else None
        inferred_running = bool(getattr(worker, "is_running", False))
        if not inferred_running and task_done is False:
            inferred_running = True
        if not inferred_running and thread_alive is True:
            inferred_running = True
        status = getattr(worker, "status", "running" if inferred_running else "unknown")
        last_error = getattr(worker, "last_error", None) or task_error
        if task_error and status not in {"STOPPED", "STOPPING"}:
            status = "FAILED"
        return {
            "status": status,
            "is_running": inferred_running,
            "task_done": task_done,
            "task_cancelled": task_cancelled,
            "thread_alive": thread_alive,
            "last_error": last_error,
        }

    @staticmethod
    def _worker_is_started(snapshot: Dict[str, Any]) -> bool:
        if snapshot.get("last_error"):
            return False
        if snapshot.get("task_done") is True:
            return False
        if snapshot.get("thread_alive") is False:
            return False
        return bool(snapshot.get("is_running") or snapshot.get("task_done") is False or snapshot.get("thread_alive") is True)

    @staticmethod
    def _future_cancelled(task: Any) -> Optional[bool]:
        if task is None or not hasattr(task, "cancelled"):
            return None
        try:
            return bool(task.cancelled())
        except Exception:
            return None

    @staticmethod
    def _future_error(task: Any) -> Optional[str]:
        if task is None or not hasattr(task, "exception"):
            return None
        try:
            if hasattr(task, "cancelled") and task.cancelled():
                return None
            exc = task.exception()
        except BaseException as exc:
            if exc.__class__.__name__ in {"CancelledError", "InvalidStateError", "TimeoutError"}:
                return None
            return str(exc)
        return str(exc) if exc else None

# Canonical Singleton
worker_manager = WorkerManager()
