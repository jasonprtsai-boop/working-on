from __future__ import annotations

import asyncio
import threading
from typing import Any, Dict

from backend.interfaces.hardware_interfaces import RobotInterface
from backend.utils import config
from backend.utils.logger import logger
from backend.application.services.estop import estop


class RobotFacade(RobotInterface):
    """
    Unifies real hardware vs simulation behind a single interface.

    - When Modbus deps are present and FAKE_ROBOT is false, uses Modbus-backed RobotService.
    - Otherwise uses FakeRobot simulation.
    """

    def __init__(self):
        self._impl = None

        if getattr(config, "FAKE_ROBOT", False):
            from backend.infrastructure.simulation.fake_robot import fake_robot
            self._impl = fake_robot
        else:
            from backend.application.services.robot_service import RobotService

            self._impl = RobotService()

        # register for E-Stop chain if supported
        try:
            estop.register_robot(self)
        except Exception:
            pass

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
            asyncio.get_running_loop()
        except RuntimeError:
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
                logger.error(f"[RobotFacade] execute_move failed: {e}")
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
            logger.error(f"[RobotFacade] emergency_stop failed: {e}")
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
                }
        except Exception:
            pass
        return {"connected": False, "busy": False, "error": None, "last_action": "", "queue_size": 0, "position": {"x": 0.0, "y": 0.0, "z": 0.0}}
