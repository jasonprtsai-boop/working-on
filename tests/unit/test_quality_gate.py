import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts import quality_gate


class TestQualityGateTrackedMutationGuard(unittest.TestCase):
    def test_changed_tracked_files_reports_hash_changes(self):
        before = {"a.py": "one", "b.py": "same"}
        after = {"a.py": "two", "b.py": "same", "c.py": "new"}

        self.assertEqual(quality_gate.changed_tracked_files(before, after), ["a.py", "c.py"])

    def test_snapshot_ignores_untracked_files_and_detects_tracked_mutation(self):
        if shutil.which("git") is None:
            self.skipTest("git is required for tracked file snapshots")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
            tracked = root / "tracked.txt"
            tracked.write_text("baseline\n", encoding="utf-8")
            subprocess.run(["git", "add", "tracked.txt"], cwd=root, check=True, capture_output=True)

            before = quality_gate.tracked_file_snapshot(root)
            (root / "untracked.txt").write_text("ignored\n", encoding="utf-8")
            self.assertEqual(quality_gate.changed_tracked_files(before, quality_gate.tracked_file_snapshot(root)), [])

            tracked.write_text("changed\n", encoding="utf-8")
            self.assertEqual(
                quality_gate.changed_tracked_files(before, quality_gate.tracked_file_snapshot(root)),
                ["tracked.txt"],
            )


if __name__ == "__main__":
    unittest.main()
