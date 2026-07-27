import unittest
from unittest.mock import patch

from backend.infrastructure.vision import vision_system as vision_module


class VisionFallbackPolicyTests(unittest.TestCase):
    def test_real_startup_failure_stays_unavailable_by_default(self):
        with patch.object(vision_module.config, "FAKE_VISION", False), patch.object(
            vision_module.config,
            "VISION_ALLOW_SIMULATION_FALLBACK",
            False,
        ), patch.object(
            vision_module,
            "_build_real_vision_system",
            side_effect=RuntimeError("model missing"),
        ):
            system = vision_module._create_vision_system()

        status = system.get_status()

        self.assertEqual(status["system"], "UnavailableVisionSystem")
        self.assertEqual(status["mode"], "unavailable")
        self.assertFalse(status["simulation"])
        self.assertFalse(status["fallback"])
        self.assertFalse(status["available"])
        self.assertIn("model missing", status["startup_error"])

    def test_explicit_simulation_fallback_keeps_old_fallback_path_available(self):
        with patch.object(vision_module.config, "FAKE_VISION", False), patch.object(
            vision_module.config,
            "VISION_ALLOW_SIMULATION_FALLBACK",
            True,
        ), patch.object(
            vision_module,
            "_build_real_vision_system",
            side_effect=RuntimeError("model missing"),
        ):
            system = vision_module._create_vision_system()

        status = system.get_status()

        self.assertEqual(status["system"], "SimulationVisionSystem")
        self.assertEqual(status["mode"], "fallback")
        self.assertTrue(status["simulation"])
        self.assertTrue(status["fallback"])
        self.assertEqual(status["fallback_reason"], "model missing")


if __name__ == "__main__":
    unittest.main()
