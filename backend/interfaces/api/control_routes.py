from __future__ import annotations

from typing import Any, Mapping

from flask import jsonify
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
    json_object_payload,
    mark_deprecated_endpoint,
    optional_json_object_payload,
    publish_base_event,
    remember_idempotent_response,
    replay_idempotent_response,
)
from backend.application.services.system_preflight import build_preflight_report
from backend.application.services.runtime_control import runtime_control
from backend.application.use_cases.coordinate_workflow import workflow_coordinator
from backend.interfaces.websocket.serializers import StateSerializer
from backend.state.store.manager.state_manager import state_manager


PLAYER_END_FINAL_CONFIRMATION = "END_GAME_CONFIRMED"


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


def _public_text(value: Any, default: str = "", *, max_length: int = 64) -> str:
    text = str(value if value is not None else default).strip()
    if not text:
        text = default
    return text[:max_length]


def _public_player_start_payload(raw: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "mode": "start",
        "source": _public_text(raw.get("source"), "player_start"),
    }


def _public_player_end_payload(raw: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source": _public_text(raw.get("source"), "player_end_button"),
        "trace_id": _public_trace_id(raw),
    }


def _player_end_game_confirmed(raw: Mapping[str, Any]) -> bool:
    confirmed_action = str(raw.get("confirmed_action") or "").strip().lower()
    final_confirmation = str(raw.get("final_confirmation") or "").strip().upper()
    return confirmed_action == "end_game" and final_confirmation == PLAYER_END_FINAL_CONFIRMATION


def _player_end_state_payload(game_result: Mapping[str, Any]) -> dict[str, Any]:
    raw_state = state_manager.current.to_dict()
    frontend_state = StateSerializer.serialize(raw_state)
    result = dict(game_result or {})
    result["ended"] = True

    game = dict(raw_state.get("game", {}) if isinstance(raw_state.get("game"), Mapping) else {})
    game.update({
        "game_status": "GAME_OVER",
        "game_phase": "ENDED",
        "game_result": result,
    })

    board = dict(frontend_state.get("board", {}) if isinstance(frontend_state.get("board"), Mapping) else {})
    board.update({
        "game_status": "GAME_OVER",
        "game_phase": "ENDED",
        "game_result": result,
        "ended": True,
    })

    return {
        **raw_state,
        **frontend_state,
        "game": game,
        "board": board,
        "state": "GAME_OVER",
    }


def _public_trace_id(raw: Mapping[str, Any]) -> str | None:
    trace_id = _public_text(raw.get("trace_id"), "", max_length=128)
    return trace_id or None


def _public_runtime_control_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    session = snapshot.get("session", {}) if isinstance(snapshot.get("session"), Mapping) else {}
    public = {
        key: snapshot.get(key)
        for key in ("safe_mode", "ai_mode", "ai_mode_label", "ai_difficulty", "engine_depth")
        if snapshot.get(key) is not None
    }
    public["session"] = {
        "active": bool(session.get("active", False)),
        "duration_sec": session.get("duration_sec", 0),
        "move_count": session.get("move_count", 0),
    }
    return public


def _public_preflight_report(preflight: Mapping[str, Any]) -> dict[str, Any]:
    checks = []
    for item in preflight.get("checks", []) or []:
        if not isinstance(item, Mapping):
            continue
        checks.append({
            "key": item.get("key"),
            "ok": bool(item.get("ok", False)),
            "label": item.get("label"),
            "message": item.get("message"),
            "severity": item.get("severity", "error"),
        })

    failures = [item for item in checks if not item["ok"] and item.get("severity") == "error"]
    warnings = [item for item in checks if not item["ok"] and item.get("severity") == "warning"]
    return {
        "ok": bool(preflight.get("ok", False)),
        "ready": bool(preflight.get("ready", False)),
        "checks": checks,
        "failures": failures,
        "warnings": warnings,
        "failure_count": len(failures),
        "warning_count": len(warnings),
    }


@api_bp.route("/control", methods=["POST"])
def control():
    """Validated control endpoint. Dispatches commands via EventBus."""
    try:
        raw = json_object_payload()
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
            trace_id=raw.get("trace_id") if "raw" in locals() else None,
            details=exc.errors(),
        )
    except ValueError as exc:
        return error_response("validation_failed", str(exc), 400)
    except Exception as exc:
        return error_response("internal_error", str(exc), 500, recoverable=False)


