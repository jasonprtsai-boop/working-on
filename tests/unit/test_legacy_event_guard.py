import tempfile
import unittest
from pathlib import Path

from scripts.check_legacy_events import find_legacy_publish_calls


class TestLegacyEventGuard(unittest.TestCase):
    def test_detects_dict_publish_call(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "legacy.py"
            path.write_text(
                "from backend.events.bus.event_bus import bus\n"
                "bus.publish({'type': 'TEST.LEGACY', 'payload': {}})\n",
                encoding="utf-8",
            )

            findings = find_legacy_publish_calls([path])

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].line, 2)

    def test_allows_base_event_publish_call(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "canonical.py"
            path.write_text(
                "from backend.events.models.base_event import BaseEvent\n"
                "from backend.events.bus.event_bus import bus\n"
                "bus.publish(BaseEvent.create(event_type='TEST.OK', source='unit', payload={}))\n",
                encoding="utf-8",
            )

            findings = find_legacy_publish_calls([path])

        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
