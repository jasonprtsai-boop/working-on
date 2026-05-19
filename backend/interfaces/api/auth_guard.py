from __future__ import annotations

from flask import jsonify, request

from backend.interfaces.api.client_identity import client_ip
from backend.utils import config
from backend.utils.error_response import build_error
from backend.utils.auth import verify_request_token
from backend.utils.rate_limit import RateLimitExceeded, rate_limiter


PROTECTED_ENDPOINTS = (
    ("/api/health", None, "operator"),
    ("/api/engine/status", None, "operator"),
    ("/api/vision/status", None, "operator"),
    ("/api/video_status", None, "operator"),
    ("/api/estop/status", None, "operator"),
    ("/api/runtime/engine-depth", None, "admin"),
    ("/api/runtime/safe-mode", None, "admin"),
    ("/api/runtime/session/start", None, "admin"),
    ("/api/runtime/session/end", None, "admin"),
    ("/api/runtime", None, "operator"),
    ("/api/assets", None, "operator"),
    ("/api/video_feed", None, "operator"),
    ("/api/vision/stream", None, "operator"),
    ("/api/vision/snapshot", None, "operator"),
    ("/api/snapshot", None, "operator"),
    ("/api/replay", None, "operator"),
    ("/api/control", None, "admin"),
    ("/api/move", None, "admin"),
    ("/api/reset", None, "admin"),
    ("/api/simulation", None, "admin"),
    ("/api/snaplog", None, "admin"),
    ("/api/estop/trigger", None, "admin"),
    ("/api/estop/reset", None, "admin"),
    ("/api/vision/camera", None, "admin"),
    ("/api/export", None, "admin"),
    ("/api/export_json", None, "admin"),
    ("/api/export_kpi", None, "admin"),
)

ROLE_LEVELS = {"viewer": 1, "operator": 2, "admin": 3}


def _required_role_for_request() -> str | None:
    path = request.path.rstrip("/")
    for item in PROTECTED_ENDPOINTS:
        prefix, method, role = item if len(item) == 3 else (*item, "admin")
        if method and request.method != method:
            continue
        if path == prefix or path.startswith(prefix + "/"):
            return role
    return None


def _client_identity() -> str:
    return client_ip()


def _rate_limit_response(exc: RateLimitExceeded):
    payload = build_error(
        "rate_limited",
        "Too many requests. Please retry later.",
        recoverable=True,
        details={"retry_after_seconds": exc.retry_after_seconds},
    )
    response = jsonify(payload)
    response.headers["Retry-After"] = str(exc.retry_after_seconds)
    return response, 429


def _enforce_rate_limit(bucket: str, limit: int):
    if not getattr(config, "RATE_LIMITS_ENABLED", True):
        return None
    key = f"{bucket}:{_client_identity()}:{request.path}"
    try:
        rate_limiter.check(key, int(limit), 60.0)
    except RateLimitExceeded as exc:
        return _rate_limit_response(exc)
    return None


def _error_response(code: str, message: str, status: int, *, recoverable: bool = True):
    return jsonify(build_error(code, message, recoverable=recoverable)), status


def _has_required_role(actual: str | None, required: str | None) -> bool:
    if not required:
        return True
    return ROLE_LEVELS.get(str(actual or "").lower(), 0) >= ROLE_LEVELS.get(str(required).lower(), 999)


def enforce_control_auth():
    """Blueprint before_request hook for control-plane endpoints."""
    if request.endpoint == "api.login":
        return _enforce_rate_limit("login", getattr(config, "LOGIN_RATE_LIMIT_PER_MINUTE", 20))

    required_role = _required_role_for_request()
    if required_role:
        limited = _enforce_rate_limit("control", getattr(config, "CONTROL_RATE_LIMIT_PER_MINUTE", 120))
        if limited:
            return limited

    if not getattr(config, "CONTROL_AUTH_REQUIRED", True):
        return None
    if not required_role:
        return None

    payload = verify_request_token()
    if payload is None:
        return _error_response("unauthorized", "Valid bearer token required.", 401)
    if not _has_required_role(payload.get("role"), required_role):
        return _error_response("forbidden", f"{required_role.title()} role required.", 403)
    request.user_role = payload.get("role")
    request.user_claims = payload
    return None
