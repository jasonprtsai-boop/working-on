from __future__ import annotations

from flask import jsonify

from backend.application.services.runtime_control import runtime_control
from backend.interfaces.api.shared import api_bp, error_response, json_object_payload


@api_bp.route("/runtime/control", methods=["GET"])
def runtime_control_status():
    return jsonify({"ok": True, **runtime_control.snapshot()})


@api_bp.route("/runtime/engine-depth", methods=["POST"])
def set_runtime_engine_depth():
    try:
        payload = json_object_payload()
    except ValueError as exc:
        return error_response("validation_failed", str(exc), 400)
    if "depth" not in payload:
        return error_response("invalid_depth", "depth is required.", 400)
    try:
        snapshot = runtime_control.set_engine_depth(int(payload.get("depth")))
    except (TypeError, ValueError):
        return error_response("invalid_depth", "depth must be an integer.", 400)
    return jsonify({"ok": True, **snapshot})


@api_bp.route("/runtime/ai-mode", methods=["POST"])
def set_runtime_ai_mode():
    try:
        payload = json_object_payload()
    except ValueError as exc:
        return error_response("validation_failed", str(exc), 400)
    mode = str(payload.get("mode", payload.get("ai_mode", "")) or "")
    if not mode:
        return error_response("invalid_ai_mode", "mode is required.", 400)
    snapshot = runtime_control.set_ai_mode(mode)
    return jsonify({"ok": True, **snapshot})


@api_bp.route("/runtime/safe-mode", methods=["POST"])
def set_runtime_safe_mode():
    try:
        payload = json_object_payload()
    except ValueError as exc:
        return error_response("validation_failed", str(exc), 400)
    enabled = payload.get("enabled", payload.get("safe_mode", payload.get("safeMode", True)))
    snapshot = runtime_control.set_safe_mode(_coerce_bool(enabled))
    return jsonify({"ok": True, **snapshot})


@api_bp.route("/runtime/session/start", methods=["POST"])
def start_runtime_session():
    try:
        payload = json_object_payload()
    except ValueError as exc:
        return error_response("validation_failed", str(exc), 400)
    snapshot = runtime_control.start_session(participant_id=str(payload.get("participant_id", "") or ""))
    return jsonify({"ok": True, **snapshot})


@api_bp.route("/runtime/session/end", methods=["POST"])
def end_runtime_session():
    snapshot = runtime_control.end_session()
    return jsonify({"ok": True, **snapshot})


def _coerce_bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off", "disabled"}
    return bool(value)
