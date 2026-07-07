import os
import subprocess
import sys
import unittest


class TestProductionPreflight(unittest.TestCase):
    def test_self_test_passes(self):
        result = subprocess.run(
            [sys.executable, "scripts/check_production_config.py", "--self-test"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Production config preflight self-test OK.", result.stdout)

    def test_current_requires_production_when_requested(self):
        env = os.environ.copy()
        env.update(
            {
                "APP_ENV": "development",
                "TEST_MODE": "1",
                "ALLOW_INSECURE_DEFAULTS": "1",
                "CHESS_SECRET_KEY": "0123456789abcdef0123456789abcdef",
                "ADMIN_PASSWORD": "not-default-admin-password",
                "CORS_ALLOWED_ORIGINS": "http://127.0.0.1:5000",
                "CONTROL_AUTH_REQUIRED": "1",
                "RATE_LIMITS_ENABLED": "1",
            }
        )
        result = subprocess.run(
            [sys.executable, "scripts/check_production_config.py", "--current", "--require-production"],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not production", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
