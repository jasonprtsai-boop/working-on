import unittest
import json

import numpy as np

from backend.infrastructure.vision.benchmark import VisionDetectionBenchmark
from backend.infrastructure.vision.detection.detection_result import BoundingBox, Detection
from backend.infrastructure.vision.detection.mode_factory import DetectorModeFactory, ROIAdjustedDetector


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


class StaticROI:
    def __init__(self, roi=(10, 20, 40, 50)):
        self.roi = roi

    def detect_change(self, _frame):
        return self.roi


class EmptyROI:
    def detect_change(self, _frame):
        return None


class TestVisionBenchmark(unittest.TestCase):
    def test_factory_builds_all_four_modes(self):
        factory = DetectorModeFactory(
            model_path="",
            yolo_builder=lambda: FakeDetector("yolo"),
            sahi_builder=lambda: FakeDetector("sahi"),
            roi_builder=EmptyROI,
        )

        detectors = factory.create_all(["full_yolo", "sahi", "roi_yolo", "roi_sahi"])

        self.assertEqual(set(detectors), {"full_yolo", "sahi", "roi_yolo", "roi_sahi"})
        self.assertIsInstance(detectors["roi_yolo"], ROIAdjustedDetector)
        self.assertIsInstance(detectors["roi_sahi"], ROIAdjustedDetector)

    def test_roi_detector_offsets_bbox_back_to_full_frame(self):
        inner = FakeDetector(
            detections=[
                Detection(
                    class_id=1,
                    class_name="R",
                    confidence=0.9,
                    bbox=BoundingBox(1, 2, 5, 6),
                )
            ]
        )
        detector = ROIAdjustedDetector(inner, roi_optimizer=StaticROI())
        frame = np.zeros((100, 100, 3), dtype=np.uint8)

        detections = detector.detect(frame)

        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].bbox.x1, 11)
        self.assertEqual(detections[0].bbox.y1, 22)
        self.assertEqual(detections[0].bbox.x2, 15)
        self.assertEqual(detections[0].bbox.y2, 26)
        self.assertTrue(detector.get_status()["roi_applied"])

    def test_no_annotations_keep_map_and_recall_as_na(self):
        detection = Detection(0, "R", 0.95, BoundingBox(0, 0, 5, 5))
        factory = DetectorModeFactory(
            model_path="",
            yolo_builder=lambda: FakeDetector("yolo", [detection]),
            sahi_builder=lambda: FakeDetector("sahi", [detection]),
            roi_builder=EmptyROI,
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

    def test_sahi_unavailable_is_reported_as_skipped(self):
        factory = DetectorModeFactory(
            model_path="",
            yolo_builder=lambda: FakeDetector("yolo"),
            sahi_builder=lambda: FakeDetector(
                "sahi",
                detections=[],
                status={"available": False, "loaded": False, "last_error": "sahi_not_available"},
            ),
            roi_builder=EmptyROI,
        )
        benchmark = VisionDetectionBenchmark(modes=["sahi"], factory=factory)
        frame = np.zeros((100, 100, 3), dtype=np.uint8)

        rows = benchmark.run_frames([frame])

        self.assertEqual(rows[0]["status"], "skipped")
        self.assertEqual(rows[0]["skip_reason"], "sahi_not_available")


if __name__ == "__main__":
    unittest.main()
