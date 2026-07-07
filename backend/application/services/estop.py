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
from typing import Any, Optional

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
        self._last_reason = ""
        self._last_triggered_at: Optional[float] = None
        self._last_reset_at: Optional[float] = None
        self._last_steps: list[dict[str, Any]] = []
        self._last_errors: list[dict[str, Any]] = []

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

    def _publish_event(self, event_type, payload: dict) -> bool:
        try:
            from backend.events.bus.event_bus import bus
            from backend.events.models.base_event import BaseEvent

            bus.publish(BaseEvent.create(
                event_type=event_type,
                source="estop",
                payload=payload,
            ))
            return True
        except Exception as e:
            logger.error(f"E-Stop event publish failed: {e}", exc_info=True)
            return False

    def _record_step(
        self,
        steps: list[dict[str, Any]],
        name: str,
        status: str,
        message: str = "",
    ):
        item = {
            "step": name,
            "status": status,
            "message": str(message or ""),
            "module": "control",
            "event_type": "ESTOP_STEP_" + ("FAILED" if status == "error" else status.upper()),
            "severity": "error" if status == "error" else ("warning" if status == "warning" else "info"),
            "code": f"estop_{name}",
            "timestamp": time.time(),
        }
        steps.append(item)
        if status in {"error", "warning"}:
            with self._lock:
                self._last_errors.append(item)
                self._last_errors = self._last_errors[-20:]

    def _publish_diagnostics(self, reason: str, steps: list[dict[str, Any]]):
        errors = [step for step in steps if step.get("status") == "error"]
        warnings = [step for step in steps if step.get("status") == "warning"]
        severity = "error" if errors else ("warning" if warnings else "info")
        snapshot = self.snapshot()
        snapshot["steps"] = list(steps)
        self._publish_event(
            "DIAGNOSTICS_UPDATED",
            {
                "control": {"estop": snapshot},
                "robot": {
                    "emergency_stop": True,
                    "status": "error" if errors else ("warning" if warnings else "success"),
                    "error": errors[0]["message"] if errors else "",
                },
                "ui": {
                    "estop": snapshot,
                    "last_error": errors[-1] if errors else None,
                },
                "telemetry": {
                    "last_error": errors[-1] if errors else None,
                    "errors": errors,
                },
                "module": "control",
                "status": "error" if errors else ("warning" if warnings else "success"),
                "severity": severity,
                "message": reason,
            },
        )

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
            self._last_reason = reason
            self._last_triggered_at = time.time()
            self._last_steps = []

        logger.critical(f"=== E-STOP TRIGGERED === Reason: {reason}")
        steps: list[dict[str, Any]] = []
        try:
            from backend.events.event_types import EventType
            ok = self._publish_event(EventType.EMERGENCY_STOP, {"reason": reason})
            self._record_step(
                steps,
                "publish_emergency_event",
                "success" if ok else "error",
                "" if ok else "EventBus publish failed.",
            )
        except Exception as exc:
            logger.warning("E-Stop emergency event publish skipped.", exc_info=True)
            self._record_step(steps, "publish_emergency_event", "error", str(exc))

        # Step 1: Clear Task Queue (prevent pending tasks from executing)
        try:
            from backend.app.task_queue import task_queue
            task_queue.clear()
            logger.info("E-Stop Step 1: Task Queue cleared.")
            self._record_step(steps, "task_queue_clear", "success")
        except Exception as e:
            logger.error(f"E-Stop Step 1 failed: {e}", exc_info=True)
            self._record_step(steps, "task_queue_clear", "error", str(e))

        # Step 2: Send hardware stop signal to robot
        try:
            if self._robot_ref and hasattr(self._robot_ref, "emergency_stop"):
                self._robot_ref.emergency_stop()
                logger.info("E-Stop Step 2: Robot hardware stop sent.")
                self._record_step(steps, "robot_hardware_stop", "success")
            else:
                logger.warning("E-Stop Step 2: No robot registered or no emergency_stop method.")
                self._record_step(
                    steps,
                    "robot_hardware_stop",
                    "warning",
                    "No robot registered or emergency_stop method unavailable.",
                )
        except Exception as e:
            logger.error(f"E-Stop Step 2 failed: {e}", exc_info=True)
            self._record_step(steps, "robot_hardware_stop", "error", str(e))

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
            self._record_step(steps, "state_force_error", "success")
        except Exception as e:
            logger.error(f"E-Stop Step 3 failed: {e}", exc_info=True)
            self._record_step(steps, "state_force_error", "error", str(e))

        # Step 4: Lock frontend UI via Socket.IO
        self._emit_ui_lock(True, reason)
        self._record_step(
            steps,
            "frontend_ui_lock",
            "success" if self._socketio_ref else "warning",
            "" if self._socketio_ref else "No Socket.IO registered for UI lock broadcast.",
        )
        with self._lock:
            self._last_steps = list(steps)
        self._publish_diagnostics(reason, steps)

        logger.critical("=== E-STOP CHAIN COMPLETE ===")

    def reset(self):
        """Clear the E-Stop state for recovery (manual operator action required)."""
        with self._lock:
            self._triggered = False
            self._global_stop = False
            self._last_reset_at = time.time()
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
        self._publish_event("DIAGNOSTICS_UPDATED", {
            "control": {"estop": self.snapshot()},
            "ui": {"estop": self.snapshot()},
            "module": "control",
            "status": "success",
            "severity": "info",
            "message": "Emergency stop cleared.",
        })
        logger.info("E-Stop state cleared. System can recover to IDLE.")

    @property
    def is_triggered(self) -> bool:
        with self._lock:
            return self._triggered

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "triggered": self._triggered,
                "global_stop": self._global_stop,
                "reason": self._last_reason,
                "last_triggered_at": self._last_triggered_at,
                "last_reset_at": self._last_reset_at,
                "steps": list(self._last_steps),
                "errors": list(self._last_errors),
            }

# Global singleton
estop = EStop()
