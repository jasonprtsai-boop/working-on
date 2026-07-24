from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


REQUIRED_GITIGNORE_PATTERNS = (
    ".env",
    ".tools/",
    ".venv.broken-*/",
    "build/",
    "dist/",
    "test_output.txt",
    "reports/",
    "analysis_artifacts/",
    "logs/",
    "data/",
    "backend/data/",
    "snapshots/",
    "*.db",
    "*.db-shm",
    "*.db-wal",
    "node_modules/",
    "*.nnue",
    "*.pt",
    "*.onnx",
    "*.exe",
)

REQUIRED_EXPORT_IGNORE_PATTERNS = (
    ".env export-ignore",
    ".tools/ export-ignore",
    ".venv.broken-*/ export-ignore",
    "build/ export-ignore",
    "dist/ export-ignore",
    "test_output.txt export-ignore",
    "logs/ export-ignore",
    "data/ export-ignore",
    "reports/ export-ignore",
    "analysis_artifacts/ export-ignore",
    "*.db export-ignore",
    "*.xlsx export-ignore",
    "*.nnue export-ignore",
    "*.pt export-ignore",
    "*.onnx export-ignore",
    "*.exe export-ignore",
)

RUNTIME_PATH_PREFIXES = (
    (".tools",),
    ("build",),
    ("dist",),
    ("logs",),
    ("data",),
    ("backend", "data"),
    ("reports",),
    ("analysis_artifacts",),
    ("snapshots",),
)

RUNTIME_DIR_PREFIXES = (
    ".venv.broken-",
)

RUNTIME_FILE_NAMES = {
    ".env",
    ".env.development",
    ".env.local",
    ".env.production",
    "test_output.txt",
}

RUNTIME_SUFFIXES = (
    ".db",
    ".db-shm",
    ".db-wal",
    ".log",
    ".sqlite",
    ".sqlite3",
    ".xlsx",
)

PROTECTED_ASSET_PREFIX = ("backend", "infrastructure", "protected_assets")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def is_protected_asset(path: Path) -> bool:
    return path.parts[: len(PROTECTED_ASSET_PREFIX)] == PROTECTED_ASSET_PREFIX


def is_runtime_artifact(path: Path) -> bool:
    parts = path.parts
    if not parts:
        return False
    if is_protected_asset(path):
        return False
    if any(part.startswith(prefix) for part in parts for prefix in RUNTIME_DIR_PREFIXES):
        return True
    if path.name in RUNTIME_FILE_NAMES:
        return True
    if path.name.lower().endswith(RUNTIME_SUFFIXES):
        return True
    return any(parts[: len(prefix)] == prefix for prefix in RUNTIME_PATH_PREFIXES)


def _git_tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    return [Path(line.strip()) for line in result.stdout.splitlines() if line.strip()]


def _check_policy_file(path: Path, required_patterns: tuple[str, ...]) -> list[str]:
    text = _read_text(path)
    missing = []
    for pattern in required_patterns:
        if pattern not in text:
            missing.append(pattern)
    return missing


def _check_tracked_runtime_artifacts() -> list[Path]:
    return [path for path in _git_tracked_files() if is_runtime_artifact(path)]


def _check_release_includes() -> list[Path]:
    from scripts.build_release_zip import collect_release_files

    included, _skipped = collect_release_files(ROOT)
    return [path for path in included if is_runtime_artifact(path)]


def _runtime_presence_summary() -> dict[str, object]:
    env_exists = (ROOT / ".env").exists()
    existing_dirs = [
        prefix[0] if len(prefix) == 1 else "/".join(prefix)
        for prefix in RUNTIME_PATH_PREFIXES
        if (ROOT.joinpath(*prefix)).exists()
    ]
    return {"env_exists": env_exists, "runtime_dirs": existing_dirs}


def main() -> int:
    parser = argparse.ArgumentParser(description="Check runtime artifact hygiene before release.")
    parser.parse_args()

    failures: list[str] = []

    missing_gitignore = _check_policy_file(ROOT / ".gitignore", REQUIRED_GITIGNORE_PATTERNS)
    if missing_gitignore:
        failures.append(".gitignore missing: " + ", ".join(missing_gitignore))

    missing_export_ignore = _check_policy_file(ROOT / ".gitattributes", REQUIRED_EXPORT_IGNORE_PATTERNS)
    if missing_export_ignore:
        failures.append(".gitattributes missing: " + ", ".join(missing_export_ignore))

    tracked_runtime = _check_tracked_runtime_artifacts()
    if tracked_runtime:
        failures.append(
            "Runtime artifacts are tracked by git: "
            + ", ".join(path.as_posix() for path in tracked_runtime[:20])
        )

    release_runtime = _check_release_includes()
    if release_runtime:
        failures.append(
            "Runtime artifacts would be included in release zip: "
            + ", ".join(path.as_posix() for path in release_runtime[:20])
        )

    summary = _runtime_presence_summary()
    if failures:
        print("Artifact hygiene FAILED.")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("Artifact hygiene OK.")
    if summary["env_exists"]:
        print("- local .env exists and is excluded from git/release output.")
    if summary["runtime_dirs"]:
        print("- runtime directories present but excluded: " + ", ".join(summary["runtime_dirs"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
