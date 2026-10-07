from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from flask import Flask

from backend.interfaces.api.shared import api_bp
from backend.interfaces.api import auth_guard, robot_routes  # noqa: F401


class RobotPlayAuthTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config["TESTING"] = True
        self.app.register_blueprint(api_bp, url_prefix="/api")
        self.client = self.app.test_client()

    def test_robot_play_requires_control_auth(self):
        with patch.object(auth_guard.config, "CONTROL_AUTH_REQUIRED", True, create=True):
            with patch.object(auth_guard.config, "RATE_LIMITS_ENABLED", False, create=True):
                response = self.client.post("/api/robot/play")

        self.assertEqual(response.status_code, 401)

    def test_robot_play_blocks_when_preflight_fails(self):
        preflight = {
            "ok": False,
            "ready": False,
            "failures": [{"key": "vision_ready", "message": "Vision is unavailable."}],
            "warnings": [],
        }

        with patch.object(auth_guard.config, "CONTROL_AUTH_REQUIRED", True, create=True):
            with patch.object(auth_guard.config, "RATE_LIMITS_ENABLED", False, create=True):
                with patch.object(auth_guard, "verify_request_token", return_value={"role": "setup"}):
                    with patch.object(robot_routes, "build_preflight_report", return_value=preflight):
                        response = self.client.post(
                            "/api/robot/play",
                            json={"confirmed_action": "robot_play", "warning_acknowledged": True},
                        )

        self.assertEqual(response.status_code, 409)
        payload = response.get_json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["code"], "robot_preflight_failed")

    def test_robot_play_requires_warning_confirmation(self):
        with patch.object(auth_guard.config, "CONTROL_AUTH_REQUIRED", True, create=True):
            with patch.object(auth_guard.config, "RATE_LIMITS_ENABLED", False, create=True):
                with patch.object(auth_guard, "verify_request_token", return_value={"role": "setup"}):
                    response = self.client.post("/api/robot/play", json={})

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["code"], "robot_play_confirmation_required")

    def test_robot_play_allows_setup_role_after_preflight_passes(self):
        write_register = Mock(return_value=True)
        robot = SimpleNamespace(adapter=SimpleNamespace(_write_register=write_register, _role=Mock(return_value="client")))
        preflight = {"ok": True, "ready": True, "failures": [], "warnings": []}

        with patch.object(auth_guard.config, "CONTROL_AUTH_REQUIRED", True, create=True):
            with patch.object(auth_guard.config, "RATE_LIMITS_ENABLED", False, create=True):
                with patch.object(auth_guard, "verify_request_token", return_value={"role": "setup"}):
                    with patch.object(robot_routes.config, "ROBOT_ADAPTER", "modbus", create=True):
                        with patch.object(robot_routes, "build_preflight_report", return_value=preflight):
                            with patch.object(robot_routes.container, "get", return_value=robot):
                                response = self.client.post(
                                    "/api/robot/play",
                                    json={"confirmed_action": "robot_play", "warning_acknowledged": True},
                                )

        self.assertEqual(response.status_code, 200)
        write_register.assert_called_once_with(7104, 1)

    def test_robot_play_rejects_modbus_server_mode(self):
        write_register = Mock(return_value=True)
        robot = SimpleNamespace(adapter=SimpleNamespace(
            _write_register=write_register,
            _role=Mock(return_value="server"),
            _payload_mode=Mock(return_value="square_command"),
        ))
        preflight = {"ok": True, "ready": True, "failures": [], "warnings": []}

        with patch.object(auth_guard.config, "CONTROL_AUTH_REQUIRED", True, create=True):
            with patch.object(auth_guard.config, "RATE_LIMITS_ENABLED", False, create=True):
                with patch.object(auth_guard, "verify_request_token", return_value={"role": "setup"}):
                    with patch.object(robot_routes.config, "ROBOT_ADAPTER", "modbus", create=True):
                        with patch.object(robot_routes, "build_preflight_report", return_value=preflight):
                            with patch.object(robot_routes.container, "get", return_value=robot):
                                response = self.client.post(
                                    "/api/robot/play",
                                    json={"confirmed_action": "robot_play", "warning_acknowledged": True},
                                )

        self.assertEqual(response.status_code, 409)
        payload = response.get_json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["code"], "unsupported_robot_play_mode")
        write_register.assert_not_called()

    def test_execute_ready_move_requires_setup_auth(self):
        with patch.object(auth_guard.config, "CONTROL_AUTH_REQUIRED", True, create=True):
            with patch.object(auth_guard.config, "RATE_LIMITS_ENABLED", False, create=True):
                response = self.client.post("/api/robot/execute-ready-move")

        self.assertEqual(response.status_code, 401)

    def test_execute_ready_move_requires_warning_confirmation(self):
        with patch.object(auth_guard.config, "CONTROL_AUTH_REQUIRED", True, create=True):
            with patch.object(auth_guard.config, "RATE_LIMITS_ENABLED", False, create=True):
                with patch.object(auth_guard, "verify_request_token", return_value={"role": "setup"}):
                    response = self.client.post("/api/robot/execute-ready-move", json={})

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["code"], "robot_execute_confirmation_required")

    def test_execute_ready_move_starts_latest_ai_move(self):
        robot = SimpleNamespace(get_status=Mock(return_value={"busy": False}), execute_move=Mock(return_value=True))
        preflight = {"ok": True, "ready": True, "failures": [], "warnings": []}

        with patch.object(auth_guard.config, "CONTROL_AUTH_REQUIRED", True, create=True):
            with patch.object(auth_guard.config, "RATE_LIMITS_ENABLED", False, create=True):
                with patch.object(auth_guard, "verify_request_token", return_value={"role": "setup"}):
                    with patch.object(robot_routes, "build_preflight_report", return_value=preflight):
                        with patch.object(robot_routes.container, "get", return_value=robot):
                            with patch.object(robot_routes, "_current_engine_best_move", return_value="a0a1"):
                                with patch.object(robot_routes, "_infer_capture_from_current_state", return_value=False):
                                    with patch.object(robot_routes.workflow_coordinator, "start_robot_move") as start_move:
                                        response = self.client.post(
                                            "/api/robot/execute-ready-move",
                                            json={
                                                "confirmed_action": "robot_execute_ready_move",
                                                "warning_acknowledged": True,
                                            },
                                        )

        self.assertEqual(response.status_code, 202)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["move"], "a0a1")
        start_move.assert_called_once()

    def test_execute_ready_move_rejects_active_workflow(self):
        robot = SimpleNamespace(get_status=Mock(return_value={"busy": False}), execute_move=Mock(return_value=True))
        preflight = {"ok": True, "ready": True, "failures": [], "warnings": []}

        with patch.object(auth_guard.config, "CONTROL_AUTH_REQUIRED", True, create=True):
            with patch.object(auth_guard.config, "RATE_LIMITS_ENABLED", False, create=True):
                with patch.object(auth_guard, "verify_request_token", return_value={"role": "setup"}):
                    with patch.object(robot_routes, "build_preflight_report", return_value=preflight):
                        with patch.object(robot_routes.container, "get", return_value=robot):
                            with patch.object(robot_routes.workflow_coordinator, "robot_command_active", return_value=True):
                                with patch.object(robot_routes.workflow_coordinator, "robot_activity_snapshot", return_value={"robot_future_active": True}):
                                    with patch.object(robot_routes.workflow_coordinator, "start_robot_move") as start_move:
                                        response = self.client.post(
                                            "/api/robot/execute-ready-move",
                                            json={
                                                "confirmed_action": "robot_execute_ready_move",
                                                "warning_acknowledged": True,
                                            },
                                        )

        self.assertEqual(response.status_code, 409)
        payload = response.get_json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["code"], "robot_busy")
        start_move.assert_not_called()

    def test_execute_ready_move_rejects_missing_ai_move(self):
        robot = SimpleNamespace(get_status=Mock(return_value={"busy": False}), execute_move=Mock(return_value=True))
        preflight = {"ok": True, "ready": True, "failures": [], "warnings": []}

        with patch.object(auth_guard.config, "CONTROL_AUTH_REQUIRED", True, create=True):
            with patch.object(auth_guard.config, "RATE_LIMITS_ENABLED", False, create=True):
                with patch.object(auth_guard, "verify_request_token", return_value={"role": "setup"}):
                    with patch.object(robot_routes, "build_preflight_report", return_value=preflight):
                        with patch.object(robot_routes.container, "get", return_value=robot):
                            with patch.object(robot_routes, "_current_engine_best_move", return_value=""):
                                response = self.client.post(
                                    "/api/robot/execute-ready-move",
                                    json={
                                        "confirmed_action": "robot_execute_ready_move",
                                        "warning_acknowledged": True,
                                    },
                                )

        self.assertEqual(response.status_code, 409)
        payload = response.get_json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["code"], "ai_move_unavailable")


if __name__ == "__main__":
    unittest.main()
