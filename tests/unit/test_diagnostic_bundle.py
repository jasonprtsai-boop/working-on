import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from backend.observability import diagnostic_bundle
from backend.utils import config


class TestDiagnosticBundle(unittest.TestCase):
    def test_redact_mapping_masks_sensitive_keys(self):
        redacted = diagnostic_bundle.redact_mapping({
            "admin_password": "secret",
            "VISION_TMFLOW_INGEST_KEY": "key",
            "robot_ip": "192.168.10.10",
        })

        self.assertEqual(redacted["admin_password"], "<redacted>")
        self.assertEqual(redacted["VISION_TMFLOW_INGEST_KEY"], "<redacted>")
        self.assertEqual(redacted["robot_ip"], "192.168.10.10")

    def test_build_diagnostic_bundle_contains_redacted_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            setup = Path(tmp) / "setup.json"
            setup.write_text('{"admin_password":"secret","robot":{"ip":"192.168.10.10"}}', encoding="utf-8")
            with patch.object(config, "SETUP_SETTINGS_FILE", str(setup)):
                path, filename = diagnostic_bundle.build_diagnostic_bundle(output_dir=tmp)

            self.assertTrue(filename.endswith(".zip"))
            with zipfile.ZipFile(path) as archive:
                names = set(archive.namelist())
                self.assertIn("summary.json", names)
                self.assertIn("config/redacted_config.json", names)
                self.assertIn("config/setup_settings.redacted.json", names)
                setup_payload = archive.read("config/setup_settings.redacted.json").decode("utf-8")
                self.assertIn("<redacted>", setup_payload)
                self.assertNotIn("secret", setup_payload)


if __name__ == "__main__":
    unittest.main()
