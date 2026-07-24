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
    ("/api/runtime/ai-mode", None, "admin"),
    ("/api/runtime/safe-mode", None, "admin"),
    ("/api/runtime/session/start", None, "admin"),
    ("/api/runtime/session/end", None, "admin"),
    ("/api/state", None, "operator"),
    ("/api/setup/settings", "GET", "setup"),
    ("/api/setup/settings", None, "setup"),
    ("/api/setup/preflight", None, "setup"),
    ("/api/setup/hardware-test", None, "setup"),
    ("/api/setup/commissioning", None, "setup"),
    ("/api/runtime", None, "operator"),
    ("/api/assets", None, "operator"),
    ("/api/video_feed", None, "operator"),
    ("/api/vision/cameras", None, "operator"),
    ("/api/vision/stream", None, "operator"),
    ("/api/vision/snapshot", None, "operator"),
    ("/api/vision/calibration", "GET", "operator"),
    ("/api/vision/calibration", None, "setup"),
    ("/api/snapshot", None, "operator"),
    ("/api/replay", None, "operator"),
    ("/api/robot/calibration", "GET", "operator"),
    ("/api/robot/calibration", None, "admin"),
    ("/api/control", None, "admin"),
    ("/api/move", None, "admin"),
    ("/api/reset", None, "admin"),
    ("/api/simulation", None, "admin"),
    ("/api/snaplog", None, "admin"),
    ("/api/estop/trigger", None, "admin"),
    ("/api/estop/reset", None, "admin"),
    ("/api/vision/camera", None, "setup"),
    ("/api/export", None, "admin"),
    ("/api/export_json", None, "admin"),
    ("/api/export_kpi", None, "admin"),
)

PUBLIC_CONTROL_ENDPOINTS = (
    ("/api/player/state", "GET"),
    ("/api/player/start", None),
    ("/api/player/move", None),
    ("/api/player/estop", None),
)

ROLE_LEVELS = {"viewer": 1, "operator": 2, "setup": 2, "admin": 3}


def _matches_request(prefix: str, method: str | None) -> bool:
    path = request.path.rstrip("/")
    if method and request.method != method:
        return False
    return path == prefix or path.startswith(prefix + "/")


def _required_role_for_request() -> str | None:
    for item in PROTECTED_ENDPOINTS:
        prefix, method, role = item if len(item) == 3 else (*item, "admin")
        if _matches_request(prefix, method):
            return role
    return None


def _is_public_control_request() -> bool:
    return any(_matches_request(prefix, method) for prefix, method in PUBLIC_CONTROL_ENDPOINTS)


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
    if str(required).lower() == "setup":
        return str(actual or "").lower() in {"setup", "admin"}
    return ROLE_LEVELS.get(str(actual or "").lower(), 0) >= ROLE_LEVELS.get(str(required).lower(), 999)


def enforce_control_auth():
    """Blueprint before_request hook for control-plane endpoints."""
    if request.endpoint in {"api.login", "api.setup_login"}:
        return _enforce_rate_limit("login", getattr(config, "LOGIN_RATE_LIMIT_PER_MINUTE", 20))

    required_role = _required_role_for_request()
    if required_role or _is_public_control_request():
        limited = _enforce_rate_limit("control", getattr(config, "CONTROL_RATE_LIMIT_PER_MINUTE", 120))
        if limited:
            return limited

    if not getattr(config, "CONTROL_AUTH_REQUIRED", True):
        return None
    if not required_role:
        return None

    payload = verify_request_token()
    if payload is None:
        return _error_response("unauthorized", "Valid session or bearer token required.", 401)
    if not _has_required_role(payload.get("role"), required_role):
        return _error_response("forbidden", f"{required_role.title()} role required.", 403)
    request.user_role = payload.get("role")
    request.user_claims = payload
    return None
