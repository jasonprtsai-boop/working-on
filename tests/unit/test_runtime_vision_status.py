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


if __name__ == "__main__":
    unittest.main()
