from __future__ import annotations

import unittest

from backend.infrastructure.vision.camera.vision_source_manager import (
    VisionSourceManager,
    normalize_vision_source,
)
from backend.interfaces.api.setup_settings_logic import current_setup_settings, normalize_setup_settings


class TMvisionHTTPSourceTest(unittest.TestCase):
    def test_normalize_tmvision_aliases_to_passive_http_source(self):
        self.assertEqual(normalize_vision_source("tmvision"), "tmvision_http")
        self.assertEqual(normalize_vision_source("eih_http"), "tmvision_http")
        self.assertEqual(normalize_vision_source("external_detection"), "tmvision_http")

    def test_passive_http_source_starts_without_opening_usb_camera(self):
        manager = VisionSourceManager("tmvision_http")

        self.assertTrue(manager.start())
        status = manager.get_status()

        self.assertEqual(status["source"], "tmvision_http")
        self.assertTrue(status["running"])
        self.assertTrue(status["passive"])
        self.assertEqual(status["endpoint"], "/api/vision/tmvision/detect")

    def test_setup_settings_accepts_tmvision_http_source(self):
        settings = normalize_setup_settings(
            {"vision": {"source": "tmvision_http"}},
            base=current_setup_settings(),
        )

        self.assertEqual(settings["vision"]["source"], "tmvision_http")


if __name__ == "__main__":
    unittest.main()
