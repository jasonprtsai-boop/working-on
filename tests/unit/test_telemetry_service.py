import unittest

from backend.events.models.base_event import BaseEvent
from backend.observability.telemetry import TelemetryService


class TestTelemetryService(unittest.TestCase):
    def test_normalizes_base_event_into_stable_schema(self):
        service = TelemetryService(max_events=5)
        event = BaseEvent.create(
            event_type="VISION.FRAME_PROCESSED",
            source="vision_worker",
            payload={
                "latency_ms": 12.5,
                "detections": [{"class_name": "red_rook"}],
                "detections_count": 1,
            },
            metadata={"span_id": "span-1"},
        )

        normalized = service.normalize_event(event)

        self.assertEqual(normalized.module, "vision")
        self.assertEqual(normalized.source, "vision_worker")
        self.assertEqual(normalized.status, "processing")
        self.assertEqual(normalized.latency_ms, 12.5)
        self.assertEqual(normalized.span_id, "span-1")
        self.assertNotIn("detections", normalized.data)
        self.assertEqual(normalized.data["detections_count"], 1)

    def test_snapshot_is_bounded_and_contains_pipeline_topology(self):
        service = TelemetryService(max_events=2, max_errors=3)
        for index in range(3):
            service.record_event(
                BaseEvent.create(
                    event_type="ENGINE_ANALYSIS_COMPLETED",
                    source="engine_worker",
                    payload={"best_move": f"m{index}", "latency_ms": 5 + index},
                    trace_id="trace-a",
                )
            )
        service.record_event(
            BaseEvent.create(
                event_type="ROBOT_ERROR",
                source="robot_worker",
                payload={"error": "blocked"},
                trace_id="trace-a",
            )
        )

        snapshot = service.snapshot(
            queue_stats={"robot": {"size": 1, "maxsize": 10, "full": False}},
            worker_status={"engine": {"status": "ENABLED"}},
        )

        self.assertEqual(len(snapshot["telemetry"]["recent_events"]), 2)
        self.assertGreaterEqual(snapshot["telemetry"]["dropped_events"], 2)
        self.assertEqual(snapshot["pipeline"]["active_trace_id"], "trace-a")
        self.assertTrue(snapshot["pipeline"]["timeline"])
        self.assertIn("nodes", snapshot["topology"])
        self.assertIn("edges", snapshot["topology"])
        self.assertTrue(snapshot["telemetry"]["errors"])
        self.assertNotIn("data", snapshot["telemetry"]["recent_events"][-1])
        self.assertIn("data", snapshot["telemetry"]["errors"][-1])

    def test_snapshot_limits_can_disable_event_lists(self):
        service = TelemetryService(max_events=5)
        service.record_event(
            BaseEvent.create(
                event_type="SYSTEM_ERROR",
                source="unit",
                payload={"error": "boom"},
                trace_id="trace-b",
            )
        )

        snapshot = service.snapshot(
            recent_events_limit=0,
            errors_limit=0,
            trace_events_limit=0,
        )

        self.assertEqual(snapshot["telemetry"]["recent_events"], [])
        self.assertEqual(snapshot["telemetry"]["errors"], [])
        self.assertEqual(snapshot["pipeline"]["timeline"], [])

    def test_topology_reports_active_blocked_and_offline_states(self):
        service = TelemetryService(max_events=5)
        service.record_event(
            BaseEvent.create(
                event_type="ENGINE_ANALYSIS_STARTED",
                source="engine_worker",
                payload={"latency_ms": 3},
                trace_id="trace-c",
            )
        )
        service.record_event(
            BaseEvent.create(
                event_type="ROBOT_DISCONNECTED",
                source="robot_worker",
                payload={"message": "serial offline"},
                trace_id="trace-c",
            )
        )

        snapshot = service.snapshot(
            queue_stats={"robot": {"size": 1, "maxsize": 10, "full": False, "blocked": True}},
            worker_status={"robot": {"status": "STOPPED"}},
        )

        nodes = {node["id"]: node for node in snapshot["topology"]["nodes"]}
        edges = {edge["id"]: edge for edge in snapshot["topology"]["edges"]}
        self.assertEqual(nodes["robot"]["status"], "offline")
        self.assertEqual(nodes["queue"]["status"], "blocked")
        self.assertEqual(edges["engine_robot"]["status"], "offline")
        self.assertEqual(edges["queue_robot"]["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
