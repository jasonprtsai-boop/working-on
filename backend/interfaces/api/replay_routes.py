from __future__ import annotations

from flask import jsonify, request

from backend.interfaces.api.shared import (
    REPLAY_STATE_EVENT_TYPES,
    api_bp,
    bounded_int_arg,
    error_response,
)


@api_bp.route("/replay/steps", methods=["GET"])
def get_replay_steps():
    """Returns the full move sequence for the current session."""
    from backend.events.store.event_store import event_store

    limit = bounded_int_arg("limit", 500, 1, 2000)
    offset = bounded_int_arg("offset", 0, 0, 1_000_000)
    session_id = request.args.get("session")
    moves = []
    for index, event in enumerate(
        event_store.load_replay(
            session_id=session_id,
            limit=limit,
            offset=offset,
            event_types=REPLAY_STATE_EVENT_TYPES,
        ),
        start=offset,
    ):
        payload = event.get("payload", {}) if isinstance(event.get("payload"), dict) else {}
        game = payload.get("game", {}) if isinstance(payload.get("game"), dict) else {}
        moves.append({
            "step": index,
            "type": event.get("type"),
            "timestamp": event.get("timestamp"),
            "fen": game.get("fen") or payload.get("fen"),
            "move": (game.get("move_history") or [None])[-1],
        })
    return jsonify({"steps": moves, "total": len(moves), "limit": limit, "offset": offset})


@api_bp.route("/replay/step/<int:step>", methods=["GET"])
def get_replay_step(step: int):
    """Best-effort replay step endpoint for frontend scrubber."""
    from backend.events.store.event_store import event_store
    from backend.interfaces.websocket.serializers import StateSerializer

    window = bounded_int_arg("window", 1000, 1, 5000)
    session_id = request.args.get("session")
    state_events = event_store.load_replay(
        session_id=session_id,
        limit=window,
        offset=0,
        event_types=REPLAY_STATE_EVENT_TYPES,
    )
    if not state_events:
        return error_response("replay_unavailable", "Replay data is not available.", 404)

    index = max(0, min(step, len(state_events) - 1))
    payload = state_events[index].get("payload", {})
    if state_events[index].get("type") == "STATE_UPDATED":
        payload = StateSerializer.serialize(payload if isinstance(payload, dict) else {})
    return jsonify(payload if isinstance(payload, dict) else {})
