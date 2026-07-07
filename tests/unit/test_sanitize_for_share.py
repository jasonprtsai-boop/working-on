import tempfile
import unittest
from pathlib import Path

from scripts import sanitize_for_share


class SanitizeForShareTests(unittest.TestCase):
    def test_share_zip_excludes_runtime_and_protected_binary_assets_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            keep = root / "frontend" / "static" / "js" / "app.js"
            protected_model = root / "backend" / "infrastructure" / "protected_assets" / "vision" / "best.onnx"
            protected_meta = root / "backend" / "infrastructure" / "protected_assets" / "vision" / "dataset_mapping.yaml"
            drop_files = [
                root / ".env",
                root / "node_modules" / "jest" / "index.js",
                root / "data" / "runtime" / "app.db",
                root / "logs" / "app.log",
                root / "reports" / "html-check.md",
                root / "analysis_artifacts" / "inventory.json",
            ]
            for path in [keep, protected_model, protected_meta, *drop_files]:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("x", encoding="utf-8")

            files, skipped = sanitize_for_share.collect_share_files(root)
            names = [path.as_posix() for path in files]

            self.assertEqual(
                names,
                [
                    "backend/infrastructure/protected_assets/vision/dataset_mapping.yaml",
                    "frontend/static/js/app.js",
                ],
            )
            self.assertGreaterEqual(sum(skipped.values()), 6)

    def test_share_zip_can_include_review_artifacts_when_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "reports" / "system-review.md"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text("review", encoding="utf-8")

            files, _skipped = sanitize_for_share.collect_share_files(root, include_analysis_artifacts=True)

            self.assertEqual([path.as_posix() for path in files], ["reports/system-review.md"])

    def test_share_zip_can_include_protected_assets_when_explicitly_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = root / "backend" / "infrastructure" / "protected_assets" / "vision" / "best.onnx"
            model.parent.mkdir(parents=True, exist_ok=True)
            model.write_text("model", encoding="utf-8")

            files, _skipped = sanitize_for_share.collect_share_files(root, include_protected_assets=True)

            self.assertEqual([path.as_posix() for path in files], ["backend/infrastructure/protected_assets/vision/best.onnx"])


if __name__ == "__main__":
    unittest.main()
