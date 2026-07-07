from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROTECTED_VISION_DIR = ROOT / "backend" / "infrastructure" / "protected_assets" / "vision"
MANIFEST_PATH = ROOT / "backend" / "infrastructure" / "protected_assets" / "ASSET_MANIFEST.md"
REQUIRED_FILES = ("best.onnx", "dataset_mapping.yaml", "args.yaml")
READONLY_FILES = {"best.onnx"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _set_readonly(path: Path, readonly: bool) -> None:
    if not path.exists():
        return
    mode = path.stat().st_mode
    if readonly:
        path.chmod(mode & ~stat.S_IWRITE)
    else:
        path.chmod(mode | stat.S_IWRITE)


def _under_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _validate_source(source: Path) -> list[Path]:
    missing = [name for name in REQUIRED_FILES if not (source / name).is_file()]
    if missing:
        raise FileNotFoundError("Missing required model artifact(s): " + ", ".join(missing))
    return [source / name for name in REQUIRED_FILES]


def _manifest_row(rel_path: str, path: Path, description: str) -> str:
    return f"| `{rel_path}` | {path.stat().st_size} | `{_sha256(path)}` | {description} |"


def _update_manifest(dest: Path) -> None:
    descriptions = {
        "vision/best.onnx": "Configured YOLO26-compatible ONNX runtime model",
        "vision/dataset_mapping.yaml": "Preserved dataset class mapping",
        "vision/args.yaml": "Preserved YOLO training/export args",
    }
    replacements = {
        rel: _manifest_row(rel, dest / Path(rel).name, description)
        for rel, description in descriptions.items()
    }

    lines = MANIFEST_PATH.read_text(encoding="utf-8").splitlines()
    updated: list[str] = []
    seen = set()
    for line in lines:
        replaced = False
        for rel, row in replacements.items():
            if line.startswith(f"| `{rel}` |"):
                updated.append(row)
                seen.add(rel)
                replaced = True
                break
        if not replaced:
            updated.append(line)

    if unseen := [rel for rel in replacements if rel not in seen]:
        insert_at = len(updated)
        for index, line in enumerate(updated):
            if line.startswith("| `vision/"):
                insert_at = index + 1
        for rel in unseen:
            updated.insert(insert_at, replacements[rel])
            insert_at += 1

    MANIFEST_PATH.write_text("\n".join(updated) + "\n", encoding="utf-8")


def update_vision_model(source: Path, *, dest: Path = PROTECTED_VISION_DIR, dry_run: bool = False) -> list[Path]:
    source = source.resolve()
    dest = dest.resolve()
    files = _validate_source(source)
    if _under_root(source, ROOT / "backend" / "infrastructure" / "protected_assets"):
        raise ValueError("Source must not be inside protected_assets.")

    copied: list[Path] = []
    if dry_run:
        for src in files:
            print(f"Would copy {src} -> {dest / src.name}")
        print(f"Would update {MANIFEST_PATH}")
        return [dest / src.name for src in files]

    dest.mkdir(parents=True, exist_ok=True)
    for src in files:
        target = dest / src.name
        if target.exists():
            _set_readonly(target, False)
        shutil.copy2(src, target)
        _set_readonly(target, src.name in READONLY_FILES)
        copied.append(target)

    _update_manifest(dest)
    return copied


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely replace protected YOLO vision model assets.")
    parser.add_argument("source", type=Path, help="Folder containing best.onnx, dataset_mapping.yaml, and args.yaml.")
    parser.add_argument("--dry-run", action="store_true", help="Show intended changes without copying files.")
    parser.add_argument("--delete-source", action="store_true", help="Delete the source folder after a successful update.")
    parser.add_argument("--warmup", action="store_true", help="Run scripts/check_vision_models.py --warmup after copying.")
    args = parser.parse_args()

    copied = update_vision_model(args.source, dry_run=args.dry_run)

    if args.warmup and not args.dry_run:
        subprocess.run(
            [sys.executable, "scripts/check_vision_models.py", "--warmup"],
            cwd=ROOT,
            check=True,
        )

    if args.delete_source and not args.dry_run:
        source = args.source.resolve()
        if not _under_root(source, ROOT):
            raise ValueError(f"Refusing to delete source outside workspace: {source}")
        if _under_root(source, ROOT / "backend" / "infrastructure" / "protected_assets"):
            raise ValueError(f"Refusing to delete protected source: {source}")
        shutil.rmtree(source)
        print(f"Deleted source folder: {source}")

    for path in copied:
        print(f"Updated: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
