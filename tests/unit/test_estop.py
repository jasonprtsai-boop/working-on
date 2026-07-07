import unittest
from unittest.mock import MagicMock, patch

from backend.application.services.estop import EStop


class FakeSocketIO:
    def __init__(self):
        self.emitted = []

    def emit(self, event, payload):
        self.emitted.append((event, payload))


class TestEStop(unittest.TestCase):
    def test_trigger_and_reset_emit_lock_transitions(self):
        controller = EStop()
        socketio = FakeSocketIO()
        controller.register_socketio(socketio)
        controller._publish_event = MagicMock()

        with patch("backend.state.store.state_store.state_store.dispatch") as dispatch:
            controller.trigger("unit-test")
            controller.reset()

        lock_payloads = [payload for event, payload in socketio.emitted if event == "ui_lock"]
        self.assertEqual(lock_payloads[0]["locked"], True)
        self.assertEqual(lock_payloads[-1]["locked"], False)
        self.assertFalse(controller.is_triggered)
        self.assertFalse(controller.GLOBAL_STOP)
        snapshot = controller.snapshot()
        self.assertIn("steps", snapshot)
        self.assertTrue(any(step.get("step") == "robot_hardware_stop" for step in snapshot["steps"]))
        self.assertIn("last_reset_at", snapshot)
        self.assertGreaterEqual(dispatch.call_count, 2)


if __name__ == "__main__":
    unittest.main()
