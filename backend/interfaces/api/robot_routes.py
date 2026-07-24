from __future__ import annotations

from flask import jsonify

from backend.interfaces.api.shared import api_bp, error_response, json_object_payload
from backend.utils.kinematics import kinematics
from backend.interfaces.api.setup_routes import current_setup_settings, normalize_setup_settings


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
        if "points" in payload:
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
    except Exception:
        pass
