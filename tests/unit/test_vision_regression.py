import json
import unittest
from pathlib import Path

import cv2
import numpy as np

from backend.infrastructure.vision.board.board_mapper import BoardMapper
from backend.infrastructure.vision.board.coordinate_system import BoardCoordinateSystem, GridConfig
from backend.infrastructure.vision.calibration.board_calibrator import BoardCalibrator
from backend.infrastructure.vision.detection.detection_result import BoundingBox, Detection
from backend.infrastructure.vision.fen.fen_generator import FENGenerator


FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "vision" / "synthetic_cases.json"


class TestVisionRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def test_synthetic_board_calibration_cases_detect_corners(self):
        for case in self.cases:
            with self.subTest(case=case["name"]):
                frame = synthetic_frame(case)
                corners = BoardCalibrator(max_detection_dim=240).detect_auto(frame)

                self.assertIsNotNone(corners)
                self.assertTrue(BoardCalibrator.validate_corners(corners, min_area=1000))

    def test_synthetic_detection_cases_generate_expected_fen(self):
        for case in self.cases:
            with self.subTest(case=case["name"]):
                grid = case["grid"]
                coord = BoardCoordinateSystem(GridConfig(**grid))
                mapper = BoardMapper(coord)
                generator = FENGenerator(rows=grid["rows"], cols=grid["cols"])

                board_state = mapper.map_detections(synthetic_detections(case, coord))
                fen = generator.generate(board_state, turn="w")

                self.assertEqual(fen, case["expected_fen"])


def synthetic_frame(case):
    image = case["image"]
    frame = np.zeros((int(image["height"]), int(image["width"]), 3), dtype=np.uint8)
    quad = np.array(image["board_quad"], dtype=np.int32)
    cv2.fillConvexPoly(frame, quad, (255, 255, 255))
    cv2.polylines(frame, [quad], isClosed=True, color=(40, 40, 40), thickness=3)
    return frame


def synthetic_detections(case, coord):
    detections = []
    for idx, item in enumerate(case["detections"]):
        col, row = item["cell"]
        cx, cy = coord.cell_to_pixel_center(col, row)
        detections.append(
            Detection(
                class_id=idx,
                class_name=item["class_name"],
                confidence=float(item["confidence"]),
                bbox=BoundingBox(cx - 8, cy - 8, cx + 8, cy + 8),
            )
        )
    return detections


if __name__ == "__main__":
    unittest.main()
