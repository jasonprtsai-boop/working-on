from __future__ import annotations

from flask import jsonify

from backend.application.container import container
from backend.application.services.system_preflight import build_preflight_report
from backend.infrastructure.robot.tmflow_ingest_state import tmflow_ingest_state
from backend.interfaces.api.shared import api_bp, error_response, json_object_payload, optional_json_object_payload
from backend.utils import config
from backend.utils.kinematics import kinematics
from backend.interfaces.api.setup_routes import current_setup_settings, normalize_setup_settings


@api_bp.route("/robot/status", methods=["GET"])
def get_robot_status():
    """Return the current robot status, including TMflow-pushed TCP pose."""
    try:
        robot = container.get("robot")
        if robot and hasattr(robot, "get_status"):
            status = dict(robot.get_status() or {})
        else:
            status = {}
        status = tmflow_ingest_state.merge_status(status)
        pose = _current_pose(status)
        if pose:
            status["pose"] = pose
        return jsonify({"ok": True, "status": status, "pose": pose})
    except Exception as exc:
        return error_response("robot_status_failed", str(exc), 500, recoverable=True)


@api_bp.route("/robot/calibration", methods=["GET"])
def get_robot_calibration():
    """Return current robot board-coordinate calibration."""
    return jsonify({"ok": True, "calibration": kinematics.to_dict()})


@api_bp.route("/robot/calibration", methods=["POST"])
def set_robot_calibration():
    """Update robot board-coordinate calibration from explicit values or measured points."""
    try:
        payload = json_object_payload()
    except ValueError as exc:
        return error_response("validation_failed", str(exc), 400)
    persist = bool(payload.get("persist", True))
    original = kinematics.to_dict()
    try:
        if _is_vision_to_robot_calibration(payload):
            calibration = _set_vision_to_robot_calibration(payload, persist=False)
        elif "clear_vision_to_robot" in payload:
            calibration = kinematics.clear_vision_to_robot_calibration(persist=False)
        elif "points" in payload:
            calibration = kinematics.calibrate_from_points(
                payload.get("points") or [],
                dead_zone=payload.get("dead_zone"),
                persist=False,
            )
        else:
            calibration = kinematics.update_calibration(
                origin_x=payload.get("origin_x"),
                origin_y=payload.get("origin_y"),
                square_size_x=payload.get("square_size_x"),
                square_size_y=payload.get("square_size_y"),
                dead_zone=payload.get("dead_zone"),
                affine_matrix=payload.get("affine_matrix"),
                persist=False,
            )
        normalize_setup_settings({"robot": {"calibration": calibration}}, base=current_setup_settings())
        if persist:
            kinematics.save_calibration()
        return jsonify({"ok": True, "calibration": calibration})
    except (TypeError, ValueError) as exc:
        _restore_calibration(original)
        return error_response("invalid_robot_calibration", str(exc), 400)
    except Exception as exc:
        _restore_calibration(original)
        return error_response("robot_calibration_failed", str(exc), 500, recoverable=False)


@api_bp.route("/robot/vision-point", methods=["POST"])
def map_robot_vision_point():
    """Map a YOLO/vision point to robot-base XY without executing motion."""
    try:
        payload = json_object_payload()
    except ValueError as exc:
        return error_response("validation_failed", str(exc), 400)

    try:
        x, y = _vision_point_payload(payload)
        coordinate_space = payload.get("coordinate_space")
        xy = kinematics.vision_point_to_robot(x, y, coordinate_space=coordinate_space)
        if xy is None:
            return error_response(
                "vision_to_robot_uncalibrated",
                "Vision-to-robot calibration is not configured.",
                409,
                recoverable=True,
            )
        z = _payload_float(payload, "z", float(getattr(config, "Z_GRAB", 20.0)))
        rx = _payload_float(payload, "rx", float(getattr(config, "ROBOT_TOOL_RX", 0.0)))
        ry = _payload_float(payload, "ry", float(getattr(config, "ROBOT_TOOL_RY", 0.0)))
        rz = _payload_float(payload, "rz", float(getattr(config, "ROBOT_TOOL_RZ", 0.0)))
        return jsonify({
            "ok": True,
            "point": {
                "x": float(x),
                "y": float(y),
                "coordinate_space": (
                    coordinate_space
                    or (kinematics.to_dict().get("vision_to_robot") or {}).get("coordinate_space")
                ),
            },
            "robot": {
                "x": float(xy[0]),
                "y": float(xy[1]),
                "z": float(z),
                "rx": float(rx),
                "ry": float(ry),
                "rz": float(rz),
            },
            "pose": [float(xy[0]), float(xy[1]), float(z), float(rx), float(ry), float(rz)],
            "calibration": kinematics.to_dict().get("vision_to_robot"),
        })
    except ValueError as exc:
        return error_response("invalid_vision_point", str(exc), 400)
    except Exception as exc:
        return error_response("vision_point_transform_failed", str(exc), 500, recoverable=True)


