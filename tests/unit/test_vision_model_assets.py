import subprocess
import sys
import unittest
from pathlib import Path

from backend.infrastructure.vision.model_assets import file_status, model_candidates, vision_model_report


class TestVisionModelAssets(unittest.TestCase):
    def test_report_exposes_single_protected_yolo_model(self):
        report = vision_model_report()
        model = report.get("model") or {}
        candidates = report.get("candidates") or []

        self.assertEqual(len(candidates), 1)
        self.assertEqual(model.get("role"), "active")
        self.assertEqual(model.get("extension"), ".onnx")
        self.assertTrue(model.get("exists"), model.get("path"))
        self.assertTrue(model.get("protected"), model.get("path"))
        self.assertTrue(model.get("readonly"), model.get("path"))
        self.assertIsNotNone(model.get("sha256"))

    def test_dataset_mapping_matches_configured_classes(self):
        report = vision_model_report()
        dataset = report.get("dataset_mapping") or {}

        self.assertTrue(dataset.get("exists"))
        self.assertEqual(dataset.get("nc"), 15)
        self.assertEqual(dataset.get("names_count"), 15)
        self.assertTrue(dataset.get("names_match_nc"))
        self.assertEqual(report.get("class_count"), 15)
        self.assertEqual((report.get("class_names") or [])[-1], "other - hand")

    def test_file_status_marks_non_protected_paths(self):
        status = file_status(Path("README.md"))

        self.assertTrue(status["exists"])
        self.assertFalse(status["protected"])

    def test_model_candidates_are_absolute_and_ordered(self):
        candidates = model_candidates()

        self.assertEqual(len(candidates), 1)
        self.assertTrue(candidates[0].endswith("best.onnx"))
        self.assertTrue(all(Path(path).is_absolute() for path in candidates))

    def test_check_vision_models_static_cli_passes(self):
        result = subprocess.run(
            [sys.executable, "scripts/check_vision_models.py"],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            timeout=30,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Vision model check OK.", result.stdout)


if __name__ == "__main__":
    unittest.main()
