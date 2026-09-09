from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from flask import Flask

from backend.interfaces.api.shared import api_bp
from backend.interfaces.api import auth_guard, setup_routes  # noqa: F401


class SetupHardwareConfirmationTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config["TESTING"] = True
        self.app.register_blueprint(api_bp, url_prefix="/api")
        self.client = self.app.test_client()

    def test_live_motion_requires_confirmation_before_robot_lookup(self):
        with patch.object(auth_guard.config, "CONTROL_AUTH_REQUIRED", False, create=True):
            with patch.object(setup_routes, "_robot_facade") as robot_facade:
                response = self.client.post(
                    "/api/setup/hardware-test",
                    json={"action": "safe_z", "dry_run": False},
                )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["code"], "invalid_hardware_test")
        robot_facade.assert_not_called()

    def test_live_one_move_accepts_explicit_confirmation(self):
        robot = SimpleNamespace(execute_move=Mock(return_value=True))

        with patch.object(auth_guard.config, "CONTROL_AUTH_REQUIRED", False, create=True):
            with patch.object(setup_routes, "_robot_facade", return_value=robot):
                with patch.object(setup_routes, "record_hardware_test", return_value={}):
                    response = self.client.post(
                        "/api/setup/hardware-test",
                        json={
                            "action": "one_move",
                            "dry_run": False,
                            "confirmed_action": "one_move",
                            "warning_acknowledged": True,
                        },
                    )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        robot.execute_move.assert_called_once_with("a0a1", is_capture=False)


if __name__ == "__main__":
    unittest.main()