@api_bp.route("/control/<action>", methods=["POST"])
def control_action(action: str):
    """Legacy frontend control shortcut endpoint."""
    try:
        payload = json_object_payload()
        data = ControlRequest(action=action, payload=payload, trace_id=payload.get("trace_id"))
        key = idempotency_key(data)
        cached = replay_idempotent_response(key)
        if cached:
            return mark_deprecated_endpoint(cached, "/api/control")
        trace_id = _dispatch_control_command(data)
        body = accepted_payload(data.action, trace_id=trace_id)
        remember_idempotent_response(key, body)
        return mark_deprecated_endpoint(jsonify(body), "/api/control")
    except ValidationError as exc:
        return error_response(
            "validation_failed",
            "Invalid control action.",
            400,
            trace_id=payload.get("trace_id") if "payload" in locals() else None,
            details=exc.errors(),
        )
    except ValueError as exc:
        return error_response("validation_failed", str(exc), 400)


@api_bp.route("/stop", methods=["POST"])
def stop_system():
    """Public website stop request; this pauses software flow only."""
    payload = optional_json_object_payload()
    trace_id = publish_base_event(
        EventType.GAME_PAUSE,
        payload={
            "phase": "paused",
            "reason": _public_text(payload.get("reason"), "website_stop", max_length=128),
            "source": _public_text(payload.get("source"), "website_stop"),
        },
        trace_id=_public_trace_id(payload),
    )
    return accepted("stop", trace_id=trace_id)


@api_bp.route("/player/start", methods=["POST"])
def player_start():
    """Start player-mode analysis without requiring console access."""
    try:
        payload = json_object_payload()
    except ValueError as exc:
        return error_response("validation_failed", str(exc), 400)
    preflight = build_preflight_report(require_auto_execute=False)
    public_preflight = _public_preflight_report(preflight)
    if public_preflight["failures"]:
        return error_response(
            "player_preflight_failed",
            "Player mode is not ready to start.",
            409,
            details={"preflight": public_preflight},
        )

    trace_id = publish_base_event(
        EventType.ENGINE_ANALYSIS_REQUESTED,
        payload=_public_player_start_payload(payload),
        trace_id=_public_trace_id(payload),
    )
    body = accepted_payload("player_start", trace_id=trace_id)
    body["runtime_control"] = _public_runtime_control_snapshot(runtime_control.snapshot())
    body["preflight"] = public_preflight
    return jsonify(body)


@api_bp.route("/player/end-game", methods=["POST"])
def player_end_game():
    """End the public player-mode game after explicit two-step confirmation."""
    try:
        payload = optional_json_object_payload()
    except ValueError as exc:
        return error_response("validation_failed", str(exc), 400)
    if not _player_end_game_confirmed(payload):
        return error_response(
            "player_end_confirmation_required",
            "Ending the game requires explicit player confirmation.",
            400,
            trace_id=_public_trace_id(payload),
            details={
                "required": {
                    "confirmed_action": "end_game",
                    "final_confirmation": PLAYER_END_FINAL_CONFIRMATION,
                }
            },
        )

    result = workflow_coordinator.end_game_by_player(_public_player_end_payload(payload))
    game_result = result.get("game_result") or {}
    body = accepted_payload(
        "player_end_game",
        trace_id=result.get("trace_id"),
        message="對局已結束。",
        game_result=game_result,
        state=_player_end_state_payload(game_result),
    )
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
        raw = json_object_payload()
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
            trace_id=raw.get("trace_id") if "raw" in locals() else None,
            details=exc.errors(),
        )
    except ValueError as exc:
        return error_response("validation_failed", str(exc), 400)


@api_bp.route("/reset", methods=["POST"])
def reset_system():
    try:
        payload = json_object_payload()
    except ValueError as exc:
        return error_response("validation_failed", str(exc), 400)
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
    try:
        payload = json_object_payload()
    except ValueError as exc:
        return error_response("validation_failed", str(exc), 400)
    trace_id = publish_base_event(
        EventType.UI_ACTION,
        payload={"action": "simulation", **payload},
        trace_id=payload.get("trace_id"),
    )
    return accepted("simulation", trace_id=trace_id)
