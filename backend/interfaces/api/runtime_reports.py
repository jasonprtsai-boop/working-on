from __future__ import annotations

import time

from backend.events.bus.event_bus import bus
from backend.runtime.contract_schema import normalize_diagnostics_payload


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
