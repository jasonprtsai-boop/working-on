from __future__ import annotations

import ipaddress
import socket
import time
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

    network_status = _robot_network_config()
    add(
        "robot_network_config",
        bool(network_status.get("ok")),
        "Robot Network",
        str(network_status.get("message") or "Robot and PC network settings are ready."),
        severity="warning" if fake_robot else "error",
        details=network_status.get("details", {}),
    )

    adapter = str(getattr(config, "ROBOT_ADAPTER", "tmflow_json")).strip().lower()
    tcp_probe = _robot_tcp_connect_probe(fake_robot=fake_robot, adapter=adapter, robot_status=robot_status)
    if tcp_probe.get("required") or not tcp_probe.get("ok"):
        add(
            "robot_tcp_connect_probe",
            bool(tcp_probe.get("ok")),
            "Robot TCP Probe",
            str(tcp_probe.get("message") or "Robot TCP probe completed."),
            severity="warning" if fake_robot else "error",
            details=tcp_probe.get("details", {}),
        )

    if adapter == "modbus":
        add(
            "robot_communication_probe",
            fake_robot or (
                bool(getattr(config, "ROBOT_VERIFY_STATUS_ON_CONNECT", False))
                and bool(getattr(config, "ROBOT_COMMAND_HANDSHAKE_ENABLED", True))
                and bool(getattr(config, "ROBOT_GRIPPER_FEEDBACK_ENABLED", True))
            ),
            "Robot Communication",
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
                "adapter": adapter,
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
    elif adapter == "techmanpy":
        listen_node_active = robot_status.get("listen_node_active")
        connected = bool(robot_status.get("connected"))
        add(
            "robot_communication_probe",
            fake_robot or (connected and listen_node_active is not False),
            "Robot Communication",
            (
                "Simulation mode does not require External Script verification."
                if fake_robot
                else (
                    "TechmanPy External Script communication is ready."
                    if connected and listen_node_active is not False
                    else "Enable TMflow Listen Node / External Script before real robot play."
                )
            ),
            severity="warning" if fake_robot else "error",
            details={
                "adapter": adapter,
                "tmflow_version": getattr(config, "TMFLOW_VERSION", None),
                "controller_version": getattr(config, "TM_CONTROLLER_VERSION", None),
                "port": getattr(config, "ROBOT_PORT", None),
                "listen_node_active": listen_node_active,
                "require_listen_node": getattr(config, "ROBOT_TECHMANPY_REQUIRE_LISTEN_NODE", True),
            },
        )
    else:
        connected = bool(robot_status.get("connected"))
        tmflow_state = robot_status.get("tmflow_json_state")
        tmflow_status = robot_status.get("tmflow_json_status")
        add(
            "robot_communication_probe",
            fake_robot or connected,
            "Robot Communication",
            (
                "Simulation mode does not require TMflow TCP JSON verification."
                if fake_robot
                else (
                    "TMflow TCP JSON communication is ready."
                    if connected
                    else "Start the TMflow TCP JSON socket server before real robot play."
                )
            ),
            severity="warning" if fake_robot else "error",
            details={
                "adapter": adapter,
                "protocol": "tcp_json",
                "tmflow_version": getattr(config, "TMFLOW_VERSION", None),
                "controller_version": getattr(config, "TM_CONTROLLER_VERSION", None),
                "port": getattr(config, "ROBOT_PORT", None),
                "wire_format": getattr(config, "ROBOT_TMFLOW_WIRE_FORMAT", "envelope"),
                "tmflow_state": tmflow_state,
                "tmflow_status": tmflow_status,
            },
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

    ingest_key_status = _tmflow_vision_ingest_key_status(fake_robot=fake_robot)
    add(
        "tmflow_vision_ingest_key",
        bool(ingest_key_status.get("ok")),
        "TMflow Vision Key",
        str(ingest_key_status.get("message") or "TMflow vision ingest key is ready."),
        severity="error" if ingest_key_status.get("required") else "warning",
        details=ingest_key_status.get("details", {}),
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


def _robot_network_config() -> Dict[str, Any]:
    robot_ip_text = str(getattr(config, "ROBOT_IP", "") or "").strip()
    pc_ip_text = str(getattr(config, "ROBOT_PC_IP", "") or "").strip()
    subnet_mask_text = str(getattr(config, "ROBOT_SUBNET_MASK", "") or "").strip()
    details: Dict[str, Any] = {
        "robot_ip": robot_ip_text,
        "pc_ip": pc_ip_text,
        "subnet_mask": subnet_mask_text,
    }
    try:
        robot_ip = ipaddress.ip_address(robot_ip_text)
        pc_ip = ipaddress.ip_address(pc_ip_text)
        robot_network = ipaddress.ip_network(f"{robot_ip}/{subnet_mask_text}", strict=False)
        pc_network = ipaddress.ip_network(f"{pc_ip}/{subnet_mask_text}", strict=False)
    except ValueError as exc:
        details["error"] = str(exc)
        return {
            "ok": False,
            "message": "Robot IP, PC IP, or subnet mask is invalid.",
            "details": details,
        }

    details.update({
        "robot_network": str(robot_network),
        "pc_network": str(pc_network),
    })
    if robot_ip.version != 4 or pc_ip.version != 4:
        return {
            "ok": False,
            "message": "Robot and PC IPs must use IPv4 for the TMflow lab link.",
            "details": details,
        }
    if robot_ip == pc_ip:
        return {
            "ok": False,
            "message": "Robot IP and PC Ethernet IP must not be the same.",
            "details": details,
        }
    if robot_network != pc_network:
        return {
            "ok": False,
            "message": "Robot IP and PC Ethernet IP are not in the same subnet.",
            "details": details,
        }
    return {
        "ok": True,
        "message": f"Robot and PC are on {robot_network}.",
        "details": details,
    }


def _robot_tcp_connect_probe(
    *,
    fake_robot: bool,
    adapter: str,
    robot_status: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    adapter_name = str(adapter or "").strip().lower()
    required = bool(not fake_robot and adapter_name == "tmflow_json")
    host = str(getattr(config, "ROBOT_IP", "") or "").strip()
    port = int(getattr(config, "ROBOT_PORT", 5890) or 5890)
    timeout = max(0.05, float(getattr(config, "ROBOT_CONNECT_TIMEOUT_SEC", 1.0) or 1.0))
    details: Dict[str, Any] = {
        "adapter": adapter_name,
        "required": required,
        "host": host,
        "port": port,
        "timeout_sec": timeout,
    }
    if fake_robot:
        return {
            "ok": True,
            "required": False,
            "message": "Simulation mode does not require a robot TCP probe.",
            "details": details,
        }
    if adapter_name != "tmflow_json":
        return {
            "ok": True,
            "required": False,
            "message": "Robot TCP probe is only required for TMflow TCP JSON mode.",
            "details": details,
        }
    if bool((robot_status or {}).get("connected")):
        details["source"] = "robot_status"
        return {
            "ok": True,
            "required": True,
            "message": "Robot TCP connection is already established.",
            "details": details,
        }
    start = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
        details["rtt_ms"] = round((time.monotonic() - start) * 1000.0, 2)
        return {
            "ok": True,
            "required": True,
            "message": "Robot TCP port accepted a connection.",
            "details": details,
        }
    except Exception as exc:
        details["error"] = str(exc)
        details["rtt_ms"] = round((time.monotonic() - start) * 1000.0, 2)
        return {
            "ok": False,
            "required": True,
            "message": "Robot TCP port did not accept a connection.",
            "details": details,
        }


def _tmflow_vision_ingest_key_status(*, fake_robot: bool | None = None) -> Dict[str, Any]:
    source = str(getattr(config, "VISION_SOURCE", "opencv") or "").strip().lower()
    key_configured = bool(str(getattr(config, "VISION_TMFLOW_INGEST_KEY", "") or "").strip())
    bind_host = str(getattr(config, "BIND_HOST", "127.0.0.1") or "").strip()
    fake = bool(getattr(config, "FAKE_ROBOT", True) if fake_robot is None else fake_robot)
    exposed_network = bind_host in {"0.0.0.0", "::"}
    required = source == "tmflow_json" and (
        bool(getattr(config, "IS_PRODUCTION", False)) or exposed_network or not fake
    )
    details = {
        "vision_source": source,
        "ingest_key_configured": key_configured,
        "required": required,
        "bind_host": bind_host,
        "exposed_network": exposed_network,
        "fake_robot": fake,
    }
    if required and not key_configured:
        return {
            "ok": False,
            "message": "Set VISION_TMFLOW_INGEST_KEY before using TMflow vision with real hardware or a shared network.",
            "details": details,
        }
    return {
        "ok": True,
        "message": (
            "TMflow vision ingest key is configured."
            if key_configured
            else "TMflow vision ingest key is not required for local simulation."
        ),
        "details": details,
    }


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
