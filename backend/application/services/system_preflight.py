from __future__ import annotations

from typing import Any, Dict

from backend.application.container import container
from backend.infrastructure.robot.safety import RobotSafety
from backend.utils import config
from backend.utils.kinematics import kinematics


def build_preflight_report(*, require_auto_execute: bool = False) -> Dict[str, Any]:
    """Return operator-facing readiness checks for setup-to-play flow."""
    checks = []

    def add(key: str, ok: bool, label: str, message: str, *, severity: str = "error", details=None):
        checks.append({
            "key": key,
            "ok": bool(ok),
            "label": label,
            "message": message,
            "severity": severity,
            "details": details or {},
        })

    robot_status = _robot_status()
    fake_robot = bool(getattr(config, "FAKE_ROBOT", True))
    auto_execute = bool(getattr(config, "AUTO_EXECUTE_ROBOT", False))
    adapter = str(getattr(config, "ROBOT_ADAPTER", "tmflow_json")).strip().lower()
    robot_mode = _robot_mode_summary(
        fake_robot=fake_robot,
        adapter=adapter,
        robot_status=robot_status,
        auto_execute=auto_execute,
    )
    add(
        "robot_mode_confirmed",
        bool(robot_mode.get("ok")),
        "Robot Mode",
        str(robot_mode.get("message") or "Robot mode is selected."),
        details=robot_mode.get("details", {}),
    )
    add(
        "auto_execute_enabled",
        auto_execute or not require_auto_execute,
        "Auto Execute",
        "Robot auto execution is enabled." if auto_execute else "Robot auto execution is disabled.",
        severity="warning" if not require_auto_execute else "error",
    )

    communication = _robot_communication_summary(fake_robot=fake_robot, adapter=adapter, robot_status=robot_status)
    add(
        "robot_communication",
        bool(communication.get("ok")),
        "Robot Communication",
        str(communication.get("message") or "Robot communication mode is selected."),
        severity="warning" if fake_robot else "error",
        details=communication.get("details", {}),
    )

    vision_readiness = _vision_readiness_status(fake_robot=fake_robot)
    add(
        "vision_ready",
        bool(vision_readiness.get("ok")),
        "Vision",
        str(vision_readiness.get("message") or "Vision is not calibrated or unavailable."),
        severity="warning" if fake_robot else "error",
        details=vision_readiness.get("details", {}),
    )

    motion_safe = _motion_profile_safe()
    add(
        "motion_profile_safe",
        motion_safe,
        "Motion Profile",
        "Z profile and speed limits are safe." if motion_safe else "Z profile or speed settings are unsafe.",
    )

    board_safe = _board_and_dead_zone_safe()
    add(
        "board_and_dead_zone_safe",
        board_safe,
        "Board Area",
        "Board and dead-zone coordinates are inside soft limits." if board_safe else "Board or dead-zone coordinates exceed soft limits.",
    )

    hard_failures = [item for item in checks if not item["ok"] and item["severity"] == "error"]
    warnings = [item for item in checks if not item["ok"] and item["severity"] == "warning"]
    return {
        "ok": not hard_failures,
        "ready": not hard_failures,
        "checks": checks,
        "warnings": warnings,
        "failures": hard_failures,
        "mode": {
            "fake_robot": fake_robot,
            "auto_execute_robot": auto_execute,
            "robot_adapter": getattr(config, "ROBOT_ADAPTER", "tmflow_json"),
            "robot_ip": getattr(config, "ROBOT_IP", ""),
            "robot_pc_ip": getattr(config, "ROBOT_PC_IP", ""),
            "robot_subnet_mask": getattr(config, "ROBOT_SUBNET_MASK", ""),
            "robot_port": getattr(config, "ROBOT_PORT", None),
            "vision_source": getattr(config, "VISION_SOURCE", "opencv"),
            "vision_tmflow_image_port": getattr(config, "VISION_TMFLOW_IMAGE_PORT", None),
            "vision_tmflow_ingest_key_configured": bool(str(getattr(config, "VISION_TMFLOW_INGEST_KEY", "") or "").strip()),
        },
        "robot": robot_status,
    }