def _restore_calibration(snapshot: dict) -> None:
    try:
        kinematics.update_calibration(
            origin_x=snapshot.get("origin_x"),
            origin_y=snapshot.get("origin_y"),
            square_size_x=snapshot.get("square_size_x"),
            square_size_y=snapshot.get("square_size_y"),
            dead_zone=snapshot.get("dead_zone_range") or snapshot.get("dead_zone"),
            affine_matrix=snapshot.get("affine_matrix"),
            persist=False,
        )
        vision_to_robot = snapshot.get("vision_to_robot") or {}
        if vision_to_robot.get("homography_matrix") is not None:
            kinematics.set_vision_to_robot_homography(
                vision_to_robot.get("homography_matrix"),
                coordinate_space=vision_to_robot.get("coordinate_space") or "rectified_board",
                calibration_error=vision_to_robot.get("calibration_error"),
                points=vision_to_robot.get("points"),
                persist=False,
            )
        else:
            kinematics.clear_vision_to_robot_calibration(persist=False)
    except Exception:
        pass


def _current_pose(status: dict) -> dict:
    telemetry = status.get("telemetry") if isinstance(status.get("telemetry"), dict) else {}
    pose = telemetry.get("pose") if isinstance(telemetry.get("pose"), dict) else {}
    if all(key in pose for key in ("x", "y", "z", "rx", "ry", "rz")):
        return {key: pose.get(key) for key in ("x", "y", "z", "rx", "ry", "rz")}

    position = status.get("position") if isinstance(status.get("position"), dict) else {}
    orientation = status.get("orientation") if isinstance(status.get("orientation"), dict) else {}
    values = {
        "x": position.get("x"),
        "y": position.get("y"),
        "z": position.get("z"),
        "rx": orientation.get("rx"),
        "ry": orientation.get("ry"),
        "rz": orientation.get("rz"),
    }
    return values if all(value is not None for value in values.values()) else {}


def _is_vision_to_robot_calibration(payload: dict) -> bool:
    if isinstance(payload.get("vision_to_robot"), dict):
        return True
    if "vision_points" in payload:
        return True
    return "image_points" in payload and "robot_points" in payload


def _set_vision_to_robot_calibration(payload: dict, *, persist: bool) -> dict:
    data = payload.get("vision_to_robot") if isinstance(payload.get("vision_to_robot"), dict) else payload
    return kinematics.calibrate_vision_to_robot(
        points=data.get("points") or data.get("vision_points") or payload.get("vision_points"),
        image_points=data.get("image_points") or data.get("camera_points"),
        robot_points=data.get("robot_points") or data.get("base_points"),
        coordinate_space=data.get("coordinate_space") or payload.get("coordinate_space") or "rectified_board",
        ransac_reprojection_threshold=_payload_float(data, "ransac_reprojection_threshold", 5.0),
        persist=persist,
    )


def _vision_point_payload(payload: dict):
    point = payload.get("point") or payload.get("image") or payload.get("pixel")
    if isinstance(point, (list, tuple)) and len(point) >= 2:
        return _coerce_float(point[0], "point.x"), _coerce_float(point[1], "point.y")
    if isinstance(point, dict):
        return (
            _coerce_float(point.get("x", point.get("u")), "point.x"),
            _coerce_float(point.get("y", point.get("v")), "point.y"),
        )
    return (
        _coerce_float(payload.get("x", payload.get("u")), "x"),
        _coerce_float(payload.get("y", payload.get("v")), "y"),
    )


