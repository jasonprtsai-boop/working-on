from __future__ import annotations

import json
from datetime import datetime, timezone

from flask import Response, jsonify, request

from backend.interfaces.api.shared import (
    REPLAY_STATE_EVENT_TYPES,
    api_bp,
    bounded_int_arg,
    error_response,
)


def _event_store():
    from backend.events.store.event_store import event_store

    return event_store


def _requested_session_id():
    session_id = request.args.get("session")
    if session_id is None:
        return None
    return str(session_id).strip()


def _session_label(session_id: str, last_timestamp=None) -> str:
    if session_id:
        return session_id
    if last_timestamp:
        try:
            return "Unassigned " + datetime.fromtimestamp(float(last_timestamp), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        except Exception:
            pass
    return "Unassigned session"


@api_bp.route("/replay/sessions", methods=["GET"])
def get_replay_sessions():
    """List replayable event sessions for the dashboard selector."""
    limit = bounded_int_arg("limit", 50, 1, 200)
    sessions = []
    for item in _event_store().list_sessions(limit=limit, event_types=REPLAY_STATE_EVENT_TYPES):
        session_id = item.get("session_id") or ""
        sessions.append(
            {
                "id": session_id,
                "session_id": session_id,
                "label": _session_label(session_id, item.get("last_timestamp")),
                "event_count": item.get("event_count", 0),
                "first_timestamp": item.get("first_timestamp"),
                "last_timestamp": item.get("last_timestamp"),
                "first_sequence_id": item.get("first_sequence_id"),
                "last_sequence_id": item.get("last_sequence_id"),
                "latest_trace_id": item.get("latest_trace_id"),
            }
        )
    return jsonify({"ok": True, "sessions": sessions, "total": len(sessions)})


@api_bp.route("/replay/steps", methods=["GET"])
def get_replay_steps():
    """Returns the full move sequence for the current session."""
    limit = bounded_int_arg("limit", 500, 1, 2000)
    offset = bounded_int_arg("offset", 0, 0, 1_000_000)
    session_id = _requested_session_id()
    store = _event_store()
    moves = []
    for index, event in enumerate(
        store.load_replay(
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
            "sequence_id": event.get("sequence_id"),
            "session_id": event.get("session_id"),
            "trace_id": event.get("trace_id"),
            "type": event.get("type"),
            "timestamp": event.get("timestamp"),
            "fen": game.get("fen") or payload.get("fen"),
            "move": (game.get("move_history") or [None])[-1],
            "move_count": len(game.get("move_history") or []),
            "turn": game.get("current_turn") or (payload.get("board") or {}).get("turn"),
        })
    total = store.count_replay(session_id=session_id, event_types=REPLAY_STATE_EVENT_TYPES)
    return jsonify({
        "ok": True,
        "steps": moves,
        "total": total,
        "count": len(moves),
        "limit": limit,
        "offset": offset,
        "session_id": session_id or "",
    })


@api_bp.route("/replay/step/<int:step>", methods=["GET"])
def get_replay_step(step: int):
    """Best-effort replay step endpoint for frontend scrubber."""
    from backend.interfaces.websocket.serializers import StateSerializer

    window = bounded_int_arg("window", 1000, 1, 5000)
    session_id = _requested_session_id()
    state_events = _event_store().load_replay(
        session_id=session_id,
        limit=window,
        offset=0,
        event_types=REPLAY_STATE_EVENT_TYPES,
    )
    if not state_events:
        return error_response("replay_unavailable", "Replay data is not available.", 404)

    index = max(0, min(step, len(state_events) - 1))
    event = state_events[index]
    payload = event.get("payload", {})
    if state_events[index].get("type") == "STATE_UPDATED":
        payload = StateSerializer.serialize(payload if isinstance(payload, dict) else {})
    if isinstance(payload, dict):
        payload = dict(payload)
        payload["_replay"] = {
            "step": index,
            "requested_step": step,
            "total": len(state_events),
            "sequence_id": event.get("sequence_id"),
            "session_id": event.get("session_id") or "",
            "trace_id": event.get("trace_id"),
            "type": event.get("type"),
            "timestamp": event.get("timestamp"),
        }
    return jsonify(payload if isinstance(payload, dict) else {})


@api_bp.route("/replay/export", methods=["GET"])
def export_replay_json():
    """Download replay steps and source events as a JSON artifact."""
    limit = bounded_int_arg("limit", 5000, 1, 20000)
    session_id = _requested_session_id()
    events = _event_store().load_replay(
        session_id=session_id,
        limit=limit,
        offset=0,
        event_types=REPLAY_STATE_EVENT_TYPES,
    )
    if not events:
        return error_response("replay_unavailable", "Replay data is not available.", 404)
    payload = {
        "ok": True,
        "session_id": session_id or "",
        "event_types": list(REPLAY_STATE_EVENT_TYPES),
        "count": len(events),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "events": events,
    }
    filename = f"replay-{session_id or 'all'}.json".replace("/", "_").replace("\\", "_")
    return Response(
        json.dumps(payload, ensure_ascii=False, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
