import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.utils import auth, config


class TestJwtRevocationStore(unittest.TestCase):
    def test_revoked_jti_survives_memory_clear_when_db_backed(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "auth_revocations.db")
            claims = {"jti": "unit-jti-1", "exp": time.time() + 600}

            with patch.object(config, "JWT_REVOCATION_DB_PATH", db_path):
                auth._revoked_jtis.clear()
                auth._REVOCATION_SCHEMA_READY.clear()

                self.assertTrue(auth.revoke_jwt_claims(claims))
                auth._revoked_jtis.clear()

                self.assertTrue(auth.is_token_revoked(claims))


if __name__ == "__main__":
    unittest.main()
