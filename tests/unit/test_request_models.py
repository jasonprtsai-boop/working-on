import unittest

from pydantic import ValidationError

from backend.interfaces.api.request_models import MoveRequest
from backend.interfaces.shared.schemas import ControlCommandSchema


class TestRequestModels(unittest.TestCase):
    def test_move_request_accepts_ucci_like_coordinate_move(self):
        payload = MoveRequest(move="h2e2")
        self.assertEqual(payload.move, "h2e2")
        self.assertEqual(payload.player, "human")

    def test_move_request_rejects_invalid_coordinate(self):
        with self.assertRaises(ValidationError):
            MoveRequest(move="j2e2")

        with self.assertRaises(ValidationError):
            MoveRequest(move="bad")

    def test_control_command_normalizes_allowed_actions(self):
        self.assertEqual(ControlCommandSchema(action="START").action, "start_engine")
        self.assertEqual(ControlCommandSchema(action="SYNC_VISION").action, "sync_vision")
        self.assertEqual(ControlCommandSchema(action="reset").action, "reset")

    def test_control_command_rejects_unknown_action(self):
        with self.assertRaises(ValidationError):
            ControlCommandSchema(action="delete_database")


if __name__ == "__main__":
    unittest.main()
