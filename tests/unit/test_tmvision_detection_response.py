from __future__ import annotations

import unittest
from io import BytesIO
from unittest.mock import patch

import numpy as np

from backend.interfaces.api.vision_frame_io import (
    detect_tmvision_frame,
    tmvision_detection_annotations,
)


class FakeVisionSystem:
    def __init__(self):
        self.calls = []

    def detect_frame(self, frame, *, publish=True, source="vision_system"):
        self.calls.append({"shape": frame.shape, "publish": publish, "source": source})
        return {
            "detections": [
                {
                    "class_name": "red_king",
                    "confidence": 0.875,
                    "bbox_xyxy": [10, 20, 30, 50],
                    "raw_bbox": [15, 25, 45, 65],
                }
            ],
            "latency_ms": 12.5,
            "calibrated": True,
            "coordinate_space": "rectified_board",
            "source": source,
        }


class TMvisionDetectionResponseTest(unittest.TestCase):
    def test_annotations_prefer_raw_bbox_for_tmvision_coordinates(self):
        annotations = tmvision_detection_annotations({
            "detections": [
                {
                    "class_name": "red_king",
                    "confidence": 0.8,
                    "bbox_xyxy": [10, 20, 30, 50],
                    "raw_bbox": [15, 25, 45, 65],
                }
            ]
        })

        self.assertEqual(len(annotations), 1)
        self.assertEqual(annotations[0]["label"], "red_king")
        self.assertEqual(annotations[0]["box_cx"], 30.0)
        self.assertEqual(annotations[0]["box_cy"], 45.0)
        self.assertEqual(annotations[0]["center_point"], [30.0, 45.0])
        self.assertEqual(annotations[0]["center_x"], 30.0)
        self.assertEqual(annotations[0]["center_y"], 45.0)
        self.assertEqual(annotations[0]["box_w"], 30.0)
        self.assertEqual(annotations[0]["box_h"], 40.0)
        self.assertEqual(annotations[0]["bbox_xyxy"], [15.0, 25.0, 45.0, 65.0])
        self.assertEqual(annotations[0]["bbox_xywh"], [15.0, 25.0, 30.0, 40.0])
        self.assertEqual(annotations[0]["coordinates"]["x1"], 15.0)
        self.assertEqual(annotations[0]["coordinates"]["y1"], 25.0)
        self.assertEqual(annotations[0]["coordinates"]["x2"], 45.0)
        self.assertEqual(annotations[0]["coordinates"]["y2"], 65.0)
        self.assertEqual(annotations[0]["coordinates"]["cx"], 30.0)
        self.assertEqual(annotations[0]["coordinates"]["cy"], 45.0)
        self.assertIn("color", annotations[0])
        self.assertIn("box_color", annotations[0])
        self.assertEqual(annotations[0]["score"], 0.8)

    def test_detect_tmvision_frame_uses_shared_vision_system_entrypoint(self):
        frame = np.zeros((80, 120, 3), dtype=np.uint8)
        fake_vision = FakeVisionSystem()

        result = detect_tmvision_frame({"_frame": frame}, fake_vision)

        self.assertTrue(result["ok"])
        self.assertEqual(len(result["annotations"]), 1)
        self.assertEqual(fake_vision.calls[0]["source"], "tmvision_http")
        self.assertTrue(fake_vision.calls[0]["publish"])
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["annotations_count"], 1)
        self.assertEqual(result["detection"]["detections_count"], 1)
        self.assertEqual(result["detection"]["count"], 1)

    def test_tmvision_detect_endpoint_returns_yolo_annotations(self):
        try:
            import cv2
        except Exception:
            self.skipTest("OpenCV is not available")

        from flask import Flask

        from backend.interfaces.api.shared import api_bp
        from backend.interfaces.api import vision_routes

        app = Flask(__name__)
        app.register_blueprint(api_bp, url_prefix="/api")

        frame = np.zeros((40, 60, 3), dtype=np.uint8)
        ok, encoded = cv2.imencode(".jpg", frame)
        self.assertTrue(ok)

        fake_vision = FakeVisionSystem()
        with patch.object(vision_routes, "_tmflow_frame_ingest_authorized", return_value=True):
            with patch.object(vision_routes, "vision_system", fake_vision):
                response = app.test_client().post(
                    "/api/vision/tmvision/detect?debug=1",
                    data={"file": (BytesIO(encoded.tobytes()), "frame.jpg")},
                    content_type="multipart/form-data",
                )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["message"], "success")
        self.assertEqual(payload["mode"], "tmvision_external_detection_yolo")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["annotations_count"], 1)
        self.assertEqual(len(payload["annotations"]), 1)
        self.assertEqual(payload["annotations"][0]["label"], "red_king")
        self.assertIn("bbox_xyxy", payload["annotations"][0])
        self.assertIn("color", payload["annotations"][0])


if __name__ == "__main__":
    unittest.main()
