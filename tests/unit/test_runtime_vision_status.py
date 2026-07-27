import unittest
from unittest.mock import patch

from backend.interfaces.api import shared


class FallbackVision:
    _fallback_reason = "model load failed"

    def get_status(self):
        return {
            "system": "SimulationVisionSystem",
            "simulation": True,
            "calibration": {},
        }


class TestRuntimeVisionStatus(unittest.TestCase):
    def test_runtime_vision_status_exposes_fallback_reason(self):
        with patch.object(shared, "vision_system", FallbackVision()):
            status = shared.runtime_vision_status()

        self.assertTrue(status["fallback"])
        self.assertTrue(status["simulation"])
        self.assertEqual(status["mode"], "fallback")
        self.assertEqual(status["fallback_reason"], "model load failed")

    def test_runtime_vision_status_keeps_unavailable_distinct_from_simulation(self):
        class UnavailableVision:
            def get_status(self):
                return {
                    "system": "UnavailableVisionSystem",
                    "mode": "unavailable",
                    "available": False,
                    "simulation": False,
                    "fallback": False,
                    "startup_failure": True,
                    "startup_error": "camera offline",
                    "calibration": {"simulation": False, "fallback": False},
                }

        with patch.object(shared, "vision_system", UnavailableVision()):
            status = shared.runtime_vision_status()

        self.assertFalse(status["fallback"])
        self.assertFalse(status["simulation"])
        self.assertFalse(status["available"])
        self.assertEqual(status["mode"], "unavailable")
        self.assertEqual(status["startup_error"], "camera offline")


if __name__ == "__main__":
    unittest.main()
