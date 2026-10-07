import unittest
from backend.infrastructure.vision.capture_session import VisionCaptureSession


class VisionCaptureSessionTest(unittest.TestCase):
    def test_lead_in_delay_waits_before_first_capture(self):
        session = VisionCaptureSession()
        start_time = 1000.0
        session.start(source="test", lead_in_sec=0.6, interval_sec=2.0)
        session._started_at = start_time

        # Immediate tick at 0.1s: should return waiting
        action, snapshot = session.tick(now=start_time + 0.1)
        self.assertEqual(action, "waiting")
        self.assertIsNone(snapshot)

        # Tick at 0.59s: still waiting
        action, snapshot = session.tick(now=start_time + 0.59)
        self.assertEqual(action, "waiting")
        self.assertIsNone(snapshot)

        # Tick at 0.61s: lead-in expired, trigger capture
        action, snapshot = session.tick(now=start_time + 0.61)
        self.assertEqual(action, "capture")
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot["attempts"], 1)

        # Tick at 1.0s: interval is 2.0s, elapsed < 2.0s -> waiting
        action, snapshot = session.tick(now=start_time + 1.0)
        self.assertEqual(action, "waiting")

        # Tick at 2.62s: interval expired -> capture #2
        action, snapshot = session.tick(now=start_time + 2.62)
        self.assertEqual(action, "capture")
        self.assertEqual(snapshot["attempts"], 2)


if __name__ == "__main__":
    unittest.main()
