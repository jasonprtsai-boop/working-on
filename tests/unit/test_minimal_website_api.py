from __future__ import annotations

import unittest
from unittest.mock import patch

from flask import Flask, Response

from backend.interfaces.api.shared import api_bp
from backend.interfaces.api import control_routes, diagnostics_routes, vision_routes  # noqa: F401
from backend.interfaces.api import auth_guard
from backend.infrastructure.vision.capture_session import vision_capture_session


class MinimalWebsiteApiTest(unittest.TestCase):
    def setUp(self):
        vision_capture_session.stop(reason="test_setup")
        self.app = Flask(__name__)
        self.app.config["TESTING"] = True
        self.app.register_blueprint(api_bp, url_prefix="/api")
        self.client = self.app.test_client()

    def tearDown(self):
        vision_capture_session.stop(reason="test_teardown")

    def test_player_done_starts_backend_recognition(self):
        with patch.object(vision_routes, "_vision_capture_available_status", return_value={}):
            response = self.client.post("/api/player-done", json={"source": "test"})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["action"], "player_done")
        self.assertTrue(payload["capture_session"]["active"])
        self.assertEqual(payload["capture_session"]["source"], "player_done")

    def test_stop_alias_publishes_pause_event(self):
        with patch.object(control_routes, "publish_base_event", return_value="trace-pause") as publish:
            response = self.client.post("/api/stop", json={"reason": "test_stop"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["action"], "stop")
        publish.assert_called_once()
        self.assertEqual(publish.call_args.kwargs["payload"]["reason"], "test_stop")

    def test_events_returns_compact_monitor_payload(self):
        with patch.object(auth_guard.config, "CONTROL_AUTH_REQUIRED", False, create=True):
            response = self.client.get("/api/events?limit=5")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertIn("events", payload)
        self.assertIn("pipeline", payload)

    def test_camera_latest_uses_existing_snapshot_source(self):
        with patch.object(vision_routes, "snapshot", return_value=Response(b"jpg", mimetype="image/jpeg")):
            with patch.object(auth_guard.config, "CONTROL_AUTH_REQUIRED", False, create=True):
                response = self.client.get("/api/camera/latest")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/jpeg")
        self.assertEqual(response.data, b"jpg")


if __name__ == "__main__":
    unittest.main()
