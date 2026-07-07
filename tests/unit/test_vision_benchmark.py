import unittest
import json

import numpy as np

from backend.infrastructure.vision.benchmark import VisionDetectionBenchmark
from backend.infrastructure.vision.detection.detection_result import BoundingBox, Detection
from backend.infrastructure.vision.detection.mode_factory import DetectorModeFactory


class FakeDetector:
    def __init__(self, name="fake", detections=None, status=None):
        self.name = name
        self.detections = detections if detections is not None else []
        self.status = status or {"loaded": True, "available": True, "name": name}

    def load_model(self, _model_path):
        return None

    def detect(self, _frame):
        return list(self.detections)

    def get_status(self):
        return dict(self.status)


class TestVisionBenchmark(unittest.TestCase):
    def test_factory_builds_yolo_mode(self):
        factory = DetectorModeFactory(
            model_path="",
            yolo_builder=lambda: FakeDetector("yolo"),
        )

        detectors = factory.create_all(["full_yolo"])

        self.assertEqual(set(detectors), {"full_yolo"})
        self.assertEqual(detectors["full_yolo"].name, "yolo")

    def test_no_annotations_keep_map_and_recall_as_na(self):
        detection = Detection(0, "R", 0.95, BoundingBox(0, 0, 5, 5))
        factory = DetectorModeFactory(
            model_path="",
            yolo_builder=lambda: FakeDetector("yolo", [detection]),
        )
        benchmark = VisionDetectionBenchmark(
            modes=["full_yolo"],
            factory=factory,
            stability_threshold=2,
            small_object_area_ratio=0.01,
        )
        frame = np.zeros((100, 100, 3), dtype=np.uint8)

        rows = benchmark.run_frames([frame, frame])
        summary = benchmark.summarize(rows)

        self.assertEqual(rows[0]["map_50"], "N/A")
        self.assertEqual(rows[0]["recall"], "N/A")
        self.assertEqual(rows[0]["metric_note"], "requires_annotations")
        self.assertTrue(rows[0]["requires_annotations"])
        self.assertEqual(rows[0]["small_object_count"], 1)
        self.assertIn(" w - - 0 1", rows[0]["fen"])
        self.assertEqual(json.loads(rows[0]["detections_json"])[0]["class_name"], "R")
        self.assertTrue(rows[1]["stable_update"])
        self.assertEqual(summary[0]["map_50"], "N/A")
        self.assertGreater(summary[0]["avg_fps"], 0)


if __name__ == "__main__":
    unittest.main()
