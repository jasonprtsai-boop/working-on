from __future__ import annotations

from flask import jsonify

from backend.interfaces.api.shared import api_bp, game_state


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
        except Exception:
            pass
        payload["ui"] = {**dict(payload.get("ui", {}) or {}), **ui_payload}
        payload.setdefault("notation", frontend_contract.get("notation"))
        game = payload.get("game", {}) if isinstance(payload.get("game"), dict) else {}
        payload.setdefault("state", game.get("game_status", "UNKNOWN"))
        payload.setdefault("history", list(game.get("move_history", []) or []))
        payload.setdefault("fen", game.get("fen", ""))
        payload.setdefault("current_turn", game.get("current_turn", "w"))
    return jsonify(payload)
