from __future__ import annotations

import math
from copy import deepcopy
from typing import Any, Mapping

from flask import jsonify, request

from backend.interfaces.api.shared import api_bp, error_response, json_object_payload, vision_system
from backend.interfaces.api.client_identity import client_ip
from backend.interfaces.api.shared import publish_security_event
from backend.application.services.system_preflight import build_preflight_report
from backend.application.services.commissioning_report import (
    load_commissioning_report,
    mark_settings_saved,
    record_hardware_test,
    record_preflight,
)
from backend.utils import config
from backend.utils.kinematics import Kinematics, kinematics
from backend.utils.setup_settings import deep_merge, load_settings, save_settings


def _finite_float(value: Any, field_name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite.")
    return number


def _bounded_int(value: Any, field_name: str, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer.") from exc
    if number < minimum or number > maximum:
        raise ValueError(f"{field_name} must be between {minimum} and {maximum}.")
    return number


def _text(value: Any, field_name: str, *, max_length: int = 128) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required.")
    if len(text) > max_length:
        raise ValueError(f"{field_name} is too long.")
    return text


def _bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{field_name} must be a boolean.")


def _get(data: Mapping[str, Any], dotted_path: str, default: Any = None) -> Any:
    current: Any = data
    for part in dotted_path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return default
        current = current[part]
    return current


def _set(data: dict[str, Any], dotted_path: str, value: Any) -> None:
    current = data
    parts = dotted_path.split(".")
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value


def current_setup_settings() -> dict[str, Any]:
    calibration = kinematics.to_dict()
    try:
        vision_calibration = vision_system.get_calibration_status() if hasattr(vision_system, "get_calibration_status") else {}
    except Exception:
        vision_calibration = {}
    return {
        "vision": {
            "camera_index": int(getattr(config, "CAMERA_INDEX", 0) or 0),
            "result_max_age_sec": float(getattr(config, "VISION_RESULT_MAX_AGE_SEC", 3.0)),
            "calibration": vision_calibration,
        },
        "robot": {
            "runtime": {
                "fake_robot": bool(getattr(config, "FAKE_ROBOT", True)),
                "auto_execute_robot": bool(getattr(config, "AUTO_EXECUTE_ROBOT", False)),
            },
            "connection": {
                "adapter": str(getattr(config, "ROBOT_ADAPTER", "tmflow_json")),
                "ip": str(getattr(config, "ROBOT_IP", "169.254.47.64")),
                "port": int(getattr(config, "ROBOT_PORT", 5890)),
                "pc_ip": str(getattr(config, "ROBOT_PC_IP", "169.254.47.50")),
                "subnet_mask": str(getattr(config, "ROBOT_SUBNET_MASK", "255.255.0.0")),
                "timeout_sec": float(getattr(config, "ROBOT_CONNECT_TIMEOUT_SEC", 3.0)),
                "tmflow_version": str(getattr(config, "TMFLOW_VERSION", "1.82")),
                "controller_version": str(getattr(config, "TM_CONTROLLER_VERSION", "1.82.51")),
            },
            "techmanpy": {
                "require_listen_node": bool(getattr(config, "ROBOT_TECHMANPY_REQUIRE_LISTEN_NODE", True)),
                "motion_mode": str(getattr(config, "ROBOT_TECHMANPY_MOTION_MODE", "ptp")),
                "suppress_warnings": bool(getattr(config, "ROBOT_TECHMANPY_SUPPRESS_WARNINGS", False)),
                "gripper_close_script": str(getattr(config, "ROBOT_GRIPPER_CLOSE_SCRIPT", "")),
                "gripper_open_script": str(getattr(config, "ROBOT_GRIPPER_OPEN_SCRIPT", "")),
            },
            "tmflow_json": {
                "protocol_version": str(getattr(config, "ROBOT_TMFLOW_PROTOCOL_VERSION", "1.0")),
                "client_version": str(getattr(config, "ROBOT_TMFLOW_CLIENT_VERSION", "1.0")),
                "wire_format": str(getattr(config, "ROBOT_TMFLOW_WIRE_FORMAT", "envelope")),
                "require_hello": bool(getattr(config, "ROBOT_TMFLOW_REQUIRE_HELLO", True)),
                "ack_timeout_sec": float(getattr(config, "ROBOT_TMFLOW_ACK_TIMEOUT_SEC", 2.0)),
                "done_timeout_sec": float(getattr(config, "ROBOT_TMFLOW_DONE_TIMEOUT_SEC", 30.0)),
                "long_task_timeout_sec": float(getattr(config, "ROBOT_TMFLOW_LONG_TASK_TIMEOUT_SEC", 90.0)),
                "heartbeat_interval_sec": float(getattr(config, "ROBOT_TMFLOW_HEARTBEAT_INTERVAL_SEC", 1.0)),
                "reconnect_interval_sec": float(getattr(config, "ROBOT_TMFLOW_RECONNECT_INTERVAL_SEC", 2.0)),
                "max_retry": int(getattr(config, "ROBOT_TMFLOW_MAX_RETRY", 2)),
                "max_message_bytes": int(getattr(config, "ROBOT_TMFLOW_MAX_MESSAGE_BYTES", 4096)),
                "base": str(getattr(config, "ROBOT_TMFLOW_BASE", "ChessBoard_Base")),
                "tcp": str(getattr(config, "ROBOT_TMFLOW_TCP", "ChessGripper_TCP")),
                "gripper_wait_ms": int(getattr(config, "ROBOT_TMFLOW_GRIPPER_WAIT_MS", 300)),
                "stop_mode": str(getattr(config, "ROBOT_TMFLOW_STOP_MODE", "CONTROLLED_STOP")),
            },
            "modbus": {
                "verify_status_on_connect": bool(getattr(config, "ROBOT_VERIFY_STATUS_ON_CONNECT", False)),
                "command_handshake_enabled": bool(getattr(config, "ROBOT_COMMAND_HANDSHAKE_ENABLED", True)),
                "motion_register_base": int(getattr(config, "ROBOT_MOTION_REGISTER_BASE", 7000)),
                "profile_register_base": int(getattr(config, "ROBOT_PROFILE_REGISTER_BASE", 7012)),
                "status_register": int(getattr(config, "ROBOT_STATUS_REGISTER", 7100)),
                "status_idle_value": int(getattr(config, "ROBOT_STATUS_IDLE_VALUE", 0)),
                "status_moving_value": int(getattr(config, "ROBOT_STATUS_MOVING_VALUE", 1)),
                "status_complete_value": int(getattr(config, "ROBOT_STATUS_COMPLETE_VALUE", 2)),
                "status_error_value": int(getattr(config, "ROBOT_STATUS_ERROR_VALUE", 3)),
                "gripper_register": int(getattr(config, "ROBOT_GRIPPER_REGISTER", 7098)),
                "command_id_register": int(getattr(config, "ROBOT_COMMAND_ID_REGISTER", 6998)),
                "command_trigger_register": int(getattr(config, "ROBOT_COMMAND_TRIGGER_REGISTER", 6999)),
                "command_ack_register": int(getattr(config, "ROBOT_COMMAND_ACK_REGISTER", 7101)),
                "error_code_register": int(getattr(config, "ROBOT_ERROR_CODE_REGISTER", 7102)),
                "command_trigger_value": int(getattr(config, "ROBOT_COMMAND_TRIGGER_VALUE", 1)),
                "command_clear_value": int(getattr(config, "ROBOT_COMMAND_CLEAR_VALUE", 0)),
                "command_ack_timeout_sec": float(getattr(config, "ROBOT_COMMAND_ACK_TIMEOUT_SEC", 2.0)),
                "register_scale": float(getattr(config, "ROBOT_REGISTER_SCALE", 100.0)),
                "register_encoding": str(getattr(config, "ROBOT_REGISTER_ENCODING", "scaled_int32")),
                "telemetry_enabled": bool(getattr(config, "ROBOT_TELEMETRY_ENABLED", False)),
                "telemetry_pose_register_base": int(getattr(config, "ROBOT_TELEMETRY_POSE_REGISTER_BASE", 7110)),
                "telemetry_joint_register_base": int(getattr(config, "ROBOT_TELEMETRY_JOINT_REGISTER_BASE", 7122)),
                "telemetry_speed_register": int(getattr(config, "ROBOT_TELEMETRY_SPEED_REGISTER", 7134)),
                "gripper_feedback_enabled": bool(getattr(config, "ROBOT_GRIPPER_FEEDBACK_ENABLED", True)),
                "gripper_status_register": int(getattr(config, "ROBOT_GRIPPER_STATUS_REGISTER", 7103)),
                "gripper_close_value": int(getattr(config, "ROBOT_GRIPPER_CLOSE_VALUE", 1)),
                "gripper_open_value": int(getattr(config, "ROBOT_GRIPPER_OPEN_VALUE", 0)),
                "gripper_opened_value": int(getattr(config, "ROBOT_GRIPPER_OPENED_VALUE", 0)),
                "gripper_closed_value": int(getattr(config, "ROBOT_GRIPPER_CLOSED_VALUE", 1)),
                "gripper_error_value": int(getattr(config, "ROBOT_GRIPPER_ERROR_VALUE", 2)),
                "gripper_feedback_timeout_sec": float(getattr(config, "ROBOT_GRIPPER_FEEDBACK_TIMEOUT_SEC", 2.0)),
            },
            "motion": {
                "z_safe": float(getattr(config, "Z_SAFE", 150.0)),
                "z_grab": float(getattr(config, "Z_GRAB", 20.0)),
                "place_z_offset": float(getattr(config, "ROBOT_PLACE_Z_OFFSET", 2.0)),
                "tool_rx": float(getattr(config, "ROBOT_TOOL_RX", 0.0)),
                "tool_ry": float(getattr(config, "ROBOT_TOOL_RY", 0.0)),
                "tool_rz": float(getattr(config, "ROBOT_TOOL_RZ", 0.0)),
                "min_speed": float(getattr(config, "ROBOT_MIN_SPEED", 1.0)),
                "max_speed": float(getattr(config, "ROBOT_MAX_SPEED", 80.0)),
                "travel_speed": float(getattr(config, "ROBOT_TRAVEL_SPEED", 30.0)),
                "lift_speed": float(getattr(config, "ROBOT_LIFT_SPEED", 30.0)),
                "approach_speed": float(getattr(config, "ROBOT_APPROACH_SPEED", 15.0)),
                "default_acceleration": float(getattr(config, "ROBOT_DEFAULT_ACCELERATION", 60.0)),
                "timeout_sec": float(getattr(config, "ROBOT_MOTION_TIMEOUT_SEC", 10.0)),
            },
            "limits": {
                "min_x": float(getattr(config, "ROBOT_MIN_X", -600.0)),
                "max_x": float(getattr(config, "ROBOT_MAX_X", 600.0)),
                "min_y": float(getattr(config, "ROBOT_MIN_Y", 100.0)),
                "max_y": float(getattr(config, "ROBOT_MAX_Y", 600.0)),
                "min_z": float(getattr(config, "ROBOT_MIN_Z", 0.0)),
                "max_z": float(getattr(config, "ROBOT_MAX_Z", max(getattr(config, "Z_SAFE", 150.0), getattr(config, "Z_GRAB", 20.0)) + 100.0)),
            },
            "calibration": calibration,
        },
    }


def normalize_setup_settings(payload: Mapping[str, Any], base: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError("settings payload must be an object.")

    normalized = deepcopy(dict(base or current_setup_settings()))
    merged = deep_merge(normalized, payload)

    _set(merged, "vision.camera_index", _bounded_int(_get(merged, "vision.camera_index", 0), "vision.camera_index", 0, 15))
    _set(merged, "vision.result_max_age_sec", _finite_float(_get(merged, "vision.result_max_age_sec", 3.0), "vision.result_max_age_sec"))
    _set(merged, "robot.runtime.fake_robot", _bool(_get(merged, "robot.runtime.fake_robot", True), "robot.runtime.fake_robot"))
    _set(merged, "robot.runtime.auto_execute_robot", _bool(_get(merged, "robot.runtime.auto_execute_robot", False), "robot.runtime.auto_execute_robot"))
    adapter = _text(_get(merged, "robot.connection.adapter", "tmflow_json"), "robot.connection.adapter").strip().lower()
    if adapter not in {"tmflow_json", "techmanpy", "modbus"}:
        raise ValueError("robot.connection.adapter must be tmflow_json, techmanpy, or modbus.")
    _set(merged, "robot.connection.adapter", adapter)
    _set(merged, "robot.connection.ip", _text(_get(merged, "robot.connection.ip"), "robot.connection.ip"))
    _set(merged, "robot.connection.port", _bounded_int(_get(merged, "robot.connection.port"), "robot.connection.port", 1, 65535))
    _set(merged, "robot.connection.pc_ip", _text(_get(merged, "robot.connection.pc_ip", "169.254.47.50"), "robot.connection.pc_ip"))
    _set(merged, "robot.connection.subnet_mask", _text(_get(merged, "robot.connection.subnet_mask", "255.255.0.0"), "robot.connection.subnet_mask"))
    _set(merged, "robot.connection.timeout_sec", _finite_float(_get(merged, "robot.connection.timeout_sec", 3.0), "robot.connection.timeout_sec"))
    _set(merged, "robot.connection.tmflow_version", _text(_get(merged, "robot.connection.tmflow_version", "1.82"), "robot.connection.tmflow_version"))
    _set(merged, "robot.connection.controller_version", _text(_get(merged, "robot.connection.controller_version", "1.82.51"), "robot.connection.controller_version"))
    _set(
        merged,
        "robot.techmanpy.require_listen_node",
        _bool(_get(merged, "robot.techmanpy.require_listen_node", True), "robot.techmanpy.require_listen_node"),
    )
    motion_mode = _text(_get(merged, "robot.techmanpy.motion_mode", "ptp"), "robot.techmanpy.motion_mode").strip().lower()
    if motion_mode not in {"ptp", "line"}:
        raise ValueError("robot.techmanpy.motion_mode must be ptp or line.")
    _set(merged, "robot.techmanpy.motion_mode", motion_mode)
    _set(
        merged,
        "robot.techmanpy.suppress_warnings",
        _bool(_get(merged, "robot.techmanpy.suppress_warnings", False), "robot.techmanpy.suppress_warnings"),
    )
    _set(
        merged,
        "robot.techmanpy.gripper_close_script",
        str(_get(merged, "robot.techmanpy.gripper_close_script", "") or "").strip(),
    )
    _set(
        merged,
        "robot.techmanpy.gripper_open_script",
        str(_get(merged, "robot.techmanpy.gripper_open_script", "") or "").strip(),
    )
    _set(merged, "robot.tmflow_json.protocol_version", _text(_get(merged, "robot.tmflow_json.protocol_version", "1.0"), "robot.tmflow_json.protocol_version"))
    _set(merged, "robot.tmflow_json.client_version", _text(_get(merged, "robot.tmflow_json.client_version", "1.0"), "robot.tmflow_json.client_version"))
    wire_format = _text(_get(merged, "robot.tmflow_json.wire_format", "envelope"), "robot.tmflow_json.wire_format").strip().lower()
    if wire_format not in {"envelope", "flat_json"}:
        raise ValueError("robot.tmflow_json.wire_format must be envelope or flat_json.")
    _set(merged, "robot.tmflow_json.wire_format", wire_format)
    _set(
        merged,
        "robot.tmflow_json.require_hello",
        _bool(_get(merged, "robot.tmflow_json.require_hello", True), "robot.tmflow_json.require_hello"),
    )
    for path in (
        "robot.tmflow_json.ack_timeout_sec",
        "robot.tmflow_json.done_timeout_sec",
        "robot.tmflow_json.long_task_timeout_sec",
        "robot.tmflow_json.heartbeat_interval_sec",
        "robot.tmflow_json.reconnect_interval_sec",
    ):
        _set(merged, path, _finite_float(_get(merged, path), path))
    _set(merged, "robot.tmflow_json.max_retry", _bounded_int(_get(merged, "robot.tmflow_json.max_retry", 2), "robot.tmflow_json.max_retry", 0, 10))
    _set(merged, "robot.tmflow_json.max_message_bytes", _bounded_int(_get(merged, "robot.tmflow_json.max_message_bytes", 4096), "robot.tmflow_json.max_message_bytes", 256, 65536))
    _set(merged, "robot.tmflow_json.base", _text(_get(merged, "robot.tmflow_json.base", "ChessBoard_Base"), "robot.tmflow_json.base"))
    _set(merged, "robot.tmflow_json.tcp", _text(_get(merged, "robot.tmflow_json.tcp", "ChessGripper_TCP"), "robot.tmflow_json.tcp"))
    _set(merged, "robot.tmflow_json.gripper_wait_ms", _bounded_int(_get(merged, "robot.tmflow_json.gripper_wait_ms", 300), "robot.tmflow_json.gripper_wait_ms", 0, 60000))
    stop_mode = _text(_get(merged, "robot.tmflow_json.stop_mode", "CONTROLLED_STOP"), "robot.tmflow_json.stop_mode").strip().upper()
    if stop_mode not in {"CONTROLLED_STOP", "EMERGENCY_STOP"}:
        raise ValueError("robot.tmflow_json.stop_mode must be CONTROLLED_STOP or EMERGENCY_STOP.")
    _set(merged, "robot.tmflow_json.stop_mode", stop_mode)
    _set(
        merged,
        "robot.modbus.verify_status_on_connect",
        _bool(_get(merged, "robot.modbus.verify_status_on_connect", False), "robot.modbus.verify_status_on_connect"),
    )
    _set(
        merged,
        "robot.modbus.command_handshake_enabled",
        _bool(_get(merged, "robot.modbus.command_handshake_enabled", True), "robot.modbus.command_handshake_enabled"),
    )
    _set(
        merged,
        "robot.modbus.gripper_feedback_enabled",
        _bool(_get(merged, "robot.modbus.gripper_feedback_enabled", True), "robot.modbus.gripper_feedback_enabled"),
    )
    _set(
        merged,
        "robot.modbus.telemetry_enabled",
        _bool(_get(merged, "robot.modbus.telemetry_enabled", False), "robot.modbus.telemetry_enabled"),
    )
    _set(merged, "robot.modbus.register_scale", _finite_float(_get(merged, "robot.modbus.register_scale", 100.0), "robot.modbus.register_scale"))
    encoding = _text(_get(merged, "robot.modbus.register_encoding", "scaled_int32"), "robot.modbus.register_encoding").strip().lower()
    if encoding not in {"scaled_int16", "scaled_int32"}:
        raise ValueError("robot.modbus.register_encoding must be scaled_int16 or scaled_int32.")
    _set(merged, "robot.modbus.register_encoding", encoding)
    for path in (
        "robot.modbus.motion_register_base",
        "robot.modbus.profile_register_base",
        "robot.modbus.status_register",
        "robot.modbus.gripper_register",
        "robot.modbus.command_id_register",
        "robot.modbus.command_trigger_register",
        "robot.modbus.command_ack_register",
        "robot.modbus.error_code_register",
        "robot.modbus.gripper_status_register",
        "robot.modbus.telemetry_pose_register_base",
        "robot.modbus.telemetry_joint_register_base",
        "robot.modbus.telemetry_speed_register",
    ):
        _set(merged, path, _bounded_int(_get(merged, path), path, 0, 65535))
    for path in (
        "robot.modbus.status_idle_value",
        "robot.modbus.status_moving_value",
        "robot.modbus.status_complete_value",
        "robot.modbus.status_error_value",
        "robot.modbus.command_trigger_value",
        "robot.modbus.command_clear_value",
        "robot.modbus.gripper_close_value",
        "robot.modbus.gripper_open_value",
        "robot.modbus.gripper_opened_value",
        "robot.modbus.gripper_closed_value",
        "robot.modbus.gripper_error_value",
    ):
        _set(merged, path, _bounded_int(_get(merged, path), path, 0, 65535))
    for path in (
        "robot.modbus.command_ack_timeout_sec",
        "robot.modbus.gripper_feedback_timeout_sec",
    ):
        _set(merged, path, _finite_float(_get(merged, path), path))

    for path in (
        "robot.motion.z_safe",
        "robot.motion.z_grab",
        "robot.motion.place_z_offset",
        "robot.motion.tool_rx",
        "robot.motion.tool_ry",
        "robot.motion.tool_rz",
        "robot.motion.min_speed",
        "robot.motion.max_speed",
        "robot.motion.travel_speed",
        "robot.motion.lift_speed",
        "robot.motion.approach_speed",
        "robot.motion.default_acceleration",
        "robot.motion.timeout_sec",
        "robot.limits.min_x",
        "robot.limits.max_x",
        "robot.limits.min_y",
        "robot.limits.max_y",
        "robot.limits.min_z",
        "robot.limits.max_z",
        "robot.calibration.origin_x",
        "robot.calibration.origin_y",
        "robot.calibration.square_size_x",
        "robot.calibration.square_size_y",
    ):
        _set(merged, path, _finite_float(_get(merged, path), path))

    dead_zone = dict(_get(merged, "robot.calibration.dead_zone_range") or _get(merged, "robot.calibration.dead_zone") or {})
    for key in ("x", "y", "width", "height", "slot_spacing"):
        dead_zone[key] = _finite_float(dead_zone.get(key), f"robot.calibration.dead_zone.{key}")
    dead_zone["slot_count"] = _bounded_int(dead_zone.get("slot_count", 1), "robot.calibration.dead_zone.slot_count", 1, 64)
    _set(merged, "robot.calibration.dead_zone_range", dead_zone)
    _set(merged, "robot.calibration.dead_zone", {"x": dead_zone["x"], "y": dead_zone["y"]})
    if _get(payload, "robot.calibration.affine_matrix") is None:
        _set(merged, "robot.calibration.affine_matrix", None)

    _validate_setup_settings(merged)
    return merged


def _validate_setup_settings(settings: Mapping[str, Any]) -> None:
    motion = _get(settings, "robot.motion", {})
    limits = _get(settings, "robot.limits", {})
    calibration = _get(settings, "robot.calibration", {})
    vision = _get(settings, "vision", {})
    connection = _get(settings, "robot.connection", {})

    if float(vision["result_max_age_sec"]) <= 0:
        raise ValueError("vision.result_max_age_sec must be positive.")
    if float(connection["timeout_sec"]) <= 0:
        raise ValueError("robot.connection.timeout_sec must be positive.")
    if str(connection["adapter"]).strip().lower() in {"tmflow_json", "techmanpy"} and int(connection["port"]) != 5890:
        raise ValueError("robot.connection.port must be 5890 when adapter is tmflow_json or techmanpy.")
    z_safe = float(motion["z_safe"])
    z_grab = float(motion["z_grab"])
    place_z = z_grab + float(motion["place_z_offset"])
    if z_safe <= z_grab:
        raise ValueError("robot.motion.z_safe must be greater than robot.motion.z_grab.")
    if float(motion["place_z_offset"]) < 0:
        raise ValueError("robot.motion.place_z_offset must be non-negative.")
    if not (z_grab <= place_z < z_safe):
        raise ValueError("robot.motion.place_z_offset keeps place height outside the safe Z profile.")
    for key in ("tool_rx", "tool_ry", "tool_rz"):
        if not math.isfinite(float(motion[key])):
            raise ValueError(f"robot.motion.{key} must be finite.")

    min_speed = float(motion["min_speed"])
    max_speed = float(motion["max_speed"])
    if min_speed <= 0 or max_speed < min_speed:
        raise ValueError("robot.motion speed limits must be positive and ordered.")
    for key in ("travel_speed", "lift_speed", "approach_speed"):
        speed = float(motion[key])
        if not (min_speed <= speed <= max_speed):
            raise ValueError(f"robot.motion.{key} must be within min_speed and max_speed.")
    if float(motion["default_acceleration"]) <= 0:
        raise ValueError("robot.motion.default_acceleration must be positive.")
    if float(motion["timeout_sec"]) <= 0:
        raise ValueError("robot.motion.timeout_sec must be positive.")

    if float(limits["min_x"]) >= float(limits["max_x"]):
        raise ValueError("robot.limits.min_x must be less than max_x.")
    if float(limits["min_y"]) >= float(limits["max_y"]):
        raise ValueError("robot.limits.min_y must be less than max_y.")
    if float(limits["min_z"]) >= float(limits["max_z"]):
        raise ValueError("robot.limits.min_z must be less than max_z.")
    if not (float(limits["min_z"]) <= z_grab <= float(limits["max_z"]) and float(limits["min_z"]) <= z_safe <= float(limits["max_z"])):
        raise ValueError("robot.limits Z range must contain z_grab and z_safe.")

    if float(calibration["square_size_x"]) <= 0 or float(calibration["square_size_y"]) <= 0:
        raise ValueError("robot.calibration square sizes must be positive.")

    modbus = _get(settings, "robot.modbus", {})
    register_ranges = []
    if float(modbus["register_scale"]) <= 0:
        raise ValueError("robot.modbus.register_scale must be positive.")
    encoding = str(modbus["register_encoding"]).strip().lower()
    if encoding not in {"scaled_int16", "scaled_int32"}:
        raise ValueError("robot.modbus.register_encoding must be scaled_int16 or scaled_int32.")
    value_register_width = 2 if encoding == "scaled_int32" else 1
    motion_width = 6 * value_register_width
    profile_width = 2
    for label, start, width in (
        ("motion", int(modbus["motion_register_base"]), motion_width),
        ("profile", int(modbus["profile_register_base"]), profile_width),
        ("status", int(modbus["status_register"]), 1),
        ("gripper", int(modbus["gripper_register"]), 1),
        ("command_id", int(modbus["command_id_register"]), 1),
        ("command_trigger", int(modbus["command_trigger_register"]), 1),
        ("command_ack", int(modbus["command_ack_register"]), 1),
        ("error_code", int(modbus["error_code_register"]), 1),
        ("gripper_status", int(modbus["gripper_status_register"]), 1),
    ):
        end = start + width - 1
        if end > 65535:
            raise ValueError(f"robot.modbus.{label} register range exceeds 65535.")
        register_ranges.append((label, start, end))
    if bool(modbus.get("telemetry_enabled", False)):
        for label, start, width in (
            ("telemetry_pose", int(modbus["telemetry_pose_register_base"]), 6 * value_register_width),
            ("telemetry_joint", int(modbus["telemetry_joint_register_base"]), 6 * value_register_width),
            ("telemetry_speed", int(modbus["telemetry_speed_register"]), value_register_width),
        ):
            end = start + width - 1
            if end > 65535:
                raise ValueError(f"robot.modbus.{label} register range exceeds 65535.")
            register_ranges.append((label, start, end))
    for index, (label, start, end) in enumerate(register_ranges):
        for other_label, other_start, other_end in register_ranges[index + 1:]:
            if start <= other_end and other_start <= end:
                raise ValueError(f"robot.modbus register overlap: {label} and {other_label}.")
    if float(modbus["command_ack_timeout_sec"]) <= 0:
        raise ValueError("robot.modbus.command_ack_timeout_sec must be positive.")
    if float(modbus["gripper_feedback_timeout_sec"]) <= 0:
        raise ValueError("robot.modbus.gripper_feedback_timeout_sec must be positive.")

    mapper = Kinematics()
    mapper.update_calibration(
        origin_x=calibration["origin_x"],
        origin_y=calibration["origin_y"],
        square_size_x=calibration["square_size_x"],
        square_size_y=calibration["square_size_y"],
        dead_zone=calibration["dead_zone_range"],
        affine_matrix=calibration.get("affine_matrix"),
        persist=False,
    )

    invalid_squares = []
    for file_char in mapper.files:
        for rank in range(10):
            xy = mapper.grid_to_robot(file_char, str(rank))
            if xy is None:
                invalid_squares.append(f"{file_char}{rank}: mapping failed")
                continue
            x, y = xy
            if not (float(limits["min_x"]) <= x <= float(limits["max_x"]) and float(limits["min_y"]) <= y <= float(limits["max_y"])):
                invalid_squares.append(f"{file_char}{rank}: ({x:.2f}, {y:.2f})")
            if len(invalid_squares) >= 3:
                break
        if len(invalid_squares) >= 3:
            break
    if invalid_squares:
        raise ValueError("robot board calibration exceeds XY soft limits: " + "; ".join(invalid_squares))

    dead_zone = calibration["dead_zone_range"]
    dz_x = float(dead_zone["x"])
    dz_y = float(dead_zone["y"])
    dz_w = float(dead_zone["width"])
    dz_h = float(dead_zone["height"])
    if dz_w <= 0 or dz_h <= 0:
        raise ValueError("robot.calibration.dead_zone width and height must be positive.")
    if not (
        float(limits["min_x"]) <= dz_x <= float(limits["max_x"])
        and float(limits["min_x"]) <= dz_x + dz_w <= float(limits["max_x"])
        and float(limits["min_y"]) <= dz_y <= float(limits["max_y"])
        and float(limits["min_y"]) <= dz_y + dz_h <= float(limits["max_y"])
    ):
        raise ValueError("robot.calibration.dead_zone range exceeds XY soft limits.")


def _persisted_setup_payload(settings: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "vision": {
            "camera_index": _get(settings, "vision.camera_index"),
            "result_max_age_sec": _get(settings, "vision.result_max_age_sec"),
        },
        "robot": {
            "runtime": dict(_get(settings, "robot.runtime", {})),
            "connection": dict(_get(settings, "robot.connection", {})),
            "tmflow_json": dict(_get(settings, "robot.tmflow_json", {})),
            "techmanpy": dict(_get(settings, "robot.techmanpy", {})),
            "modbus": dict(_get(settings, "robot.modbus", {})),
            "motion": dict(_get(settings, "robot.motion", {})),
            "limits": dict(_get(settings, "robot.limits", {})),
        },
    }


def _apply_runtime_settings(settings: Mapping[str, Any]) -> list[str]:
    warnings: list[str] = []

    config.CAMERA_INDEX = int(_get(settings, "vision.camera_index"))
    config.VISION_RESULT_MAX_AGE_SEC = float(_get(settings, "vision.result_max_age_sec"))
    config.FAKE_ROBOT = bool(_get(settings, "robot.runtime.fake_robot"))
    config.AUTO_EXECUTE_ROBOT = bool(_get(settings, "robot.runtime.auto_execute_robot"))
    config.ROBOT_ADAPTER = str(_get(settings, "robot.connection.adapter")).strip().lower()
    config.ROBOT_IP = str(_get(settings, "robot.connection.ip"))
    config.ROBOT_PORT = int(_get(settings, "robot.connection.port"))
    config.ROBOT_PC_IP = str(_get(settings, "robot.connection.pc_ip"))
    config.ROBOT_SUBNET_MASK = str(_get(settings, "robot.connection.subnet_mask"))
    config.ROBOT_CONNECT_TIMEOUT_SEC = float(_get(settings, "robot.connection.timeout_sec"))
    config.TMFLOW_VERSION = str(_get(settings, "robot.connection.tmflow_version"))
    config.TM_CONTROLLER_VERSION = str(_get(settings, "robot.connection.controller_version"))
    config.ROBOT_TECHMANPY_REQUIRE_LISTEN_NODE = bool(_get(settings, "robot.techmanpy.require_listen_node"))
    config.ROBOT_TECHMANPY_MOTION_MODE = str(_get(settings, "robot.techmanpy.motion_mode")).strip().lower()
    config.ROBOT_TECHMANPY_SUPPRESS_WARNINGS = bool(_get(settings, "robot.techmanpy.suppress_warnings"))
    config.ROBOT_GRIPPER_CLOSE_SCRIPT = str(_get(settings, "robot.techmanpy.gripper_close_script") or "")
    config.ROBOT_GRIPPER_OPEN_SCRIPT = str(_get(settings, "robot.techmanpy.gripper_open_script") or "")
    config.ROBOT_TMFLOW_PROTOCOL_VERSION = str(_get(settings, "robot.tmflow_json.protocol_version"))
    config.ROBOT_TMFLOW_CLIENT_VERSION = str(_get(settings, "robot.tmflow_json.client_version"))
    config.ROBOT_TMFLOW_WIRE_FORMAT = str(_get(settings, "robot.tmflow_json.wire_format")).strip().lower()
    config.ROBOT_TMFLOW_REQUIRE_HELLO = bool(_get(settings, "robot.tmflow_json.require_hello"))
    config.ROBOT_TMFLOW_ACK_TIMEOUT_SEC = float(_get(settings, "robot.tmflow_json.ack_timeout_sec"))
    config.ROBOT_TMFLOW_DONE_TIMEOUT_SEC = float(_get(settings, "robot.tmflow_json.done_timeout_sec"))
    config.ROBOT_TMFLOW_LONG_TASK_TIMEOUT_SEC = float(_get(settings, "robot.tmflow_json.long_task_timeout_sec"))
    config.ROBOT_TMFLOW_HEARTBEAT_INTERVAL_SEC = float(_get(settings, "robot.tmflow_json.heartbeat_interval_sec"))
    config.ROBOT_TMFLOW_RECONNECT_INTERVAL_SEC = float(_get(settings, "robot.tmflow_json.reconnect_interval_sec"))
    config.ROBOT_TMFLOW_MAX_RETRY = int(_get(settings, "robot.tmflow_json.max_retry"))
    config.ROBOT_TMFLOW_MAX_MESSAGE_BYTES = int(_get(settings, "robot.tmflow_json.max_message_bytes"))
    config.ROBOT_TMFLOW_BASE = str(_get(settings, "robot.tmflow_json.base"))
    config.ROBOT_TMFLOW_TCP = str(_get(settings, "robot.tmflow_json.tcp"))
    config.ROBOT_TMFLOW_GRIPPER_WAIT_MS = int(_get(settings, "robot.tmflow_json.gripper_wait_ms"))
    config.ROBOT_TMFLOW_STOP_MODE = str(_get(settings, "robot.tmflow_json.stop_mode")).strip().upper()
    config.ROBOT_VERIFY_STATUS_ON_CONNECT = bool(_get(settings, "robot.modbus.verify_status_on_connect"))
    config.ROBOT_COMMAND_HANDSHAKE_ENABLED = bool(_get(settings, "robot.modbus.command_handshake_enabled"))
    config.ROBOT_MOTION_REGISTER_BASE = int(_get(settings, "robot.modbus.motion_register_base"))
    config.ROBOT_PROFILE_REGISTER_BASE = int(_get(settings, "robot.modbus.profile_register_base"))
    config.ROBOT_STATUS_REGISTER = int(_get(settings, "robot.modbus.status_register"))
    config.ROBOT_STATUS_IDLE_VALUE = int(_get(settings, "robot.modbus.status_idle_value"))
    config.ROBOT_STATUS_MOVING_VALUE = int(_get(settings, "robot.modbus.status_moving_value"))
    config.ROBOT_STATUS_COMPLETE_VALUE = int(_get(settings, "robot.modbus.status_complete_value"))
    config.ROBOT_STATUS_ERROR_VALUE = int(_get(settings, "robot.modbus.status_error_value"))
    config.ROBOT_GRIPPER_REGISTER = int(_get(settings, "robot.modbus.gripper_register"))
    config.ROBOT_COMMAND_ID_REGISTER = int(_get(settings, "robot.modbus.command_id_register"))
    config.ROBOT_COMMAND_TRIGGER_REGISTER = int(_get(settings, "robot.modbus.command_trigger_register"))
    config.ROBOT_COMMAND_ACK_REGISTER = int(_get(settings, "robot.modbus.command_ack_register"))
    config.ROBOT_ERROR_CODE_REGISTER = int(_get(settings, "robot.modbus.error_code_register"))
    config.ROBOT_COMMAND_TRIGGER_VALUE = int(_get(settings, "robot.modbus.command_trigger_value"))
    config.ROBOT_COMMAND_CLEAR_VALUE = int(_get(settings, "robot.modbus.command_clear_value"))
    config.ROBOT_COMMAND_ACK_TIMEOUT_SEC = float(_get(settings, "robot.modbus.command_ack_timeout_sec"))
    config.ROBOT_REGISTER_SCALE = float(_get(settings, "robot.modbus.register_scale"))
    config.ROBOT_REGISTER_ENCODING = str(_get(settings, "robot.modbus.register_encoding")).strip().lower()
    config.ROBOT_TELEMETRY_ENABLED = bool(_get(settings, "robot.modbus.telemetry_enabled"))
    config.ROBOT_TELEMETRY_POSE_REGISTER_BASE = int(_get(settings, "robot.modbus.telemetry_pose_register_base"))
    config.ROBOT_TELEMETRY_JOINT_REGISTER_BASE = int(_get(settings, "robot.modbus.telemetry_joint_register_base"))
    config.ROBOT_TELEMETRY_SPEED_REGISTER = int(_get(settings, "robot.modbus.telemetry_speed_register"))
    config.ROBOT_GRIPPER_FEEDBACK_ENABLED = bool(_get(settings, "robot.modbus.gripper_feedback_enabled"))
    config.ROBOT_GRIPPER_STATUS_REGISTER = int(_get(settings, "robot.modbus.gripper_status_register"))
    config.ROBOT_GRIPPER_CLOSE_VALUE = int(_get(settings, "robot.modbus.gripper_close_value"))
    config.ROBOT_GRIPPER_OPEN_VALUE = int(_get(settings, "robot.modbus.gripper_open_value"))
    config.ROBOT_GRIPPER_OPENED_VALUE = int(_get(settings, "robot.modbus.gripper_opened_value"))
    config.ROBOT_GRIPPER_CLOSED_VALUE = int(_get(settings, "robot.modbus.gripper_closed_value"))
    config.ROBOT_GRIPPER_ERROR_VALUE = int(_get(settings, "robot.modbus.gripper_error_value"))
    config.ROBOT_GRIPPER_FEEDBACK_TIMEOUT_SEC = float(_get(settings, "robot.modbus.gripper_feedback_timeout_sec"))

    motion_map = {
        "Z_SAFE": "robot.motion.z_safe",
        "Z_GRAB": "robot.motion.z_grab",
        "ROBOT_PLACE_Z_OFFSET": "robot.motion.place_z_offset",
        "ROBOT_TOOL_RX": "robot.motion.tool_rx",
        "ROBOT_TOOL_RY": "robot.motion.tool_ry",
        "ROBOT_TOOL_RZ": "robot.motion.tool_rz",
        "ROBOT_MIN_SPEED": "robot.motion.min_speed",
        "ROBOT_MAX_SPEED": "robot.motion.max_speed",
        "ROBOT_TRAVEL_SPEED": "robot.motion.travel_speed",
        "ROBOT_LIFT_SPEED": "robot.motion.lift_speed",
        "ROBOT_APPROACH_SPEED": "robot.motion.approach_speed",
        "ROBOT_DEFAULT_ACCELERATION": "robot.motion.default_acceleration",
        "ROBOT_MOTION_TIMEOUT_SEC": "robot.motion.timeout_sec",
    }
    for attr, path in motion_map.items():
        setattr(config, attr, float(_get(settings, path)))

    limits = _get(settings, "robot.limits", {})
    for attr, key in (
        ("ROBOT_MIN_X", "min_x"),
        ("ROBOT_MAX_X", "max_x"),
        ("ROBOT_MIN_Y", "min_y"),
        ("ROBOT_MAX_Y", "max_y"),
        ("ROBOT_MIN_Z", "min_z"),
        ("ROBOT_MAX_Z", "max_z"),
    ):
        setattr(config, attr, float(limits[key]))
    config.SOFT_LIMIT_X = (config.ROBOT_MIN_X, config.ROBOT_MAX_X)
    config.SOFT_LIMIT_Y = (config.ROBOT_MIN_Y, config.ROBOT_MAX_Y)
    config.SOFT_LIMIT_Z = (config.ROBOT_MIN_Z, config.ROBOT_MAX_Z)

    try:
        if hasattr(vision_system, "set_camera_index"):
            vision_system.set_camera_index(config.CAMERA_INDEX)
    except Exception as exc:
        warnings.append(f"Camera switch failed: {exc}")

    try:
        from backend.application.container import container
        from backend.infrastructure.robot.safety import RobotSafety

        robot = container.get("robot")
        if hasattr(robot, "reconfigure_from_config"):
            connected = robot.reconfigure_from_config()
            if not connected and not config.FAKE_ROBOT:
                warnings.append("Robot reconnect failed after applying setup settings.")
            return warnings
        impl = getattr(robot, "_impl", robot)
        if hasattr(impl, "_build_motion_profiles"):
            impl.motion_profiles = impl._build_motion_profiles()
        if hasattr(impl, "safety"):
            impl.safety = RobotSafety(config)
        adapter = getattr(impl, "adapter", None)
        if adapter is not None and not getattr(adapter, "connected", False):
            adapter.host = config.ROBOT_IP
            adapter.port = config.ROBOT_PORT
    except Exception:
        pass

    return warnings


def _robot_facade():
    from backend.application.container import container

    robot = container.get("robot")
    if not robot:
        raise RuntimeError("Robot service is not registered.")
    return robot


def _hardware_test(action: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    robot = _robot_facade()
    impl = getattr(robot, "_impl", robot)
    dry_run = _bool(payload.get("dry_run", True), "dry_run")

    if action == "preflight":
        return build_preflight_report(require_auto_execute=False)
    if action == "connect":
        connected = bool(robot.reconfigure_from_config() if hasattr(robot, "reconfigure_from_config") else robot.connect())
        return {"ok": connected, "action": action, "connected": connected, "status": robot.get_status()}
    if action == "status":
        return {"ok": True, "action": action, "status": robot.get_status()}
    if action in {"gripper_open", "gripper_close"}:
        if dry_run:
            return {"ok": True, "action": action, "dry_run": True, "message": "Gripper command validated only."}
        setter = getattr(impl, "adapter", None)
        setter = getattr(setter, "set_gripper", None)
        if not callable(setter):
            raise RuntimeError("Active robot adapter does not support direct gripper test.")
        closed = action == "gripper_close"
        return {"ok": bool(setter(closed)), "action": action, "closed": closed}
    if action == "write_pose":
        target = _hardware_test_target("safe_z")
        if dry_run:
            return {"ok": True, "action": action, "dry_run": True, "target": target, "message": "Pose target validated only."}
        adapter = getattr(impl, "adapter", None)
        writer = getattr(adapter, "write_pose_registers", None)
        if not callable(writer):
            raise RuntimeError("No-trigger pose register write is available only with ROBOT_ADAPTER=modbus.")
        ok = bool(writer(
            [target["x"], target["y"], target["z"], config.ROBOT_TOOL_RX, config.ROBOT_TOOL_RY, config.ROBOT_TOOL_RZ],
            speed=config.ROBOT_TRAVEL_SPEED,
            acceleration=config.ROBOT_DEFAULT_ACCELERATION,
        ))
        return {"ok": ok, "action": action, "target": target, "triggered": False}
    if action in {"safe_z", "origin", "dead_zone", "corner_a0", "corner_i0", "corner_a9", "corner_i9", "center_e4", "grab_z"}:
        target = _hardware_test_target(action)
        if dry_run:
            return {"ok": True, "action": action, "dry_run": True, "target": target, "message": "Motion target validated only."}
        mover = getattr(impl, "_motion", None)
        if not callable(mover):
            raise RuntimeError("Active robot implementation does not support direct motion test.")
        import asyncio

        asyncio.run(mover(target["x"], target["y"], target["z"]))
        return {"ok": True, "action": action, "target": target}
    if action == "one_move":
        move = str(payload.get("move") or "a0a1").strip().lower()
        if dry_run:
            from backend.application.services.robot_service import RobotService

            service = RobotService()
            service._plan_move(move, is_capture=False)
            return {"ok": True, "action": action, "dry_run": True, "move": move}
        return {"ok": bool(robot.execute_move(move, is_capture=False)), "action": action, "move": move}
    raise ValueError(f"Unsupported hardware test action: {action}")


def _hardware_test_target(action: str) -> dict[str, float]:
    if action == "dead_zone":
        x, y = kinematics.get_dead_zone_coords(1)
    elif action in {"corner_a0", "corner_i0", "corner_a9", "corner_i9", "center_e4", "grab_z"}:
        square = {
            "corner_a0": "a0",
            "corner_i0": "i0",
            "corner_a9": "a9",
            "corner_i9": "i9",
            "center_e4": "e4",
            "grab_z": "e4",
        }[action]
        xy = kinematics.grid_to_robot(square[0], square[1])
        if xy is None:
            raise ValueError(f"Robot square {square} cannot be mapped.")
        x, y = xy
    else:
        xy = kinematics.grid_to_robot("a", "0")
        if xy is None:
            raise ValueError("Robot origin square a0 cannot be mapped.")
        x, y = xy
    z = float(config.Z_SAFE)
    if action in {"origin", "grab_z"}:
        z = float(config.Z_GRAB)
    from backend.infrastructure.robot.safety import RobotSafety

    ok, msg = RobotSafety(config).validate_position(x, y, z)
    if not ok:
        raise ValueError(msg)
    return {"x": float(x), "y": float(y), "z": float(z)}


@api_bp.route("/setup/login", methods=["POST"])
def setup_login():
    try:
        payload = json_object_payload()
    except ValueError as exc:
        return error_response("validation_failed", str(exc), 400)
    password = str(payload.get("password", ""))
    if password != str(getattr(config, "SETUP_PASSWORD", "login")):
        publish_security_event("SECURITY.SETUP_LOGIN_FAILED", {
            "client": client_ip(),
            "reason": "invalid_credentials",
        })
        return error_response("invalid_credentials", "Invalid setup credentials.", 401, recoverable=True)

    try:
        from backend.utils.auth import create_jwt, decode_jwt_token
    except ModuleNotFoundError:
        return error_response("setup_auth_unavailable", "JWT support is required for setup login.", 503)

    token = create_jwt("setup", subject="setup")
    claims = decode_jwt_token(token) or {}
    publish_security_event("SECURITY.SETUP_LOGIN_SUCCEEDED", {
        "client": client_ip(),
        "jti": claims.get("jti"),
        "sub": claims.get("sub"),
    })
    return jsonify({
        "ok": True,
        "token": token,
        "role": "setup",
        "expires_at": claims.get("exp"),
        "expires_in": int(getattr(config, "JWT_TTL_MINUTES", 120)) * 60,
    })


@api_bp.route("/setup/settings", methods=["GET"])
def get_setup_settings():
    settings = current_setup_settings()
    return jsonify({
        "ok": True,
        "settings": settings,
        "commissioning": load_commissioning_report(),
        "files": {
            "setup_settings": str(getattr(config, "SETUP_SETTINGS_FILE", "")),
            "robot_calibration": settings["robot"]["calibration"].get("path"),
            "vision_calibration": str(getattr(config, "VISION_CALIBRATION_FILE", "")),
        },
    })


@api_bp.route("/setup/preflight", methods=["GET"])
def get_setup_preflight():
    require_auto = str(request.args.get("require_auto_execute", "0")).strip().lower() in {"1", "true", "yes", "on"}
    report = build_preflight_report(require_auto_execute=require_auto)
    commissioning = record_preflight(report)
    return jsonify({**report, "commissioning": commissioning})


@api_bp.route("/setup/hardware-test", methods=["POST"])
def setup_hardware_test():
    try:
        payload = json_object_payload()
    except ValueError as exc:
        return error_response("validation_failed", str(exc), 400)
    action = str(payload.get("action") or "").strip().lower()
    try:
        result = _hardware_test(action, payload)
        commissioning = record_hardware_test(action, result)
        result = {**result, "commissioning": commissioning}
        status = 200 if result.get("ok", True) else 409
        return jsonify(result), status
    except ValueError as exc:
        return error_response("invalid_hardware_test", str(exc), 400)
    except Exception as exc:
        return error_response("hardware_test_failed", str(exc), 500, recoverable=True)


@api_bp.route("/setup/settings", methods=["POST"])
def save_setup_settings():
    try:
        payload = json_object_payload()
    except ValueError as exc:
        return error_response("validation_failed", str(exc), 400)
    settings_payload = payload.get("settings", payload)
    try:
        normalized = normalize_setup_settings(settings_payload, base=current_setup_settings())
        calibration = normalized["robot"]["calibration"]
        kinematics.update_calibration(
            origin_x=calibration["origin_x"],
            origin_y=calibration["origin_y"],
            square_size_x=calibration["square_size_x"],
            square_size_y=calibration["square_size_y"],
            dead_zone=calibration["dead_zone_range"],
            affine_matrix=calibration.get("affine_matrix"),
            persist=True,
        )
        persisted = deep_merge(load_settings(), _persisted_setup_payload(normalized))
        save_settings(persisted, getattr(config, "SETUP_SETTINGS_FILE", None))
        warnings = _apply_runtime_settings(normalized)
        commissioning = mark_settings_saved(normalized)
        current = current_setup_settings()
        return jsonify({
            "ok": True,
            "settings": current,
            "warnings": warnings,
            "commissioning": commissioning,
            "files": {
                "setup_settings": str(getattr(config, "SETUP_SETTINGS_FILE", "")),
                "robot_calibration": current["robot"]["calibration"].get("path"),
                "vision_calibration": str(getattr(config, "VISION_CALIBRATION_FILE", "")),
            },
        })
    except ValueError as exc:
        return error_response("invalid_setup_settings", str(exc), 400)
    except Exception as exc:
        return error_response("setup_settings_save_failed", str(exc), 500, recoverable=False)


@api_bp.route("/setup/commissioning", methods=["GET"])
def get_setup_commissioning():
    return jsonify({"ok": True, "commissioning": load_commissioning_report()})
