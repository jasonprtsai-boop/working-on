from __future__ import annotations

import argparse
import os
import sys
import zipfile
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_release_zip

DEFAULT_OUTPUT = ROOT / "dist" / "smart-chess-share-clean.zip"

PROTECTED_BINARY_SUFFIXES = (".exe", ".nnue", ".onnx", ".pt")
OPTIONAL_SHARE_EXCLUDED_PREFIXES = {
    ("analysis_artifacts",),
    ("reports",),
}


def _relative_path(path: Path, root: Path) -> Path:
    path = Path(path)
    if path.is_absolute():
        return path.relative_to(root)
    return path


def share_exclusion_reason(
    path: Path,
    *,
    root: Path = ROOT,
    is_dir: bool | None = None,
    include_analysis_artifacts: bool = False,
    include_protected_assets: bool = False,
) -> str | None:
    rel = _relative_path(path, root)
    parts = rel.parts
    if not parts:
        return None

    release_reason = build_release_zip.exclusion_reason(rel, root=root, is_dir=is_dir)
    if release_reason:
        if include_analysis_artifacts and parts[:1] == ("analysis_artifacts",):
            return None
        if include_analysis_artifacts and parts[:1] == ("reports",):
            return None
        return release_reason

    if not include_analysis_artifacts:
        for prefix in OPTIONAL_SHARE_EXCLUDED_PREFIXES:
            if parts[: len(prefix)] == prefix:
                return f"share excluded path: {'/'.join(prefix)}"

    if not include_protected_assets and parts[:3] == ("backend", "infrastructure", "protected_assets"):
        if is_dir is True:
            return None
        if rel.name.lower().endswith(PROTECTED_BINARY_SUFFIXES):
            return "share excludes protected binary/model assets"

    return None


def collect_share_files(
    root: Path = ROOT,
    *,
    include_analysis_artifacts: bool = False,
    include_protected_assets: bool = False,
) -> tuple[list[Path], Counter]:
    root = Path(root).resolve()
    included: list[Path] = []
    skipped: Counter = Counter()

    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        rel_dir = current_path.relative_to(root)

        kept_dirs = []
        for dirname in dirs:
            rel_path = rel_dir / dirname if str(rel_dir) != "." else Path(dirname)
            reason = share_exclusion_reason(
                rel_path,
                root=root,
                is_dir=True,
                include_analysis_artifacts=include_analysis_artifacts,
                include_protected_assets=include_protected_assets,
            )
            if reason:
                skipped[reason] += 1
            else:
                kept_dirs.append(dirname)
        dirs[:] = kept_dirs

        for filename in files:
            rel_path = rel_dir / filename if str(rel_dir) != "." else Path(filename)
            reason = share_exclusion_reason(
                rel_path,
                root=root,
                is_dir=False,
                include_analysis_artifacts=include_analysis_artifacts,
                include_protected_assets=include_protected_assets,
            )
            if reason:
                skipped[reason] += 1
                continue
            included.append(rel_path)

    return sorted(included, key=lambda item: item.as_posix()), skipped


def build_share_zip(
    root: Path,
    output: Path,
    *,
    dry_run: bool = False,
    include_analysis_artifacts: bool = False,
    include_protected_assets: bool = False,
) -> tuple[list[Path], Counter]:
    root = Path(root).resolve()
    output = Path(output).resolve()
    files, skipped = collect_share_files(
        root,
        include_analysis_artifacts=include_analysis_artifacts,
        include_protected_assets=include_protected_assets,
    )

    if dry_run:
        return files, skipped

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for rel_path in files:
            archive.write(root / rel_path, rel_path.as_posix())
    return files, skipped


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a sanitized zip for sharing source review/demo code.")
    parser.add_argument("--root", type=Path, default=ROOT, help="Project root to package.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output zip path.")
    parser.add_argument("--dry-run", action="store_true", help="List what would be packaged without writing a zip.")
    parser.add_argument(
        "--include-analysis-artifacts",
        action="store_true",
        help="Include analysis_artifacts/ and reports/ when sharing review evidence.",
    )
    parser.add_argument(
        "--include-protected-assets",
        action="store_true",
        help="Include protected binary/model assets. Default share zips exclude them.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    files, skipped = build_share_zip(
        args.root,
        args.output,
        dry_run=args.dry_run,
        include_analysis_artifacts=args.include_analysis_artifacts,
        include_protected_assets=args.include_protected_assets,
    )
    mode = "Dry run" if args.dry_run else "Created"
    print(f"{mode}: {args.output}")
    print(f"Included files: {len(files)}")
    print(f"Excluded entries: {sum(skipped.values())}")
    for reason, count in sorted(skipped.items()):
        print(f"- {reason}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
