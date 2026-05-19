from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], label: str, env: dict[str, str] | None = None) -> None:
    print(f"\n== {label} ==")
    subprocess.run(command, cwd=ROOT, check=True, env=env)


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
    for path in sorted(js_files):
        run(["node", "--check", str(path)], f"node --check {path.relative_to(ROOT)}")


def npm_test() -> None:
    npm = "npm.cmd" if os.name == "nt" else "npm"
    run([npm, "test"], "frontend unit tests")


def main() -> int:
    run([sys.executable, "-m", "compileall", "backend", "frontend", "scripts", "tests", "-q"], "python compileall")
    run([sys.executable, "scripts/consistency_audit.py"], "file consistency audit")
    run([sys.executable, "scripts/check_contract.py"], "event contract check")
    run([sys.executable, "scripts/check_assets.py"], "protected asset manifest check")
    run([sys.executable, "scripts/build_release_zip.py", "--dry-run"], "release zip dry-run")
    test_env = os.environ.copy()
    test_env["ENGINE_AUTO_ANALYZE"] = "false"
    test_env["ENGINE_PROBE_ON_BOOT"] = "false"
    test_env["FAKE_VISION"] = "true"
    run([sys.executable, "-m", "unittest", "discover", "tests", "-v"], "python tests", env=test_env)
    node_check()
    npm_test()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
