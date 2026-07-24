from __future__ import annotations

from flask import current_app, jsonify

from backend.interfaces.api.shared import api_bp, game_state
from backend.observability.error_reporter import publish_error_diagnostic


def _authoritative_state_payload():
    payload = game_state.to_dict()
    if isinstance(payload, dict):
        from backend.interfaces.websocket.serializers import StateSerializer
        frontend_contract = StateSerializer.serialize(payload)
        payload.setdefault("board", frontend_contract.get("board", {}))
        payload.setdefault("sync", frontend_contract.get("sync", {}))
        ui_payload = dict(frontend_contract.get("ui", {}) or {})
        try:
            from backend.application.services.runtime_control import runtime_control
            ui_payload.update(runtime_control.frontend_ui_payload())
        except Exception as exc:
            current_app.logger.warning("runtime_control UI payload unavailable", exc_info=True)
            ui_payload.update({
                "runtime_control_status": "degraded",
                "runtime_control_error": str(exc),
            })
            publish_error_diagnostic(
                source="api.state",
                module="health",
                code="runtime_control_ui_payload_failed",
                message=str(exc),
                severity="warning",
                status="warning",
                recoverable=True,
                details={"endpoint": "/api/state"},
                throttle_seconds=15.0,
            )
        payload["ui"] = {**dict(payload.get("ui", {}) or {}), **ui_payload}
        payload.setdefault("notation", frontend_contract.get("notation"))
        game = payload.get("game", {}) if isinstance(payload.get("game"), dict) else {}
        payload.setdefault("state", game.get("game_status", "UNKNOWN"))
        payload.setdefault("history", list(game.get("move_history", []) or []))
        payload.setdefault("fen", game.get("fen", ""))
        payload.setdefault("current_turn", game.get("current_turn", "w"))
    return payload


def _player_state_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return {}

    board = dict(payload.get("board", {}) or {})
    sync = dict(payload.get("sync", {}) or {})
    game = payload.get("game", {}) if isinstance(payload.get("game"), dict) else {}
    ui = payload.get("ui", {}) if isinstance(payload.get("ui"), dict) else {}
    robot = payload.get("robot", {}) if isinstance(payload.get("robot"), dict) else {}
    vision = payload.get("vision", {}) if isinstance(payload.get("vision"), dict) else {}
    engine = payload.get("engine", {}) if isinstance(payload.get("engine"), dict) else {}

    public_ui = {
        "safe_mode": ui.get("safe_mode"),
        "ai_mode": ui.get("ai_mode"),
        "ai_mode_label": ui.get("ai_mode_label"),
        "ai_difficulty": ui.get("ai_difficulty"),
        "engine_depth": ui.get("engine_depth"),
        "estop_triggered": bool(ui.get("estop_triggered") or robot.get("estop_triggered") or robot.get("global_stop")),
    }
    public_robot = {
        "busy": bool(robot.get("busy", False)),
        "connected": bool(robot.get("connected") or robot.get("is_connected")),
    }
    public_vision = {
        "status": vision.get("status"),
        "stale": bool(vision.get("stale") or vision.get("is_stale") or vision.get("isStale")),
        "stable": bool(vision.get("stable", False)),
        "fen_valid": vision.get("fen_valid"),
        "vision_age_ms": vision.get("vision_age_ms", vision.get("visionAgeMs")),
        "camera_ready": vision.get("camera_ready"),
    }
    public_engine = {
        "is_thinking": bool(engine.get("is_thinking", False)),
        "status": engine.get("status", "IDLE"),
    }
    if engine.get("best_move") or engine.get("bestMove"):
        public_engine["best_move"] = engine.get("best_move") or engine.get("bestMove")
        public_engine["bestMove"] = public_engine["best_move"]

    return {
        "board": board,
        "sync": {
            "contract_version": sync.get("contract_version"),
            "version": sync.get("version"),
            "latency": sync.get("latency", 0),
            "fps": sync.get("fps", 0),
        },
        "engine": public_engine,
        "robot": public_robot,
        "vision": public_vision,
        "ui": {key: value for key, value in public_ui.items() if value is not None},
        "notation": payload.get("notation"),
        "state": game.get("game_status", payload.get("state", "UNKNOWN")),
        "history": list(game.get("move_history", []) or []),
        "fen": game.get("fen", board.get("fen", "")),
        "current_turn": game.get("current_turn", payload.get("current_turn", "w")),
    }


@api_bp.route("/state", methods=["GET"])
def get_state():
    """Authoritative system state snapshot for authenticated operators."""
    payload = _authoritative_state_payload()
    return jsonify(payload)


@api_bp.route("/player/state", methods=["GET"])
def get_player_state():
    """Public player-mode snapshot with operational details redacted."""
    return jsonify(_player_state_payload(_authoritative_state_payload()))
