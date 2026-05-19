import unittest
import os


class TestMJPEGSmoke(unittest.TestCase):
    def test_mjpeg_stream_returns_multipart(self):
        os.environ.setdefault("FAKE_VISION", "1")
        from backend.main import create_app
        from backend.utils import config

        app, _socketio = create_app()
        client = app.test_client()
        denied = client.get("/api/vision/stream")
        self.assertEqual(denied.status_code, 401)

        login = client.post("/api/login", json={"username": "admin", "password": config.ADMIN_PASSWORD})
        token = (login.get_json() or {}).get("token")
        resp = client.get("/api/vision/stream", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(resp.status_code, 200)
        ctype = resp.headers.get("Content-Type", "")
        self.assertIn("multipart/x-mixed-replace", ctype)

        # Read a small chunk from the generator to ensure it yields bytes.
        it = iter(resp.response)
        first = next(it)
        self.assertIsInstance(first, (bytes, bytearray))
        self.assertTrue(first.startswith(b"--frame") or b"Content-Type: image/jpeg" in first)
