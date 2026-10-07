from __future__ import annotations

import unittest

import numpy as np

from backend.infrastructure.vision.detection.opencv_dnn_detector import Detector


class DetectorInterfaceTest(unittest.TestCase):
    def test_opencv_detector_accepts_expected_count_argument(self):
        detector = Detector(model_path="")

        detections = detector.detect(
            np.zeros((32, 32, 3), dtype=np.uint8),
            expected_count=32,
        )

        self.assertEqual(detections, [])


if __name__ == "__main__":
    unittest.main()
