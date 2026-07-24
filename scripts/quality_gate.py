from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _git_tracked_paths(root: Path = ROOT) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return [
        item.decode("utf-8", errors="surrogateescape")
        for item in result.stdout.split(b"\0")
        if item
    ]


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tracked_file_snapshot(root: Path = ROOT) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for rel_path in _git_tracked_paths(root):
        path = root / rel_path
        snapshot[rel_path] = _file_digest(path) if path.is_file() else "<missing>"
    return snapshot


def changed_tracked_files(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return [
        path
        for path in sorted(set(before) | set(after))
        if before.get(path) != after.get(path)
    ]


def assert_tracked_files_unchanged(before: dict[str, str], root: Path = ROOT) -> None:
    changed = changed_tracked_files(before, tracked_file_snapshot(root))
    if not changed:
        return
    print_tracked_file_changes(changed)
    raise RuntimeError("Quality gate modified tracked files.")


def print_tracked_file_changes(changed: list[str]) -> None:
    print("\nTracked files changed during quality gate:")
    for path in changed[:50]:
        print(f"- {path}")
    if len(changed) > 50:
        print(f"- ... and {len(changed) - 50} more")


def run(command: list[str], label: str, env: dict[str, str] | None = None) -> None:
    print(f"\n== {label} ==")
    subprocess.run(command, cwd=ROOT, check=True, env=env)


def node_command() -> str:
    if os.name == "nt":
        wrapper = ROOT / "scripts" / "node24.cmd"
        if wrapper.exists():
            return str(wrapper)
        return "node.exe"
    return "node"


def npm_command() -> str:
    if os.name == "nt":
        wrapper = ROOT / "scripts" / "npm24.cmd"
        if wrapper.exists():
            return str(wrapper)
        return "npm.cmd"
    return "npm"


def node_check() -> None:
    js_files = [
        path for base in (
            ROOT / "frontend" / "static" / "js",
            ROOT / "frontend" / "tests",
            ROOT / "backend" / "interfaces" / "dashboard" / "static",
        )
        for path in base.rglob("*.js")
    ]
    js_files += list((ROOT / "scripts").glob("*.mjs"))
    node = node_command()
    for path in sorted(js_files):
        run([node, "--check", str(path)], f"node --check {path.relative_to(ROOT)}")


def npm_test() -> None:
    run([npm_command(), "test"], "frontend unit tests")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the full project quality gate.")
    parser.add_argument(
        "--skip-tracked-mutation-check",
        action="store_true",
        help="Do not fail if the quality gate changes git-tracked files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    baseline = None if args.skip_tracked_mutation_check else tracked_file_snapshot()
    exit_code = 0
    try:
        run([sys.executable, "-m", "compileall", "backend", "frontend", "scripts", "tests", "-q"], "python compileall")
        run([sys.executable, "scripts/consistency_audit.py"], "file consistency audit")
        run([sys.executable, "scripts/check_contract.py"], "event contract check")
        run([sys.executable, "scripts/check_legacy_events.py"], "legacy event publisher check")
        run([sys.executable, "scripts/check_assets.py"], "protected asset manifest check")
        run(
            [sys.executable, "scripts/check_vision_models.py", "--warmup", "--allow-runtime-skip"],
            "vision model asset/runtime check",
        )
        run([sys.executable, "scripts/audit_dependencies.py"], "dependency lock audit")
        run([sys.executable, "scripts/check_production_config.py", "--self-test"], "production config preflight self-test")
        run([sys.executable, "scripts/check_artifact_hygiene.py"], "runtime artifact hygiene check")
        run([sys.executable, "scripts/maintenance/cleanup.py", "--dry-run"], "artifact cleanup dry-run")
        run([sys.executable, "scripts/build_release_zip.py", "--dry-run"], "release zip dry-run")
        run([sys.executable, "scripts/sanitize_for_share.py", "--dry-run"], "share zip sanitize dry-run")
        test_env = os.environ.copy()
        test_env["ENGINE_AUTO_ANALYZE"] = "false"
        test_env["ENGINE_PROBE_ON_BOOT"] = "false"
        test_env["FAKE_VISION"] = "true"
        run([sys.executable, "-m", "unittest", "discover", "tests", "-v"], "python tests", env=test_env)
        node_check()
        npm_test()
    except subprocess.CalledProcessError as exc:
        command = " ".join(str(part) for part in exc.cmd)
        print(f"\nQuality gate step failed: {command} (exit {exc.returncode})")
        exit_code = exc.returncode or 1
    except Exception as exc:
        print(f"\nQuality gate failed: {exc}")
        exit_code = 1
    finally:
        if baseline is not None:
            changed = changed_tracked_files(baseline, tracked_file_snapshot())
            if changed:
                print_tracked_file_changes(changed)
                exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
