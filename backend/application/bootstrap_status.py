"""Bootstrap status helpers for readiness and diagnostics."""

from typing import Any, Optional, Tuple


BootstrapStatus = dict[str, Any]


def new_bootstrap_status(config: Any) -> BootstrapStatus:
    """Create the mutable status snapshot shared through the container."""
    return {
        "booted": False,
        "ready": False,
        "errors": [],
        "runtime_started": False,
        "engine_registered": False,
        "vision_registered": False,
        "robot_registered": False,
        "robot_connected": False,
        "workers_started": False,
        "workflow_started": False,
        "telemetry_started": False,
        "tmflow_ingest_started": False,
        "persistence_started": False,
        "vision_started": False,
        "vision_fallback": False,
        "vision_fallback_reason": None,
        "vision_mode": "unknown",
        "vision_unavailable": False,
        "vision_runtime_owner": getattr(config, "VISION_RUNTIME_OWNER", "vision_system"),
        "vision_start_error": None,
    }


def record_bootstrap_error(
    bootstrap_status: BootstrapStatus,
    component: str,
    exc: Exception,
    logger: Any,
    level: str = "warning",
) -> None:
    """Append a bootstrap error and mirror it to the project logger."""
    entry = {"component": component, "error": str(exc), "level": level}
    bootstrap_status["errors"].append(entry)
    if level == "error":
        logger.error(f"[Bootstrap] {component} failed: {exc}", exc_info=True)
    else:
        logger.warning(f"[Bootstrap] {component} degraded: {exc}", exc_info=True)


def read_vision_runtime_status(vision_system: Any) -> dict[str, Any]:
    if not hasattr(vision_system, "get_status"):
        return {}
    try:
        return dict(vision_system.get_status() or {})
    except Exception as exc:
        return {"error": str(exc)}


def update_vision_bootstrap_status(
    bootstrap_status: BootstrapStatus,
    vision_system: Any,
    config: Any,
) -> Tuple[dict[str, Any], Optional[Exception]]:
    vision_runtime_status = read_vision_runtime_status(vision_system)
    start_error = None
    fallback_reason = (
        vision_runtime_status.get("fallback_reason")
        or getattr(vision_system, "_fallback_reason", None)
    )
    bootstrap_status["vision_fallback"] = bool(
        vision_runtime_status.get("fallback")
        or getattr(vision_system, "_fallback_from_real_vision", False)
        or fallback_reason
    )
    bootstrap_status["vision_fallback_reason"] = str(fallback_reason) if fallback_reason else None
    bootstrap_status["vision_unavailable"] = bool(
        vision_runtime_status.get("mode") == "unavailable"
        or vision_runtime_status.get("startup_failure")
        or vision_runtime_status.get("available") is False
    )
    bootstrap_status["vision_mode"] = str(
        vision_runtime_status.get("mode")
        or (
            "fallback"
            if bootstrap_status["vision_fallback"]
            else ("simulation" if getattr(config, "FAKE_VISION", False) else "real")
        )
    )
    try:
        bootstrap_status["vision_started"] = bool(vision_system.start())
    except Exception as exc:
        bootstrap_status["vision_started"] = False
        bootstrap_status["vision_start_error"] = str(exc)
        start_error = exc
    if bootstrap_status["vision_unavailable"] and not bootstrap_status["vision_start_error"]:
        bootstrap_status["vision_start_error"] = str(
            vision_runtime_status.get("startup_error") or "vision unavailable"
        )
    return vision_runtime_status, start_error


def vision_diagnostics_payload(
    bootstrap_status: BootstrapStatus,
    config: Any,
    vision_runtime_status: dict[str, Any],
) -> dict[str, Any]:
    status = (
        "UNAVAILABLE"
        if bootstrap_status["vision_unavailable"] or not bootstrap_status["vision_started"]
        else ("FALLBACK" if bootstrap_status["vision_fallback"] else "READY")
    )
    return {
        "vision": {
            "mode": bootstrap_status["vision_mode"],
            "owner": bootstrap_status["vision_runtime_owner"],
            "fallback": bootstrap_status["vision_fallback"],
            "simulation": bool(
                vision_runtime_status.get("simulation") or getattr(config, "FAKE_VISION", False)
            ),
            "available": not bootstrap_status["vision_unavailable"],
            "status": status,
            "fallback_reason": bootstrap_status["vision_fallback_reason"],
            "start_error": bootstrap_status["vision_start_error"],
        }
    }


def is_bootstrap_ready(bootstrap_status: BootstrapStatus, config: Any) -> bool:
    vision_uses_simulation = bool(
        getattr(config, "FAKE_VISION", False)
        or bootstrap_status["vision_fallback"]
        or bootstrap_status["vision_mode"] == "simulation"
    )
    vision_ready = bool(bootstrap_status["vision_started"]) and (
        not vision_uses_simulation or bool(getattr(config, "FAKE_ROBOT", False))
    ) and not bool(bootstrap_status["vision_unavailable"])
    return all(
        [
            bootstrap_status["runtime_started"],
            bootstrap_status["engine_registered"],
            bootstrap_status["vision_registered"],
            bootstrap_status["robot_registered"],
            bootstrap_status["robot_connected"] or getattr(config, "FAKE_ROBOT", False),
            bootstrap_status["workers_started"],
            bootstrap_status["workflow_started"],
            bootstrap_status["persistence_started"],
            vision_ready,
        ]
    )
