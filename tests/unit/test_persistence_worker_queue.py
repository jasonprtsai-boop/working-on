import unittest
from unittest.mock import patch, MagicMock
from backend.runtime.workers.persistence_worker import PersistenceWorker
from backend.events.event_types import EventType

class TestPersistenceWorkerQueue(unittest.TestCase):
    @patch("backend.runtime.workers.persistence_worker.config")
    @patch("backend.runtime.workers.persistence_worker.bus")
    def test_persistence_worker_emits_drop_diagnostics(self, mock_bus, mock_config):
        mock_config.PERSISTENCE_QUEUE_SIZE = 1
        mock_config.PERSISTENCE_DROP_WARNING_THRESHOLD = 1
        mock_config.PERSISTENCE_DROP_WARNING_INTERVAL_SEC = 0.0
        mock_config.DB_PATH = ":memory:"

        worker = PersistenceWorker()
        worker._queue.maxsize = 1

        # Fill the queue
        worker._on_event({"type": "EVENT_1"})
        self.assertEqual(worker._queue.qsize(), 1)
        self.assertEqual(worker._dropped_events, 0)
        self.assertEqual(mock_bus.publish.call_count, 0)

        # Trigger drop
        worker._on_event({"type": "EVENT_2"})
        self.assertEqual(worker._queue.qsize(), 1)
        self.assertEqual(worker._dropped_events, 1)

        # Verify diagnostics published
        self.assertEqual(mock_bus.publish.call_count, 1)
        published_event = mock_bus.publish.call_args[0][0]
        self.assertEqual(published_event.event_type, EventType.DIAGNOSTICS_UPDATED)
        self.assertEqual(published_event.source, "persistence_worker")
        self.assertIn("persistence", published_event.payload)
        self.assertEqual(published_event.payload["dropped_event_type"], "EVENT_2")
        self.assertEqual(published_event.payload["persistence"]["dropped_events"], 1)

    @patch("backend.runtime.workers.persistence_worker.config")
    @patch("backend.runtime.workers.persistence_worker.bus")
    def test_persistence_worker_does_not_emit_drop_diagnostics_recursively(self, mock_bus, mock_config):
        mock_config.PERSISTENCE_QUEUE_SIZE = 1
        mock_config.PERSISTENCE_DROP_WARNING_THRESHOLD = 1
        mock_config.PERSISTENCE_DROP_WARNING_INTERVAL_SEC = 0.0
        mock_config.DB_PATH = ":memory:"

        worker = PersistenceWorker()
        worker._queue.maxsize = 1

        # Fill the queue
        worker._on_event({"type": "EVENT_1"})

        # Trigger drop with an event that came from persistence_worker
        worker._on_event({
            "type": EventType.DIAGNOSTICS_UPDATED.value,
            "source": "persistence_worker",
            "payload": {}
        })

        # Verify drop counter increased but no diagnostics event published to avoid recursive drop loops
        self.assertEqual(worker._dropped_events, 1)
        self.assertEqual(mock_bus.publish.call_count, 0)

if __name__ == "__main__":
    unittest.main()
