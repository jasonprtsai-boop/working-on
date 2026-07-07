from __future__ import annotations

from flask import jsonify, request
from pydantic import ValidationError

from backend.core.rules import ChessLogic
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
from backend.application.services.system_preflight import build_preflight_report
from backend.application.services.runtime_control import runtime_control
from backend.state.store.manager.state_manager import state_manager


def _dispatch_control_command(data: ControlRequest) -> str | None:
    action = str(data.action)
    payload = dict(data.payload or {})
    trace_id = data.trace_id

    if action == "start_engine":
        return publish_base_event(
            EventType.ENGINE_ANALYSIS_REQUESTED,
            payload={**payload, "mode": "start"},
            trace_id=trace_id,
        )
    if action == "stop_engine":
        return publish_base_event(
            EventType.ENGINE_ANALYSIS_REQUESTED,
            payload={**payload, "mode": "stop"},
            trace_id=trace_id,
        )
    if action == "sync_vision":
        return publish_base_event(
            EventType.UI_ACTION,
            payload={"action": "SYNC_VISION", "payload": payload},
            trace_id=trace_id,
        )
    if action == "reset":
        trace_id = publish_base_event(EventType.SYSTEM_RESET, payload=payload, trace_id=trace_id)
        publish_base_event(EventType.GAME_RESET, payload=payload, trace_id=trace_id)
        return trace_id
    if action == "pause":
        return publish_base_event(EventType.GAME_PAUSE, payload=payload, trace_id=trace_id)
    if action == "undo":
        return publish_base_event(EventType.GAME_UNDO, payload=payload, trace_id=trace_id)
    if action == "resume":
        return publish_base_event(
            EventType.ENGINE_ANALYSIS_REQUESTED,
            payload={**payload, "mode": "start"},
            trace_id=trace_id,
        )

    return publish_base_event(
        EventType.UI_ACTION,
        payload={"action": action, "payload": payload},
        trace_id=trace_id,
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

        trace_id = _dispatch_control_command(data)
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
        trace_id = _dispatch_control_command(data)
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


@api_bp.route("/player/start", methods=["POST"])
def player_start():
    """Start player-mode analysis without requiring console access."""
    payload = request.get_json(silent=True) or {}
    preflight = build_preflight_report(require_auto_execute=False)
    if not preflight.get("ready"):
        return error_response(
            "preflight_failed",
            "System preflight failed. Please complete setup before starting player mode.",
            409,
            details=preflight,
            recoverable=True,
        )
    trace_id = publish_base_event(
        EventType.ENGINE_ANALYSIS_REQUESTED,
        payload={**payload, "mode": "start", "source": payload.get("source", "player_start")},
        trace_id=payload.get("trace_id"),
    )
    body = accepted_payload("player_start", trace_id=trace_id)
    body["runtime_control"] = runtime_control.snapshot()
    return jsonify(body)


@api_bp.route("/move", methods=["POST"])
def apply_move():
    """Accept a manual UCCI move from the browser."""
    return _apply_move_request(default_type="MANUAL")


@api_bp.route("/player/move", methods=["POST"])
def apply_player_move():
    """Accept a player-view UCCI move without granting broader admin controls."""
    return _apply_move_request(default_type="PLAYER")


def _apply_move_request(default_type: str = "MANUAL"):
    try:
        raw = request.get_json(silent=True) or {}
        data = MoveRequest(**raw)
        key = idempotency_key(data)
        cached = replay_idempotent_response(key)
        if cached:
            return cached
        current_fen = state_manager.current.game.fen
        next_fen = ChessLogic.apply_move(current_fen, data.move)
        if next_fen == current_fen:
            return error_response(
                "illegal_move",
                "Move is not legal for the current board state.",
                400,
                trace_id=data.trace_id,
                details={"move": data.move},
            )

        trace_id = publish_base_event(
            EventType.GAME_PLAYER_MOVE,
            payload={
                "move": data.move,
                "player": data.player,
                "type": raw.get("type", default_type),
                "fen": next_fen,
                "fen_before": current_fen,
                "fen_after": next_fen,
            },
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
