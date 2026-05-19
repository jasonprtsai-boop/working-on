import os
import tempfile
import unittest

from backend.events.models.base_event import BaseEvent
from backend.events.store.event_store import EventStore
from backend.infrastructure.database.event_store import EventStore as SqliteEventStore


class TestEventStoreAdapter(unittest.TestCase):
    def test_append_and_history_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "events.db")
            store = EventStore(db_path=db_path)
            event = BaseEvent.create(
                event_type="TEST.EVENT",
                source="unit_test",
                payload={"value": 42},
                trace_id="trace-roundtrip",
            )

            store.append(event)
            history = store.get_history()

            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["type"], "TEST.EVENT")
            self.assertEqual(history[0]["payload"], {"value": 42})
            self.assertEqual(history[0]["trace_id"], "trace-roundtrip")

    def test_sqlite_store_auto_assigns_sequence_without_replacing_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "events.db")
            store = SqliteEventStore(db_path=db_path)
            self.assertEqual(store.get_schema_version(), 2)

            store.save_event({"session_id": "s1", "trace_id": "t1", "type": "A", "payload": {"v": 1}, "timestamp": 1.0})
            store.save_event({"session_id": "s1", "trace_id": "t2", "type": "B", "payload": {"v": 2}, "timestamp": 2.0})

            history = store.get_events("s1")
            self.assertEqual([event["sequence_id"] for event in history], [1, 2])
            self.assertEqual([event["type"] for event in history], ["A", "B"])

            store.save_event({
                "sequence_id": 1,
                "session_id": "s1",
                "trace_id": "legacy-duplicate-sequence",
                "type": "LEGACY_SEQUENCE_IGNORED",
                "payload": {},
                "timestamp": 3.0,
            })

            history = store.get_events("s1")
            self.assertEqual([event["sequence_id"] for event in history], [1, 2, 3])
            self.assertEqual([event["type"] for event in history], ["A", "B", "LEGACY_SEQUENCE_IGNORED"])

    def test_query_events_filters_by_trace_session_and_type(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "events.db")
            store = SqliteEventStore(db_path=db_path)
            store.save_events([
                {"session_id": "s1", "trace_id": "t1", "type": "STATE_UPDATE", "payload": {"v": 1}, "timestamp": 1.0},
                {"session_id": "s1", "trace_id": "t2", "type": "ENGINE.INFO_UPDATED", "payload": {"v": 2}, "timestamp": 2.0},
                {"session_id": "s2", "trace_id": "t1", "type": "STATE_UPDATE", "payload": {"v": 3}, "timestamp": 3.0},
            ])

            by_trace = store.query_events(trace_id="t1")
            self.assertEqual([event["payload"]["v"] for event in by_trace], [1, 3])

            state_s1 = store.query_events(session_id="s1", event_types=("STATE_UPDATE",))
            self.assertEqual(len(state_s1), 1)
            self.assertEqual(state_s1[0]["payload"], {"v": 1})

    def test_adapter_load_replay_uses_type_filter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "events.db")
            store = EventStore(db_path=db_path)
            store.append({"session_id": "s1", "trace_id": "t1", "type": "STATE_UPDATE", "payload": {"v": 1}, "timestamp": 1.0})
            store.append({"session_id": "s1", "trace_id": "t2", "type": "OTHER", "payload": {"v": 2}, "timestamp": 2.0})

            events = store.load_replay(session_id="s1", event_types=("STATE_UPDATE",))

            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["type"], "STATE_UPDATE")


if __name__ == "__main__":
    unittest.main()
