from __future__ import annotations

import os
import time
from functools import lru_cache
from importlib.util import find_spec
from typing import Any, Mapping

from flask import Blueprint, current_app, jsonify, request

from backend.application.container import container
from backend.events.bus.event_bus import bus
from backend.events.models.base_event import BaseEvent
from backend.runtime.workers.engine_worker import engine_worker
from backend.runtime.contract_schema import normalize_diagnostics_payload
from backend.state.store.state_store import state_store as game_state
from backend.utils import config
from backend.utils.error_response import build_error
from backend.utils.idempotency import idempotency_store
from backend.observability.error_reporter import publish_error_diagnostic

from backend.interfaces.api.auth_guard import enforce_control_auth
from backend.interfaces.api.client_identity import client_ip


api_bp = Blueprint("api", __name__)
api_bp.before_request(enforce_control_auth)

REPLAY_STATE_EVENT_TYPES = ("STATE_UPDATE", "STATE_UPDATED", "GAME.STATE_APPLIED")


class _VisionSystemProxy:
    def _target(self):
        from backend.infrastructure.vision.vision_system import vision_system as real_vision_system

        return real_vision_system

    @property
    def __class__(self):
        return self._target().__class__

    def __getattr__(self, name):
        return getattr(self._target(), name)


vision_system = _VisionSystemProxy()


def bounded_int_arg(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(request.args.get(name, default))
    except Exception:
        value = default
    return max(minimum, min(value, maximum))


def json_object_payload() -> dict[str, Any]:
    payload = request.get_json(silent=True)
    if payload is None:
        return {}
    if not isinstance(payload, Mapping):
        raise ValueError("Request JSON body must be an object.")
    return dict(payload)


def optional_json_object_payload() -> dict[str, Any]:
    payload = request.get_json(silent=True)
    return dict(payload) if isinstance(payload, Mapping) else {}


@lru_cache(maxsize=64)
def has_module(name: str) -> bool:
    try:
        return bool(name and find_spec(name) is not None)
    except (ImportError, ValueError, AttributeError):
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
            status = vision_system.get_status()
            if not isinstance(status, dict):
                return {"system": vision_system.__class__.__name__, "status": status}
            fallback_reason = (
                status.get("fallback_reason")
                or ((status.get("calibration") or {}) if isinstance(status.get("calibration"), Mapping) else {}).get("fallback_reason")
                or getattr(vision_system, "_fallback_reason", None)
            )
            fallback = bool(status.get("fallback") or fallback_reason)
            status.setdefault("configured_fake_vision", bool(getattr(config, "FAKE_VISION", False)))
            status["fallback"] = fallback
            if fallback_reason:
                status["fallback_reason"] = str(fallback_reason)
            if fallback:
                status["simulation"] = True
                status.setdefault("mode", "fallback")
            return status
        except Exception as exc:
            return {"error": str(exc), "system": vision_system.__class__.__name__}
    return {"system": vision_system.__class__.__name__}


def runtime_observability_report() -> dict:
    """Runtime-oriented diagnostics for workers, queues, and event dispatch."""
    report = {"workers": {}, "event_bus": {}, "queues": {}}

    try:
        from backend.runtime.workers.worker_manager import worker_manager
        report["workers"] = worker_manager.status_snapshot()
        report["async_runtime"] = worker_manager.runtime_snapshot()
    except Exception as exc:
        report["workers"] = {"error": str(exc)}
        report["async_runtime"] = {"error": str(exc)}

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
        report["queues"] = queue_manager.stats()
    except Exception as exc:
        report["queues"] = {"error": str(exc)}

    try:
        from backend.observability.telemetry import telemetry_service
        telemetry_snapshot = telemetry_service.snapshot(
            queue_stats=report.get("queues", {}),
            worker_status=report.get("workers", {}),
        )
        report.update(telemetry_snapshot)
    except Exception as exc:
        report["telemetry"] = {"enabled": False, "error": str(exc)}

    try:
        from backend.application.services.runtime_control import runtime_control
        report["control"] = runtime_control.snapshot()
    except Exception as exc:
        report["control"] = {"error": str(exc)}

    report.setdefault("queue", report.get("queues", {}))
    return normalize_diagnostics_payload(report)


def runtime_metrics_report() -> dict:
    """Compact machine-readable runtime metrics for dashboards and smoke checks."""
    report = runtime_observability_report()
    workers = report.get("workers", {}) if isinstance(report.get("workers"), dict) else {}
    queues = report.get("queue", {}) if isinstance(report.get("queue"), dict) else {}
    if not queues:
        queues = report.get("queues", {}) if isinstance(report.get("queues"), dict) else {}
    event_bus = report.get("event_bus", {}) if isinstance(report.get("event_bus"), dict) else {}
    persistence = report.get("persistence", {}) if isinstance(report.get("persistence"), dict) else {}
    telemetry = report.get("telemetry", {}) if isinstance(report.get("telemetry"), dict) else {}
    pipeline = report.get("pipeline", {}) if isinstance(report.get("pipeline"), dict) else {}

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
        "async_runtime": report.get("async_runtime", {}),
        "persistence": {
            "queue_size": persistence.get("queue_size", 0),
            "queue_maxsize": persistence.get("queue_maxsize", 0),
            "received_events": persistence.get("received_events", 0),
            "dropped_events": persistence.get("dropped_events", 0),
            "drop_warning": persistence.get("drop_warning", False),
            "drop_rate": persistence.get("drop_rate", 0.0),
            "persisted_events": persistence.get("persisted_events", 0),
            "last_drop_at": persistence.get("last_drop_at"),
            "last_persist_at": persistence.get("last_persist_at"),
        },
        "telemetry": {
            "enabled": telemetry.get("enabled", False),
            "recorded_events": telemetry.get("recorded_events", 0),
            "dropped_events": telemetry.get("dropped_events", 0),
            "recent_events": len(telemetry.get("recent_events", []) or []),
            "errors": len(telemetry.get("errors", []) or []),
        },
        "pipeline": {
            "status": pipeline.get("status", "idle"),
            "active_trace_id": pipeline.get("active_trace_id", ""),
            "total_latency_ms": pipeline.get("total_latency_ms", 0.0),
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
        current_app.logger.warning("Structured event publish failed", exc_info=True)
        return trace_id


def accepted_payload(action: str, trace_id=None, **extra):
    payload = {"ok": True, "status": "accepted", "action": action, "trace_id": trace_id}
    payload.update(extra)
    return payload


def accepted(action: str, trace_id=None, **extra):
    return jsonify(accepted_payload(action, trace_id=trace_id, **extra))


def error_response(code: str, message: str, status: int, *, trace_id=None, recoverable=True, details=None):
    if status >= 500 or recoverable is False:
        try:
            publish_error_diagnostic(
                source="rest_api",
                module="health",
                code=code,
                message=message,
                severity="error" if status >= 500 else "warning",
                status="error" if status >= 500 else "warning",
                trace_id=trace_id,
                recoverable=recoverable,
                details={
                    "method": request.method,
                    "path": request.path,
                    "endpoint": request.endpoint,
                    "http_status": status,
                    "details": details if details is not None else {},
                },
            )
        except Exception:
            current_app.logger.warning("Failed to publish API error diagnostics", exc_info=True)
    return jsonify(build_error(code, message, trace_id=trace_id, recoverable=recoverable, details=details)), status


def publish_security_event(event_type: str, payload: dict):
    try:
        bus.publish(BaseEvent.create(event_type=event_type, source="rest_api", payload=payload))
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
