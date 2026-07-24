import math
import re
import asyncio
import threading
import time
from dataclasses import dataclass
from typing import Optional, Tuple
from backend.utils.logger import logger
from backend.utils import config
from backend.utils.kinematics import kinematics
from backend.infrastructure.robot.safety import RobotSafety
from backend.application.services.estop import estop
from backend.events.bus.event_bus import bus
from backend.events.models.base_event import BaseEvent
from backend.events.event_types import EventType


@dataclass(frozen=True)
class MotionProfile:
    label: str
    speed: float
    acceleration: float
    timeout: float


@dataclass(frozen=True)
class RobotMovePlan:
    move: str
    start_xy: Tuple[float, float]
    end_xy: Tuple[float, float]
    capture_xy: Optional[Tuple[float, float]] = None


class RobotService:
    """Actuation service with a consistent API (real TMflow JSON/TechmanPy/Modbus or mock)."""

    def __init__(self):
        self.connected = False
        self.is_moving = False
        self.last_error = None
        self.pos = [0, 0, config.Z_SAFE]
        self.current_speed = 0.0
        self.gripper_closed = False
        self._move_lock = threading.Lock()
        self.safety = RobotSafety(config)
        self.adapter_name = None
        self.adapter = None
        self.configure_adapter()
        self.motion_profiles = self._build_motion_profiles()

    def configure_adapter(self, *, force: bool = False):
        adapter_name = str(getattr(config, "ROBOT_ADAPTER", "tmflow_json")).strip().lower()
        if adapter_name not in {"tmflow_json", "techmanpy", "modbus"}:
            adapter_name = "tmflow_json"
        endpoint_changed = (
            self.adapter is not None
            and (
                str(getattr(self.adapter, "host", "")) != str(config.ROBOT_IP)
                or int(getattr(self.adapter, "port", 0) or 0) != int(config.ROBOT_PORT)
            )
        )
        force = bool(force or endpoint_changed)
        if not force and self.adapter is not None and self.adapter_name == adapter_name:
            if not getattr(self.adapter, "connected", False):
                self.adapter.host = config.ROBOT_IP
                self.adapter.port = config.ROBOT_PORT
            return self.adapter

        old_adapter = self.adapter
        try:
            if old_adapter and hasattr(old_adapter, "disconnect"):
                old_adapter.disconnect()
        except Exception:
            logger.debug("[RobotService] old adapter disconnect failed", exc_info=True)

        if adapter_name == "modbus":
            from backend.infrastructure.robot.modbus_adapter import ModbusAdapter

            self.adapter = ModbusAdapter(host=config.ROBOT_IP, port=config.ROBOT_PORT)
        elif adapter_name == "techmanpy":
            from backend.infrastructure.robot.techmanpy_adapter import TechmanPyAdapter

            self.adapter = TechmanPyAdapter(host=config.ROBOT_IP, port=config.ROBOT_PORT)
        else:
            from backend.infrastructure.robot.tmflow_json_adapter import TMflowJsonAdapter

            self.adapter = TMflowJsonAdapter(host=config.ROBOT_IP, port=config.ROBOT_PORT)
        self.adapter_name = adapter_name
        self.connected = False
        return self.adapter

    def refresh_runtime_config(self):
        self.configure_adapter(force=self.adapter_name != str(getattr(config, "ROBOT_ADAPTER", "tmflow_json")).strip().lower())
        self.safety = RobotSafety(config)
        self.motion_profiles = self._build_motion_profiles()

    def connect(self):
        self.configure_adapter()
        logger.info(f"Initializing TM Robot Interface ({config.ROBOT_IP}:{config.ROBOT_PORT}, adapter={self.adapter_name})")
        ok = self.adapter.connect()
        self.connected = bool(ok)
        if self.connected:
            logger.info("TM Robot Handshake Successful.")
            self.last_error = None
        else:
            self.last_error = getattr(self.adapter, "last_error", None) or "Robot connection failed."
        return self.connected

    def get_status(self) -> dict:
        self.connected = self._connection_alive()
        status_registers = self._read_status_registers()
        telemetry = self._read_telemetry()
        pose = telemetry.get("pose") if isinstance(telemetry, dict) else None
        position = self._position_from_pose(pose)
        orientation = (
            telemetry.get("orientation")
            if isinstance(telemetry, dict) and isinstance(telemetry.get("orientation"), dict)
            else self._orientation_dict()
        )
        joint_angles = (
            telemetry.get("joint_angles")
            if isinstance(telemetry, dict) and isinstance(telemetry.get("joint_angles"), dict)
            else {}
        )
        speed = telemetry.get("speed") if isinstance(telemetry, dict) else None
        if speed is None:
            speed = self.current_speed if self.is_moving else 0.0

        return {
            "connected": bool(self.connected),
            "is_connected": bool(self.connected),
            "busy": bool(self.is_moving),
            "error": self.last_error,
            "last_action": "",
            "queue_size": 0,
            "position": position,
            "orientation": orientation,
            "joint_angles": joint_angles,
            "speed": float(speed),
            "gripper_closed": bool(self.gripper_closed),
            "ip": str(config.ROBOT_IP),
            "port": int(config.ROBOT_PORT),
            "connection": {
                "ip": str(config.ROBOT_IP),
                "host": str(config.ROBOT_IP),
                "port": int(config.ROBOT_PORT),
                "connected": bool(self.connected),
                "mode": str(getattr(self.adapter, "mode", self.adapter_name or getattr(config, "ROBOT_ADAPTER", "tmflow_json"))),
                "adapter": str(getattr(self.adapter, "mode", self.adapter_name or getattr(config, "ROBOT_ADAPTER", "tmflow_json"))),
                "checked_at": time.time(),
            },
            "telemetry": telemetry,
            **status_registers,
        }

    async def move_piece(self, move_str: str, is_capture: bool = False):
        if estop.GLOBAL_STOP:
            logger.error("E-Stop active. Aborting robot move.")
            return False

        if not self._move_lock.acquire(blocking=False):
            self.last_error = "Robot is already executing a move."
            logger.error(self.last_error)
            self._publish_status(EventType.DIAGNOSTICS_UPDATED, {"robot": {"error": self.last_error}})
            return False

        try:
            if not self.connected and not config.FAKE_ROBOT:
                self.last_error = "Robot is not connected."
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
                plan = self._plan_move(move_str, is_capture=is_capture)

                if plan.capture_xy:
                    logger.info(f"Capture detected at {move_str[2:4]}. Clearing space...")
                    await self._execute_pick_and_place(
                        plan.end_xy[0],
                        plan.end_xy[1],
                        plan.capture_xy[0],
                        plan.capture_xy[1],
                    )

                logger.info(f"Robot Primary Move: {move_str}")
                await self._execute_pick_and_place(plan.start_xy[0], plan.start_xy[1], plan.end_xy[0], plan.end_xy[1])

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
        finally:
            self._move_lock.release()

    def _build_motion_profiles(self) -> dict:
        return {
            "travel": self._profile("travel", config.ROBOT_TRAVEL_SPEED),
            "lift": self._profile("lift", config.ROBOT_LIFT_SPEED),
            "approach": self._profile("approach", config.ROBOT_APPROACH_SPEED),
        }

    def _profile(self, label: str, speed: float) -> MotionProfile:
        speed = float(speed)
        acceleration = float(config.ROBOT_DEFAULT_ACCELERATION)
        timeout = float(config.ROBOT_MOTION_TIMEOUT_SEC)
        min_speed = float(config.ROBOT_MIN_SPEED)
        max_speed = float(config.ROBOT_MAX_SPEED)

        values = {
            "speed": speed,
            "acceleration": acceleration,
            "timeout": timeout,
            "min_speed": min_speed,
            "max_speed": max_speed,
        }
        for name, value in values.items():
            if not math.isfinite(value):
                raise ValueError(f"Robot motion {name} must be finite.")

        if min_speed <= 0 or max_speed < min_speed:
            raise ValueError("Robot speed limits must be positive and ordered.")
        if not (min_speed <= speed <= max_speed):
            raise ValueError(f"Robot {label} speed {speed} is outside safe limits.")
        if acceleration <= 0:
            raise ValueError("Robot acceleration must be positive.")
        if timeout <= 0:
            raise ValueError("Robot motion timeout must be positive.")

        return MotionProfile(label=label, speed=speed, acceleration=acceleration, timeout=timeout)

    def _check_not_stopped(self) -> None:
        if estop.GLOBAL_STOP:
            raise RuntimeError("E-Stop active during robot move.")

    def _validate_xy_target(self, x, y) -> None:
        ok, msg = self.safety.validate_move(x, y)
        if not ok:
            raise ValueError(msg)

    def _plan_move(self, move_str: str, is_capture: bool = False) -> RobotMovePlan:
        self._check_not_stopped()
        self._validate_move_command(move_str)
        self._validate_vertical_profile()
        self._validate_tool_pose()

        start_f, start_r = move_str[0], move_str[1]
        end_f, end_r = move_str[2], move_str[3]
        start_xy = kinematics.grid_to_robot(start_f, start_r)
        end_xy = kinematics.grid_to_robot(end_f, end_r)
        if not start_xy or not end_xy:
            raise ValueError("Kinematics mapping failed.")

        targets = [("start", start_xy), ("end", end_xy)]
        capture_xy = None
        if is_capture:
            capture_xy = kinematics.get_dead_zone_coords(1)
            targets.append(("capture dead zone", capture_xy))

        for label, xy in targets:
            self._validate_pick_place_target(label, xy[0], xy[1])

        return RobotMovePlan(
            move=move_str,
            start_xy=(float(start_xy[0]), float(start_xy[1])),
            end_xy=(float(end_xy[0]), float(end_xy[1])),
            capture_xy=(float(capture_xy[0]), float(capture_xy[1])) if capture_xy else None,
        )

    def _validate_pick_place_target(self, label: str, x, y) -> None:
        z_values = (
            float(config.Z_SAFE),
            float(config.Z_GRAB),
            float(config.Z_GRAB) + float(config.ROBOT_PLACE_Z_OFFSET),
        )
        for z in z_values:
            ok, msg = self.safety.validate_position(x, y, z)
            if not ok:
                raise ValueError(f"{label} target is unsafe: {msg}")

    def _validate_move_command(self, move_str: str) -> None:
        if not isinstance(move_str, str) or not re.fullmatch(r"[a-i][0-9][a-i][0-9]", move_str):
            raise ValueError(f"Invalid UCCI move command: {move_str!r}")
        if move_str[:2] == move_str[2:]:
            raise ValueError(f"Refusing no-op robot move: {move_str}")

    def _validate_vertical_profile(self) -> None:
        z_safe = float(config.Z_SAFE)
        z_grab = float(config.Z_GRAB)
        z_place = z_grab + float(config.ROBOT_PLACE_Z_OFFSET)
        if not all(math.isfinite(value) for value in (z_safe, z_grab, z_place)):
            raise ValueError("Robot Z profile must be finite.")
        if z_safe <= z_grab:
            raise ValueError(f"Unsafe Z profile: Z_SAFE ({z_safe}) must be greater than Z_GRAB ({z_grab}).")
        if not (z_grab <= z_place < z_safe):
            raise ValueError("Unsafe place Z profile: place height must stay between grab and safe height.")

    def _validate_tool_pose(self) -> None:
        for axis, value in zip(("RX", "RY", "RZ"), self._tool_pose()):
            if not math.isfinite(value):
                raise ValueError(f"Robot tool {axis} must be finite.")

    def _tool_pose(self):
        return [
            float(getattr(config, "ROBOT_TOOL_RX", 0.0)),
            float(getattr(config, "ROBOT_TOOL_RY", 0.0)),
            float(getattr(config, "ROBOT_TOOL_RZ", 0.0)),
        ]

    def _orientation_dict(self) -> dict:
        rx, ry, rz = self._tool_pose()
        return {"rx": rx, "ry": ry, "rz": rz}

    def _position_from_pose(self, pose) -> dict:
        if isinstance(pose, dict):
            position = {
                "x": float(pose.get("x", self.pos[0]) or 0.0),
                "y": float(pose.get("y", self.pos[1]) or 0.0),
                "z": float(pose.get("z", self.pos[2]) or 0.0),
            }
            self.pos = [position["x"], position["y"], position["z"]]
            return position
        return {"x": float(self.pos[0]), "y": float(self.pos[1]), "z": float(self.pos[2])}

    def _connection_alive(self) -> bool:
        if not self.connected:
            return False
        ping = getattr(self.adapter, "ping", None)
        if callable(ping):
            try:
                return bool(ping())
            except Exception as exc:
                logger.warning(f"[Robot] connection ping failed: {exc}")
                return False
        return bool(getattr(self.adapter, "connected", self.connected))

    def _read_status_registers(self) -> dict:
        if not self.connected:
            return {}
        reader = getattr(self.adapter, "read_status_registers", None)
        if not callable(reader):
            return {}
        try:
            return dict(reader() or {})
        except Exception as exc:
            logger.warning(f"[Robot] status register read failed: {exc}")
            return {"status_error": str(exc)}

    def _read_telemetry(self) -> dict:
        reader = getattr(self.adapter, "read_telemetry", None)
        if not self.connected or not callable(reader):
            return {"enabled": bool(getattr(config, "ROBOT_TELEMETRY_ENABLED", False)), "source": "software"}
        telemetry = reader() or {}
        if telemetry.get("source") in {"hardware", "unavailable"}:
            return dict(telemetry)
        return {**dict(telemetry), "source": telemetry.get("source") or "software"}

    async def _execute_pick_and_place(self, sx, sy, ex, ey):
        await self._motion(sx, sy, config.Z_SAFE, self.motion_profiles["travel"])
        await self._motion(sx, sy, config.Z_GRAB, self.motion_profiles["approach"])
        await self._set_gripper(True)
        await self._motion(sx, sy, config.Z_SAFE, self.motion_profiles["lift"])

        await self._motion(ex, ey, config.Z_SAFE, self.motion_profiles["travel"])
        await self._motion(ex, ey, config.Z_GRAB + config.ROBOT_PLACE_Z_OFFSET, self.motion_profiles["approach"])
        await self._set_gripper(False)
        await self._motion(ex, ey, config.Z_SAFE, self.motion_profiles["lift"])

    async def _motion(self, x, y, z, profile: MotionProfile = None):
        profile = profile or self.motion_profiles["travel"]
        self._check_not_stopped()
        coords = [float(x), float(y), float(z), *self._tool_pose()]
        ok, msg = self.safety.validate_position(coords[0], coords[1], coords[2])
        if not ok:
            raise ValueError(msg)
        self.current_speed = float(profile.speed)
        if self.connected:
            sender = getattr(self.adapter, "send_motion", None)
            if callable(sender):
                ok = await self._wait_for_hardware_motion(
                    asyncio.to_thread(
                        sender,
                        coords,
                        speed=profile.speed,
                        acceleration=profile.acceleration,
                        timeout=profile.timeout,
                    ),
                    profile=profile,
                    coords=coords,
                )
            else:
                ok = await self._wait_for_hardware_motion(
                    asyncio.to_thread(self.adapter.send_move, coords),
                    profile=profile,
                    coords=coords,
                )
                if not ok:
                    raise RuntimeError(f"Robot motion failed for target {coords[:3]}")
            if not ok:
                raise RuntimeError(f"Robot motion failed for target {coords[:3]}")
        else:
            if not config.FAKE_ROBOT:
                raise RuntimeError("Robot is not connected.")
            await asyncio.sleep(min(0.5, profile.timeout))
        self._check_not_stopped()
        self.pos = coords[:3]
        self.current_speed = float(profile.speed) if self.is_moving else 0.0

    async def _wait_for_hardware_motion(self, awaitable, profile: MotionProfile, coords):
        try:
            return await asyncio.wait_for(awaitable, timeout=float(profile.timeout))
        except asyncio.TimeoutError as exc:
            try:
                await asyncio.to_thread(self.adapter.halt)
            except Exception:
                logger.warning("[Robot] halt failed after motion timeout", exc_info=True)
            raise RuntimeError(
                f"Robot motion timed out after {profile.timeout:.2f}s for target {coords[:3]}"
            ) from exc

    async def _set_gripper(self, closed: bool):
        self._check_not_stopped()
        action = "close" if closed else "open"
        dwell = config.ROBOT_GRIPPER_CLOSE_DWELL_SEC if closed else config.ROBOT_GRIPPER_OPEN_DWELL_SEC
        if not math.isfinite(float(dwell)) or float(dwell) < 0:
            raise ValueError("Robot gripper dwell must be finite and non-negative.")

        if self.connected:
            setter = getattr(self.adapter, "set_gripper", None)
            if not callable(setter):
                raise RuntimeError("Robot adapter does not support gripper control.")
            ok = await asyncio.to_thread(setter, bool(closed))
            if not ok:
                raise RuntimeError(f"Robot gripper {action} failed.")
        else:
            if not config.FAKE_ROBOT:
                raise RuntimeError("Robot is not connected.")
            logger.info(f"[Robot] Simulated gripper {action}.")

        logger.info(f"[Robot] Gripper/Vacuum {action.upper()}")
        if dwell:
            await asyncio.sleep(float(dwell))
        self._check_not_stopped()
        self.gripper_closed = bool(closed)

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

    def disconnect(self):
        try:
            if self.adapter and hasattr(self.adapter, "disconnect"):
                self.adapter.disconnect()
        finally:
            self.connected = False


# Optional module-level singleton (wired during bootstrap if needed)
robot_service = None
