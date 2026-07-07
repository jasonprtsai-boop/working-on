from __future__ import annotations

import threading
import time
from collections import OrderedDict, deque
from typing import Any, Deque, Dict, List, Optional

from pydantic import BaseModel, Field

from backend.events.bus.event_bus import bus


class TelemetryEvent(BaseModel):
    """Stable, compact event shape for the observability dashboard."""

    event_id: str = ""
    trace_id: str = ""
    timestamp: float = Field(default_factory=time.time)
    source: str = ""
    module: str = "system"
    event_type: str = "UNKNOWN"
    status: str = "idle"
    severity: str = "info"
    latency_ms: Optional[float] = None
    span_id: Optional[str] = None
    parent_span_id: Optional[str] = None
    message: str = ""
    data: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TelemetryService:
    """
    Low-overhead EventBus observer.

    It keeps bounded in-memory summaries only. It never writes to disk and never
    publishes per-event socket traffic, so observability cannot backpressure the
    robot, engine, or vision pipeline.
    """

    MODULE_LABELS = OrderedDict(
        [
            ("vision", "Vision"),
            ("engine", "AI Engine"),
            ("robot", "Robot"),
            ("state", "Game State"),
            ("queue", "Queues"),
            ("socket", "Socket.IO"),
            ("storage", "Storage"),
            ("health", "Health"),
        ]
    )

    EDGES = [
        ("vision_engine", "vision", "engine", "Frame to inference"),
        ("engine_robot", "engine", "robot", "Move command"),
        ("robot_state", "robot", "state", "Execution result"),
        ("state_socket", "state", "socket", "State sync"),
        ("health_socket", "health", "socket", "Diagnostics"),
        ("queue_robot", "queue", "robot", "Command queue"),
        ("state_storage", "state", "storage", "Persistence"),
    ]

    def __init__(
        self,
        max_events: int = 300,
        max_errors: int = 80,
        max_traces: int = 40,
        max_trace_events: int = 32,
        snapshot_events: int = 80,
        snapshot_errors: int = 25,
        snapshot_trace_events: int = 24,
    ):
        self.max_events = int(max_events)
        self.max_errors = int(max_errors)
        self.max_traces = int(max_traces)
        self.max_trace_events = int(max_trace_events)
        self.snapshot_events = int(snapshot_events)
        self.snapshot_errors = int(snapshot_errors)
        self.snapshot_trace_events = int(snapshot_trace_events)
        self._events: Deque[TelemetryEvent] = deque(maxlen=self.max_events)
        self._errors: Deque[TelemetryEvent] = deque(maxlen=self.max_errors)
        self._traces: "OrderedDict[str, Deque[TelemetryEvent]]" = OrderedDict()
        self._nodes = {
            node_id: self._new_node(node_id, label)
            for node_id, label in self.MODULE_LABELS.items()
        }
        self._edge_activity: Dict[str, Dict[str, Any]] = {
            edge_id: {"last_event_at": 0.0, "status": "idle", "last_event": ""}
            for edge_id, _source, _target, _label in self.EDGES
        }
        self._lock = threading.RLock()
        self._started = False
        self._dropped_events = 0
        self._recorded_events = 0
        self._active_trace_id = ""

    def start(self) -> None:
        if self._started:
            return
        bus.subscribe_all(
            self.record_event,
            key="observability.telemetry",
            replace=True,
            is_async=True,
        )
        self._started = True

    def record_event(self, event: Any) -> None:
        telemetry_event = self.normalize_event(event)
        with self._lock:
            if len(self._events) >= self.max_events:
                self._dropped_events += 1
            self._events.append(telemetry_event)
            self._recorded_events += 1

            if telemetry_event.severity in {"warning", "error"} or telemetry_event.status == "error":
                self._errors.append(telemetry_event)

            self._update_trace(telemetry_event)
            self._update_node(telemetry_event)
            self._update_edge(telemetry_event)

    def normalize_event(self, event: Any) -> TelemetryEvent:
        event_type = self._event_key(event)
        payload = getattr(event, "payload", {}) if hasattr(event, "payload") else {}
        if not isinstance(payload, dict):
            payload = {}
        metadata = getattr(event, "metadata", {}) if hasattr(event, "metadata") else {}
        if not isinstance(metadata, dict):
            metadata = {}

        module = self._module_for(event_type, getattr(event, "source", ""), payload, metadata)
        status = self._status_for(event_type, payload, metadata)
        severity = self._severity_for(event_type, payload, metadata, status)
        message = self._message_for(event_type, payload)

        return TelemetryEvent(
            event_id=str(getattr(event, "event_id", "")),
            trace_id=str(getattr(event, "trace_id", "") or payload.get("trace_id", "")),
            timestamp=float(getattr(event, "timestamp", time.time()) or time.time()),
            source=str(getattr(event, "source", "") or payload.get("source", "")),
            module=module,
            event_type=event_type,
            status=status,
            severity=severity,
            latency_ms=self._first_number(payload, metadata, ("latency_ms", "latency", "duration_ms")),
            span_id=self._first_text(payload, metadata, ("span_id",)),
            parent_span_id=self._first_text(payload, metadata, ("parent_span_id",)),
            message=message,
            data=self._compact_payload(payload),
            metadata=self._compact_payload(metadata, max_items=6),
        )

    def snapshot(
        self,
        queue_stats: Optional[dict] = None,
        worker_status: Optional[dict] = None,
        *,
        recent_events_limit: Optional[int] = None,
        errors_limit: Optional[int] = None,
        trace_events_limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        now = time.time()
        queue_stats = queue_stats if isinstance(queue_stats, dict) else {}
        worker_status = worker_status if isinstance(worker_status, dict) else {}
        recent_events_limit = self._bounded_limit(recent_events_limit, self.snapshot_events, self.max_events)
        errors_limit = self._bounded_limit(errors_limit, self.snapshot_errors, self.max_errors)
        trace_events_limit = self._bounded_limit(trace_events_limit, self.snapshot_trace_events, self.max_trace_events)

        with self._lock:
            # Calculate Performance Analytics
            now_ms = time.time() * 1000
            total_events = len(self._events)
            error_count = len([e for e in self._events if e.status == "error"])
            error_rate = round(error_count / total_events, 4) if total_events > 0 else 0.0

            latencies = [e.latency_ms for e in self._events if e.latency_ms is not None]
            latencies.sort()
            p95_latency = latencies[int(len(latencies) * 0.95)] if latencies else 0.0

            telemetry = {
                "enabled": True,
                "bounded": True,
                "max_events": self.max_events,
                "snapshot_events": recent_events_limit,
                "recorded_events": self._recorded_events,
                "dropped_events": self._dropped_events,
                "error_rate": error_rate,
                "p95_latency_ms": p95_latency,
                "recent_events": [self._dump_event(e) for e in self._tail(self._events, recent_events_limit)],
                "errors": [self._dump_event(e, include_data=True) for e in self._tail(self._errors, errors_limit)],
                "active_trace_id": self._active_trace_id,
            }
            pipeline = self._pipeline_snapshot_locked(now, trace_events_limit=trace_events_limit)
            topology = self._topology_snapshot_locked(now, queue_stats, worker_status)
            return {
                "telemetry": telemetry,
                "pipeline": pipeline,
                "topology": topology,
            }

    def _update_trace(self, event: TelemetryEvent) -> None:
        if not event.trace_id:
            return
        self._active_trace_id = event.trace_id
        if event.trace_id not in self._traces:
            self._traces[event.trace_id] = deque(maxlen=self.max_trace_events)
        self._traces[event.trace_id].append(event)
        self._traces.move_to_end(event.trace_id)
        while len(self._traces) > self.max_traces:
            self._traces.popitem(last=False)

    def _update_node(self, event: TelemetryEvent) -> None:
        module = event.module if event.module in self._nodes else "state"
        node = self._nodes[module]
        node.update(
            {
                "status": event.status,
                "severity": event.severity,
                "last_event": event.event_type,
                "last_event_at": event.timestamp,
                "latency_ms": event.latency_ms,
                "message": event.message,
            }
        )

    def _update_edge(self, event: TelemetryEvent) -> None:
        edge_ids = []
        if event.module == "vision":
            edge_ids.append("vision_engine")
        elif event.module == "engine":
            edge_ids.append("engine_robot")
        elif event.module == "robot":
            edge_ids.extend(["engine_robot", "robot_state", "queue_robot"])
        elif event.module == "state":
            edge_ids.extend(["robot_state", "state_socket", "state_storage"])
        elif event.module in {"health", "queue"}:
            edge_ids.append("health_socket")
            if event.module == "queue":
                edge_ids.append("queue_robot")
        elif event.module == "socket":
            edge_ids.append("state_socket")

        status = event.status if event.status in {"error", "blocked", "offline"} else "active"
        for edge_id in edge_ids:
            edge = self._edge_activity.get(edge_id)
            if edge is not None:
                edge.update({
                    "last_event_at": event.timestamp,
                    "status": status,
                    "last_event": event.event_type,
                    "latency_ms": event.latency_ms,
                })

    def _pipeline_snapshot_locked(self, now: float, *, trace_events_limit: int) -> Dict[str, Any]:
        active_events = list(self._traces.get(self._active_trace_id, [])) if self._active_trace_id else []
        status = "idle"
        total_latency_ms = 0.0
        if active_events:
            last_event = active_events[-1]
            if last_event.status == "error":
                status = "error"
            elif now - last_event.timestamp <= 10.0:
                status = "running"
            else:
                status = "idle"
            total_latency_ms = max(0.0, (active_events[-1].timestamp - active_events[0].timestamp) * 1000.0)
        return {
            "active_trace_id": self._active_trace_id,
            "status": status,
            "total_latency_ms": total_latency_ms,
            "timeline": [self._dump_event(e) for e in self._tail(active_events, trace_events_limit)],
            "updated_at": now,
        }

    def _topology_snapshot_locked(self, now: float, queue_stats: dict, worker_status: dict) -> Dict[str, Any]:
        nodes = [dict(node) for node in self._nodes.values()]
        node_by_id = {node["id"]: node for node in nodes}

        queue_node = node_by_id.get("queue")
        if queue_node is not None and queue_stats:
            queue_full = any(bool(info.get("full")) for info in queue_stats.values() if isinstance(info, dict))
            queue_blocked = any(bool(info.get("blocked")) for info in queue_stats.values() if isinstance(info, dict))
            queue_size = sum(int(info.get("size", 0) or 0) for info in queue_stats.values() if isinstance(info, dict))
            queue_node.update(
                {
                    "status": "blocked" if queue_blocked else ("warning" if queue_full else ("processing" if queue_size else queue_node.get("status", "idle"))),
                    "message": f"{queue_size} queued",
                    "queue_size": queue_size,
                }
            )

        health_node = node_by_id.get("health")
        if health_node is not None and worker_status:
            has_error = any(
                bool(info.get("last_error")) or str(info.get("status", "")).upper() in {"ERROR", "FAILED"}
                for info in worker_status.values()
                if isinstance(info, dict)
            )
            health_node["status"] = "warning" if has_error else "running"
            health_node["message"] = f"{len(worker_status)} workers"

        edges: List[Dict[str, Any]] = []
        for edge_id, source, target, label in self.EDGES:
            activity = self._edge_activity.get(edge_id, {})
            age = now - float(activity.get("last_event_at") or 0.0)
            status = activity.get("status") if age <= 20.0 else "idle"
            if source == "queue" or target == "queue" or edge_id == "queue_robot":
                if any(bool(info.get("blocked")) for info in queue_stats.values() if isinstance(info, dict)):
                    status = "blocked"
            edges.append(
                {
                    "id": edge_id,
                    "source": source,
                    "target": target,
                    "label": label,
                    "status": status or "idle",
                    "last_event": activity.get("last_event", ""),
                    "last_event_at": activity.get("last_event_at", 0.0),
                    "latency_ms": activity.get("latency_ms"),
                }
            )

        return {
            "nodes": nodes,
            "edges": edges,
            "active_trace_id": self._active_trace_id,
            "updated_at": now,
        }

    def _new_node(self, node_id: str, label: str) -> Dict[str, Any]:
        return {
            "id": node_id,
            "label": label,
            "kind": "service",
            "status": "idle",
            "severity": "info",
            "last_event": "",
            "last_event_at": 0.0,
            "latency_ms": None,
            "message": "",
        }

    def _dump_event(self, event: TelemetryEvent, *, include_data: bool = False) -> Dict[str, Any]:
        item = event.model_dump(exclude_none=True, exclude={"data", "metadata"})
        if include_data and event.data:
            item["data"] = event.data
        return item

    def _bounded_limit(self, value: Optional[int], default: int, maximum: int) -> int:
        try:
            limit = int(value if value is not None else default)
        except (TypeError, ValueError):
            limit = default
        return max(0, min(limit, maximum))

    def _tail(self, items: Any, limit: int) -> List[TelemetryEvent]:
        if limit <= 0:
            return []
        return list(items)[-limit:]

    def _event_key(self, event: Any) -> str:
        key = getattr(event, "event_type", None)
        if key is None and isinstance(event, dict):
            key = event.get("type") or event.get("event_type")
        return str(key.value if hasattr(key, "value") else key or "UNKNOWN")

    def _module_for(self, event_type: str, source: str, payload: dict, metadata: dict) -> str:
        explicit = payload.get("module") or metadata.get("module") or metadata.get("telemetry_module")
        if explicit:
            normalized = str(explicit).strip().lower().replace("_", "-")
            return self._known_module(normalized)

        upper = event_type.upper()
        source_text = str(source or "").lower()
        if upper.startswith("VISION") or "vision" in source_text:
            return "vision"
        if upper.startswith("ENGINE") or "engine" in source_text or "pikafish" in source_text:
            return "engine"
        if upper.startswith("ROBOT") or "robot" in source_text:
            return "robot"
        if upper.startswith("STATE") or upper.startswith("BOARD") or upper.startswith("GAME"):
            return "state"
        if "QUEUE" in upper or "queue" in source_text:
            return "queue"
        if "SOCKET" in upper or "socket" in source_text:
            return "socket"
        if "PERSIST" in upper or "storage" in source_text or "database" in source_text:
            return "storage"
        if upper.startswith("DIAGNOSTICS") or upper == "HEARTBEAT" or "monitor" in source_text or "health" in source_text:
            return "health"
        return "state"

    def _known_module(self, value: str) -> str:
        value = value.replace("-", "_")
        aliases = {
            "ai": "engine",
            "ai_engine": "engine",
            "gamestate": "state",
            "game_state": "state",
            "eventbus": "state",
            "event_bus": "state",
            "websocket": "socket",
            "socketio": "socket",
            "metrics": "health",
        }
        return aliases.get(value, value if value in self.MODULE_LABELS else "state")

    def _status_for(self, event_type: str, payload: dict, metadata: dict) -> str:
        explicit = payload.get("status") or metadata.get("status")
        if explicit:
            return self._normalize_status(explicit)
        upper = event_type.upper()
        if any(token in upper for token in ("ERROR", "EXCEPTION", "TIMEOUT", "FAILED")):
            return "error"
        if any(token in upper for token in ("OFFLINE", "DISCONNECTED")):
            return "offline"
        if "BLOCKED" in upper:
            return "blocked"
        if any(token in upper for token in ("WARNING", "DEGRADED")):
            return "warning"
        if any(token in upper for token in ("COMPLETED", "FINISHED", "READY", "CONNECTED")):
            return "success"
        if any(token in upper for token in ("STARTED", "REQUESTED", "MOVING", "ANALYZING", "RUNNING")):
            return "running"
        if any(token in upper for token in ("FRAME", "DETECTED", "UPDATED", "SYNCHRONIZED")):
            return "processing"
        return "idle"

    def _severity_for(self, event_type: str, payload: dict, metadata: dict, status: str) -> str:
        explicit = payload.get("severity") or metadata.get("severity") or payload.get("level")
        if explicit:
            value = str(explicit).strip().lower()
            if value in {"debug", "info", "warning", "error", "critical"}:
                return "error" if value == "critical" else value
        if status == "error":
            return "error"
        if status in {"warning", "blocked", "offline"}:
            return "warning"
        return "info"

    def _normalize_status(self, value: Any) -> str:
        text = str(value or "").strip().lower()
        aliases = {
            "ok": "success",
            "ready": "success",
            "connected": "success",
            "done": "success",
            "finished": "success",
            "busy": "running",
            "active": "running",
            "enabled": "running",
            "starting": "running",
            "stopping": "running",
            "stopped": "offline",
            "disabled": "offline",
            "degraded": "warning",
            "warn": "warning",
            "blocked": "blocked",
            "failed": "error",
            "offline": "offline",
            "disconnected": "offline",
        }
        return aliases.get(text, text if text in {"idle", "running", "processing", "success", "warning", "error", "active", "blocked", "offline"} else "idle")

    def _message_for(self, event_type: str, payload: dict) -> str:
        for key in ("message", "error", "text", "reason", "handler"):
            value = payload.get(key)
            if value:
                return self._clip(value, 180)
        return event_type

    def _compact_payload(self, payload: dict, max_items: int = 10) -> Dict[str, Any]:
        interesting = (
            "status",
            "error",
            "message",
            "best_move",
            "bestmove",
            "depth",
            "fps",
            "latency_ms",
            "latency",
            "queue_size",
            "connected",
            "busy",
            "mode",
            "fallback",
            "detections_count",
            "avg_confidence",
            "min_confidence",
            "confidence",
            "action",
            "handler",
        )
        compact: Dict[str, Any] = {}
        for key in interesting:
            if key in payload:
                compact[key] = self._compact_value(payload[key])
        for key, value in payload.items():
            if len(compact) >= max_items:
                break
            if key in compact or key in {"detections", "board_state", "image", "frame", "raw", "payload"}:
                continue
            if self._is_scalar(value):
                compact[key] = self._compact_value(value)
        return compact

    def _compact_value(self, value: Any) -> Any:
        if isinstance(value, str):
            return self._clip(value, 180)
        if self._is_scalar(value):
            return value
        if isinstance(value, list):
            return {"count": len(value)}
        if isinstance(value, dict):
            return {"keys": list(value.keys())[:8], "count": len(value)}
        return self._clip(value, 120)

    def _clip(self, value: Any, limit: int) -> str:
        text = str(value)
        return text if len(text) <= limit else f"{text[:limit]}..."

    def _is_scalar(self, value: Any) -> bool:
        return value is None or isinstance(value, (str, int, float, bool))

    def _first_number(self, payload: dict, metadata: dict, keys: tuple[str, ...]) -> Optional[float]:
        for source in (payload, metadata):
            for key in keys:
                try:
                    if source.get(key) is not None:
                        return float(source.get(key))
                except (TypeError, ValueError):
                    continue
        return None

    def _first_text(self, payload: dict, metadata: dict, keys: tuple[str, ...]) -> Optional[str]:
        for source in (payload, metadata):
            for key in keys:
                value = source.get(key)
                if value:
                    return str(value)
        return None


telemetry_service = TelemetryService()
