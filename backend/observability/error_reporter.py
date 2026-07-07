from __future__ import annotations

import logging
import threading
import time
from typing import Any, Mapping

from backend.events.bus.event_bus import bus
from backend.events.event_types import EventType
from backend.events.models.base_event import BaseEvent
from backend.runtime.contract_schema import normalize_diagnostics_payload

logger = logging.getLogger(__name__)

_LOCK = threading.RLock()
_GUARD = threading.local()
_LAST_EMITTED: dict[tuple[str, str, str], float] = {}

_MODULE_ROOTS = {
    "vision",
    "engine",
    "robot",
    "health",
    "control",
    "event_bus",
    "persistence",
    "async_runtime",
}


def reset_error_reporter_state() -> None:
    """Clear reporter throttling for isolated tests."""
    with _LOCK:
        _LAST_EMITTED.clear()


def publish_error_diagnostic(
    *,
    source: str,
    code: str,
    message: str,
    module: str = "health",
    severity: str = "error",
    status: str | None = None,
    trace_id: str | None = None,
    recoverable: bool = True,
    details: Mapping[str, Any] | None = None,
    throttle_seconds: float = 5.0,
) -> bool:
    """
    Publish a compact DIAGNOSTICS update for failures that should be visible in
    Mission Control without turning every transient 4xx into EventBus traffic.
    """
    source = _clip(source or "unknown", 80)
    code = _clip(code or "unknown_error", 80)
    message = _clip(message or code, 240)
    module = _normalize_module(module)
    severity = _normalize_severity(severity)
    status = status or ("error" if severity == "error" else "warning")

    if getattr(_GUARD, "active", False):
        return False

    key = (source, code, message[:120])
    now = time.time()
    with _LOCK:
        last_at = _LAST_EMITTED.get(key)
        if last_at is not None and now - last_at < max(0.0, float(throttle_seconds)):
            return False
        _LAST_EMITTED[key] = now

    error = {
        "timestamp": now,
        "source": source,
        "module": module,
        "code": code,
        "message": message,
        "severity": severity,
        "status": status,
        "recoverable": bool(recoverable),
        "trace_id": trace_id or "",
        "details": _compact_details(details or {}),
    }
    payload: dict[str, Any] = {
        "module": module,
        "status": status,
        "severity": severity,
        "code": code,
        "message": message,
        "error": message,
        "telemetry": {
            "last_error": error,
            "errors": [error],
        },
        "ui": {
            "last_error": error,
        },
    }
    if module in _MODULE_ROOTS:
        payload[module] = {
            "status": status,
            "severity": severity,
            "error": message,
            "last_error": error,
        }

    try:
        _GUARD.active = True
        bus.publish(
            BaseEvent.create(
                event_type=EventType.DIAGNOSTICS_UPDATED,
                source=source,
                payload=normalize_diagnostics_payload(payload),
                trace_id=trace_id,
                metadata={"module": module, "severity": severity, "status": status, "code": code},
            )
        )
        return True
    except Exception:
        logger.warning("[ErrorReporter] failed to publish diagnostics: %s", code, exc_info=True)
        return False
    finally:
        _GUARD.active = False


def _normalize_module(value: str) -> str:
    text = str(value or "health").strip().lower().replace("-", "_")
    aliases = {
        "api": "health",
        "rest": "health",
        "rest_api": "health",
        "eventbus": "event_bus",
        "storage": "persistence",
        "runtime": "async_runtime",
        "estop": "control",
    }
    return aliases.get(text, text or "health")


def _normalize_severity(value: str) -> str:
    text = str(value or "error").strip().lower()
    if text == "critical":
        return "error"
    return text if text in {"debug", "info", "warning", "error"} else "error"


def _compact_details(details: Mapping[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key, value in list(details.items())[:12]:
        if isinstance(value, (str, int, float, bool)) or value is None:
            compact[str(key)] = _clip(value, 180) if isinstance(value, str) else value
        elif isinstance(value, list):
            compact[str(key)] = {"count": len(value)}
        elif isinstance(value, dict):
            compact[str(key)] = {"keys": list(value.keys())[:8], "count": len(value)}
        else:
            compact[str(key)] = _clip(value, 120)
    return compact


def _clip(value: Any, limit: int) -> str:
    text = str(value)
    return text if len(text) <= limit else f"{text[:limit]}..."
