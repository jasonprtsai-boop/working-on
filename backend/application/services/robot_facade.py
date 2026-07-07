from __future__ import annotations

import asyncio
import threading
from typing import Any, Dict

from backend.interfaces.hardware_interfaces import RobotInterface
from backend.utils import config
from backend.utils.logger import logger
from backend.application.services.estop import estop
from backend.observability.error_reporter import publish_error_diagnostic


class RobotFacade(RobotInterface):
    """
    Unifies real hardware vs simulation behind a single interface.

    - When Modbus deps are present and FAKE_ROBOT is false, uses Modbus-backed RobotService.
    - Otherwise uses FakeRobot simulation.
    """

    def __init__(self):
        self._impl = None
        self._fake_mode = None

        self._configure_impl()

        # register for E-Stop chain if supported
        try:
            estop.register_robot(self)
        except Exception as exc:
            logger.warning("[RobotFacade] failed to register with E-Stop controller", exc_info=True)
            publish_error_diagnostic(
                source="robot_facade",
                module="robot",
                code="robot_estop_registration_failed",
                message=str(exc),
                severity="error",
                recoverable=False,
                throttle_seconds=30.0,
            )

    def _configure_impl(self):
        fake_mode = bool(getattr(config, "FAKE_ROBOT", False))
        if fake_mode:
            from backend.infrastructure.simulation.fake_robot import fake_robot
            self._impl = fake_robot
        else:
            from backend.application.services.robot_service import RobotService

            self._impl = RobotService()
        self._fake_mode = fake_mode

    def reconfigure_from_config(self) -> bool:
        """Switch between fake and real implementations after setup settings change."""
        fake_mode = bool(getattr(config, "FAKE_ROBOT", False))
        if fake_mode != self._fake_mode:
            old_impl = self._impl
            try:
                if old_impl and hasattr(old_impl, "disconnect"):
                    old_impl.disconnect()
            except Exception:
                logger.debug("[RobotFacade] old robot implementation disconnect failed", exc_info=True)
            self._configure_impl()
        else:
            impl = self._impl
            try:
                from backend.infrastructure.robot.safety import RobotSafety

                if hasattr(impl, "_build_motion_profiles"):
                    impl.motion_profiles = impl._build_motion_profiles()
                if hasattr(impl, "safety"):
                    impl.safety = RobotSafety(config)
            except Exception:
                logger.debug("[RobotFacade] runtime robot safety/profile refresh failed", exc_info=True)
            adapter = getattr(impl, "adapter", None)
            if adapter is not None and not getattr(adapter, "connected", False):
                adapter.host = config.ROBOT_IP
                adapter.port = config.ROBOT_PORT
        return self.connect()

    def connect(self) -> bool:
        if hasattr(self._impl, "connect"):
            return bool(self._impl.connect())
        return True

    def _run_coroutine_sync(self, coro) -> Any:
        """
        Run a coroutine from a synchronous call site.

        - If no event loop is running in this thread, use `asyncio.run`.
        - If an event loop is already running, execute in a dedicated thread to
          avoid "asyncio.run() cannot be called from a running event loop".
        """
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop is None:
            return asyncio.run(coro)

        result_holder: Dict[str, Any] = {}

        def _runner():
            try:
                result_holder["value"] = asyncio.run(coro)
            except Exception as e:
                result_holder["error"] = e

        t = threading.Thread(target=_runner, daemon=True)
        t.start()
        t.join()
        if "error" in result_holder:
            raise result_holder["error"]
        return result_holder.get("value")

    def execute_move(self, move: str, is_capture: bool = False) -> bool:
        if estop.GLOBAL_STOP:
            logger.error("[RobotFacade] Refusing execute_move due to GLOBAL_STOP")
            return False

        # FakeRobot is sync; RobotService is async.
        if hasattr(self._impl, "move_piece"):
            try:
                return bool(self._run_coroutine_sync(self._impl.move_piece(move, is_capture=is_capture)))
            except Exception as e:
                logger.error(f"[RobotFacade] execute_move failed: {e}", exc_info=True)
                publish_error_diagnostic(
                    source="robot_facade",
                    module="robot",
                    code="robot_execute_move_failed",
                    message=str(e),
                    severity="error",
                    recoverable=True,
                    details={"move": move, "is_capture": is_capture},
                )
                return False
        if hasattr(self._impl, "execute_chess_move"):
            return bool(self._impl.execute_chess_move(move))
        if hasattr(self._impl, "execute_move"):
            return bool(self._impl.execute_move(move, is_capture=is_capture))
        return False

    def emergency_stop(self) -> bool:
        try:
            if hasattr(self._impl, "stop_all"):
                return bool(self._impl.stop_all())
            if hasattr(self._impl, "emergency_stop"):
                self._impl.emergency_stop()
                return True
        except Exception as e:
            logger.error(f"[RobotFacade] emergency_stop failed: {e}", exc_info=True)
            publish_error_diagnostic(
                source="robot_facade",
                module="robot",
                code="robot_emergency_stop_failed",
                message=str(e),
                severity="error",
                recoverable=False,
                throttle_seconds=10.0,
            )
        return False

    def get_status(self) -> Dict[str, Any]:
        try:
            if hasattr(self._impl, "get_status"):
                raw = dict(self._impl.get_status())
                # Normalize to frontend contract schema.
                return {
                    "connected": bool(raw.get("connected", False)),
                    "busy": bool(raw.get("busy", False)),
                    "error": raw.get("error"),
                    "last_action": raw.get("last_action", ""),
                    "queue_size": int(raw.get("queue_size", 0) or 0),
                    "position": raw.get("position") or {"x": 0.0, "y": 0.0, "z": 0.0},
                    "fake_robot": bool(self._fake_mode),
                }
        except Exception as exc:
            logger.warning("[RobotFacade] get_status failed", exc_info=True)
            publish_error_diagnostic(
                source="robot_facade",
                module="robot",
                code="robot_status_unavailable",
                message=str(exc),
                severity="warning",
                status="warning",
                recoverable=True,
                throttle_seconds=15.0,
            )
            error = str(exc)
        else:
            error = "status_unavailable"
        return {"connected": False, "busy": False, "error": error, "last_action": "", "queue_size": 0, "position": {"x": 0.0, "y": 0.0, "z": 0.0}}
