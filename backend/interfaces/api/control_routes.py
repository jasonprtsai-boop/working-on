from __future__ import annotations

from flask import jsonify, request
from pydantic import ValidationError

from backend.events.event_types import EventType
from backend.interfaces.api.request_models import ControlRequest, MoveRequest
from backend.interfaces.api.shared import (
    accepted,
    accepted_payload,
    api_bp,
    error_response,
    idempotency_key,
    publish_base_event,
    remember_idempotent_response,
    replay_idempotent_response,
)


@api_bp.route("/control", methods=["POST"])
def control():
    """Validated control endpoint. Dispatches commands via EventBus."""
    try:
        raw = request.get_json(silent=True) or {}
        data = ControlRequest(**raw)
        key = idempotency_key(data)
        cached = replay_idempotent_response(key)
        if cached:
            return cached

        trace_id = publish_base_event(
            EventType.UI_ACTION,
            payload={"action": data.action.lower(), "payload": data.payload},
            trace_id=data.trace_id,
        )
        body = accepted_payload("control", trace_id=trace_id)
        remember_idempotent_response(key, body)
        return jsonify(body)
    except ValidationError as exc:
        return error_response(
            "validation_failed",
            "Invalid control request payload.",
            400,
            trace_id=(request.get_json(silent=True) or {}).get("trace_id"),
            details=exc.errors(),
        )
    except Exception as exc:
        return error_response("internal_error", str(exc), 500, recoverable=False)


@api_bp.route("/control/<action>", methods=["POST"])
def control_action(action: str):
    """Legacy frontend control shortcut endpoint."""
    try:
        payload = request.get_json(silent=True) or {}
        data = ControlRequest(action=action, payload=payload, trace_id=payload.get("trace_id"))
        key = idempotency_key(data)
        cached = replay_idempotent_response(key)
        if cached:
            return cached
        trace_id = publish_base_event(
            EventType.UI_ACTION,
            payload={"action": data.action, "payload": payload},
            trace_id=data.trace_id,
        )
        body = accepted_payload(data.action, trace_id=trace_id)
        remember_idempotent_response(key, body)
        return jsonify(body)
    except ValidationError as exc:
        return error_response(
            "validation_failed",
            "Invalid control action.",
            400,
            trace_id=(request.get_json(silent=True) or {}).get("trace_id"),
            details=exc.errors(),
        )


@api_bp.route("/move", methods=["POST"])
def apply_move():
    """Accept a manual UCCI move from the browser."""
    try:
        raw = request.get_json(silent=True) or {}
        data = MoveRequest(**raw)
        key = idempotency_key(data)
        cached = replay_idempotent_response(key)
        if cached:
            return cached
        trace_id = publish_base_event(
            EventType.GAME_PLAYER_MOVE,
            payload={"move": data.move, "player": data.player, "type": raw.get("type", "MANUAL")},
            trace_id=data.trace_id,
        )
        body = accepted_payload("move", trace_id=trace_id, move=data.move)
        remember_idempotent_response(key, body)
        return jsonify(body)
    except ValidationError as exc:
        return error_response(
            "validation_failed",
            "Invalid move request payload.",
            400,
            trace_id=(request.get_json(silent=True) or {}).get("trace_id"),
            details=exc.errors(),
        )


@api_bp.route("/reset", methods=["POST"])
def reset_system():
    payload = request.get_json(silent=True) or {}
    key = idempotency_key(None)
    cached = replay_idempotent_response(key)
    if cached:
        return cached
    trace_id = publish_base_event(EventType.SYSTEM_RESET, payload=payload)
    body = accepted_payload("reset", trace_id=trace_id)
    remember_idempotent_response(key, body)
    return jsonify(body)


@api_bp.route("/simulation", methods=["POST"])
def simulation_action():
    payload = request.get_json(silent=True) or {}
    trace_id = publish_base_event(
        EventType.UI_ACTION,
        payload={"action": "simulation", **payload},
        trace_id=payload.get("trace_id"),
    )
    return accepted("simulation", trace_id=trace_id)
