from __future__ import annotations

from flask import current_app, jsonify

from backend.interfaces.api.shared import api_bp, game_state
from backend.observability.error_reporter import publish_error_diagnostic


@api_bp.route("/state", methods=["GET"])
def get_state():
    """Authoritative system state snapshot."""
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
    return jsonify(payload)
