import asyncio
import concurrent.futures
import unittest

from backend.runtime.async_runtime import AsyncRuntime
from backend.runtime.lifecycle.base_worker import BaseWorker
from backend.runtime.workers.monitoring_worker import MonitoringWorker
from backend.runtime.workers.worker_manager import WorkerManager
from backend.utils import config


class TestWorkerLifecycle(unittest.TestCase):
    def test_base_worker_marks_fatal_run_error_failed(self):
        class FailingWorker(BaseWorker):
            def __init__(self):
                super().__init__("UnitFailing")
                self.published = None

            async def run(self):
                raise RuntimeError("worker boom")

            def _publish_worker_failure(self, exc):
                self.published = str(exc)

        async def scenario():
            worker = FailingWorker()
            await worker.start()
            await asyncio.sleep(0.01)
            return worker

        worker = asyncio.run(scenario())

        self.assertFalse(worker.is_running)
        self.assertEqual(worker.status, "FAILED")
        self.assertEqual(worker.failure_count, 1)
        self.assertEqual(worker.last_error, "worker boom")
        self.assertEqual(worker.published, "worker boom")
        self.assertIsNotNone(worker.stopped_at)

    def test_base_worker_stop_is_bounded_when_run_ignores_cancel(self):
        class StubbornWorker(BaseWorker):
            def __init__(self):
                super().__init__("UnitStubborn")

            async def run(self):
                while True:
                    try:
                        await asyncio.sleep(60)
                    except asyncio.CancelledError:
                        continue

        async def scenario():
            worker = StubbornWorker()
            await worker.start()
            await worker.stop()
            return worker

        worker = asyncio.run(scenario())

        self.assertEqual(worker.status, "STOPPED")
        self.assertFalse(worker.is_running)
        self.assertIsNotNone(worker.stopped_at)

    def test_worker_manager_snapshot_surfaces_task_exception(self):
        future = concurrent.futures.Future()
        future.set_exception(RuntimeError("task boom"))

        class Worker:
            status = "RUNNING"
            is_running = True
            last_error = None
            _task = future
            _thread = None

        snapshot = WorkerManager()._worker_snapshot(Worker())

        self.assertEqual(snapshot["status"], "FAILED")
        self.assertEqual(snapshot["last_error"], "task boom")
        self.assertTrue(snapshot["task_done"])

    def test_monitoring_worker_uses_configurable_fast_interval_with_floor(self):
        original = getattr(config, "MONITORING_INTERVAL_SEC", None)
        try:
            config.MONITORING_INTERVAL_SEC = 0.75
            self.assertEqual(MonitoringWorker().interval, 0.75)
            self.assertEqual(MonitoringWorker(interval_sec=0.05).interval, 0.25)
            self.assertEqual(MonitoringWorker(interval_sec="bad").interval, 1.0)
            self.assertEqual(MonitoringWorker(interval_sec=0.75).stats()["interval_sec"], 0.75)
        finally:
            if original is None:
                delattr(config, "MONITORING_INTERVAL_SEC")
            else:
                config.MONITORING_INTERVAL_SEC = original

    def test_async_runtime_observer_records_failed_future(self):
        runtime = AsyncRuntime()
        with runtime._lock:
            original = {
                "completed": runtime._completed_count,
                "failed": runtime._failed_count,
                "last_error": runtime._last_error,
                "futures": set(runtime._futures),
            }

        future = concurrent.futures.Future()
        future.set_exception(RuntimeError("runtime boom"))

        try:
            runtime._observe_future(future, name="unit")
            stats = runtime.stats()

            self.assertGreaterEqual(stats["completed"], original["completed"] + 1)
            self.assertGreaterEqual(stats["failed"], original["failed"] + 1)
            self.assertEqual(stats["last_error"], "runtime boom")
        finally:
            with runtime._lock:
                runtime._completed_count = original["completed"]
                runtime._failed_count = original["failed"]
                runtime._last_error = original["last_error"]
                runtime._futures = original["futures"]

    def test_worker_manager_shutdown_sync_stops_async_worker_via_runtime(self):
        runtime = AsyncRuntime()
        runtime.start()
        manager = WorkerManager()
        original_workers = dict(manager._workers)
        original_async_tasks = list(manager._async_tasks)

        class AsyncStopWorker:
            def __init__(self):
                self.status = "RUNNING"
                self.is_running = True
                self._task = None
                self._thread = None

            async def stop(self):
                await asyncio.sleep(0.01)
                self.is_running = False
                self.status = "STOPPED"

        try:
            manager._workers = {"async": AsyncStopWorker()}
            manager._async_tasks = []
            result = manager.shutdown_sync(runtime=runtime, timeout=1.0)

            self.assertTrue(result["completed"])
            self.assertTrue(result["workers"]["async"]["stopped"])
            self.assertEqual(result["workers"]["async"]["status"], "STOPPED")
        finally:
            manager._workers = original_workers
            manager._async_tasks = original_async_tasks
            runtime.stop()


if __name__ == "__main__":
    unittest.main()
