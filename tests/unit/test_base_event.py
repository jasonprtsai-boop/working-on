import unittest

from backend.events.models.base_event import BaseEvent


class TestBaseEvent(unittest.TestCase):
    def test_to_dict_exposes_runtime_and_persistence_fields(self):
        event = BaseEvent.create(
            event_type="TEST.EVENT",
            source="unit_test",
            payload={"ok": True},
            trace_id="trace-123",
        )

        payload = event.to_dict()
        self.assertEqual(payload["type"], "TEST.EVENT")
        self.assertEqual(payload["event_type"], "TEST.EVENT")
        self.assertEqual(payload["trace_id"], "trace-123")
        self.assertEqual(payload["payload"], {"ok": True})


if __name__ == "__main__":
    unittest.main()
