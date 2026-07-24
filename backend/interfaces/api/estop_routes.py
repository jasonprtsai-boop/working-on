from __future__ import annotations

from flask import jsonify

from backend.interfaces.api.shared import api_bp, optional_json_object_payload


@api_bp.route("/estop/status", methods=["GET"])
def estop_status():
    from backend.application.services.estop import estop
    snapshot = estop.snapshot()
    snapshot.setdefault("triggered", bool(estop.is_triggered))
    snapshot.setdefault("global_stop", bool(estop.GLOBAL_STOP))
    return jsonify(snapshot)


@api_bp.route("/estop/trigger", methods=["POST"])
def estop_trigger():
    from backend.application.services.estop import estop
    payload = optional_json_object_payload()
    estop.trigger(reason=str(payload.get("reason", "REST API Trigger")))
    return jsonify({"ok": True})


@api_bp.route("/player/estop", methods=["POST"])
def player_estop_trigger():
    """Public player-side emergency stop. Stop commands should remain easy to reach."""
    from backend.application.services.estop import estop

    payload = optional_json_object_payload()
    estop.trigger(reason=str(payload.get("reason", "Player emergency stop")))
    return jsonify({"ok": True})


@api_bp.route("/estop/reset", methods=["POST"])
def estop_reset():
    from backend.application.services.estop import estop
    estop.reset()
    return jsonify({"ok": True})
