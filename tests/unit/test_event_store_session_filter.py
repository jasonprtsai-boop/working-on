from __future__ import annotations

import tempfile
import time
from pathlib import Path
import unittest

from backend.infrastructure.database.event_store import EventStore


class EventStoreSessionFilterTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "events.db")
        self.store = EventStore(self.db_path)
        now = time.time()
        self.store.save_events(
            [
                {"type": "STATE_UPDATED", "payload": {"fen": "unassigned-null"}, "timestamp": now},
                {
                    "session_id": "",
                    "type": "STATE_UPDATED",
                    "payload": {"fen": "unassigned-empty"},
                    "timestamp": now + 1,
                },
                {
                    "session_id": "session-a",
                    "type": "STATE_UPDATED",
                    "payload": {"fen": "assigned"},
                    "timestamp": now + 2,
                },
            ]
        )

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def test_none_session_filter_returns_all_events(self):
        events = self.store.query_events(session_id=None, event_types=["STATE_UPDATED"])

        self.assertEqual(len(events), 3)
        self.assertEqual(self.store.count_events(session_id=None, event_types=["STATE_UPDATED"]), 3)

    def test_empty_session_filter_returns_only_unassigned_events(self):
        events = self.store.query_events(session_id="", event_types=["STATE_UPDATED"])

        self.assertEqual(len(events), 2)
        self.assertEqual(self.store.count_events(session_id="", event_types=["STATE_UPDATED"]), 2)
        self.assertEqual({event.get("session_id") or "" for event in events}, {""})

    def test_named_session_filter_returns_only_that_session(self):
        events = self.store.query_events(session_id="session-a", event_types=["STATE_UPDATED"])

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["session_id"], "session-a")
        self.assertEqual(self.store.count_events(session_id="session-a", event_types=["STATE_UPDATED"]), 1)


if __name__ == "__main__":
    unittest.main()
