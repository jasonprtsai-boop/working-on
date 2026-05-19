import time
import asyncio
from backend.utils.logger import logger
from backend.utils import config
from backend.utils.kinematics import kinematics
from backend.infrastructure.robot.safety import RobotSafety
from backend.infrastructure.robot.modbus_adapter import ModbusAdapter
from backend.application.services.estop import estop
from backend.events.bus.event_bus import bus
from backend.events.models.base_event import BaseEvent
from backend.events.event_types import EventType


class RobotService:
    """Actuation service with a consistent API (real Modbus or mock)."""

    def __init__(self):
        self.connected = False
        self.is_moving = False
        self.last_error = None
        self.pos = [0, 0, config.Z_SAFE]
        self.safety = RobotSafety(config)
        self.adapter = ModbusAdapter(host=config.ROBOT_IP, port=config.ROBOT_PORT)

    def connect(self):
        logger.info(f"Initializing TM Robot Interface ({config.ROBOT_IP})")
        ok = self.adapter.connect()
        self.connected = bool(ok)
        if self.connected:
            logger.info("TM Robot Handshake Successful.")
        return self.connected

    def get_status(self) -> dict:
        return {
            "connected": bool(self.connected),
            "busy": bool(self.is_moving),
            "error": self.last_error,
            "last_action": "",
            "queue_size": 0,
            "position": {"x": float(self.pos[0]), "y": float(self.pos[1]), "z": float(self.pos[2])},
        }

    async def move_piece(self, move_str: str, is_capture: bool = False):
        if estop.GLOBAL_STOP:
            logger.error("E-Stop active. Aborting robot move.")
            return False

        if not self.connected and not config.FAKE_ROBOT:
            logger.error("Robot not connected. Aborting move.")
            return False

        self.is_moving = True
        self.last_error = None
        self._publish_status(EventType.ROBOT_MOVE_STARTED, {"move": move_str, "is_capture": is_capture})
        # Immediate contract-level status update for UI.
        bus.publish(BaseEvent.create(
            event_type=EventType.ROBOT_STATUS_UPDATED,
            payload=self.get_status(),
            source="robot_service"
        ))

        try:
            start_f, start_r = move_str[0], move_str[1]
            end_f, end_r = move_str[2], move_str[3]

            start_xy = kinematics.grid_to_robot(start_f, start_r)
            end_xy = kinematics.grid_to_robot(end_f, end_r)

            if not start_xy or not end_xy:
                raise ValueError("Kinematics mapping failed.")

            ok, msg = self.safety.validate_move(start_xy[0], start_xy[1])
            if not ok:
                raise ValueError(msg)
            ok, msg = self.safety.validate_move(end_xy[0], end_xy[1])
            if not ok:
                raise ValueError(msg)

            if is_capture:
                logger.info(f"Capture detected at {end_f}{end_r}. Clearing space...")
                dz_x, dz_y = kinematics.get_dead_zone_coords(1)
                await self._execute_pick_and_place(end_xy[0], end_xy[1], dz_x, dz_y)

            logger.info(f"Robot Primary Move: {move_str}")
            await self._execute_pick_and_place(start_xy[0], start_xy[1], end_xy[0], end_xy[1])

            self.is_moving = False
            self.last_error = None
            self._publish_status(EventType.ROBOT_MOVE_COMPLETED, {"move": move_str, "status": "success"})
            bus.publish(BaseEvent.create(
                event_type=EventType.ROBOT_STATUS_UPDATED,
                payload=self.get_status(),
                source="robot_service"
            ))
            return True

        except Exception as e:
            logger.error(f"Robot Execution Failed: {e}")
            self.is_moving = False
            self.last_error = str(e)
            self._publish_status(EventType.ROBOT_MOVE_COMPLETED, {
                "move": move_str,
                "status": "failed",
                "error": str(e),
            })
            self._publish_status(EventType.DIAGNOSTICS_UPDATED, {"robot": {"error": str(e)}})
            bus.publish(BaseEvent.create(
                event_type=EventType.ROBOT_STATUS_UPDATED,
                payload={**self.get_status(), "error": str(e)},
                source="robot_service"
            ))
            return False

    async def _execute_pick_and_place(self, sx, sy, ex, ey):
        await self._motion(sx, sy, config.Z_SAFE)
        await self._motion(sx, sy, config.Z_GRAB)
        logger.info("[Robot] Gripper/Vacuum ACTIVATED")
        await self._motion(sx, sy, config.Z_SAFE)

        await self._motion(ex, ey, config.Z_SAFE)
        await self._motion(ex, ey, config.Z_GRAB + 2.0)
        logger.info("[Robot] Gripper/Vacuum DEACTIVATED")
        await self._motion(ex, ey, config.Z_SAFE)

    async def _motion(self, x, y, z):
        coords = [float(x), float(y), float(z), 0.0, 0.0, 0.0]
        if self.connected:
            ok = await asyncio.to_thread(self.adapter.send_move, coords)
            if not ok:
                raise RuntimeError(f"Robot motion failed for target {coords[:3]}")
        else:
            if not config.FAKE_ROBOT:
                raise RuntimeError("Robot is not connected.")
            await asyncio.sleep(0.5)
        self.pos = [x, y, z]

    def _publish_status(self, event_type: EventType, payload: dict):
        bus.publish(BaseEvent.create(event_type=event_type, source="robot_service", payload=payload))

    def stop_all(self):
        try:
            self.adapter.halt()
        except Exception as exc:
            logger.warning(f"[RobotService] halt failed during stop_all: {exc}", exc_info=True)
        self.is_moving = False
        return True

    def emergency_stop(self):
        return self.stop_all()


# Optional module-level singleton (wired during bootstrap if needed)
robot_service = None
