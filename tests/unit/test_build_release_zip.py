import tempfile
import unittest
from pathlib import Path

from scripts import build_release_zip


class BuildReleaseZipTests(unittest.TestCase):
    def test_default_output_uses_current_release_name(self):
        self.assertEqual(build_release_zip.DEFAULT_OUTPUT.name, "code-17-clean.zip")

    def test_exclusion_rules_keep_protected_assets_but_drop_runtime_artifacts(self):
        self.assertEqual(
            build_release_zip.exclusion_reason(Path(".env"), is_dir=False),
            "local environment secret",
        )
        self.assertIsNotNone(build_release_zip.exclusion_reason(Path("node_modules/jest/index.js"), is_dir=False))
        self.assertIsNotNone(build_release_zip.exclusion_reason(Path("data/runtime/app.db"), is_dir=False))
        self.assertIsNotNone(build_release_zip.exclusion_reason(Path("logs/app.log"), is_dir=False))
        self.assertIsNotNone(
            build_release_zip.exclusion_reason(Path("chess_robot_experiment.before_excel_fix_20260515040648.xlsx"), is_dir=False)
        )
        self.assertIsNone(
            build_release_zip.exclusion_reason(
                Path("backend/infrastructure/protected_assets/engine/pikafish.nnue"),
                is_dir=False,
            )
        )

    def test_collect_release_files_prunes_ignored_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            keep = root / "frontend" / "static" / "js" / "app.js"
            protected = root / "backend" / "infrastructure" / "protected_assets" / "vision" / "best.pt"
            drop_files = [
                root / ".env",
                root / "node_modules" / "jest" / "index.js",
                root / "data" / "runtime" / "app.db",
                root / "logs" / "app.log",
                root / "chess_robot_experiment.xlsx",
            ]
            for path in [keep, protected, *drop_files]:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("x", encoding="utf-8")

            files, skipped = build_release_zip.collect_release_files(root)
            names = [path.as_posix() for path in files]

            self.assertEqual(
                names,
                [
                    "backend/infrastructure/protected_assets/vision/best.pt",
                    "frontend/static/js/app.js",
                ],
            )
            self.assertGreaterEqual(sum(skipped.values()), 5)


if __name__ == "__main__":
    unittest.main()
