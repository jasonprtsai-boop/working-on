from __future__ import annotations

import unittest

from backend.core.rules import ChessLogic


class GameEndDetectionTest(unittest.TestCase):
    def test_missing_black_general_ends_game_for_red(self):
        result = ChessLogic.game_result("9/9/9/9/9/9/9/9/9/4K4 b - - 0 1")

        self.assertTrue(result["ended"])
        self.assertEqual(result["winner"], "red")
        self.assertEqual(result["reason"], "black_general_missing")

    def test_initial_position_is_not_finished(self):
        result = ChessLogic.game_result(
            "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
        )

        self.assertFalse(result["ended"])
        self.assertGreater(result["legal_moves_count"], 0)


if __name__ == "__main__":
    unittest.main()
