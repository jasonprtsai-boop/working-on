import asyncio
from typing import Optional, Any
from backend.application.container import container
from backend.state.store.state_store import state_store
from backend.events.bus.event_bus import bus
from backend.events.models.base_event import BaseEvent
from backend.events.event_types import EventType
from backend.utils.logger import logger
from backend.utils import config
from backend.runtime.async_runtime import runtime

class EnginePollingWorker:
    """
    [Industrial Architecture] Asyncio-native Engine Worker.
    Periodically triggers analysis for the latest SSOT FEN using the central runtime.
    """

    def __init__(self, interval_sec: float = 2.0, depth: int = 12):
        self.interval_on_idle_sec = interval_sec
        self.interval_on_change_sec = 0.2
        self.depth_on_change = depth
        self.depth_on_idle = max(6, min(depth, 10))

        self._task: Optional[asyncio.Task] = None
        self._enabled = False
        self._stop = False
        self.status = "IDLE"
        self.last_analysis_at: float = 0.0
        self.failure_count = 0
        self.last_error = None
        self._backoff_sec = 1.0
        self._setup_subscriptions()

    def _setup_subscriptions(self):
        bus.subscribe(EventType.ENGINE_ANALYSIS_REQUESTED, self.on_analysis_requested)
        bus.subscribe(EventType.GAME_PAUSE, self.on_pause_requested)
        bus.subscribe(EventType.GAME_RESET, self.on_reset_requested)

    def on_analysis_requested(self, event: BaseEvent):
        payload = event.payload or {}
        mode = payload.get("mode", "start")
        if payload.get("depth") is not None:
            try:
                depth = max(1, min(60, int(payload.get("depth"))))
                self.depth_on_change = depth
                self.depth_on_idle = depth
            except (TypeError, ValueError):
                logger.warning("[EngineWorker] Ignored invalid depth override: %r", payload.get("depth"))
        if mode == "start":
            logger.info("[EngineWorker] Analysis started via event.")
            self.enable()
        else:
            logger.info("[EngineWorker] Analysis stopped via event.")
            self.disable()

    def on_pause_requested(self, event: BaseEvent):
        logger.info("[EngineWorker] Analysis paused via event.")
        self.disable()

    def on_reset_requested(self, event: BaseEvent):
        logger.info("[EngineWorker] Analysis reset via event.")
        self.enable()

    def start(self):
        if self._task and not self._task.done():
            return
        self._stop = False
        self._enabled = bool(getattr(config, "ENGINE_AUTO_ANALYZE", True))
        self.status = "ENABLED" if self._enabled else "IDLE"
        self._task = runtime.run_task(self._run_async())
        logger.info("[EngineWorker] Async task submitted to runtime.")

    def stop(self):
        self._enabled = False
        self._stop = True
        task = self._task
        if task:
            task.cancel()
            try:
                import threading
                if getattr(runtime, "_thread", None) is not threading.current_thread():
                    task.result(timeout=2.0)
            except Exception:
                logger.debug("[EngineWorker] async task cancellation did not complete synchronously.", exc_info=True)
            self._task = None
        self.status = "STOPPED"

    def enable(self): self._enabled = True
    def disable(self): self._enabled = False
    def is_enabled(self): return self._enabled
    def backoff_sec(self): return self._backoff_sec

    @property
    def is_running(self):
        return bool(self._task and not self._task.done() and not self._stop)

    def stats(self):
        return {
            "enabled": self._enabled,
            "last_analysis_at": self.last_analysis_at,
            "failure_count": self.failure_count,
            "backoff_sec": self._backoff_sec,
            "last_error": self.last_error,
        }

    async def _run_async(self):
        engine = container.get("engine")
        if not engine:
            logger.error("[EngineWorker] No engine service in container.")
            return

        last_fen = None
        last_run = 0.0

        while not self._stop:
            try:
                if not self._enabled:
                    await asyncio.sleep(0.5)
                    continue

                # Get current FEN from SSOT
                raw = state_store.to_dict()
                game = raw.get("game", {})
                fen = game.get("fen", "")

                now = asyncio.get_running_loop().time()
                fen_changed = bool(fen and fen != last_fen)
                interval = self.interval_on_change_sec if fen_changed else self.interval_on_idle_sec
                depth = self.depth_on_change if fen_changed else self.depth_on_idle

                if fen and (fen_changed or (now - last_run) >= interval):
                    last_fen = fen
                    last_run = now
                    self.status = "BUSY"

                    # Propagate trace_id from state for end-to-end tracing
                    trace_id = raw.get("trace_id", "unknown")

                    result = await engine.compute(fen, depth=depth)

                    self.last_analysis_at = now
                    self.status = "ENABLED"
                    self.failure_count = 0
                    self.last_error = None
                    self._backoff_sec = 1.0

                    if result:
                        result = dict(result)
                        result["final"] = True
                        result.setdefault("fen", fen)
                        result.setdefault("fen_before", fen)
                        result.setdefault("board", game.get("board") or {})
                        result.setdefault("current_turn", game.get("current_turn"))
                        bus.publish(BaseEvent.create(
                            event_type=EventType.ENGINE_ANALYSIS_COMPLETED,
                            source="engine_worker",
                            payload=result,
                            trace_id=trace_id
                        ))

                await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[EngineWorker] Error: {e}")
                self.failure_count += 1
                self.last_error = str(e)
                self._backoff_sec = min(max(self._backoff_sec * 2.0, 1.0), 10.0)
                await asyncio.sleep(self._backoff_sec)

        self.status = "STOPPED"

engine_worker = EnginePollingWorker()
