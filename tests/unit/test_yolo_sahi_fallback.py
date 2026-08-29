from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np

from backend.infrastructure.vision.detection import yolo_detector
from backend.infrastructure.vision.detection.yolo_detector import YOLODetector


class _FakeBoxes:
    def __init__(self, rows):
        self.xyxy = np.asarray([row[0] for row in rows], dtype=float)
        self.conf = np.asarray([row[1] for row in rows], dtype=float)
        self.cls = np.asarray([row[2] for row in rows], dtype=float)


class _FakeResult:
    def __init__(self, rows):
        self.boxes = _FakeBoxes(rows)
        self.names = {1: "fast_piece", 2: "sahi_piece"}


class _FakeModel:
    def __init__(self, rows):
        self.rows = rows

    def predict(self, **_kwargs):
        return [_FakeResult(self.rows)]


class _FakeBbox:
    minx = 4.0
    miny = 5.0
    maxx = 24.0
    maxy = 35.0


class _FakeCategory:
    id = 2
    name = "sahi_piece"


class _FakeScore:
    value = 0.91


class _FakeObjectPrediction:
    bbox = _FakeBbox()
    category = _FakeCategory()
    score = _FakeScore()


class _FakeSahiResult:
    object_prediction_list = [_FakeObjectPrediction()]


class YOLOSAHIFallbackTest(unittest.TestCase):
    def _detector(self, rows):
        detector = YOLODetector(model_path="")
        detector.model = _FakeModel(rows)
        detector.sahi_model = object()
        return detector

    def test_fast_path_result_does_not_trigger_sahi_without_expected_count(self):
        detector = self._detector([([1, 2, 20, 30], 0.88, 1)])
        frame = np.zeros((64, 64, 3), dtype=np.uint8)

        with patch.object(yolo_detector.config, "YOLO_USE_SAHI", True, create=True):
            with patch.object(yolo_detector, "SAHI_AVAILABLE", True):
                with patch.object(yolo_detector, "get_sliced_prediction", create=True) as sahi:
                    detections = detector.detect(frame)

        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].class_name, "fast_piece")
        sahi.assert_not_called()

    def test_empty_fast_path_triggers_sahi_fallback(self):
        detector = self._detector([])
        frame = np.zeros((64, 64, 3), dtype=np.uint8)

        with patch.object(yolo_detector.config, "YOLO_USE_SAHI", True, create=True):
            with patch.object(yolo_detector, "SAHI_AVAILABLE", True):
                with patch.object(
                    yolo_detector,
                    "get_sliced_prediction",
                    return_value=_FakeSahiResult(),
                    create=True,
                ) as sahi:
                    detections = detector.detect(frame)

        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].class_name, "sahi_piece")
        sahi.assert_called_once()

    def test_expected_count_shortfall_uses_sahi_when_it_improves_count(self):
        detector = self._detector([([1, 2, 20, 30], 0.88, 1)])
        frame = np.zeros((64, 64, 3), dtype=np.uint8)

        with patch.object(yolo_detector.config, "YOLO_USE_SAHI", True, create=True):
            with patch.object(yolo_detector, "SAHI_AVAILABLE", True):
                with patch.object(
                    yolo_detector,
                    "get_sliced_prediction",
                    return_value=_FakeSahiResult(),
                    create=True,
                ) as sahi:
                    detections = detector.detect(frame, expected_count=2)

        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].class_name, "fast_piece")
        sahi.assert_called_once()


if __name__ == "__main__":
    unittest.main()
