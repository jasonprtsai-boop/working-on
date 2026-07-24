import unittest
import base64
from unittest.mock import patch

from flask import Flask
import numpy as np

from backend.interfaces.api import vision_routes


class TestVisionSourceRoutes(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)

    def test_vision_source_status_returns_active_source(self):
        with self.app.test_request_context("/api/vision/source/status"):
            with patch.object(
                vision_routes,
                "runtime_vision_status",
                return_value={"camera": {"source": "tmflow_json", "running": True, "connected": False}},
            ):
                with patch.object(vision_routes.config, "ROBOT_PORT", 5890):
                    with patch.object(vision_routes.config, "VISION_TMFLOW_IMAGE_PORT", 5891):
                        response = vision_routes.vision_source_status()

        data = response.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["source"], "tmflow_json")
        self.assertIn("tmflow_json", data["config"])
        self.assertEqual(data["diagnostics"]["control_channel"]["port"], 5890)
        self.assertEqual(data["diagnostics"]["vision_channel"]["port"], 5891)
        self.assertEqual(data["diagnostics"]["vision_channel"]["last_frame_age_sec"], None)
        self.assertEqual(data["diagnostics"]["vision_channel"]["reconnects"], 0)

    def test_inject_vision_source_test_frame_generates_synthetic_frame(self):
        with self.app.test_request_context(
            "/api/vision/source/test-frame",
            method="POST",
            json={"mode": "synthetic", "width": 320, "height": 240},
        ):
            with patch.object(vision_routes, "runtime_vision_status", return_value={"camera": {"source": "opencv"}}):
                response = vision_routes.inject_vision_source_test_frame()

        data = response.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["mode"], "synthetic")
        self.assertEqual(data["frames_injected"], 3)
        self.assertEqual(data["frame_size"], [320, 240])

    def test_issue_vision_stream_token_returns_scoped_ticket(self):
        with self.app.test_request_context("/api/vision/stream-token", method="POST"):
            response = vision_routes.issue_vision_stream_token()

        data = response.get_json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["stream_token"])
        self.assertEqual(data["expires_in"], 300)

    def test_tmflow_frame_push_accepts_lab_loopback_jpeg_payload(self):
        try:
            import cv2
        except Exception as exc:  # pragma: no cover - depends on optional vision runtime
            self.skipTest(f"OpenCV unavailable: {exc}")

        frame = np.zeros((12, 16, 3), dtype=np.uint8)
        ok, encoded = cv2.imencode(".jpg", frame)
        self.assertTrue(ok)
        payload = {"image": base64.b64encode(encoded.tobytes()).decode("ascii")}

        with self.app.test_request_context(
            "/api/vision/tmflow/frame",
            method="POST",
            json=payload,
            environ_base={"REMOTE_ADDR": "127.0.0.1"},
        ):
            with patch.object(vision_routes, "vision_system", object()):
                response = vision_routes.ingest_tmflow_frame()

        data = response.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["mode"], "tmflow_http_push")
        self.assertEqual(data["frame_size"], [16, 12])

    def test_tmflow_frame_push_requires_key_in_production(self):
        with self.app.test_request_context(
            "/api/vision/tmflow/frame",
            method="POST",
            json={"image": "abc"},
            environ_base={"REMOTE_ADDR": "192.168.10.10"},
        ):
            with patch.object(vision_routes.config, "IS_PRODUCTION", True):
                with patch.object(vision_routes.config, "VISION_TMFLOW_INGEST_KEY", ""):
                    response, status = vision_routes.ingest_tmflow_frame()

        self.assertEqual(status, 401)
        self.assertEqual(response.get_json()["code"], "tmflow_frame_ingest_unauthorized")

    def test_tmflow_frame_push_accepts_configured_ingest_key(self):
        with self.app.test_request_context(
            "/api/vision/tmflow/frame",
            method="POST",
            json={"image": "abc"},
            headers={"X-TMflow-Key": "secret-key"},
            environ_base={"REMOTE_ADDR": "192.168.10.10"},
        ):
            with patch.object(vision_routes.config, "IS_PRODUCTION", True):
                with patch.object(vision_routes.config, "VISION_TMFLOW_INGEST_KEY", "secret-key"):
                    with patch.object(
                        vision_routes,
                        "_ingest_frame_payload",
                        return_value={"ok": True, "frame_size": [16, 12]},
                    ):
                        response = vision_routes.ingest_tmflow_frame()

        data = response.get_json()
        self.assertTrue(data["ok"])


if __name__ == "__main__":
    unittest.main()
