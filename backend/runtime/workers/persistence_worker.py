import asyncio
import queue
import threading
import time
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
        self._critical_queue: "queue.Queue[dict]" = queue.Queue(
            maxsize=max(10, int(getattr(config, "PERSISTENCE_CRITICAL_QUEUE_SIZE", 500)))
        )
        self._critical_event_types = {
            str(item) for item in getattr(config, "PERSISTENCE_CRITICAL_EVENT_TYPES", ()) if str(item)
        }
        self._batch_size = max(1, int(getattr(config, "PERSISTENCE_BATCH_SIZE", 100)))
        self._flush_interval = max(0.05, float(getattr(config, "PERSISTENCE_FLUSH_INTERVAL_SEC", 0.25)))
        self._stop = threading.Event()
        self._subscribed = False
        self._dropped_events = 0
        self._critical_overflow_events = 0
        self._received_events = 0
        self._persisted_events = 0
        self._last_drop_at = None
        self._last_persist_at = None
        self._last_drop_diagnostics_at = 0.0
        self.status = "IDLE"
        self.last_error = None

    def start(self):
        if self._task and not self._task.done():
            return
        self._stop.clear()
        if not self._subscribed:
            bus.subscribe_all(self._on_event)
            self._subscribed = True
        self._task = runtime.run_task(self._run_async())
        self.status = "RUNNING"
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
                self._received_events += 1
                if self._is_critical_event(data):
                    self._enqueue_critical(data)
                else:
                    self._queue.put_nowait(data)
            except queue.Full:
                self._dropped_events += 1
                self._last_drop_at = time.time()
                logger.warning(
                    f"[PersistenceWorker] queue full; dropped event type={data.get('type') or data.get('event_type')} (total dropped={self._dropped_events})"
                )
                if self._should_publish_drop_diagnostics(data):
                    self._publish_drop_diagnostics(data)
        except Exception as e:
            self.last_error = str(e)
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
            self.last_error = str(exc)
            logger.warning(f"[PersistenceWorker] batch save failed: {exc}", exc_info=True)

    def _save_batch_sync(self, batch, phase: str):
        try:
            self.store.save_events(batch)
            self._record_persisted(len(batch))
        except Exception as exc:
            self.last_error = str(exc)
            logger.warning(f"[PersistenceWorker] {phase} failed: {exc}", exc_info=True)

    def _record_persisted(self, count: int):
        self._persisted_events += int(count or 0)
        self._last_persist_at = time.time()
        self.last_error = None

    def _should_publish_drop_diagnostics(self, event_data: dict) -> bool:
        if event_data.get("source") == "persistence_worker":
            return False
        threshold = max(1, int(getattr(config, "PERSISTENCE_DROP_WARNING_THRESHOLD", 1)))
        if self._dropped_events < threshold:
            return False
        interval = max(0.0, float(getattr(config, "PERSISTENCE_DROP_WARNING_INTERVAL_SEC", 5.0)))
        now = time.time()
        if interval and (now - self._last_drop_diagnostics_at) < interval:
            return False
        self._last_drop_diagnostics_at = now
        return True

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
            "critical_queue_size": self._critical_queue.qsize(),
            "critical_queue_maxsize": self._critical_queue.maxsize,
            "critical_queue_full": self._critical_queue.full(),
            "critical_event_types": sorted(self._critical_event_types),
            "critical_overflow_events": self._critical_overflow_events,
            "received_events": self._received_events,
            "dropped_events": self._dropped_events,
            "drop_warning": self._dropped_events >= max(1, int(getattr(config, "PERSISTENCE_DROP_WARNING_THRESHOLD", 1))),
            "drop_rate": (self._dropped_events / self._received_events) if self._received_events else 0.0,
            "persisted_events": self._persisted_events,
            "last_drop_at": self._last_drop_at,
            "last_persist_at": self._last_persist_at,
            "last_error": self.last_error,
        }

    def _collect_batch(self):
        batch = []
        try:
            first = self._critical_queue.get_nowait()
            batch.append(first)
        except queue.Empty:
            pass

        if not batch:
            try:
                first = self._queue.get(timeout=self._flush_interval)
                batch.append(first)
            except queue.Empty:
                return batch

        while len(batch) < self._batch_size:
            try:
                batch.append(self._critical_queue.get_nowait())
            except queue.Empty:
                break

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
                batch.append(self._critical_queue.get_nowait())
            except queue.Empty:
                break
        while len(batch) < self._batch_size:
            try:
                batch.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return batch

    def _is_critical_event(self, event_data: dict) -> bool:
        event_type = str(event_data.get("type") or event_data.get("event_type") or "")
        return event_type in self._critical_event_types

    def _enqueue_critical(self, data: dict):
        try:
            self._critical_queue.put_nowait(data)
        except queue.Full:
            self._critical_overflow_events += 1
            logger.error(
                "[PersistenceWorker] critical queue full; synchronously persisting event type=%s",
                data.get("type") or data.get("event_type"),
            )
            self.store.save_event(data)
            self._record_persisted(1)

    def stop(self):
        self._stop.set()
        future = self._task
        if future:
            if getattr(runtime, "_thread", None) is threading.current_thread():
                future.cancel()
            else:
                try:
                    future.result(timeout=5.0)
                except Exception:
                    future.cancel()
                    logger.debug("[PersistenceWorker] async task did not stop before timeout.", exc_info=True)
            self._task = None
        self.status = "STOPPED"
        logger.info("[PersistenceWorker] Stopped.")

    @property
    def is_running(self):
        return bool(self._task and not self._task.done() and not self._stop.is_set())

persistence_worker = PersistenceWorker()
