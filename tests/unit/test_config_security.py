import os
import subprocess
import sys
import tempfile
import unittest


class TestConfigSecurity(unittest.TestCase):
    def test_production_rejects_weak_secret_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = self._production_env(tmpdir)
            env["CHESS_SECRET_KEY"] = "change-me"
            result = self._import_config(env)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CHESS_SECRET_KEY", result.stderr + result.stdout)

    def test_production_rejects_secret_key_containing_change_me(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = self._production_env(tmpdir)
            env["CHESS_SECRET_KEY"] = "smart-chess-production-secret-change-me-2026"
            result = self._import_config(env)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CHESS_SECRET_KEY", result.stderr + result.stdout)

    def test_production_rejects_test_mode_cors_and_disabled_auth(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = self._production_env(tmpdir)
            env.update({
                "TEST_MODE": "1",
                "CORS_ALLOWED_ORIGINS": "*",
                "CONTROL_AUTH_REQUIRED": "0",
                "SOCKET_PUBLIC_SNAPSHOT_ENABLED": "1",
                "EVENTBUS_ALLOW_LEGACY_DICT_EVENTS": "1",
            })
            result = self._import_config(env)

        output = result.stderr + result.stdout
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("TEST_MODE", output)
        self.assertIn("CORS_ALLOWED_ORIGINS", output)
        self.assertIn("CONTROL_AUTH_REQUIRED", output)
        self.assertIn("SOCKET_PUBLIC_SNAPSHOT_ENABLED", output)
        self.assertIn("EVENTBUS_ALLOW_LEGACY_DICT_EVENTS", output)

    def test_production_rejects_default_admin_even_if_insecure_defaults_allowed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = self._production_env(tmpdir)
            env.update({
                "ADMIN_PASSWORD": "888888",
                "ALLOW_INSECURE_DEFAULTS": "1",
            })
            result = self._import_config(env)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ADMIN_PASSWORD", result.stderr + result.stdout)

    def test_production_rejects_default_setup_password(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = self._production_env(tmpdir)
            env["SETUP_PASSWORD"] = "login"
            result = self._import_config(env)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SETUP_PASSWORD", result.stderr + result.stdout)

    def test_development_rejects_default_secrets_unless_explicitly_allowed(self):
        env = os.environ.copy()
        env.update({
            "APP_ENV": "development",
            "TEST_MODE": "0",
            "ALLOW_INSECURE_DEFAULTS": "0",
            "CHESS_SECRET_KEY": "industrial-secret",
            "ADMIN_PASSWORD": "888888",
            "PYTHONPATH": os.getcwd(),
        })
        result = self._import_config(env)

        output = result.stderr + result.stdout
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CHESS_SECRET_KEY", output)
        self.assertIn("ADMIN_PASSWORD", output)

    def test_bind_all_requires_explicit_flag_and_hardened_config(self):
        env = os.environ.copy()
        env.update({
            "APP_ENV": "development",
            "TEST_MODE": "0",
            "ALLOW_INSECURE_DEFAULTS": "0",
            "CHESS_SECRET_KEY": "0123456789abcdef0123456789abcdef",
            "ADMIN_PASSWORD": "not-default-admin-password",
            "SETUP_PASSWORD": "not-default-setup-password",
            "CORS_ALLOWED_ORIGINS": "http://127.0.0.1:5000",
            "HOST": "0.0.0.0",
            "PYTHONPATH": os.getcwd(),
        })
        result = self._import_config(env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SMART_CHESS_BIND_ALL", result.stderr + result.stdout)

        env["SMART_CHESS_BIND_ALL"] = "1"
        result = self._import_config(env)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_production_rejects_trusting_xff_without_proxy_allowlist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = self._production_env(tmpdir)
            env.update({
                "TRUST_X_FORWARDED_FOR": "1",
                "TRUSTED_PROXY_IPS": "",
            })
            result = self._import_config(env)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("TRUSTED_PROXY_IPS", result.stderr + result.stdout)

    def test_production_rejects_wildcard_trusted_proxy_allowlist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = self._production_env(tmpdir)
            env.update({
                "TRUST_X_FORWARDED_FOR": "1",
                "TRUSTED_PROXY_IPS": "*",
            })
            result = self._import_config(env)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("TRUSTED_PROXY_IPS", result.stderr + result.stdout)

    def test_production_accepts_explicit_safe_deployment_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = self._production_env(tmpdir)
            result = self._import_config(env)

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_production_rejects_missing_db_path_and_fake_modes(self):
        env = self._production_env("")
        env.pop("DB_PATH", None)
        env.update({
            "FAKE_VISION": "1",
            "FAKE_ROBOT": "1",
            "FAKE_AI": "1",
            "SYSTEM_MODE": "simulation",
        })

        result = self._import_config(env)
        output = result.stderr + result.stdout

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DB_PATH", output)
        self.assertIn("FAKE_VISION", output)
        self.assertIn("FAKE_ROBOT", output)
        self.assertIn("FAKE_AI", output)
        self.assertIn("SYSTEM_MODE", output)

    def test_production_rejects_memory_or_relative_db_path(self):
        env = self._production_env("")
        env["DB_PATH"] = ":memory:"
        memory_result = self._import_config(env)

        env = self._production_env("")
        env["DB_PATH"] = "data/runtime/prod.db"
        relative_result = self._import_config(env)

        self.assertNotEqual(memory_result.returncode, 0)
        self.assertIn("DB_PATH", memory_result.stderr + memory_result.stdout)
        self.assertNotEqual(relative_result.returncode, 0)
        self.assertIn("absolute path", relative_result.stderr + relative_result.stdout)

    def test_production_rejects_engine_assets_outside_protected_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            engine_path = os.path.join(tmpdir, "pikafish.exe")
            nnue_path = os.path.join(tmpdir, "pikafish.nnue")
            open(engine_path, "wb").close()
            open(nnue_path, "wb").close()

            env = self._production_env(tmpdir)
            env["ENGINE_PATH"] = engine_path
            env["NNUE_PATH"] = nnue_path
            result = self._import_config(env)

        output = result.stderr + result.stdout
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ENGINE_PATH", output)
        self.assertIn("ENGINE_NNUE_CANDIDATES", output)

    def _production_env(self, tmpdir: str) -> dict:
        env = os.environ.copy()
        env.update({
            "APP_ENV": "production",
            "SYSTEM_MODE": "production",
            "CHESS_SECRET_KEY": "0123456789abcdef0123456789abcdef",
            "ADMIN_PASSWORD": "not-default-admin-password",
            "SETUP_PASSWORD": "not-default-setup-password",
            "ALLOW_INSECURE_DEFAULTS": "0",
            "TEST_MODE": "0",
            "CORS_ALLOWED_ORIGINS": "https://example.test",
            "CONTROL_AUTH_REQUIRED": "1",
            "RATE_LIMITS_ENABLED": "1",
            "SOCKET_PUBLIC_SNAPSHOT_ENABLED": "0",
            "EVENTBUS_ALLOW_LEGACY_DICT_EVENTS": "0",
            "FAKE_VISION": "0",
            "FAKE_ROBOT": "0",
            "FAKE_AI": "0",
            "PYTHONPATH": os.getcwd(),
        })
        if tmpdir:
            env["DB_PATH"] = os.path.join(tmpdir, "prod.db")
        return env

    def _import_config(self, env: dict):
        return subprocess.run(
            [sys.executable, "-c", "import backend.utils.config"],
            cwd=os.getcwd(),
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )


if __name__ == "__main__":
    unittest.main()
