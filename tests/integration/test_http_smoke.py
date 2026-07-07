import unittest
import os


class TestHttpSmoke(unittest.TestCase):
    def _auth_headers(self, client):
        from backend.utils import config

        login = client.post("/api/login", json={"username": "admin", "password": config.ADMIN_PASSWORD})
        token = (login.get_json() or {}).get("token")
        return {"Authorization": f"Bearer {token}"}

    def test_health_importable(self):
        os.environ.setdefault("FAKE_VISION", "1")
        # Importing app factory should not execute network I/O and should wire routes.
        from backend.main import create_app

        app, _socketio = create_app()
        client = app.test_client()
        denied = client.get("/api/health")
        self.assertEqual(denied.status_code, 401)

        resp = client.get("/api/health", headers=self._auth_headers(client))
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json() or {}
        self.assertIn("ok", data)

    def test_login_endpoint_accepts_configured_admin_password(self):
        os.environ.setdefault("FAKE_VISION", "1")
        from backend.main import create_app
        from backend.utils import config

        app, _socketio = create_app()
        client = app.test_client()
        resp = client.post("/api/login", json={"username": "admin", "password": config.ADMIN_PASSWORD})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json() or {}
        self.assertTrue(data.get("token"))
        self.assertIn("token=", resp.headers.get("Set-Cookie", ""))

        from backend.utils.auth import decode_jwt_token
        claims = decode_jwt_token(data.get("token"))
        self.assertEqual(claims.get("role"), "admin")
        self.assertIn("iat", claims)
        self.assertIn("jti", claims)
        self.assertIn("sub", claims)
        self.assertEqual(data.get("auth_mode"), "cookie")
        self.assertEqual(data.get("token_storage"), "cookie")
        self.assertGreater(data.get("expires_in", 0), 0)

    def test_logout_revokes_current_jwt(self):
        os.environ.setdefault("FAKE_VISION", "1")
        from backend.main import create_app
        from backend.utils import config

        app, _socketio = create_app()
        client = app.test_client()
        login = client.post("/api/login", json={"username": "admin", "password": config.ADMIN_PASSWORD})
        token = (login.get_json() or {}).get("token")
        headers = {"Authorization": f"Bearer {token}"}

        before = client.get("/api/health", headers=headers)
        self.assertEqual(before.status_code, 200)

        logout = client.post("/api/logout", headers=headers)
        self.assertEqual(logout.status_code, 200)

        after = client.get("/api/health", headers=headers)
        self.assertEqual(after.status_code, 401)

    def test_security_headers_are_present(self):
        os.environ.setdefault("FAKE_VISION", "1")
        from backend.main import create_app

        app, _socketio = create_app()
        client = app.test_client()
        resp = client.get("/api/ready")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(resp.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(resp.headers.get("Referrer-Policy"), "no-referrer")
        self.assertIn("default-src 'self'", resp.headers.get("Content-Security-Policy", ""))

    def test_player_endpoints_require_operator_auth(self):
        os.environ.setdefault("FAKE_VISION", "1")
        from backend.main import create_app

        app, _socketio = create_app()
        client = app.test_client()

        player_start = client.post("/api/player/start", json={"source": "unit-test"})
        self.assertEqual(player_start.status_code, 401)

        admin_move = client.post("/api/move", json={"move": "b2b5", "player": "human"})
        self.assertEqual(admin_move.status_code, 401)

        player_move = client.post("/api/player/move", json={"move": "b2b5", "player": "human"})
        self.assertEqual(player_move.status_code, 401)

        headers = self._auth_headers(client)
        player_start = client.post("/api/player/start", json={"source": "unit-test"}, headers=headers)
        self.assertEqual(player_start.status_code, 200)
        self.assertEqual((player_start.get_json() or {}).get("action"), "player_start")

        player_move = client.post(
            "/api/player/move",
            json={"move": "b2b5", "player": "human"},
            headers=headers,
        )
        self.assertEqual(player_move.status_code, 200)
        self.assertEqual((player_move.get_json() or {}).get("move"), "b2b5")

    def test_setup_preflight_and_hardware_test_require_setup_auth(self):
        os.environ.setdefault("FAKE_VISION", "1")
        from backend.main import create_app
        from backend.utils import config
        import tempfile
        from pathlib import Path

        old_report_path = getattr(config, "COMMISSIONING_REPORT_FILE", None)
        with tempfile.TemporaryDirectory() as tmp:
            try:
                config.COMMISSIONING_REPORT_FILE = str(Path(tmp) / "commissioning.json")
                app, _socketio = create_app()
                client = app.test_client()

                self.assertEqual(client.get("/api/setup/preflight").status_code, 401)
                self.assertEqual(client.get("/api/setup/commissioning").status_code, 401)
                headers = self._auth_headers(client)

                commissioning = client.get("/api/setup/commissioning", headers=headers)
                self.assertEqual(commissioning.status_code, 200)
                self.assertIn("commissioning", commissioning.get_json() or {})

                preflight = client.get("/api/setup/preflight", headers=headers)
                self.assertEqual(preflight.status_code, 200)
                self.assertIn("checks", preflight.get_json() or {})
                self.assertIn("commissioning", preflight.get_json() or {})

                hardware = client.post(
                    "/api/setup/hardware-test",
                    json={"action": "status", "dry_run": True},
                    headers=headers,
                )
                self.assertEqual(hardware.status_code, 200)
                self.assertEqual((hardware.get_json() or {}).get("action"), "status")
                self.assertIn("commissioning", hardware.get_json() or {})

                for action in ("write_pose", "corner_a0", "corner_i0", "corner_a9", "corner_i9", "center_e4", "grab_z"):
                    with self.subTest(action=action):
                        response = client.post(
                            "/api/setup/hardware-test",
                            json={"action": action, "dry_run": True},
                            headers=headers,
                        )
                        self.assertEqual(response.status_code, 200)
                        payload = response.get_json() or {}
                        self.assertEqual(payload.get("action"), action)
                        self.assertTrue(payload.get("dry_run"))
                        self.assertIn("target", payload)
            finally:
                config.COMMISSIONING_REPORT_FILE = old_report_path

    def test_player_estop_is_public_stop_only_entrypoint(self):
        os.environ.setdefault("FAKE_VISION", "1")
        from backend.main import create_app
        from backend.application.services.estop import estop

        app, _socketio = create_app()
        client = app.test_client()
        try:
            response = client.post("/api/player/estop", json={"reason": "test"})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(estop.GLOBAL_STOP)
        finally:
            estop.reset()

    def test_dashboard_requires_auth_and_uses_local_assets(self):
        os.environ.setdefault("FAKE_VISION", "1")
        from backend.main import create_app
        from backend.utils import config

        app, _socketio = create_app()
        client = app.test_client()
        denied = client.get("/dashboard")
        self.assertEqual(denied.status_code, 401)

        login = client.post("/api/login", json={"username": "admin", "password": config.ADMIN_PASSWORD})
        token = (login.get_json() or {}).get("token")
        resp = client.get("/dashboard", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        resp.close()
        self.assertIn("/static/vendor/socket.io.min.js", html)
        self.assertIn("/dashboard/static/dashboard.js", html)
        self.assertNotIn("cdn.socket.io", html)
        self.assertNotIn("fonts.googleapis.com", html)
        self.assertNotIn("innerHTML", html)

    def test_login_rate_limit_returns_standard_error(self):
        os.environ.setdefault("FAKE_VISION", "1")
        from backend.main import create_app
        from backend.utils import config
        from backend.utils.rate_limit import rate_limiter

        old_limit = config.LOGIN_RATE_LIMIT_PER_MINUTE
        old_enabled = config.RATE_LIMITS_ENABLED
        config.LOGIN_RATE_LIMIT_PER_MINUTE = 1
        config.RATE_LIMITS_ENABLED = True
        rate_limiter.clear()
        try:
            app, _socketio = create_app()
            client = app.test_client()
            first = client.post("/api/login", json={"username": "admin", "password": "wrong"})
            second = client.post("/api/login", json={"username": "admin", "password": "wrong"})
        finally:
            config.LOGIN_RATE_LIMIT_PER_MINUTE = old_limit
            config.RATE_LIMITS_ENABLED = old_enabled
            rate_limiter.clear()

        self.assertEqual(first.status_code, 401)
        self.assertEqual(second.status_code, 429)
        payload = second.get_json() or {}
        self.assertEqual(payload.get("code"), "rate_limited")
        self.assertIn("retry_after_seconds", payload.get("details") or {})

    def test_login_rate_limit_ignores_untrusted_x_forwarded_for(self):
        os.environ.setdefault("FAKE_VISION", "1")
        from backend.main import create_app
        from backend.utils import config
        from backend.utils.rate_limit import rate_limiter

        old_limit = config.LOGIN_RATE_LIMIT_PER_MINUTE
        old_enabled = config.RATE_LIMITS_ENABLED
        old_trust_xff = getattr(config, "TRUST_X_FORWARDED_FOR", False)
        old_trusted_proxies = getattr(config, "TRUSTED_PROXY_IPS", ())
        config.LOGIN_RATE_LIMIT_PER_MINUTE = 1
        config.RATE_LIMITS_ENABLED = True
        config.TRUST_X_FORWARDED_FOR = False
        config.TRUSTED_PROXY_IPS = ()
        rate_limiter.clear()
        try:
            app, _socketio = create_app()
            client = app.test_client()
            first = client.post(
                "/api/login",
                json={"username": "admin", "password": "wrong"},
                headers={"X-Forwarded-For": "203.0.113.10"},
                environ_overrides={"REMOTE_ADDR": "198.51.100.77"},
            )
            second = client.post(
                "/api/login",
                json={"username": "admin", "password": "wrong"},
                headers={"X-Forwarded-For": "203.0.113.11"},
                environ_overrides={"REMOTE_ADDR": "198.51.100.77"},
            )
        finally:
            config.LOGIN_RATE_LIMIT_PER_MINUTE = old_limit
            config.RATE_LIMITS_ENABLED = old_enabled
            config.TRUST_X_FORWARDED_FOR = old_trust_xff
            config.TRUSTED_PROXY_IPS = old_trusted_proxies
            rate_limiter.clear()

        self.assertEqual(first.status_code, 401)
        self.assertEqual(second.status_code, 429)

    def test_login_rate_limit_can_trust_xff_from_configured_proxy(self):
        os.environ.setdefault("FAKE_VISION", "1")
        from backend.main import create_app
        from backend.utils import config
        from backend.utils.rate_limit import rate_limiter

        old_limit = config.LOGIN_RATE_LIMIT_PER_MINUTE
        old_enabled = config.RATE_LIMITS_ENABLED
        old_trust_xff = getattr(config, "TRUST_X_FORWARDED_FOR", False)
        old_trusted_proxies = getattr(config, "TRUSTED_PROXY_IPS", ())
        config.LOGIN_RATE_LIMIT_PER_MINUTE = 1
        config.RATE_LIMITS_ENABLED = True
        config.TRUST_X_FORWARDED_FOR = True
        config.TRUSTED_PROXY_IPS = ("10.0.0.10",)
        rate_limiter.clear()
        try:
            app, _socketio = create_app()
            client = app.test_client()
            first = client.post(
                "/api/login",
                json={"username": "admin", "password": "wrong"},
                headers={"X-Forwarded-For": "203.0.113.20"},
                environ_overrides={"REMOTE_ADDR": "10.0.0.10"},
            )
            second = client.post(
                "/api/login",
                json={"username": "admin", "password": "wrong"},
                headers={"X-Forwarded-For": "203.0.113.21"},
                environ_overrides={"REMOTE_ADDR": "10.0.0.10"},
            )
        finally:
            config.LOGIN_RATE_LIMIT_PER_MINUTE = old_limit
            config.RATE_LIMITS_ENABLED = old_enabled
            config.TRUST_X_FORWARDED_FOR = old_trust_xff
            config.TRUSTED_PROXY_IPS = old_trusted_proxies
            rate_limiter.clear()

        self.assertEqual(first.status_code, 401)
        self.assertEqual(second.status_code, 401)
