"""
E-Stop (Emergency Stop) Module
Implements the full E-Stop interlock chain:
  1. Clear Task Queue
  2. Send hardware stop signal
  3. Force State into ERROR
  4. Lock frontend UI via Socket.IO event
"""
import logging
import threading
import time
from typing import Optional

logger = logging.getLogger("EStop")

class EStop:
    """
    Emergency Stop controller.
    Triggered by:
    - Frontend long-press (0.5s) via API
    - Internal safety violation
    - Physical E-Stop signal
    """

    def __init__(self):
        self._triggered = False
        self._global_stop = False
        self._lock = threading.Lock()
        self._robot_ref = None
        self._socketio_ref = None

    @property
    def GLOBAL_STOP(self) -> bool:
        """Backward compatible property with thread safety."""
        with self._lock:
            return self._global_stop

    @GLOBAL_STOP.setter
    def GLOBAL_STOP(self, value: bool):
        """Allow legacy tests and integrations to force the interlock flag."""
        with self._lock:
            flag = bool(value)
            self._global_stop = flag
            self._triggered = flag

    def register_robot(self, robot):
        """Register the robot controller for hardware stop."""
        self._robot_ref = robot

    def register_socketio(self, sio):
        """Register the Socket.IO instance for UI lock broadcast."""
        self._socketio_ref = sio

    def _publish_event(self, event_type, payload: dict):
        try:
            from backend.events.bus.event_bus import bus
            from backend.events.models.base_event import BaseEvent

            bus.publish(BaseEvent.create(
                event_type=event_type,
                source="estop",
                payload=payload,
            ))
        except Exception as e:
            logger.error(f"E-Stop event publish failed: {e}")

    def _emit_ui_lock(self, locked: bool, reason: str):
        try:
            if self._socketio_ref:
                self._socketio_ref.emit("ui_lock", {
                    "locked": bool(locked),
                    "reason": reason,
                    "timestamp": time.time()
                })
                logger.info("E-Stop UI lock event emitted.")
            else:
                logger.warning("E-Stop UI lock skipped: no Socket.IO registered.")
        except Exception as e:
            logger.error(f"E-Stop UI lock emit failed: {e}")

    def trigger(self, reason: str = "Manual E-Stop"):
        """
        Execute the full E-Stop interlock chain.
        Thread-safe; idempotent (safe to call multiple times).
        """
        with self._lock:
            if self._triggered:
                logger.warning("E-Stop already active, ignoring duplicate trigger.")
                return
            self._triggered = True
            self._global_stop = True # Halt all background tasks

        logger.critical(f"=== E-STOP TRIGGERED === Reason: {reason}")
        try:
            from backend.events.event_types import EventType
            self._publish_event(EventType.EMERGENCY_STOP, {"reason": reason})
        except Exception:
            logger.debug("E-Stop emergency event publish skipped.", exc_info=True)

        # Step 1: Clear Task Queue (prevent pending tasks from executing)
        try:
            from backend.app.task_queue import task_queue
            task_queue.clear()
            logger.info("E-Stop Step 1: Task Queue cleared.")
        except Exception as e:
            logger.error(f"E-Stop Step 1 failed: {e}")

        # Step 2: Send hardware stop signal to robot
        try:
            if self._robot_ref and hasattr(self._robot_ref, "emergency_stop"):
                self._robot_ref.emergency_stop()
                logger.info("E-Stop Step 2: Robot hardware stop sent.")
            else:
                logger.warning("E-Stop Step 2: No robot registered or no emergency_stop method.")
        except Exception as e:
            logger.error(f"E-Stop Step 2 failed: {e}")

        # Step 3: Force State into ERROR
        try:
            from backend.state.store.state_store import state_store
            from backend.state.store.models.game_state import SystemPhase
            from backend.events.models.base_event import BaseEvent
            from backend.events.event_types import EventType

            state_store.dispatch(BaseEvent.create(
                event_type=EventType.SYSTEM_ERROR,
                source="estop",
                payload={"game_status": "ERROR", "phase": SystemPhase.ERROR.value, "reason": reason}
            ))
            logger.info("E-Stop Step 3: State set to ERROR.")
        except Exception as e:
            logger.error(f"E-Stop Step 3 failed: {e}")

        # Step 4: Lock frontend UI via Socket.IO
        self._emit_ui_lock(True, reason)

        logger.critical("=== E-STOP CHAIN COMPLETE ===")

    def reset(self):
        """Clear the E-Stop state for recovery (manual operator action required)."""
        with self._lock:
            self._triggered = False
            self._global_stop = False
        try:
            from backend.events.event_types import EventType
            from backend.state.store.state_store import state_store
            from backend.events.models.base_event import BaseEvent

            state_store.dispatch(BaseEvent.create(
                event_type=EventType.SYSTEM_RESET,
                source="estop",
                payload={"reason": "E-Stop reset"},
            ))
            self._publish_event(EventType.RECOVERY_COMPLETED, {
                "strategy": "MANUAL_ESTOP_RESET",
                "status": "SYSTEM_RESTORED",
            })
            self._publish_event(EventType.UI_TOAST, {
                "text": "Emergency stop cleared.",
                "level": "success",
            })
        except Exception as e:
            logger.error(f"E-Stop reset recovery publish failed: {e}")
        self._emit_ui_lock(False, "Emergency stop cleared.")
        logger.info("E-Stop state cleared. System can recover to IDLE.")

    @property
    def is_triggered(self) -> bool:
        with self._lock:
            return self._triggered

# Global singleton
estop = EStop()
