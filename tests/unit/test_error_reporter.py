import unittest
from unittest.mock import patch

from backend.events.event_types import EventType
from backend.observability.error_reporter import (
    publish_error_diagnostic,
    reset_error_reporter_state,
)


class TestErrorReporter(unittest.TestCase):
    def setUp(self):
        reset_error_reporter_state()

    def test_publish_error_diagnostic_uses_stable_diagnostics_contract(self):
        published = []

        with patch("backend.observability.error_reporter.bus.publish", side_effect=published.append):
            emitted = publish_error_diagnostic(
                source="unit",
                module="robot",
                code="robot_stop_failed",
                message="motor stop failed",
                severity="error",
                trace_id="trace-1",
                details={"endpoint": "/api/estop/trigger"},
            )

        self.assertTrue(emitted)
        self.assertEqual(len(published), 1)
        event = published[0]
        self.assertEqual(event.event_type, EventType.DIAGNOSTICS_UPDATED)
        self.assertEqual(event.trace_id, "trace-1")
        self.assertEqual(event.metadata["module"], "robot")
        self.assertEqual(event.metadata["severity"], "error")
        self.assertEqual(event.payload["robot"]["last_error"]["code"], "robot_stop_failed")
        self.assertEqual(event.payload["telemetry"]["errors"][0]["message"], "motor stop failed")
        self.assertIn("runtime", event.payload)

    def test_publish_error_diagnostic_is_throttled(self):
        published = []

        with patch("backend.observability.error_reporter.bus.publish", side_effect=published.append):
            first = publish_error_diagnostic(
                source="unit",
                module="health",
                code="same_error",
                message="same message",
                throttle_seconds=60.0,
            )
            second = publish_error_diagnostic(
                source="unit",
                module="health",
                code="same_error",
                message="same message",
                throttle_seconds=60.0,
            )

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(len(published), 1)


if __name__ == "__main__":
    unittest.main()
