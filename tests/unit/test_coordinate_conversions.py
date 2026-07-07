import unittest

from backend.core.coordinate_system import CoordinateSystem
from backend.core.notation import move_to_chinese
from backend.infrastructure.robot.planner import MotionPlanner
from backend.utils.fen.parser import FENValidationError, board_to_fen, fen_to_board, validate_fen
from backend.utils.kinematics import Kinematics


START_FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"


class TestCoordinateConversions(unittest.TestCase):
    def test_ucci_internal_conversion_is_bidirectional(self):
        coord = CoordinateSystem()

        self.assertEqual(coord.uci_to_internal("a0"), (9, 0))
        self.assertEqual(coord.uci_to_internal("i9"), (0, 8))
        self.assertEqual(coord.internal_to_uci(9, 0), "a0")
        self.assertEqual(coord.internal_to_uci(0, 8), "i9")
        self.assertEqual(coord.move_to_internal("b2b5"), ((7, 1), (4, 1)))
        self.assertEqual(coord.internal_to_move(7, 1, 4, 1), "b2b5")
        self.assertFalse(coord.is_valid_square("a10"))
        self.assertFalse(coord.is_valid_square("a00"))

    def test_robot_coordinate_round_trip_uses_calibration(self):
        mapper = Kinematics()
        mapper.update_calibration(
            origin_x=100,
            origin_y=200,
            square_size_x=10,
            square_size_y=20,
            persist=False,
        )
        coord = CoordinateSystem(robot_kinematics=mapper)

        self.assertEqual(coord.uci_to_world("b1"), (110.0, 220.0))
        self.assertEqual(coord.world_to_uci(110.0, 220.0), "b1")
        self.assertEqual(coord.world_to_internal(110.0, 220.0), (8, 1))

    def test_affine_robot_calibration_supports_rotated_board(self):
        mapper = Kinematics()
        mapper.calibrate_from_points(
            [
                {"square": "a0", "x": 10, "y": 100},
                {"square": "i0", "x": 90, "y": 108},
                {"square": "a9", "x": 1, "y": 190},
            ],
            persist=False,
        )

        x, y = mapper.square_to_robot("b1")
        self.assertAlmostEqual(x, 19.0, places=6)
        self.assertAlmostEqual(y, 111.0, places=6)
        self.assertEqual(mapper.robot_to_square(19.0, 111.0, tolerance_ratio=0.1), "b1")
        self.assertIsNotNone(mapper.to_dict()["calibration_error"])

    def test_robot_coordinate_cache_is_invalidated_after_calibration_update(self):
        mapper = Kinematics()
        mapper.update_calibration(origin_x=100, origin_y=200, square_size_x=10, square_size_y=20)
        before = mapper.square_to_robot("b1")

        mapper.update_calibration(origin_x=200, origin_y=300, square_size_x=10, square_size_y=20)
        after = mapper.square_to_robot("b1")

        self.assertEqual(before, (110.0, 220.0))
        self.assertEqual(after, (210.0, 320.0))

    def test_dead_zone_range_is_persisted_and_slots_are_clamped(self):
        mapper = Kinematics()
        mapper.update_calibration(
            origin_x=100,
            origin_y=200,
            square_size_x=10,
            square_size_y=20,
            dead_zone={
                "x": 300,
                "y": 250,
                "width": 80,
                "height": 40,
                "slot_spacing": 15,
                "slot_count": 3,
            },
            persist=False,
        )

        self.assertEqual(mapper.get_dead_zone_coords(1), (300.0, 250.0))
        self.assertEqual(mapper.get_dead_zone_coords(3), (330.0, 250.0))
        self.assertEqual(mapper.get_dead_zone_coords(99), (330.0, 250.0))
        self.assertEqual(mapper.to_dict()["dead_zone_range"]["width"], 80.0)

    def test_fen_parser_validates_and_preserves_board_shape(self):
        board = fen_to_board(START_FEN)

        self.assertEqual(len(board), 10)
        self.assertEqual(len(board[0]), 9)
        self.assertEqual(board[7][1], "C")
        self.assertTrue(validate_fen(START_FEN))
        self.assertTrue(board_to_fen(board, turn="black").endswith(" b - - 0 1"))

        with self.assertRaises(FENValidationError):
            fen_to_board("9/9 w - - 0 1")
        with self.assertRaises(FENValidationError):
            fen_to_board("rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNZ w - - 0 1")
        self.assertFalse(validate_fen("9/9 w - - 0 1"))

    def test_board_to_fen_accepts_legacy_mapping(self):
        fen = board_to_fen({"0,0": "r", "4,9": "K"}, turn="r")

        self.assertEqual(fen, "r8/9/9/9/9/9/9/9/9/4K4 w - - 0 1")

    def test_chinese_notation_uses_board_piece_and_side_orientation(self):
        self.assertEqual(move_to_chinese("b2b5", START_FEN, True), "\u70ae\u516b\u9032\u4e09")
        self.assertEqual(move_to_chinese("a9a8", START_FEN, False), "\u8eca\u4e00\u9032\u4e00")
        self.assertEqual(move_to_chinese("zzzz", START_FEN, True), "zzzz")

    def test_legacy_motion_planner_now_resolves_world_coordinates(self):
        mapper = Kinematics()
        mapper.update_calibration(
            origin_x=100,
            origin_y=200,
            square_size_x=10,
            square_size_y=20,
            persist=False,
        )
        planner = MotionPlanner(CoordinateSystem(robot_kinematics=mapper))

        commands = planner.plan_move("a0a1")

        self.assertEqual(len(commands), 11)
        self.assertIn("X100.00 Y200.00", commands[1])
        self.assertIn("X100.00 Y220.00", commands[6])


if __name__ == "__main__":
    unittest.main()
