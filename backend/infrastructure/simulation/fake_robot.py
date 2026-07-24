import re
import time
from backend.utils.logger import logger
from backend.utils import config
from backend.utils.kinematics import kinematics
from backend.infrastructure.robot.safety import RobotSafety

class FakeRobot:
    def __init__(self):
        self.connected = False
        self.pos = [0, 0, 150]
        self.busy = False
        self.error = None
        self.last_action = ""
        self.safety = RobotSafety(config)

    def connect(self):
        logger.info("FakeRobot: Simulating connection...")
        time.sleep(0.5)
        self.connected = True
        return True

    def execute_chess_move(self, move_ucci):
        return self.execute_move(move_ucci)

    def execute_move(self, move_ucci, is_capture=False):
        logger.info(f"FakeRobot: Executing move {move_ucci}...")
        self.busy = True
        self.error = None
        try:
            if not isinstance(move_ucci, str) or not re.fullmatch(r"[a-i][0-9][a-i][0-9]", move_ucci):
                raise ValueError(f"Invalid UCCI move command: {move_ucci!r}")
            if move_ucci[:2] == move_ucci[2:]:
                raise ValueError(f"Refusing no-op robot move: {move_ucci}")

            start_xy = kinematics.grid_to_robot(move_ucci[0], move_ucci[1])
            end_xy = kinematics.grid_to_robot(move_ucci[2], move_ucci[3])
            if not start_xy or not end_xy:
                raise ValueError("Kinematics mapping failed.")

            self._validate_position(start_xy[0], start_xy[1], config.Z_SAFE)
            self._validate_position(start_xy[0], start_xy[1], config.Z_GRAB)
            self._validate_position(end_xy[0], end_xy[1], config.Z_SAFE)
            self._validate_position(end_xy[0], end_xy[1], config.Z_GRAB + 2.0)

            if is_capture:
                dz_x, dz_y = kinematics.get_dead_zone_coords(1)
                self._validate_position(dz_x, dz_y, config.Z_SAFE)

            self.pos = [float(end_xy[0]), float(end_xy[1]), float(config.Z_SAFE)]
            self.last_action = move_ucci
            time.sleep(0.1)
            logger.info(f"FakeRobot: Move {move_ucci} finished.")
            return True
        except Exception as exc:
            self.error = str(exc)
            logger.error(f"FakeRobot: Move {move_ucci} rejected: {exc}")
            return False
        finally:
            self.busy = False

    def _validate_position(self, x, y, z):
        ok, msg = self.safety.validate_position(x, y, z)
        if not ok:
            raise ValueError(msg)

    def stop_all(self):
        logger.warning("FakeRobot: EMERGENCY STOP EXECUTED!")
        self.busy = False
        return True

    def get_status(self):
        position = {"x": float(self.pos[0]), "y": float(self.pos[1]), "z": float(self.pos[2])}
        orientation = {
            "rx": float(getattr(config, "ROBOT_TOOL_RX", 0.0)),
            "ry": float(getattr(config, "ROBOT_TOOL_RY", 0.0)),
            "rz": float(getattr(config, "ROBOT_TOOL_RZ", 0.0)),
        }
        joint_angles = {f"j{index}": 0.0 for index in range(1, 7)}
        speed = float(config.ROBOT_TRAVEL_SPEED if self.busy else 0.0)
        return {
            "pos": self.pos,
            "angles": [0]*6,
            "connected": self.connected,
            "is_connected": self.connected,
            "busy": self.busy,
            "error": self.error,
            "last_action": self.last_action,
            "queue_size": 0,
            "position": position,
            "orientation": orientation,
            "joint_angles": joint_angles,
            "speed": speed,
            "ip": str(config.ROBOT_IP),
            "port": int(config.ROBOT_PORT),
            "connection": {
                "ip": str(config.ROBOT_IP),
                "host": str(config.ROBOT_IP),
                "port": int(config.ROBOT_PORT),
                "connected": bool(self.connected),
                "mode": "simulation",
                "checked_at": time.time(),
            },
            "telemetry": {
                "enabled": bool(getattr(config, "ROBOT_TELEMETRY_ENABLED", False)),
                "source": "simulation",
                "pose": {**position, **orientation},
                "orientation": orientation,
                "joint_angles": joint_angles,
                "speed": speed,
            },
        }

fake_robot = FakeRobot()
