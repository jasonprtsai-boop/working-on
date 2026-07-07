from typing import Dict, List, Any
import logging
import time
from backend.events.bus.event_bus import bus
from backend.events.event_types import EventType
from backend.events.models.base_event import BaseEvent

logger = logging.getLogger(__name__)

class TimelineTracer:
    """
    [Observability Layer] High-resolution pipeline profiler.
    Tracks event latency across the system using correlation IDs.
    """
    def __init__(self):
        # Maps trace_id -> List of recorded event milestones
        self._traces: Dict[str, List[Dict[str, Any]]] = {}
        self._max_traces = 100

    def start(self):
        # Subscribe to all events with is_async=True to avoid profiling overhead
        bus.subscribe_all(self.on_event, is_async=True)

    def on_event(self, event: Any):
        if not hasattr(event, "trace_id") or not event.trace_id:
            return

        trace_id = event.trace_id
        timestamp = getattr(event, "timestamp", time.time())
        event_type = getattr(event, "event_type", "unknown")

        if hasattr(event_type, "value"):
            event_type = event_type.value

        with self._lock_for_trace(trace_id):
            if trace_id not in self._traces:
                self._traces[trace_id] = []
                # Auto-cleanup old traces
                if len(self._traces) > self._max_traces:
                    oldest = next(iter(self._traces))
                    del self._traces[oldest]

            milestones = self._traces[trace_id]

            # Record the milestone
            milestones.append({
                "type": event_type,
                "source": getattr(event, "source", "unknown"),
                "timestamp": timestamp,
                "delta": (timestamp - milestones[0]["timestamp"]) if milestones else 0.0
            })

            # If it's a completion event, broadcast the full timeline
            if self._is_terminal_event(event_type):
                self._broadcast_timeline(trace_id, milestones)

    def _lock_for_trace(self, trace_id):
        # RLock prevents recursive diagnostics broadcasts from blocking the event bus.
        import threading
        if not hasattr(self, "_global_lock"):
            self._global_lock = threading.RLock()
        return self._global_lock

    def _is_terminal_event(self, event_type: str) -> bool:
        return event_type in [
            EventType.ROBOT_MOVE_COMPLETED.value,
            EventType.ENGINE_ANALYSIS_COMPLETED.value,
            EventType.SYSTEM_ERROR.value
        ]

    def _broadcast_timeline(self, trace_id: str, milestones: List[Dict[str, Any]]):
        try:
            # Send to UI for waterfall rendering
            bus.publish(BaseEvent.create(
                event_type=EventType.DIAGNOSTICS_UPDATED,
                source="timeline_tracer",
                payload={
                    "telemetry": {
                        "trace_id": trace_id,
                        "waterfall": milestones,
                        "total_latency_ms": (milestones[-1]["timestamp"] - milestones[0]["timestamp"]) * 1000
                    }
                }
            ))
        except Exception:
            logger.warning(
                "[TimelineTracer] failed to publish waterfall trace_id=%s",
                trace_id,
                exc_info=True,
            )

timeline_tracer = TimelineTracer()
