import tempfile
import unittest
from pathlib import Path

from scripts.update_vision_model import REQUIRED_FILES, update_vision_model


class TestUpdateVisionModel(unittest.TestCase):
    def test_dry_run_requires_complete_source_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            for name in REQUIRED_FILES:
                (source / name).write_text("x", encoding="utf-8")

            targets = update_vision_model(source, dry_run=True)

        self.assertEqual([path.name for path in targets], list(REQUIRED_FILES))

    def test_dry_run_rejects_incomplete_source_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            (source / "best.onnx").write_text("x", encoding="utf-8")

            with self.assertRaises(FileNotFoundError):
                update_vision_model(source, dry_run=True)


if __name__ == "__main__":
    unittest.main()
