import unittest

from backend.infrastructure.vision.board.board_mapper import BoardMapper
from backend.infrastructure.vision.board.coordinate_system import BoardCoordinateSystem, GridConfig
from backend.infrastructure.vision.detection.detection_result import BoundingBox, Detection


class TestBoardMapper(unittest.TestCase):
    def setUp(self):
        coord = BoardCoordinateSystem(GridConfig(rows=10, cols=9, width=900, height=1000))
        self.mapper = BoardMapper(coord)

    def test_detection_to_dict_exposes_coordinate_metadata(self):
        det = Detection(
            0,
            "red_rook",
            0.75,
            BoundingBox(10, 20, 30, 60),
            coordinate_space="rectified_board",
            frame_width=100,
            frame_height=200,
        )

        payload = det.to_dict(anchor_ratio=(0.5, 1.0))

        self.assertEqual(payload["bbox"], [10.0, 20.0, 30.0, 60.0])
        self.assertEqual(payload["bbox_xywh"], [10.0, 20.0, 20.0, 40.0])
        self.assertEqual(payload["bbox_center"], [20.0, 40.0])
        self.assertEqual(payload["anchor_point"], [20.0, 60.0])
        self.assertEqual(payload["frame_size"], [100, 200])
        self.assertEqual(payload["bbox_normalized"], [0.1, 0.1, 0.3, 0.3])
        self.assertEqual(payload["coordinate_space"], "rectified_board")

    def test_describe_detections_includes_board_mapping_metadata(self):
        coord = self.mapper.coord_system
        cx, cy = coord.cell_to_pixel_center(2, 3)
        detections = [Detection(0, "red_rook", 0.9, BoundingBox(cx - 10, cy - 10, cx + 10, cy + 10))]

        details = self.mapper.describe_detections(
            detections,
            coordinate_space="rectified_board",
            frame_size=(900, 1000),
        )

        self.assertEqual(len(details), 1)
        self.assertEqual(details[0]["mapping_status"], "mapped")
        self.assertEqual(details[0]["mapped_cell"], "2,3")
        self.assertEqual(details[0]["piece_code"], "R")
        self.assertEqual(details[0]["board_mapping"]["key"], "2,3")
        self.assertEqual(details[0]["coordinate_space"], "rectified_board")

    def test_maps_common_yolo_xiangqi_labels(self):
        cases = {
            "red_rook": "R",
            "black_cannon": "c",
            "red_soldier": "P",
            "black_horse": "n",
            "red_advisor": "A",
            "black_elephant": "b",
            "red_general": "K",
            "black_king": "k",
            "w_pawn": "P",
            "b_rook": "r",
            "chess-red-guard": "A",
            "chess-black-cannon": "c",
            "xiangqi-red-rook": "R",
            "piece-black-horse": "n",
        }

        for label, expected in cases.items():
            with self.subTest(label=label):
                self.assertEqual(self.mapper._map_class_to_piece(label), expected)

    def test_maps_chinese_yolo_xiangqi_labels(self):
        cases = {
            "紅色-帥": "K",
            "紅色-仕": "A",
            "紅色-相": "B",
            "紅色-車": "R",
            "紅色-馬": "N",
            "紅色-炮": "C",
            "紅色-兵": "P",
            "黑色-將": "k",
            "黑色-仕": "a",
            "黑色-象": "b",
            "黑色-車": "r",
            "黑色-馬": "n",
            "黑色-砲": "c",
            "黑色-包": "c",
            "黑色-卒": "p",
        }

        for label, expected in cases.items():
            with self.subTest(label=label):
                self.assertEqual(self.mapper._map_class_to_piece(label), expected)

    def test_unknown_labels_are_skipped_instead_of_emitting_question_mark(self):
        detections = [
            Detection(0, "red_rook", 0.7, BoundingBox(10, 10, 90, 90)),
            Detection(1, "board_corner", 0.99, BoundingBox(120, 10, 180, 90)),
        ]

        board = self.mapper.map_detections(detections)

        self.assertEqual(board, {"0,0": "R"})
        self.assertNotIn("?", board.values())

    def test_conflict_resolution_keeps_highest_confidence_piece(self):
        detections = [
            Detection(0, "red_rook", 0.4, BoundingBox(10, 10, 90, 90)),
            Detection(1, "black_cannon", 0.9, BoundingBox(20, 20, 80, 80)),
        ]

        board = self.mapper.map_detections(detections)

        self.assertEqual(board["0,0"], "c")

    def test_conflict_resolution_prefers_closer_anchor_when_confidence_ties(self):
        coord = self.mapper.coord_system
        cx, cy = coord.cell_to_pixel_center(2, 3)
        detections = [
            Detection(0, "black_cannon", 0.8, BoundingBox(cx + 14, cy + 14, cx + 34, cy + 34)),
            Detection(1, "red_rook", 0.8, BoundingBox(cx - 10, cy - 10, cx + 10, cy + 10)),
        ]

        board = self.mapper.map_detections(detections)

        self.assertEqual(board["2,3"], "R")

    def test_maps_to_nearest_board_intersection(self):
        coord = self.mapper.coord_system
        cx = coord.cell_w * 2 + 4
        cy = coord.cell_h * 3 - 3
        detections = [Detection(0, "紅色-車", 0.8, BoundingBox(cx - 5, cy - 5, cx + 5, cy + 5))]

        board = self.mapper.map_detections(detections)

        self.assertEqual(board, {"2,3": "R"})

    def test_detection_far_from_intersections_is_skipped(self):
        detections = [Detection(0, "紅色-車", 0.8, BoundingBox(-210, -210, -190, -190))]

        board = self.mapper.map_detections(detections)

        self.assertEqual(board, {})


if __name__ == "__main__":
    unittest.main()
