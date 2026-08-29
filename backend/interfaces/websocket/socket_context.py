from __future__ import annotations

import json
import threading

from flask import request
from pydantic import ValidationError

from backend.utils import config
from backend.utils.error_response import build_error
from backend.utils.logger import logger
from backend.utils.rate_limit import RateLimitExceeded, rate_limiter


def viewer_claims() -> dict:
    return {"role": "viewer", "sub": "anonymous", "authenticated": False}


def payload_size_ok(data, *, max_bytes: int | None = None) -> bool:
    try:
        encoded = json.dumps(data or {}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except Exception:
        encoded = str(data).encode("utf-8", errors="ignore")
    limit = int(max_bytes if max_bytes is not None else getattr(config, "MAX_SOCKET_PAYLOAD_BYTES", 65536))
    return len(encoded) <= limit


class SocketSessionContext:
    def __init__(self, socketio):
        self._socketio = socketio
        self._claims_by_sid: dict[str, dict] = {}
        self._lock = threading.RLock()

    def set_claims(self, claims: dict):
        sid = getattr(request, "sid", None)
        if sid:
            with self._lock:
                self._claims_by_sid[sid] = dict(claims or {})

    def drop_claims(self):
        sid = getattr(request, "sid", None)
        if sid:
            with self._lock:
                self._claims_by_sid.pop(sid, None)

    def get_claims(self):
        if not getattr(config, "CONTROL_AUTH_REQUIRED", True):
            return {"role": "admin"}
        sid = getattr(request, "sid", None)
        if not sid:
            return None
        with self._lock:
            return self._claims_by_sid.get(sid)

    def socket_error(
        self,
        error: str,
        message: str,
        *,
        trace_id=None,
        recoverable=True,
        details=None,
    ):
        payload = build_error(error, message, trace_id=trace_id, recoverable=recoverable, details=details)
        try:
            self._socketio.emit("AUTH_ERROR", payload, room=getattr(request, "sid", None))
        except Exception:
            logger.debug("[Socket] failed to emit AUTH_ERROR", exc_info=True)
        return payload

    def require_admin(self):
        claims = self.get_claims()
        if not claims or claims.get("authenticated") is False:
            return None, self.socket_error("unauthorized", "Valid bearer token required.")
        if claims.get("role") != "admin":
            return None, self.socket_error("forbidden", "Admin role required.")
        return claims, None

    def validation_error(self, exc: ValidationError):
        return self.socket_error("invalid_payload", "Invalid socket payload.", details=exc.errors())

    def payload_too_large_error(self):
        return self.socket_error(
            "payload_too_large",
            "Socket payload exceeds the configured size limit.",
            recoverable=False,
            details={"max_bytes": int(getattr(config, "MAX_SOCKET_PAYLOAD_BYTES", 65536))},
        )

    def payload_size_ok(self, data) -> bool:
        return payload_size_ok(data)

    def rate_limit_socket(self, event_name: str):
        if not getattr(config, "RATE_LIMITS_ENABLED", True):
            return None
        sid = getattr(request, "sid", None) or "unknown"
        try:
            rate_limiter.check(
                f"socket:{sid}:{event_name}",
                int(getattr(config, "SOCKET_RATE_LIMIT_PER_MINUTE", 120)),
                60.0,
            )
        except RateLimitExceeded as exc:
            return self.socket_error(
                "rate_limited",
                "Too many socket events. Please retry later.",
                details={"retry_after_seconds": exc.retry_after_seconds},
            )
        return None
