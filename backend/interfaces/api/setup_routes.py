from __future__ import annotations

from typing import Any, Mapping

from flask import jsonify, request

from backend.interfaces.api.shared import api_bp, error_response, json_object_payload, vision_system
from backend.interfaces.api.client_identity import client_ip
from backend.interfaces.api.shared import publish_security_event
from backend.interfaces.api.setup_settings_logic import (
    _bool,
    _get,
    _persisted_setup_payload,
    current_setup_settings,
    normalize_setup_settings,
)
from backend.application.services.system_preflight import build_preflight_report
from backend.application.services.commissioning_report import (
    load_commissioning_report,
    mark_settings_saved,
    record_hardware_test,
    record_preflight,
)
from backend.utils import config
from backend.utils.kinematics import kinematics
from backend.utils.setup_settings import deep_merge, load_settings, save_settings


def _apply_runtime_settings(settings: Mapping[str, Any]) -> list[str]:
    warnings: list[str] = []

    config.VISION_SOURCE = str(_get(settings, "vision.source", "opencv")).strip().lower()
    config.CAMERA_INDEX = int(_get(settings, "vision.camera_index"))
    config.VISION_RESULT_MAX_AGE_SEC = float(_get(settings, "vision.result_max_age_sec"))
    config.VISION_OPENCV_SOURCE = str(_get(settings, "vision.opencv.source", "") or "").strip()
    config.VISION_CAPTURE_WIDTH = int(_get(settings, "vision.opencv.width", 0) or 0)
    config.VISION_CAPTURE_HEIGHT = int(_get(settings, "vision.opencv.height", 0) or 0)
    config.VISION_CAPTURE_FPS = float(_get(settings, "vision.opencv.fps", 0.0) or 0.0)
    config.VISION_CAPTURE_FOURCC = str(_get(settings, "vision.opencv.fourcc", "MJPG") or "").strip().upper()
    config.VISION_CAPTURE_BUFFER_SIZE = int(_get(settings, "vision.opencv.buffer_size", 1) or 1)
    config.VISION_CAPTURE_GRAB_DRAIN = int(_get(settings, "vision.opencv.grab_drain", 0) or 0)
    config.VISION_CAPTURE_THREAD_FPS_LIMIT = float(_get(settings, "vision.opencv.thread_fps_limit", 0.0) or 0.0)
    config.VISION_TMFLOW_IMAGE_HOST = str(_get(settings, "vision.tmflow_json.host"))
    config.VISION_TMFLOW_IMAGE_PORT = int(_get(settings, "vision.tmflow_json.port"))
    config.VISION_TMFLOW_IMAGE_TIMEOUT_SEC = float(_get(settings, "vision.tmflow_json.timeout_sec"))
    config.VISION_TMFLOW_IMAGE_MAX_MESSAGE_BYTES = int(_get(settings, "vision.tmflow_json.max_message_bytes"))
    config.VISION_TMFLOW_IMAGE_FPS_LIMIT = float(_get(settings, "vision.tmflow_json.fps_limit"))
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
    config.ROBOT_MODBUS_ROLE = str(_get(settings, "robot.modbus.role", "client")).strip().lower()
    config.ROBOT_MODBUS_SERVER_HOST = str(_get(settings, "robot.modbus.server_host", config.ROBOT_PC_IP)).strip()
    config.ROBOT_MODBUS_SERVER_PORT = int(_get(settings, "robot.modbus.server_port", config.ROBOT_PORT))
    config.ROBOT_MODBUS_PAYLOAD_MODE = str(_get(settings, "robot.modbus.payload_mode", "pose")).strip().lower()
    config.ROBOT_MODBUS_REGISTER_ADDRESSING = str(
        _get(settings, "robot.modbus.register_addressing", "holding_40001")
    ).strip().lower()
    config.ROBOT_VERIFY_STATUS_ON_CONNECT = bool(_get(settings, "robot.modbus.verify_status_on_connect"))
    config.ROBOT_COMMAND_HANDSHAKE_ENABLED = bool(_get(settings, "robot.modbus.command_handshake_enabled"))
    config.ROBOT_MOTION_REGISTER_BASE = int(_get(settings, "robot.modbus.motion_register_base"))
    config.ROBOT_PROFILE_REGISTER_BASE = int(_get(settings, "robot.modbus.profile_register_base"))
    config.ROBOT_STATUS_REGISTER = int(_get(settings, "robot.modbus.status_register"))
    config.ROBOT_STATUS_IDLE_VALUE = int(_get(settings, "robot.modbus.status_idle_value"))
    config.ROBOT_STATUS_MOVING_VALUE = int(_get(settings, "robot.modbus.status_moving_value"))
    config.ROBOT_STATUS_COMPLETE_VALUE = int(_get(settings, "robot.modbus.status_complete_value"))
    config.ROBOT_STATUS_ERROR_VALUE = int(_get(settings, "robot.modbus.status_error_value"))
    config.ROBOT_STATUS_FAULT_VALUE = int(_get(settings, "robot.modbus.status_fault_value", 4))
    config.ROBOT_GRIPPER_REGISTER = int(_get(settings, "robot.modbus.gripper_register"))
    config.ROBOT_COMMAND_ID_REGISTER = int(_get(settings, "robot.modbus.command_id_register"))
    config.ROBOT_COMMAND_TRIGGER_REGISTER = int(_get(settings, "robot.modbus.command_trigger_register"))
    config.ROBOT_COMMAND_ACK_REGISTER = int(_get(settings, "robot.modbus.command_ack_register"))
    config.ROBOT_ERROR_CODE_REGISTER = int(_get(settings, "robot.modbus.error_code_register"))
    config.ROBOT_COMMAND_TRIGGER_VALUE = int(_get(settings, "robot.modbus.command_trigger_value"))
    config.ROBOT_COMMAND_CLEAR_VALUE = int(_get(settings, "robot.modbus.command_clear_value"))
    config.ROBOT_COMMAND_ACK_TIMEOUT_SEC = float(_get(settings, "robot.modbus.command_ack_timeout_sec"))
    config.ROBOT_SQUARE_COMMAND_REGISTER_BASE = int(
        _get(settings, "robot.modbus.square_command_register_base", 40001)
    )
    config.ROBOT_SQUARE_FROM_REGISTER = int(_get(settings, "robot.modbus.square_from_register", 40001))
    config.ROBOT_SQUARE_TO_REGISTER = int(_get(settings, "robot.modbus.square_to_register", 40002))
    config.ROBOT_SQUARE_ACTION_REGISTER = int(_get(settings, "robot.modbus.square_action_register", 40003))
    config.ROBOT_SQUARE_COMMAND_ID_REGISTER = int(
        _get(settings, "robot.modbus.square_command_id_register", 40004)
    )
    config.ROBOT_SQUARE_TRIGGER_REGISTER = int(_get(settings, "robot.modbus.square_trigger_register", 40005))
    config.ROBOT_SQUARE_STATUS_REGISTER = int(_get(settings, "robot.modbus.square_status_register", 40006))
    config.ROBOT_SQUARE_ERROR_CODE_REGISTER = int(_get(settings, "robot.modbus.square_error_code_register", 40007))
    config.ROBOT_SQUARE_COMPLETED_COMMAND_REGISTER = int(
        _get(settings, "robot.modbus.square_completed_command_register", 40008)
    )
    config.ROBOT_SQUARE_HEARTBEAT_REGISTER = int(_get(settings, "robot.modbus.square_heartbeat_register", 40009))
    config.ROBOT_SQUARE_ROBOT_STATE_REGISTER = int(
        _get(settings, "robot.modbus.square_robot_state_register", 40010)
    )
    config.ROBOT_SQUARE_REQUIRE_COMPLETED_COMMAND = bool(
        _get(settings, "robot.modbus.square_require_completed_command", True)
    )
    config.ROBOT_SQUARE_FILES = str(_get(settings, "robot.modbus.square_files", "abcdefghi")).strip()
    config.ROBOT_SQUARE_RANKS = str(_get(settings, "robot.modbus.square_ranks", "0123456789")).strip()
    config.ROBOT_SQUARE_INDEX_BASE = int(_get(settings, "robot.modbus.square_index_base", 0))
    config.ROBOT_SQUARE_ACTION_NORMAL_VALUE = int(_get(settings, "robot.modbus.square_action_normal_value", 0))
    config.ROBOT_SQUARE_ACTION_CAPTURE_VALUE = int(_get(settings, "robot.modbus.square_action_capture_value", 1))
    config.ROBOT_SQUARE_ACTION_PROMOTION_VALUE = int(_get(settings, "robot.modbus.square_action_promotion_value", 3))
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
        if hasattr(vision_system, "set_frame_source"):
            vision_system.set_frame_source(config.VISION_SOURCE, camera_index=config.CAMERA_INDEX)
        elif hasattr(vision_system, "set_camera_index"):
            vision_system.set_camera_index(config.CAMERA_INDEX)
    except Exception as exc:
        warnings.append(f"Vision source switch failed: {exc}")

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
