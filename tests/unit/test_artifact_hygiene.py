import subprocess
import sys
import unittest
from pathlib import Path

from scripts.check_artifact_hygiene import is_runtime_artifact
from scripts.maintenance import cleanup


class TestArtifactHygiene(unittest.TestCase):
    def test_runtime_artifact_detection(self):
        self.assertTrue(is_runtime_artifact(Path(".env")))
        self.assertTrue(is_runtime_artifact(Path("logs/app.log")))
        self.assertTrue(is_runtime_artifact(Path("data/runtime/app.db")))
        self.assertTrue(is_runtime_artifact(Path("reports/chess_robot_experiment.xlsx")))
        self.assertFalse(is_runtime_artifact(Path("backend/utils/config.py")))
        self.assertFalse(is_runtime_artifact(Path("backend/infrastructure/protected_assets/engine/pikafish-avx2.exe")))
        self.assertFalse(is_runtime_artifact(Path("backend/infrastructure/protected_assets/vision/best.onnx")))
        self.assertFalse(is_runtime_artifact(Path("backend/infrastructure/protected_assets/vision/best.pt")))

    def test_cleanup_refuses_protected_assets(self):
        protected_model = Path("backend/infrastructure/protected_assets/vision/best.onnx")
        protected_dir = Path("backend/infrastructure/protected_assets/vision")

        self.assertTrue(cleanup._is_protected_asset(protected_model))
        with self.assertRaises(RuntimeError):
            cleanup._remove_file(protected_model, dry_run=True)
        with self.assertRaises(RuntimeError):
            cleanup._remove_dir(protected_dir, dry_run=True)

    def test_repo_artifact_hygiene_passes(self):
        result = subprocess.run(
            [sys.executable, "scripts/check_artifact_hygiene.py"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Artifact hygiene OK.", result.stdout)


if __name__ == "__main__":
    unittest.main()
