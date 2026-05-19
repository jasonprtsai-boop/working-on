import unittest

from backend.core.rules import ChessLogic


class TestChessLogic(unittest.TestCase):
    def setUp(self):
        self.start_fen = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"

    def test_validate_move_checks_ucci_format(self):
        self.assertTrue(ChessLogic.validate_move(self.start_fen, "h2e2"))
        self.assertFalse(ChessLogic.validate_move(self.start_fen, "bad"))
        self.assertFalse(ChessLogic.validate_move(self.start_fen, "j2e2"))

    def test_parse_move_extracts_piece(self):
        move = ChessLogic.parse_move(self.start_fen, "b2b5")
        self.assertEqual(move["from"], "b2")
        self.assertEqual(move["to"], "b5")
        self.assertEqual(move["piece"], "C")

    def test_apply_move_updates_board_and_turn(self):
        new_fen = ChessLogic.apply_move(self.start_fen, "b2b5")
        self.assertNotEqual(new_fen, self.start_fen)
        self.assertIn(" b ", f" {new_fen} ")

        parsed = ChessLogic.parse_move(new_fen, "b5b6")
        self.assertEqual(parsed["piece"], "C")


if __name__ == "__main__":
    unittest.main()
