import asyncio
import concurrent.futures
import queue
import threading
import time
from contextlib import suppress
from typing import Optional
from backend.events.bus.event_bus import bus
from backend.infrastructure.database.event_store import EventStore
from backend.utils import config
from backend.utils.logger import logger
from backend.runtime.async_runtime import runtime

class PersistenceWorker:
    """
    [Observability] Asyncio-native Persistence Worker.
    Subscribes to all system events and persists them to SQLite via AsyncRuntime.
        """
    def __init__(self):
        self.store = EventStore(config.DB_PATH)
        self._task: Optional[asyncio.Task] = None
        self._queue: "queue.Queue[dict]" = queue.Queue(maxsize=max(100, int(getattr(config, "PERSISTENCE_QUEUE_SIZE", 2000))))
        self._batch_size = max(1, int(getattr(config, "PERSISTENCE_BATCH_SIZE", 100)))
        self._flush_interval = max(0.05, float(getattr(config, "PERSISTENCE_FLUSH_INTERVAL_SEC", 0.25)))
        self._stop = threading.Event()
        self._subscribed = False
        self._dropped_events = 0
        self._persisted_events = 0
        self._last_drop_at = None
        self._last_persist_at = None

    def start(self):
        if self._task and not self._task.done():
            return
        self._stop.clear()
        if not self._subscribed:
            bus.subscribe_all(self._on_event)
            self._subscribed = True
        self._task = runtime.run_task(self._run_async())
        logger.info("[PersistenceWorker] Started with async queue-backed event persistence.")

    def _on_event(self, event):
        """Standardized callback for all EventBus publications."""
        try:
            if hasattr(event, "to_dict"):
                data = event.to_dict()
            elif isinstance(event, dict):
                data = event
            else: return

            data = dict(data)
            if not data.get("session_id"):
                try:
                    from backend.application.services.runtime_control import runtime_control
                    data["session_id"] = runtime_control.active_session_id
                except Exception:
                    data["session_id"] = None

            try:
                self._queue.put_nowait(data)
            except queue.Full:
                self._dropped_events += 1
                self._last_drop_at = time.time()
                logger.warning(
                    f"[PersistenceWorker] queue full; dropped event type={data.get('type') or data.get('event_type')} (total dropped={self._dropped_events})"
                )
                if data.get("source") != "persistence_worker":
                    self._publish_drop_diagnostics(data)
        except Exception as e:
            logger.debug(f"[PersistenceWorker] Failed to save event: {e}")

    async def _run_async(self):
        try:
            while not self._stop.is_set():
                try:
                    batch = await asyncio.to_thread(self._collect_batch)
                except RuntimeError as exc:
                    if "cannot schedule new futures after shutdown" not in str(exc):
                        raise
                    batch = self._collect_batch()
                if batch:
                    await self._save_batch(batch)
                else:
                    await asyncio.sleep(self._flush_interval)
        except asyncio.CancelledError:
            raise
        finally:
            while True:
                remaining = self._drain_nowait()
                if not remaining:
                    break
                self._save_batch_sync(remaining, phase="final flush")

    async def _save_batch(self, batch):
        try:
            await asyncio.to_thread(self.store.save_events, batch)
            self._record_persisted(len(batch))
        except RuntimeError as exc:
            if "cannot schedule new futures after shutdown" not in str(exc):
                raise
            self._save_batch_sync(batch, phase="executor shutdown fallback")
        except Exception as exc:
            logger.warning(f"[PersistenceWorker] batch save failed: {exc}", exc_info=True)

    def _save_batch_sync(self, batch, phase: str):
        try:
            self.store.save_events(batch)
            self._record_persisted(len(batch))
        except Exception as exc:
            logger.warning(f"[PersistenceWorker] {phase} failed: {exc}", exc_info=True)

    def _record_persisted(self, count: int):
        self._persisted_events += int(count or 0)
        self._last_persist_at = time.time()

    def _publish_drop_diagnostics(self, event_data: dict):
        try:
            from backend.events.event_types import EventType
            from backend.events.models.base_event import BaseEvent

            bus.publish(BaseEvent.create(
                event_type=EventType.DIAGNOSTICS_UPDATED,
                source="persistence_worker",
                payload={
                    "persistence": self.stats(),
                    "dropped_event_type": event_data.get("type") or event_data.get("event_type") or "unknown",
                },
            ))
        except Exception:
            logger.debug("[PersistenceWorker] failed to publish drop diagnostics", exc_info=True)

    def stats(self):
        return {
            "queue_size": self._queue.qsize(),
            "queue_maxsize": self._queue.maxsize,
            "queue_full": self._queue.full(),
            "dropped_events": self._dropped_events,
            "persisted_events": self._persisted_events,
            "last_drop_at": self._last_drop_at,
            "last_persist_at": self._last_persist_at,
        }

    def _collect_batch(self):
        batch = []
        try:
            first = self._queue.get(timeout=self._flush_interval)
            batch.append(first)
        except queue.Empty:
            return batch

        while len(batch) < self._batch_size:
            try:
                batch.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return batch

    def _drain_nowait(self):
        batch = []
        while len(batch) < self._batch_size:
            try:
                batch.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return batch

    async def stop(self):
        self._stop.set()
        future = self._task
        if future:
            future.cancel()
            with suppress(asyncio.CancelledError, concurrent.futures.CancelledError, asyncio.TimeoutError):
                await asyncio.wait_for(asyncio.wrap_future(future), timeout=5.0)
            self._task = None
        logger.info("[PersistenceWorker] Stopped.")

persistence_worker = PersistenceWorker()
