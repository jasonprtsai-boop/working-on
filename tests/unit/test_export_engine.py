import json
import os
import sqlite3
import tempfile
import unittest

from backend.infrastructure.database.export_engine import export_excel_report, export_full_snapshot
from backend.infrastructure.database.db import Database


class TestExportEngine(unittest.TestCase):
    def _seed_db(self, db_path):
        with sqlite3.connect(db_path) as conn:
            conn.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, type TEXT)")
            conn.execute("INSERT INTO events (type) VALUES (?)", ("STATE_UPDATE",))
            conn.execute("CREATE TABLE internal_shadow (secret TEXT)")
            conn.execute("INSERT INTO internal_shadow (secret) VALUES (?)", ("hidden",))

    def test_export_excel_report_allows_known_table(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "events.db")
            out_path = os.path.join(tmpdir, "events.csv")
            self._seed_db(db_path)

            self.assertTrue(export_excel_report("events", out_path, db_path=db_path))

            with open(out_path, encoding="utf-8") as handle:
                content = handle.read()
            self.assertIn("STATE_UPDATE", content)

    def test_export_excel_report_rejects_unlisted_or_malicious_table(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "events.db")
            out_path = os.path.join(tmpdir, "bad.csv")
            self._seed_db(db_path)

            self.assertFalse(export_excel_report("events; DROP TABLE events; --", out_path, db_path=db_path))
            self.assertFalse(export_excel_report("internal_shadow", out_path, db_path=db_path))
            self.assertFalse(os.path.exists(out_path))

    def test_legacy_database_export_uses_safe_table_allowlist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "events.db")
            out_path = os.path.join(tmpdir, "bad.csv")
            self._seed_db(db_path)
            from backend.utils import config

            old_test_mode = config.TEST_MODE
            config.TEST_MODE = False
            database = Database(db_path=db_path)
            try:
                self.assertFalse(database.export_excel_csv("events; DROP TABLE events; --", out_path))
                self.assertFalse(os.path.exists(out_path))
            finally:
                database.close()
                config.TEST_MODE = old_test_mode

    def test_export_full_snapshot_skips_unlisted_tables(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "events.db")
            out_path = os.path.join(tmpdir, "snapshot.json")
            self._seed_db(db_path)

            self.assertTrue(export_full_snapshot(out_path, db_path=db_path))
            with open(out_path, encoding="utf-8") as handle:
                snapshot = json.loads(handle.read())

            self.assertIn("events", snapshot)
            self.assertNotIn("internal_shadow", snapshot)


if __name__ == "__main__":
    unittest.main()