def _robot_communication_summary(
    *,
    fake_robot: bool,
    adapter: str,
    robot_status: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    adapter_name = str(adapter or "tmflow_json").strip().lower()
    status = robot_status or {}
    connected = bool((robot_status or {}).get("connected"))
    if fake_robot:
        return {
            "ok": True,
            "message": "Simulation mode is active.",
            "details": {"adapter": adapter_name},
        }
    if adapter_name == "modbus":
        role = str(getattr(config, "ROBOT_MODBUS_ROLE", "client")).strip().lower()
        payload_mode = str(getattr(config, "ROBOT_MODBUS_PAYLOAD_MODE", "pose")).strip().lower()
        details = {
            "adapter": adapter_name,
            "role": role,
            "payload_mode": payload_mode,
            "server_host": getattr(config, "ROBOT_MODBUS_SERVER_HOST", None),
            "server_port": getattr(config, "ROBOT_MODBUS_SERVER_PORT", None),
            "register_addressing": getattr(config, "ROBOT_MODBUS_REGISTER_ADDRESSING", "holding_40001"),
        }
        if role == "server":
            tmflow_ready, tmflow_details = _tmflow_server_polling_ready(status)
            details.update(tmflow_details)
            if payload_mode != "square_command":
                return {
                    "ok": False,
                    "message": "Modbus server mode requires square-command payload mode for TMflow polling.",
                    "details": details,
                }
            if not connected:
                return {
                    "ok": False,
                    "message": "Python Modbus server is not listening.",
                    "details": details,
                }
            return {
                "ok": bool(tmflow_ready),
                "message": (
                    "Python Modbus server is listening and TMflow heartbeat/ready signal has been observed."
                    if tmflow_ready
                    else "Python Modbus server is listening, but no TMflow heartbeat/ready signal has been observed."
                ),
                "details": details,
            }
        return {
            "ok": connected,
            "message": "Modbus client mode is selected; confirm the robot register map before motion.",
            "details": {**details, "connected": connected},
        }
    if adapter_name == "techmanpy":
        return {
            "ok": connected,
            "message": "TechmanPy / External Script mode is selected.",
            "details": {
                "adapter": adapter_name,
                "port": getattr(config, "ROBOT_PORT", None),
                "connected": connected,
            },
        }
    return {
        "ok": connected,
        "message": "TMflow TCP JSON mode is selected.",
        "details": {
            "adapter": adapter_name,
            "port": getattr(config, "ROBOT_PORT", None),
            "wire_format": getattr(config, "ROBOT_TMFLOW_WIRE_FORMAT", "envelope"),
            "connected": connected,
        },
    }


def _robot_mode_summary(
    *,
    fake_robot: bool,
    adapter: str,
    robot_status: Dict[str, Any] | None,
    auto_execute: bool,
) -> Dict[str, Any]:
    adapter_name = str(adapter or "tmflow_json").strip().lower()
    connected = bool((robot_status or {}).get("connected"))
    details: Dict[str, Any] = {
        "fake_robot": fake_robot,
        "auto_execute_robot": auto_execute,
        "adapter": adapter_name,
    }
    if fake_robot:
        return {"ok": True, "message": "Simulation robot is active.", "details": details}
    if adapter_name == "modbus":
        role = str(getattr(config, "ROBOT_MODBUS_ROLE", "client")).strip().lower()
        details.update({
            "role": role,
            "payload_mode": str(getattr(config, "ROBOT_MODBUS_PAYLOAD_MODE", "pose")).strip().lower(),
        })
        if role == "server":
            return {
                "ok": connected,
                "message": (
                    "Python Modbus server is listening; TMflow polling is checked separately."
                    if connected
                    else "Real robot mode is selected, but the Python Modbus server is not listening."
                ),
                "details": details,
            }
    return {
        "ok": connected,
        "message": "Real robot is connected." if connected else "Real robot mode is selected but robot is not connected.",
        "details": details,
    }


def _tmflow_server_polling_ready(robot_status: Dict[str, Any]) -> tuple[bool, Dict[str, Any]]:
    telemetry = robot_status.get("telemetry") if isinstance(robot_status.get("telemetry"), dict) else {}
    connection = robot_status.get("connection") if isinstance(robot_status.get("connection"), dict) else {}
    heartbeat = _optional_int(robot_status.get("heartbeat"))
    robot_state = _optional_int(robot_status.get("robot_state_code"))
    completed_command = _optional_int(robot_status.get("completed_command_id"))
    heartbeat_seen = bool(robot_status.get("heartbeat_seen") or telemetry.get("heartbeat_seen"))
    ready = bool(
        heartbeat_seen
        or (heartbeat is not None and heartbeat > 0)
        or (robot_state is not None and robot_state > 0)
        or (completed_command is not None and completed_command > 0)
    )
    return ready, {
        "tmflow_heartbeat_seen": heartbeat_seen,
        "modbus_heartbeat": heartbeat,
        "robot_state_code": robot_state,
        "completed_command_id": completed_command,
        "telemetry_connected": bool(connection.get("telemetry_connected")),
    }


def _optional_int(value) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _robot_status() -> Dict[str, Any]:
    try:
        robot = container.get("robot")
        if robot and hasattr(robot, "get_status"):
            return dict(robot.get_status())
    except Exception as exc:
        return {"connected": False, "busy": False, "error": str(exc)}
    return {"connected": False, "busy": False, "error": "robot_not_registered"}


def _vision_readiness_status(*, fake_robot: bool | None = None) -> Dict[str, Any]:
    fake = bool(getattr(config, "FAKE_ROBOT", True) if fake_robot is None else fake_robot)
    configured_fake_vision = bool(getattr(config, "FAKE_VISION", False))
    details: Dict[str, Any] = {
        "fake_robot": fake,
        "configured_fake_vision": configured_fake_vision,
        "vision_source": getattr(config, "VISION_SOURCE", "opencv"),
    }
    if configured_fake_vision:
        details.update({
            "simulation": True,
            "fallback": False,
        })
        if fake:
            return {
                "ok": True,
                "message": "Vision simulation is active.",
                "details": details,
            }
        return {
            "ok": False,
            "message": "Fake vision is enabled while real robot mode is selected.",
            "details": details,
        }

    try:
        from backend.interfaces.api.shared import runtime_vision_status, vision_system

        runtime_status = runtime_vision_status()
        calibration = vision_system.get_calibration_status() if hasattr(vision_system, "get_calibration_status") else {}
        fallback_reason = (
            runtime_status.get("fallback_reason")
            or calibration.get("fallback_reason")
            or getattr(vision_system, "_fallback_reason", None)
        )
        fallback = bool(runtime_status.get("fallback") or calibration.get("fallback") or fallback_reason)
        simulation = bool(runtime_status.get("simulation") or calibration.get("simulation"))
        calibrated = bool(calibration.get("calibrated") or calibration.get("loaded_from_file"))
        details.update({
            "system": runtime_status.get("system") or vision_system.__class__.__name__,
            "mode": runtime_status.get("mode"),
            "available": runtime_status.get("available"),
            "startup_failure": bool(runtime_status.get("startup_failure")),
            "startup_error": runtime_status.get("startup_error"),
            "degraded": bool(runtime_status.get("degraded")),
            "simulation": simulation,
            "fallback": fallback,
            "fallback_reason": str(fallback_reason) if fallback_reason else None,
            "calibrated": bool(calibration.get("calibrated")),
            "loaded_from_file": bool(calibration.get("loaded_from_file")),
            "calibration_path": calibration.get("path"),
            "calibration_path_exists": bool(calibration.get("path_exists")),
        })
        if fallback:
            return {
                "ok": False,
                "message": "Real vision failed to start and fallback simulation is active.",
                "details": details,
            }
        if simulation:
            return {
                "ok": False,
                "message": "Vision is running in simulation while FAKE_VISION is false.",
                "details": details,
            }
        if details["startup_failure"] or details["available"] is False or runtime_status.get("mode") == "unavailable":
            return {
                "ok": False,
                "message": "Real vision is unavailable and simulation fallback is disabled.",
                "details": details,
            }
        if calibrated:
            return {
                "ok": True,
                "message": "Vision system is calibrated.",
                "details": details,
            }
        return {
            "ok": False,
            "message": "Vision is not calibrated or unavailable.",
            "details": details,
        }
    except Exception as exc:
        details["error"] = str(exc)
        return {
            "ok": False,
            "message": "Vision readiness check failed.",
            "details": details,
        }


def _vision_ready() -> bool:
    try:
        return bool(_vision_readiness_status().get("ok"))
    except Exception:
        return False


def _motion_profile_safe() -> bool:
    try:
        z_safe = float(config.Z_SAFE)
        z_grab = float(config.Z_GRAB)
        z_place = z_grab + float(config.ROBOT_PLACE_Z_OFFSET)
        min_speed = float(config.ROBOT_MIN_SPEED)
        max_speed = float(config.ROBOT_MAX_SPEED)
        speeds = [float(config.ROBOT_TRAVEL_SPEED), float(config.ROBOT_LIFT_SPEED), float(config.ROBOT_APPROACH_SPEED)]
        return (
            z_safe > z_grab
            and z_grab <= z_place < z_safe
            and min_speed > 0
            and max_speed >= min_speed
            and all(min_speed <= speed <= max_speed for speed in speeds)
            and float(config.ROBOT_DEFAULT_ACCELERATION) > 0
            and float(config.ROBOT_MOTION_TIMEOUT_SEC) > 0
        )
    except Exception:
        return False


def _board_and_dead_zone_safe() -> bool:
    try:
        safety = RobotSafety(config)
        for file_char in kinematics.files:
            for rank in range(10):
                xy = kinematics.grid_to_robot(file_char, str(rank))
                if xy is None or not safety.validate_move(*xy)[0]:
                    return False
        dz_x, dz_y = kinematics.get_dead_zone_coords(1)
        return bool(safety.validate_move(dz_x, dz_y)[0])
    except Exception:
        return False
