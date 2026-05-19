import unittest


class TestRuntimeSmoke(unittest.TestCase):
    def _auth_headers(self, client):
        from backend.utils import config

        login = client.post("/api/login", json={"username": "admin", "password": config.ADMIN_PASSWORD})
        token = (login.get_json() or {}).get("token")
        return {"Authorization": f"Bearer {token}"}

    def test_app_factory_and_health(self):
        # Import should not start the server or spawn duplicate workers.
        from backend.main import create_app

        app, _socketio = create_app()
        client = app.test_client()

        r = client.get("/api/ready")
        self.assertEqual(r.status_code, 200)

        denied = client.get("/api/health")
        self.assertEqual(denied.status_code, 401)

        r = client.get("/api/health", headers=self._auth_headers(client))
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn("engine", data)
        self.assertIn("vision", data)

    def test_root_renders_html_instead_of_raw_template_source(self):
        from backend.main import create_app

        app, _socketio = create_app()
        client = app.test_client()

        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("<!DOCTYPE html>", body)
        self.assertNotIn("{% extends", body)
        self.assertIn('/static/vendor/socket.io.min.js', body)
        self.assertNotIn('/socket.io/socket.io.js', body)

        socket_client = client.get('/static/vendor/socket.io.min.js')
        try:
            self.assertEqual(socket_client.status_code, 200)
            self.assertIn('io', socket_client.get_data(as_text=True)[:2000])
        finally:
            socket_client.close()


if __name__ == "__main__":
    unittest.main()
