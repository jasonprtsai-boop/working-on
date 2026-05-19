from __future__ import annotations

import argparse
import os
import zipfile
from collections import Counter
from fnmatch import fnmatchcase
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "dist" / "code-17-clean.zip"

EXCLUDED_DIR_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "dist",
    "env",
    "logs",
    "node_modules",
    "snapshots",
    "venv",
}

EXCLUDED_PATH_PREFIXES = {
    ("backend", "data"),
    ("data",),
    ("reports",),
}

EXCLUDED_FILE_NAMES = {
    ".env",
    ".env.development",
    ".env.local",
    ".env.production",
}

ROOT_ONLY_EXCLUDED_FILE_NAMES = {
    "pikafish.exe",
    "pikafish.nnue",
}

EXCLUDED_FILE_SUFFIXES = (
    ".db",
    ".db-shm",
    ".db-wal",
    ".log",
    ".pyc",
    ".pyo",
    ".sqlite",
    ".sqlite3",
    ".tmp",
)

EXCLUDED_FILE_GLOBS = (
    "*.before_excel_fix_*.xlsx",
    "*.corrupt-*",
    "*.xlsx",
)


def _relative_path(path: Path, root: Path) -> Path:
    path = Path(path)
    if path.is_absolute():
        return path.relative_to(root)
    return path


def exclusion_reason(path: Path, root: Path = ROOT, is_dir: bool | None = None) -> str | None:
    rel = _relative_path(path, root)
    parts = rel.parts
    if not parts:
        return None

    if is_dir is True:
        dir_parts = parts
    else:
        dir_parts = parts[:-1]

    for part in dir_parts:
        if part in EXCLUDED_DIR_NAMES:
            return f"excluded directory: {part}"

    for prefix in EXCLUDED_PATH_PREFIXES:
        if parts[: len(prefix)] == prefix:
            return f"excluded path: {'/'.join(prefix)}"

    name = rel.name
    if is_dir is True:
        if name in EXCLUDED_DIR_NAMES:
            return f"excluded directory: {name}"
        return None

    if name in EXCLUDED_FILE_NAMES:
        return "local environment secret"

    if len(parts) == 1 and name in ROOT_ONLY_EXCLUDED_FILE_NAMES:
        return "root engine binary/cache artifact"

    lower_name = name.lower()
    if lower_name.endswith(EXCLUDED_FILE_SUFFIXES):
        return "runtime/cache file suffix"

    for pattern in EXCLUDED_FILE_GLOBS:
        if fnmatchcase(lower_name, pattern.lower()):
            return f"excluded file pattern: {pattern}"

    return None


def collect_release_files(root: Path = ROOT) -> tuple[list[Path], Counter]:
    root = Path(root).resolve()
    included: list[Path] = []
    skipped: Counter = Counter()

    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        rel_dir = current_path.relative_to(root)

        kept_dirs = []
        for dirname in dirs:
            rel_path = rel_dir / dirname if str(rel_dir) != "." else Path(dirname)
            reason = exclusion_reason(rel_path, root=root, is_dir=True)
            if reason:
                skipped[reason] += 1
            else:
                kept_dirs.append(dirname)
        dirs[:] = kept_dirs

        for filename in files:
            rel_path = rel_dir / filename if str(rel_dir) != "." else Path(filename)
            reason = exclusion_reason(rel_path, root=root, is_dir=False)
            if reason:
                skipped[reason] += 1
                continue
            included.append(rel_path)

    return sorted(included, key=lambda item: item.as_posix()), skipped


def build_zip(root: Path, output: Path, dry_run: bool = False) -> tuple[list[Path], Counter]:
    root = Path(root).resolve()
    output = Path(output).resolve()
    files, skipped = collect_release_files(root)

    if dry_run:
        return files, skipped

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for rel_path in files:
            archive.write(root / rel_path, rel_path.as_posix())

    return files, skipped


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a clean source release zip.")
    parser.add_argument("--root", type=Path, default=ROOT, help="Project root to package.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output zip path.")
    parser.add_argument("--dry-run", action="store_true", help="List what would be packaged without writing a zip.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    files, skipped = build_zip(args.root, args.output, dry_run=args.dry_run)
    mode = "Dry run" if args.dry_run else "Created"
    print(f"{mode}: {args.output}")
    print(f"Included files: {len(files)}")
    print(f"Excluded entries: {sum(skipped.values())}")
    for reason, count in sorted(skipped.items()):
        print(f"- {reason}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
