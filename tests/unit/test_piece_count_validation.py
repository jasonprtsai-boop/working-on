from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from backend.infrastructure.vision.confidence_estimator import ConfidenceEstimator
from backend.utils.fen.parser import (
    INITIAL_XIANGQI_PIECE_COUNT,
    count_fen_pieces,
    validate_piece_count,
)


class TestPieceCountValidation(unittest.TestCase):
    def test_initial_fen_piece_count_is_32(self):
        initial_fen = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
        counts = count_fen_pieces(initial_fen)
        self.assertEqual(counts["total"], INITIAL_XIANGQI_PIECE_COUNT)
        self.assertEqual(counts["red"], 16)
        self.assertEqual(counts["black"], 16)

    def test_fen_after_capture_decrements(self):
        # Red cannon captures black horse at b7 -> 31 pieces (16 red, 15 black)
        capture_fen = "r1bakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR b - - 0 1"
        counts = count_fen_pieces(capture_fen)
        self.assertEqual(counts["total"], 31)
        self.assertEqual(counts["red"], 16)
        self.assertEqual(counts["black"], 15)

    def test_validate_piece_count_normal_and_capture(self):
        # Equal count
        valid, status = validate_piece_count(32, 32, allow_capture=True)
        self.assertTrue(valid)
        self.assertEqual(status, "count_match")

        # Capture decremented
        valid, status = validate_piece_count(31, 32, allow_capture=True)
        self.assertTrue(valid)
        self.assertEqual(status, "capture_decremented")

        # Capture not allowed mode
        valid, status = validate_piece_count(31, 32, allow_capture=False)
        self.assertFalse(valid)
        self.assertTrue(status.startswith("missing_pieces"))

        # Missing piece (dropped or occluded)
        valid, status = validate_piece_count(30, 32, allow_capture=True)
        self.assertFalse(valid)
        self.assertEqual(status, "missing_pieces_1")

        # Extra piece (ghost detection or clutter)
        valid, status = validate_piece_count(33, 32, allow_capture=True)
        self.assertFalse(valid)
        self.assertEqual(status, "extra_pieces_1")

    def test_confidence_estimator(self):
        # Exact count gives high score
        score = ConfidenceEstimator.estimate(32, expected_count=32)
        self.assertGreaterEqual(score, 0.9)

        # Capture count is tolerated without count penalty
        capture_score = ConfidenceEstimator.estimate(31, expected_count=32, allow_capture=True)
        self.assertEqual(score, capture_score)

        # Missing pieces lowers count confidence
        low_score = ConfidenceEstimator.estimate(20, expected_count=32)
        self.assertLess(low_score, score)

        # Evaluate count helper
        eval_ok = ConfidenceEstimator.evaluate_count(32, 32)
        self.assertTrue(eval_ok["valid"])
        self.assertEqual(eval_ok["difference"], 0)

        eval_missing = ConfidenceEstimator.evaluate_count(28, 32)
        self.assertFalse(eval_missing["valid"])
        self.assertEqual(eval_missing["status"], "missing")
        self.assertEqual(eval_missing["difference"], -4)

    def test_vision_service_force_sync_resets_validator(self):
        from backend.application.services.vision_service import VisionService
        from backend.events.event_types import EventType
        from backend.events.models.base_event import BaseEvent

        vs = VisionService()
        mock_validator = MagicMock()
        mock_validator.last_stable_state = {}
        mock_validator.last_confidence = 0.95
        vs._vision.validator = mock_validator
        vs._vision.get_status = MagicMock(return_value={"mode": "simulated", "available": True, "simulation": True})

        event = BaseEvent.create(
            event_type=EventType.UI_ACTION,
            payload={"action": "FORCE_SYNC"},
            source="test",
        )
        vs.on_ui_action(event)
        mock_validator.reset.assert_called_once()

    def test_count_fen_piece_types_initial(self):
        from backend.utils.fen.parser import count_fen_piece_types, INITIAL_PIECE_COUNTS
        initial_fen = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
        counts = count_fen_piece_types(initial_fen)
        for piece, exp in INITIAL_PIECE_COUNTS.items():
            self.assertEqual(counts[piece], exp, f"Mismatch for piece {piece}")

    def test_count_board_piece_types(self):
        from backend.utils.fen.parser import count_board_piece_types
        board_state = {
            "0,0": "r", "1,0": "n", "2,0": "b", "3,0": "a", "4,0": "k",
            "0,9": "R", "1,9": "N", "2,9": "B", "3,9": "A", "4,9": "K",
        }
        counts = count_board_piece_types(board_state)
        self.assertEqual(counts["r"], 1)
        self.assertEqual(counts["R"], 1)
        self.assertEqual(counts["k"], 1)
        self.assertEqual(counts["K"], 1)
        self.assertEqual(counts["P"], 0)

    def test_validate_piece_types_matching_and_capture(self):
        from backend.utils.fen.parser import (
            count_fen_piece_types,
            validate_piece_types,
            INITIAL_PIECE_COUNTS,
        )
        # 1. Exact match on initial board
        res = validate_piece_types(INITIAL_PIECE_COUNTS, INITIAL_PIECE_COUNTS, moving_side="w")
        self.assertTrue(res["valid"])
        self.assertEqual(res["status"], "count_match")
        self.assertEqual(res["total"], 32)
        self.assertEqual(len(res["mismatches"]), 0)
        self.assertIn("完全吻合", res["summary_message"])

        # 2. Legal capture: Red captures Black Horse 'n'
        captured_counts = dict(INITIAL_PIECE_COUNTS)
        captured_counts["n"] -= 1
        res_cap = validate_piece_types(captured_counts, INITIAL_PIECE_COUNTS, moving_side="w", allow_capture=True)
        self.assertTrue(res_cap["valid"])
        self.assertEqual(res_cap["status"], "capture_decremented")
        self.assertEqual(res_cap["captured_piece"], "n")
        self.assertEqual(res_cap["total"], 31)
        self.assertIn("黑馬", res_cap["summary_message"])

        # 3. Illegal piece type mismatch: Red gets extra Rook 'R' and misses Cannon 'C'
        tampered_counts = dict(INITIAL_PIECE_COUNTS)
        tampered_counts["R"] += 1
        tampered_counts["C"] -= 1
        res_err = validate_piece_types(tampered_counts, INITIAL_PIECE_COUNTS, moving_side="w")
        self.assertFalse(res_err["valid"])
        self.assertEqual(res_err["status"], "piece_type_mismatch")
        self.assertEqual(len(res_err["mismatches"]), 2)
        self.assertIn("紅俥多 1 顆", res_err["summary_message"])
        self.assertIn("紅炮少 1 顆", res_err["summary_message"])

        # 4. Moving side loses piece on own turn (illegal!)
        own_loss_counts = dict(INITIAL_PIECE_COUNTS)
        own_loss_counts["P"] -= 1
        res_own_err = validate_piece_types(own_loss_counts, INITIAL_PIECE_COUNTS, moving_side="w", allow_capture=True)
        self.assertFalse(res_own_err["valid"])
        self.assertIn("紅兵少 1 顆", res_own_err["summary_message"])

    def test_confidence_estimator_piece_types(self):
        from backend.utils.fen.parser import INITIAL_PIECE_COUNTS
        res = ConfidenceEstimator.evaluate_piece_types(INITIAL_PIECE_COUNTS, INITIAL_PIECE_COUNTS)
        self.assertTrue(res["valid"])
        self.assertEqual(res["total"], 32)

    def test_capture_seconds_config(self):
        from backend.utils import config
        self.assertGreater(float(getattr(config, "VISION_USER_CAPTURE_INTERVAL_SEC", 0)), 0)
        self.assertGreater(float(getattr(config, "VISION_USER_CAPTURE_TIMEOUT_SEC", 0)), 0)


if __name__ == "__main__":
    unittest.main()
