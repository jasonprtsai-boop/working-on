from __future__ import annotations

from flask import jsonify, request

from backend.interfaces.api.shared import api_bp


@api_bp.route("/estop/status", methods=["GET"])
def estop_status():
    from backend.application.services.estop import estop
    return jsonify({
        "triggered": bool(estop.is_triggered),
        "global_stop": bool(estop.GLOBAL_STOP),
    })


@api_bp.route("/estop/trigger", methods=["POST"])
def estop_trigger():
    from backend.application.services.estop import estop
    payload = request.get_json(silent=True) or {}
    estop.trigger(reason=str(payload.get("reason", "REST API Trigger")))
    return jsonify({"ok": True})


@api_bp.route("/estop/reset", methods=["POST"])
def estop_reset():
    from backend.application.services.estop import estop
    estop.reset()
    return jsonify({"ok": True})
