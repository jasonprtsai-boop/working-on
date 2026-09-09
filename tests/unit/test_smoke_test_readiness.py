from __future__ import annotations

import contextlib
import importlib.util
import io
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SMOKE_TEST_PATH = ROOT / "scripts" / "test" / "smoke_test.py"


def load_smoke_test_module():
    spec = importlib.util.spec_from_file_location("smart_chess_smoke_test", SMOKE_TEST_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class SmokeTestReadinessTest(unittest.TestCase):
    def setUp(self):
        self.smoke_test = load_smoke_test_module()

    def test_ready_false_is_reported_without_failing_software_smoke(self):
        payload = {
            "ready": False,
            "robot_connected": False,
            "bootstrap": {
                "ready": False,
                "errors": [{"component": "robot.connect", "error": "Robot unavailable"}],
            },
        }
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            self.smoke_test.report_readiness(payload, require_hardware_ready=False)

        text = output.getvalue()
        self.assertIn("Hardware readiness: NOT READY", text)
        self.assertIn("robot.connect", text)
        self.assertIn("Robot unavailable", text)

    def test_ready_false_fails_when_hardware_readiness_is_required(self):
        payload = {"ready": False, "robot_connected": False, "bootstrap": {"ready": False}}
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            with self.assertRaisesRegex(RuntimeError, "reports not ready"):
                self.smoke_test.report_readiness(payload, require_hardware_ready=True)

    def test_non_json_ready_response_fails_when_hardware_readiness_is_required(self):
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            with self.assertRaisesRegex(RuntimeError, "could not be read"):
                self.smoke_test.report_readiness(None, require_hardware_ready=True)

    def test_degraded_health_fails_when_hardware_readiness_is_required(self):
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            with self.assertRaisesRegex(RuntimeError, "reports degraded"):
                self.smoke_test.report_health({"ok": False}, require_hardware_ready=True)


if __name__ == "__main__":
    unittest.main()
