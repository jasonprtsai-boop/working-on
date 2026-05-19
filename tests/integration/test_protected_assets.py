import unittest

from backend.infrastructure.protected_assets.manifest import validate_assets


class TestProtectedAssets(unittest.TestCase):
    def test_manifest_assets_exist_and_match_checksum(self):
        report = validate_assets()
        self.assertTrue(report["items"], "protected asset manifest should declare canonical assets")
        failures = [item for item in report["items"] if not item["ok"]]
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