def _payload_float(payload: dict, key: str, default: float) -> float:
    value = payload.get(key, default) if isinstance(payload, dict) else default
    if value is None:
        value = default
    return _coerce_float(value, key)


def _coerce_float(value, field_name: str) -> float:
    import math

    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    return number


@api_bp.route("/robot/play", methods=["POST"])
def play_tmflow_project():
    """Send the TM Robot Play register only when using direct Modbus client mode."""
    try:
        payload = optional_json_object_payload()
        if not _robot_play_confirmed(payload):
            return error_response(
                "robot_play_confirmation_required",
                "請先在網頁確認「請勿靠近」警告後，再啟動機械手臂流程。",
                400,
                details={
                    "required": {
                        "confirmed_action": "robot_play",
                        "warning_acknowledged": True,
                    }
                },
            )

        preflight = build_preflight_report(require_auto_execute=False)
        if not bool(preflight.get("ready", preflight.get("ok", False))):
            return error_response(
                "robot_preflight_failed",
                "Robot preflight failed; Play was not sent.",
                409,
                details={
                    "failures": preflight.get("failures", []),
                    "warnings": preflight.get("warnings", []),
                },
            )

        robot = container.get("robot")
        if not robot:
            return error_response("robot_unavailable", "Robot service is not initialized.", 503)

        adapter = getattr(robot, "adapter", None)
        if not adapter:
            return error_response("robot_unavailable", "Robot adapter is not initialized.", 503)

        if _is_modbus_server_mode(adapter):
            return error_response(
                "unsupported_robot_play_mode",
                (
                    "Modbus server mode cannot press the TMflow Play button. "
                    "Start the TMflow project on the robot controller, then use square-command registers for moves."
                ),
                409,
                details={
                    "adapter": "modbus",
                    "role": _adapter_role(adapter),
                    "payload_mode": _adapter_payload_mode(adapter),
                    "play_register": 7104,
                },
            )

        write_register = getattr(adapter, "_write_register", None)
        if not callable(write_register):
            return error_response("unsupported_adapter", "Adapter does not support register writes.", 400)

        # 7104 is the TM Robot standard Modbus register for Play/Pause/Stop
        # 1 = Play
        if not write_register(7104, 1):
            return error_response("play_failed", "Failed to write play command to robot.", 500)

        return jsonify({"ok": True, "message": "Play signal sent to robot."})
    except Exception as exc:
        return error_response("play_failed", str(exc), 500, recoverable=True)


def _robot_play_confirmed(payload: dict) -> bool:
    if not isinstance(payload, dict):
        return False
    return (
        str(payload.get("confirmed_action") or "").strip().lower() == "robot_play"
        and _payload_bool(payload.get("warning_acknowledged", False))
    )


def _is_modbus_server_mode(adapter) -> bool:
    adapter_name = str(getattr(config, "ROBOT_ADAPTER", "") or "").strip().lower()
    return adapter_name == "modbus" and _adapter_role(adapter) == "server"


def _adapter_role(adapter) -> str:
    role_getter = getattr(adapter, "_role", None)
    if callable(role_getter):
        try:
            role = role_getter()
        except Exception:
            role = None
    else:
        role = getattr(adapter, "role", None)
    role = str(role or getattr(config, "ROBOT_MODBUS_ROLE", "client")).strip().lower()
    return role if role in {"client", "server"} else "client"


def _adapter_payload_mode(adapter) -> str:
    mode_getter = getattr(adapter, "_payload_mode", None)
    if callable(mode_getter):
        try:
            mode = mode_getter()
        except Exception:
            mode = None
    else:
        mode = getattr(adapter, "payload_mode", None)
    mode = str(mode or getattr(config, "ROBOT_MODBUS_PAYLOAD_MODE", "pose")).strip().lower()
    return mode if mode in {"pose", "square_command"} else "pose"


def _payload_bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "confirmed"}
    return bool(value)
