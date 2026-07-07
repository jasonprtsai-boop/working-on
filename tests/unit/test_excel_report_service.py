import os
import tempfile
import time
import unittest

from backend.utils.serialization.excel_report_service import game_record_filename, unique_record_path


class TestExcelReportService(unittest.TestCase):
    def test_game_record_filename_uses_local_start_date_and_time(self):
        started_at = time.mktime((2026, 6, 8, 14, 37, 20, 0, 0, -1))

        self.assertEqual(game_record_filename(started_at), "2026-06-08_14-37-20.xlsx")

    def test_unique_record_path_keeps_date_filename_and_avoids_overwrite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            first = unique_record_path(tmpdir, "2026-06-08_14-37-20.xlsx")
            open(first, "wb").close()

            second = unique_record_path(tmpdir, "2026-06-08_14-37-20.xlsx")

            self.assertTrue(second.endswith(os.path.join(tmpdir, "2026-06-08_14-37-20_2.xlsx")))


if __name__ == "__main__":
    unittest.main()
