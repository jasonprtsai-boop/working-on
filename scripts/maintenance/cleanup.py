from __future__ import annotations

import os
import shutil
import logging
from pathlib import Path
from datetime import datetime

# --- Configuration ---
ROOT = Path(__file__).resolve().parents[2]
RETENTION_COUNT = 3  # Keep latest 3 of each artifact type

SKIP_DIR_NAMES = {".git", ".venv", "node_modules", "engine"}
PROTECTED_FILES = {"system-review-20260515.md", "file_consistency_audit.md"}

PURGE_DIRS = [
    ROOT / "logs",
    ROOT / "reports",
    ROOT / "dist",
    ROOT / "backend" / "data" / "cache",
]

PURGE_PATTERNS = [
    "chess_robot_experiment*.xlsx",
    "*.before_excel_fix_*.xlsx",
    "*.corrupt-*",
]

# Configure basic logging
logging.basicConfig(level=logging.INFO, format="[Cleanup] %(message)s")
logger = logging.getLogger(__name__)


def _is_skipped(path: Path) -> bool:
    try:
        rel = path.resolve().relative_to(ROOT)
        return any(part in SKIP_DIR_NAMES for part in rel.parts)
    except Exception:
        return True


def smart_purge_directory(dir_path: Path):
    if not dir_path.exists() or not dir_path.is_dir():
        return

    logger.info(f"Processing directory: {dir_path.relative_to(ROOT)}")

    # Categorize files by prefix to apply retention
    # e.g., html-function-check-*, browser-smoke-*, html-check-*
    groups: dict[str, list[Path]] = {}

    for item in dir_path.iterdir():
        if item.is_dir():
            if not _is_skipped(item):
                shutil.rmtree(item)
                logger.info(f"  Deleted subdir: {item.name}")
            continue

        if item.name in PROTECTED_FILES:
            continue

        # Extract prefix (e.g., "html-check")
        prefix = item.name.split("-202")[0] if "-202" in item.name else "misc"
        if prefix not in groups:
            groups[prefix] = []
        groups[prefix].append(item)

    for prefix, files in groups.items():
        if prefix == "misc":
            # Just delete misc files that aren't protected
            for f in files:
                f.unlink()
                logger.info(f"  Deleted: {f.name}")
            continue

        # Sort by modification time (newest first)
        files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

        # Keep recent, delete old
        to_keep = files[:RETENTION_COUNT]
        to_delete = files[RETENTION_COUNT:]

        for f in to_delete:
            f.unlink()
            logger.info(f"  Purged (stale): {f.name}")

        if to_keep:
            logger.info(f"  Retained {len(to_keep)} latest files for prefix '{prefix}'")


def cleanup_project():
    logger.info("Starting industrial cleanup sequence...")
    start_time = datetime.now()

    # 1. Clear __pycache__
    cache_count = 0
    for path in ROOT.rglob("__pycache__"):
        if path.is_dir() and not _is_skipped(path):
            shutil.rmtree(path)
            cache_count += 1
    logger.info(f"Cleared {cache_count} __pycache__ directories.")

    # 2. Smart Purge targeted directories
    for d in PURGE_DIRS:
        smart_purge_directory(d)

    # 3. Purge root patterns
    file_count = 0
    for pattern in PURGE_PATTERNS:
        for f in ROOT.glob(pattern):
            if f.is_file() and f.name not in PROTECTED_FILES:
                f.unlink()
                file_count += 1
    logger.info(f"Removed {file_count} temporary root files.")

    duration = (datetime.now() - start_time).total_seconds()
    logger.info(f"Cleanup finished in {duration:.2f}s.")


if __name__ == "__main__":
    os.chdir(ROOT)
    try:
        cleanup_project()
    except Exception as e:
        logger.error(f"Cleanup failed: {e}", exc_info=True)
