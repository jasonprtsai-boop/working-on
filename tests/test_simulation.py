import os
import unittest


class TestLegacySimulationCompatibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("FAKE_VISION", "1")
        from backend.main import create_app

        cls.app, _socketio = create_app()
        cls.client = cls.app.test_client()
        from backend.utils import config

        login = cls.client.post("/api/login", json={"username": "admin", "password": config.ADMIN_PASSWORD})
        token = (login.get_json() or {}).get("token")
        cls.auth_headers = {"Authorization": f"Bearer {token}"}

    def test_ready_and_vision_status_are_import_safe(self):
        ready = self.client.get("/api/ready")
        self.assertEqual(ready.status_code, 200)
        ready_payload = ready.get_json() or {}
        self.assertIn("ready", ready_payload)

        vision = self.client.get("/api/vision/status", headers=self.auth_headers)
        self.assertEqual(vision.status_code, 200)
        vision_payload = vision.get_json() or {}
        self.assertIn("system", vision_payload)
        self.assertIn("models", vision_payload)


if __name__ == "__main__":
    unittest.main()
