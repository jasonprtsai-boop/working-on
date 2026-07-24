from __future__ import annotations

from typing import Any, Dict

from backend.application.container import container
from backend.application.services.estop import estop
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

    add(
        "estop_clear",
        not bool(getattr(estop, "GLOBAL_STOP", False)),
        "E-Stop",
        "Emergency stop is clear." if not getattr(estop, "GLOBAL_STOP", False) else "Emergency stop is active.",
    )

    robot_status = _robot_status()
    fake_robot = bool(getattr(config, "FAKE_ROBOT", True))
    auto_execute = bool(getattr(config, "AUTO_EXECUTE_ROBOT", False))
    add(
        "robot_mode_confirmed",
        fake_robot or robot_status.get("connected"),
        "Robot Mode",
        "Simulation robot is active." if fake_robot else (
            "Real robot is connected." if robot_status.get("connected") else "Real robot mode is selected but robot is not connected."
        ),
        details={"fake_robot": fake_robot, "auto_execute_robot": auto_execute},
    )
    add(
        "auto_execute_enabled",
        auto_execute or not require_auto_execute,
        "Auto Execute",
        "Robot auto execution is enabled." if auto_execute else "Robot auto execution is disabled.",
        severity="warning" if not require_auto_execute else "error",
    )

    add(
        "robot_register_probe",
        fake_robot or (
            bool(getattr(config, "ROBOT_VERIFY_STATUS_ON_CONNECT", False))
            and bool(getattr(config, "ROBOT_COMMAND_HANDSHAKE_ENABLED", True))
            and bool(getattr(config, "ROBOT_GRIPPER_FEEDBACK_ENABLED", True))
        ),
        "Robot Registers",
        (
            "Status, command ack, and gripper feedback checks are enabled."
            if (
                getattr(config, "ROBOT_VERIFY_STATUS_ON_CONNECT", False)
                and getattr(config, "ROBOT_COMMAND_HANDSHAKE_ENABLED", True)
                and getattr(config, "ROBOT_GRIPPER_FEEDBACK_ENABLED", True)
            )
            else (
                "Simulation mode does not require register verification."
                if fake_robot
                else "Enable status verification, command handshake, and gripper feedback before real robot play."
            )
        ),
        severity="warning" if fake_robot else "error",
        details={
            "status_register": getattr(config, "ROBOT_STATUS_REGISTER", None),
            "motion_register_base": getattr(config, "ROBOT_MOTION_REGISTER_BASE", None),
            "command_id_register": getattr(config, "ROBOT_COMMAND_ID_REGISTER", None),
            "command_trigger_register": getattr(config, "ROBOT_COMMAND_TRIGGER_REGISTER", None),
            "command_ack_register": getattr(config, "ROBOT_COMMAND_ACK_REGISTER", None),
            "error_code_register": getattr(config, "ROBOT_ERROR_CODE_REGISTER", None),
            "gripper_status_register": getattr(config, "ROBOT_GRIPPER_STATUS_REGISTER", None),
            "telemetry_enabled": getattr(config, "ROBOT_TELEMETRY_ENABLED", False),
            "telemetry_pose_register_base": getattr(config, "ROBOT_TELEMETRY_POSE_REGISTER_BASE", None),
            "telemetry_joint_register_base": getattr(config, "ROBOT_TELEMETRY_JOINT_REGISTER_BASE", None),
            "telemetry_speed_register": getattr(config, "ROBOT_TELEMETRY_SPEED_REGISTER", None),
        },
    )

    add(
        "vision_ready",
        _vision_ready(),
        "Vision",
        "Vision system is calibrated or running in simulation." if _vision_ready() else "Vision is not calibrated or unavailable.",
        severity="warning",
    )

    add(
        "motion_profile_safe",
        _motion_profile_safe(),
        "Motion Profile",
        "Z profile and speed limits are safe." if _motion_profile_safe() else "Z profile or speed settings are unsafe.",
    )

    add(
        "board_and_dead_zone_safe",
        _board_and_dead_zone_safe(),
        "Board Area",
        "Board and dead-zone coordinates are inside soft limits." if _board_and_dead_zone_safe() else "Board or dead-zone coordinates exceed soft limits.",
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
            "robot_ip": getattr(config, "ROBOT_IP", ""),
            "robot_port": getattr(config, "ROBOT_PORT", None),
        },
        "robot": robot_status,
    }


def _robot_status() -> Dict[str, Any]:
    try:
        robot = container.get("robot")
        if robot and hasattr(robot, "get_status"):
            return dict(robot.get_status())
    except Exception as exc:
        return {"connected": False, "busy": False, "error": str(exc)}
    return {"connected": False, "busy": False, "error": "robot_not_registered"}


def _vision_ready() -> bool:
    try:
        if bool(getattr(config, "FAKE_VISION", False)):
            return True
        from backend.interfaces.api.shared import vision_system

        status = vision_system.get_calibration_status() if hasattr(vision_system, "get_calibration_status") else {}
        return bool(status.get("calibrated") or status.get("loaded_from_file") or status.get("simulation"))
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
