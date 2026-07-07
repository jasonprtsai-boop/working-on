import asyncio
import unittest

import numpy as np

from backend.infrastructure.vision.board.board_mapper import BoardMapper
from backend.infrastructure.vision.board.coordinate_system import BoardCoordinateSystem, GridConfig
from backend.infrastructure.vision.detection.detection_result import BoundingBox, Detection
from backend.infrastructure.vision.fen.fen_generator import FENGenerator
from backend.infrastructure.vision.pipeline import VisionPipeline


class FakePerspective:
    matrix = None

    def transform(self, frame):
        return frame

    def update_corners(self, _corners):
        self.matrix = np.eye(3, dtype=np.float32)


class FakePreprocess:
    def process(self, frame):
        return frame


class FakeDetector:
    def __init__(self, detections):
        self.detections = detections

    def detect(self, _frame):
        return list(self.detections)


class TestVisionPipeline(unittest.TestCase):
    def test_process_returns_stage_metadata_and_detection_payloads(self):
        frame = np.zeros((100, 90, 3), dtype=np.uint8)
        detections = [Detection(7, "red_rook", 0.91, BoundingBox(0, 0, 20, 20))]
        pipeline = VisionPipeline(
            camera=None,
            preprocess=FakePreprocess(),
            perspective=FakePerspective(),
            morphology=None,
            detector=FakeDetector(detections),
            fen_gen=None,
        )

        result = asyncio.run(pipeline.process(frame))

        self.assertIsNotNone(result)
        self.assertEqual(len(result.detections), 1)
        payload = result.to_dict()
        self.assertEqual(payload["detections"][0]["class_id"], 7)
        self.assertEqual(payload["detections"][0]["bbox"], [0.0, 0.0, 20.0, 20.0])
        self.assertEqual(payload["detections"][0]["coordinate_space"], "camera_frame")
        self.assertIn("homography", payload["stage_timings_ms"])
        self.assertIn("inference", payload["stage_timings_ms"])

    def test_process_maps_board_state_when_mapper_is_available(self):
        frame = np.zeros((1000, 900, 3), dtype=np.uint8)
        coord = BoardCoordinateSystem(GridConfig(rows=10, cols=9, width=900, height=1000))
        mapper = BoardMapper(coord)
        detections = [Detection(0, "red_rook", 0.95, BoundingBox(0, 0, 20, 20))]
        perspective = FakePerspective()
        perspective.update_corners([[0, 0], [899, 0], [899, 999], [0, 999]])
        pipeline = VisionPipeline(
            camera=None,
            preprocess=FakePreprocess(),
            perspective=perspective,
            morphology=None,
            detector=FakeDetector(detections),
            fen_gen=FENGenerator(rows=10, cols=9),
            board_mapper=mapper,
        )

        result = asyncio.run(pipeline.process(frame, turn="b"))

        self.assertEqual(result.board_state, {"0,0": "R"})
        self.assertEqual(result.fen, "R8/9/9/9/9/9/9/9/9/9 b - - 0 1")
        self.assertTrue(result.calibrated)
        self.assertEqual(result.coordinate_space, "rectified_board")
        self.assertEqual(result.to_dict()["detections"][0]["mapped_cell"], "0,0")

    def test_process_skips_invalid_frame(self):
        pipeline = VisionPipeline(
            camera=None,
            preprocess=FakePreprocess(),
            perspective=FakePerspective(),
            morphology=None,
            detector=FakeDetector([]),
            fen_gen=None,
        )

        self.assertIsNone(asyncio.run(pipeline.process(np.array([]))))


if __name__ == "__main__":
    unittest.main()
