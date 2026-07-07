from __future__ import annotations

import os
import shutil
import logging
import argparse
from pathlib import Path
from datetime import datetime

# --- Configuration ---
ROOT = Path(__file__).resolve().parents[2]
RETENTION_COUNT = 3  # Keep latest 3 of each artifact type

SKIP_DIR_NAMES = {".git", ".venv", "node_modules", "engine"}
PROTECTED_FILES = {"system-review-20260515.md", "file_consistency_audit.md"}
PROTECTED_ASSET_PREFIX = ("backend", "infrastructure", "protected_assets")

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
        return _is_protected_asset(path) or any(part in SKIP_DIR_NAMES for part in rel.parts)
    except Exception:
        return True


def _is_protected_asset(path: Path) -> bool:
    try:
        rel = path.resolve().relative_to(ROOT)
    except Exception:
        return False
    return rel.parts[: len(PROTECTED_ASSET_PREFIX)] == PROTECTED_ASSET_PREFIX


def _refuse_protected_delete(path: Path) -> None:
    if _is_protected_asset(path):
        rel = path.resolve().relative_to(ROOT)
        raise RuntimeError(f"Refusing to delete protected asset: {rel.as_posix()}")


def _remove_file(path: Path, *, dry_run: bool) -> bool:
    _refuse_protected_delete(path)
    if dry_run:
        logger.info(f"  Would delete: {path.name}")
        return False
    path.unlink()
    logger.info(f"  Deleted: {path.name}")
    return True


def _remove_dir(path: Path, *, dry_run: bool) -> bool:
    _refuse_protected_delete(path)
    if dry_run:
        logger.info(f"  Would delete subdir: {path.name}")
        return False
    shutil.rmtree(path)
    logger.info(f"  Deleted subdir: {path.name}")
    return True


def smart_purge_directory(dir_path: Path, *, dry_run: bool = False) -> dict[str, int]:
    summary = {"deleted": 0, "would_delete": 0, "retained": 0}
    if not dir_path.exists() or not dir_path.is_dir():
        return summary

    logger.info(f"Processing directory: {dir_path.relative_to(ROOT)}")

    # Categorize files by prefix to apply retention
    # e.g., html-function-check-*, browser-smoke-*, html-check-*
    groups: dict[str, list[Path]] = {}

    for item in dir_path.iterdir():
        if item.is_dir():
            if not _is_skipped(item):
                removed = _remove_dir(item, dry_run=dry_run)
                summary["deleted" if removed else "would_delete"] += 1
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
                removed = _remove_file(f, dry_run=dry_run)
                summary["deleted" if removed else "would_delete"] += 1
            continue

        # Sort by modification time (newest first)
        files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

        # Keep recent, delete old
        to_keep = files[:RETENTION_COUNT]
        to_delete = files[RETENTION_COUNT:]

        for f in to_delete:
            removed = _remove_file(f, dry_run=dry_run)
            summary["deleted" if removed else "would_delete"] += 1

        if to_keep:
            summary["retained"] += len(to_keep)
            logger.info(f"  Retained {len(to_keep)} latest files for prefix '{prefix}'")
    return summary


def cleanup_project(*, dry_run: bool = False):
    logger.info("Starting industrial cleanup sequence%s...", " (dry-run)" if dry_run else "")
    start_time = datetime.now()
    summary = {"deleted": 0, "would_delete": 0, "retained": 0}

    # 1. Clear __pycache__
    cache_count = 0
    for path in ROOT.rglob("__pycache__"):
        if path.is_dir() and not _is_skipped(path):
            removed = _remove_dir(path, dry_run=dry_run)
            summary["deleted" if removed else "would_delete"] += 1
            cache_count += 1
    logger.info(f"{'Would clear' if dry_run else 'Cleared'} {cache_count} __pycache__ directories.")

    # 2. Smart Purge targeted directories
    for d in PURGE_DIRS:
        partial = smart_purge_directory(d, dry_run=dry_run)
        for key, value in partial.items():
            summary[key] += value

    # 3. Purge root patterns
    file_count = 0
    for pattern in PURGE_PATTERNS:
        for f in ROOT.glob(pattern):
            if f.is_file() and f.name not in PROTECTED_FILES:
                removed = _remove_file(f, dry_run=dry_run)
                summary["deleted" if removed else "would_delete"] += 1
                file_count += 1
    logger.info(f"{'Would remove' if dry_run else 'Removed'} {file_count} temporary root files.")

    duration = (datetime.now() - start_time).total_seconds()
    logger.info(
        "Cleanup finished in %.2fs. deleted=%s would_delete=%s retained=%s",
        duration,
        summary["deleted"],
        summary["would_delete"],
        summary["retained"],
    )
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clean regenerable S.M.A.R.T. Chess runtime artifacts.")
    parser.add_argument("--dry-run", action="store_true", help="Report files that would be removed without deleting them.")
    args = parser.parse_args()
    os.chdir(ROOT)
    try:
        cleanup_project(dry_run=args.dry_run)
    except Exception as e:
        logger.error(f"Cleanup failed: {e}", exc_info=True)
        raise
