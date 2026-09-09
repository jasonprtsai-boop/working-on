from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from backend.application.container import container
from backend.events.bus.event_bus import bus
from backend.events.models.base_event import BaseEvent
from backend.interfaces.api.auth_guard import enforce_control_auth
from backend.interfaces.api.client_identity import client_ip
from backend.interfaces.api.request_helpers import (
    asset_info,
    bounded_int_arg,
    has_module,
    json_object_payload,
    optional_json_object_payload,
)
from backend.interfaces.api.runtime_reports import runtime_metrics_report, runtime_observability_report
from backend.interfaces.api.vision_runtime import VisionSystemProxy, runtime_vision_status_payload
from backend.observability.error_reporter import publish_error_diagnostic
from backend.runtime.workers.engine_worker import engine_worker
from backend.state.store.state_store import state_store as game_state
from backend.utils import config
from backend.utils.error_response import build_error
from backend.utils.idempotency import idempotency_store


api_bp = Blueprint("api", __name__)
api_bp.before_request(enforce_control_auth)

REPLAY_STATE_EVENT_TYPES = ("STATE_UPDATE", "STATE_UPDATED", "GAME.STATE_APPLIED")
vision_system = VisionSystemProxy()


def runtime_vision_status() -> dict:
    return runtime_vision_status_payload(vision_system, config)


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


def mark_deprecated_endpoint(response, replacement: str):
    if isinstance(response, tuple):
        body = mark_deprecated_endpoint(response[0], replacement)
        return (body, *response[1:])
    response.headers["Deprecation"] = "true"
    response.headers["X-Deprecated-Endpoint"] = "true"
    response.headers["X-Replacement-Endpoint"] = replacement
    return response


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
