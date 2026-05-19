from __future__ import annotations

import os
import time

from flask import Blueprint, current_app, jsonify, request

from backend.application.container import container
from backend.events.bus.event_bus import bus
from backend.events.models.base_event import BaseEvent
from backend.infrastructure.vision.vision_system import vision_system
from backend.runtime.workers.engine_worker import engine_worker
from backend.state.store.state_store import state_store as game_state
from backend.utils import config
from backend.utils.error_response import build_error
from backend.utils.idempotency import idempotency_store

from backend.interfaces.api.auth_guard import enforce_control_auth
from backend.interfaces.api.client_identity import client_ip


api_bp = Blueprint("api", __name__)
api_bp.before_request(enforce_control_auth)

REPLAY_STATE_EVENT_TYPES = ("STATE_UPDATE", "STATE_UPDATED", "GAME.STATE_APPLIED")


def bounded_int_arg(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(request.args.get(name, default))
    except Exception:
        value = default
    return max(minimum, min(value, maximum))


def has_module(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


def asset_info(path: str) -> dict:
    abs_path = os.path.abspath(path or "")
    exists = bool(abs_path and os.path.exists(abs_path))
    return {
        "path": abs_path,
        "exists": exists,
        "size_bytes": os.path.getsize(abs_path) if exists and os.path.isfile(abs_path) else 0,
    }


def runtime_vision_status() -> dict:
    if hasattr(vision_system, "get_status"):
        try:
            return vision_system.get_status()
        except Exception as exc:
            return {"error": str(exc), "system": vision_system.__class__.__name__}
    return {"system": vision_system.__class__.__name__}


def runtime_observability_report() -> dict:
    """Runtime-oriented diagnostics for workers, queues, and event dispatch."""
    report = {"workers": {}, "event_bus": {}, "queues": {}}

    try:
        from backend.runtime.workers.worker_manager import worker_manager
        report["workers"] = worker_manager.status_snapshot()
    except Exception as exc:
        report["workers"] = {"error": str(exc)}

    try:
        report["event_bus"] = bus.stats() if hasattr(bus, "stats") else {}
    except Exception as exc:
        report["event_bus"] = {"error": str(exc)}

    try:
        from backend.runtime.workers.persistence_worker import persistence_worker
        report["persistence"] = persistence_worker.stats()
    except Exception as exc:
        report["persistence"] = {"error": str(exc)}

    try:
        from backend.runtime.messaging.queues import queue_manager

        def queue_state(queue):
            if queue is None:
                return {"initialized": False, "size": 0, "maxsize": 0}
            return {
                "initialized": True,
                "size": queue.qsize(),
                "maxsize": queue.maxsize,
                "full": queue.full(),
                "empty": queue.empty(),
            }

        report["queues"] = {
            "frame": queue_state(getattr(queue_manager, "_frame_queue", None)),
            "detect": queue_state(getattr(queue_manager, "_detect_queue", None)),
            "robot": queue_state(getattr(queue_manager, "_robot_queue", None)),
        }
    except Exception as exc:
        report["queues"] = {"error": str(exc)}

    try:
        from backend.application.services.runtime_control import runtime_control
        report["control"] = runtime_control.snapshot()
    except Exception as exc:
        report["control"] = {"error": str(exc)}

    return report


def runtime_metrics_report() -> dict:
    """Compact machine-readable runtime metrics for dashboards and smoke checks."""
    report = runtime_observability_report()
    workers = report.get("workers", {}) if isinstance(report.get("workers"), dict) else {}
    queues = report.get("queues", {}) if isinstance(report.get("queues"), dict) else {}
    event_bus = report.get("event_bus", {}) if isinstance(report.get("event_bus"), dict) else {}
    persistence = report.get("persistence", {}) if isinstance(report.get("persistence"), dict) else {}

    worker_status_counts = {}
    for worker in workers.values():
        if not isinstance(worker, dict):
            continue
        status = str(worker.get("status") or "unknown")
        worker_status_counts[status] = worker_status_counts.get(status, 0) + 1

    queue_depths = {
        name: {
            "size": int((queue_info or {}).get("size", 0) or 0),
            "maxsize": int((queue_info or {}).get("maxsize", 0) or 0),
            "full": bool((queue_info or {}).get("full", False)),
        }
        for name, queue_info in queues.items()
        if isinstance(queue_info, dict)
    }

    return {
        "timestamp": time.time(),
        "workers": {"count": len(workers), "status_counts": worker_status_counts},
        "queues": queue_depths,
        "event_bus": {
            "sequence": event_bus.get("sequence", 0),
            "dead_letters": event_bus.get("dead_letters", 0),
            "specific_subscribers": event_bus.get("specific_subscribers", 0),
            "global_subscribers": event_bus.get("global_subscribers", 0),
        },
        "persistence": {
            "queue_size": persistence.get("queue_size", 0),
            "queue_maxsize": persistence.get("queue_maxsize", 0),
            "dropped_events": persistence.get("dropped_events", 0),
            "persisted_events": persistence.get("persisted_events", 0),
            "last_drop_at": persistence.get("last_drop_at"),
            "last_persist_at": persistence.get("last_persist_at"),
        },
    }


def publish_base_event(event_type, payload=None, source="rest_api", trace_id=None):
    try:
        event = BaseEvent.create(
            event_type=event_type,
            source=source,
            payload=payload or {},
            trace_id=trace_id,
        )
        bus.publish(event)
        return event.trace_id
    except Exception:
        current_app.logger.debug("Structured event publish failed; falling back to raw event", exc_info=True)
        try:
            bus.publish({
                "type": str(getattr(event_type, "value", event_type)),
                "source": source,
                "payload": payload or {},
                "trace_id": trace_id,
            })
        except Exception:
            current_app.logger.warning("Raw fallback event publish failed", exc_info=True)
        return trace_id


def accepted_payload(action: str, trace_id=None, **extra):
    payload = {"ok": True, "status": "accepted", "action": action, "trace_id": trace_id}
    payload.update(extra)
    return payload


def accepted(action: str, trace_id=None, **extra):
    return jsonify(accepted_payload(action, trace_id=trace_id, **extra))


def error_response(code: str, message: str, status: int, *, trace_id=None, recoverable=True, details=None):
    return jsonify(build_error(code, message, trace_id=trace_id, recoverable=recoverable, details=details)), status


def publish_security_event(event_type: str, payload: dict):
    try:
        bus.publish({"type": event_type, "source": "rest_api", "payload": payload})
    except Exception:
        current_app.logger.debug("Failed to publish security event", exc_info=True)


def idempotency_key(data=None) -> str | None:
    body_key = getattr(data, "idempotency_key", None)
    header_key = request.headers.get("Idempotency-Key") or request.headers.get("X-Idempotency-Key")
    key = body_key or header_key
    if not key:
        return None
    claims = getattr(request, "user_claims", {}) or {}
    subject = claims.get("sub") or claims.get("role") or "anonymous"
    return f"{subject}:{request.method}:{request.path}:{str(key).strip()[:128]}"


def replay_idempotent_response(key: str | None):
    cached = idempotency_store.get(key)
    if not cached:
        return None
    body, status = cached
    response = jsonify(body)
    response.headers["X-Idempotent-Replay"] = "true"
    return response, status


def remember_idempotent_response(key: str | None, body: dict, status: int = 200):
    idempotency_store.save(key, body, status=status, ttl_seconds=300)
