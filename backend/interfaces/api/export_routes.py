from __future__ import annotations

import os
import csv
import json
import tempfile
import time

from flask import after_this_request, current_app, jsonify, request, send_file

from backend.events.event_types import EventType
from backend.interfaces.api.shared import (
    accepted,
    api_bp,
    bounded_int_arg,
    error_response,
    game_state,
    publish_base_event,
)
from backend.utils import config


@api_bp.route("/snaplog", methods=["POST"])
def snaplog():
    payload = request.get_json(silent=True) or {}
    snapshot = game_state.to_dict()
    trace_id = publish_base_event(
        EventType.DIAGNOSTICS_UPDATED,
        payload={"snaplog": True, "state": snapshot, **payload},
        trace_id=payload.get("trace_id"),
    )
    return accepted("snaplog", trace_id=trace_id, state=snapshot)


@api_bp.route("/export_json", methods=["GET"])
def export_json():
    return jsonify(game_state.to_dict())


@api_bp.route("/export_kpi", methods=["GET"])
def export_kpi():
    snapshot = game_state.to_dict()
    sync = snapshot.get("sync", {}) if isinstance(snapshot, dict) else {}
    engine = snapshot.get("engine", {}) if isinstance(snapshot, dict) else {}
    vision = snapshot.get("vision", {}) if isinstance(snapshot, dict) else {}
    return jsonify({
        "sync": sync,
        "engine": engine,
        "vision": vision,
        "health": getattr(game_state, "health", {}),
    })


@api_bp.route("/export/excel", methods=["GET"])
def export_excel():
    """Exports the experimental logs to Excel."""
    from backend.utils.serialization.excel_report_service import export_research_workbook

    session_id = request.args.get("session")
    limit = bounded_int_arg("limit", config.EXCEL_EXPORT_EVENT_LIMIT, 1, 50000)
    try:
        result = export_research_workbook(session_id, event_limit=limit)
    except Exception as exc:
        return error_response("export_failed", str(exc), 500, recoverable=False)

    @after_this_request
    def cleanup(resp):
        try:
            if os.path.exists(result.path):
                os.remove(result.path)
        except Exception:
            current_app.logger.debug("Temporary Excel export cleanup failed: %s", result.path, exc_info=True)
        return resp

    return send_file(result.path, as_attachment=True, download_name=result.filename)


@api_bp.route("/export/csv", methods=["GET"])
def export_csv():
    """Export persisted runtime events as a compact CSV file."""
    from backend.events.store.event_store import event_store

    session_id = request.args.get("session") or None
    try:
        limit = min(max(int(request.args.get("limit", 10000) or 10000), 1), 50000)
    except (TypeError, ValueError):
        limit = 10000
    try:
        events = event_store.load_replay(session_id=session_id, limit=limit)
    except Exception as exc:
        return error_response("export_failed", str(exc), 500, recoverable=False)

    fd, path = tempfile.mkstemp(prefix="smart_chess_events_", suffix=".csv")
    os.close(fd)
    headers = [
        "sequence_id",
        "session_id",
        "trace_id",
        "type",
        "timestamp",
        "payload_json",
        "event_id",
        "source",
        "metadata_json",
    ]
    try:
        with open(path, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            for event in events:
                writer.writerow({
                    "sequence_id": event.get("sequence_id", ""),
                    "session_id": event.get("session_id", ""),
                    "trace_id": event.get("trace_id", ""),
                    "type": event.get("type", ""),
                    "timestamp": event.get("timestamp", ""),
                    "payload_json": json.dumps(event.get("payload") or {}, ensure_ascii=False, sort_keys=True),
                    "event_id": event.get("event_id", ""),
                    "source": event.get("source", ""),
                    "metadata_json": json.dumps(event.get("metadata") or {}, ensure_ascii=False, sort_keys=True),
                })
    except Exception as exc:
        try:
            os.remove(path)
        except Exception:
            pass
        return error_response("export_failed", str(exc), 500, recoverable=False)

    @after_this_request
    def cleanup(resp):
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            current_app.logger.debug("Temporary CSV export cleanup failed: %s", path, exc_info=True)
        return resp

    suffix = session_id or time.strftime("%Y%m%d_%H%M%S")
    return send_file(
        path,
        as_attachment=True,
        download_name=f"smart-chess-events-{suffix}.csv",
        mimetype="text/csv",
    )
