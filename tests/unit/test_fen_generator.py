import unittest

from backend.infrastructure.vision.board.board_mapper import BoardMapper
from backend.infrastructure.vision.board.coordinate_system import BoardCoordinateSystem, GridConfig
from backend.infrastructure.vision.detection.detection_result import BoundingBox, Detection
from backend.infrastructure.vision.fen.fen_generator import DetectionFENGenerator, FENGenerator


class TestFENGenerator(unittest.TestCase):
    def test_fen_generator_uses_requested_side_to_move(self):
        generator = FENGenerator()

        fen = generator.generate({"0,0": "r", "4,9": "K"}, turn="black")

        self.assertTrue(fen.endswith(" b - - 0 1"))

    def test_detection_fen_generator_preserves_turn(self):
        coord = BoardCoordinateSystem(GridConfig(rows=10, cols=9, width=900, height=1000))
        mapper = BoardMapper(coord)
        generator = DetectionFENGenerator(mapper, FENGenerator())
        detections = [Detection(0, "紅色-車", 0.95, BoundingBox(-5, -5, 5, 5))]

        fen = generator.generate(detections, turn="b")

        self.assertIsNotNone(fen)
        self.assertTrue(fen.startswith("R8/"))
        self.assertTrue(fen.endswith(" b - - 0 1"))


if __name__ == "__main__":
    unittest.main()
