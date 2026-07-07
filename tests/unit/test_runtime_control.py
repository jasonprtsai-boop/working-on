import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.application.services.runtime_control import RuntimeControl
from backend.events.models.base_event import BaseEvent


class TestRuntimeControlSessionRecords(unittest.TestCase):
    def test_ai_mode_updates_label_and_engine_depth(self):
        from backend.runtime.workers.engine_worker import engine_worker

        control = RuntimeControl()
        snapshot = control.set_ai_mode("training")

        self.assertEqual(snapshot["ai_mode"], "training")
        self.assertEqual(snapshot["ai_mode_label"], "訓練模式")
        self.assertEqual(snapshot["engine_depth"], 10)
        self.assertEqual(engine_worker.depth_on_change, 10)

    def test_adaptive_mode_adjusts_depth_from_recent_move_time(self):
        from backend.runtime.workers.engine_worker import engine_worker

        control = RuntimeControl()
        control.start_session(participant_id="P-ADAPT")
        control.set_ai_mode("adaptive")
        control._last_step_at = 1000.0

        with patch("backend.application.services.runtime_control.time.time", return_value=1008.0):
            control._on_move_applied(BaseEvent.create(
                event_type="MOVE_APPLIED",
                source="unit",
                payload={"move": "a0a1"},
            ))

        self.assertEqual(control.snapshot()["engine_depth"], 9)
        self.assertEqual(engine_worker.depth_on_change, 9)

    def test_end_session_exports_one_record_file(self):
        control = RuntimeControl()
        control.start_session(participant_id="P-001")
        result = SimpleNamespace(
            filename="2026-06-08_14-37-20.xlsx",
            path="C:\\tmp\\2026-06-08_14-37-20.xlsx",
        )

        with patch("backend.application.services.runtime_control.time.sleep"), patch.object(
            control,
            "_save_session_record",
            return_value=result,
        ) as save_record:
            snapshot = control.end_session()

        save_record.assert_called_once()
        session = snapshot["session"]
        self.assertEqual(session["record_status"], "saved")
        self.assertEqual(session["record_filename"], "2026-06-08_14-37-20.xlsx")
        self.assertEqual(session["record_path"], "C:\\tmp\\2026-06-08_14-37-20.xlsx")


if __name__ == "__main__":
    unittest.main()
