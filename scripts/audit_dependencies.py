from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIREMENT_FILES = ("requirements.txt", "requirements.runtime.txt", "requirements.vision.txt")
LOCK_FILE = ROOT / "requirements.lock.txt"
PACKAGE_LOCK = ROOT / "package-lock.json"


def _normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _requirement_name(line: str) -> str | None:
    text = line.strip()
    if not text or text.startswith("#") or text.startswith("-"):
        return None
    match = re.match(r"([A-Za-z0-9_.-]+)", text)
    return _normalize_name(match.group(1)) if match else None


def _locked_python_packages() -> set[str]:
    if not LOCK_FILE.exists():
        raise AssertionError("Missing requirements.lock.txt")
    names = set()
    for line in LOCK_FILE.read_text(encoding="utf-8").splitlines():
        if "==" not in line or line.strip().startswith("#"):
            continue
        names.add(_normalize_name(line.split("==", 1)[0]))
    return names


def _declared_python_packages() -> set[str]:
    names = set()
    for filename in REQUIREMENT_FILES:
        path = ROOT / filename
        if not path.exists():
            raise AssertionError(f"Missing {filename}")
        for line in path.read_text(encoding="utf-8").splitlines():
            name = _requirement_name(line)
            if name:
                names.add(name)
    return names


def check_python_lock() -> list[str]:
    declared = _declared_python_packages()
    locked = _locked_python_packages()
    missing = sorted(declared - locked)
    if missing:
        raise AssertionError("requirements.lock.txt missing top-level packages: " + ", ".join(missing))
    return [f"python lock covers {len(declared)} declared packages"]


def check_npm_lock() -> list[str]:
    if not PACKAGE_LOCK.exists():
        raise AssertionError("Missing package-lock.json")
    data = json.loads(PACKAGE_LOCK.read_text(encoding="utf-8"))
    if int(data.get("lockfileVersion", 0)) < 2:
        raise AssertionError("package-lock.json lockfileVersion must be >= 2")
    root_pkg = (data.get("packages") or {}).get("") or {}
    declared = set((root_pkg.get("dependencies") or {}).keys()) | set((root_pkg.get("devDependencies") or {}).keys())
    missing = [name for name in sorted(declared) if f"node_modules/{name}" not in (data.get("packages") or {})]
    if missing:
        raise AssertionError("package-lock.json missing declared npm packages: " + ", ".join(missing))
    return [f"npm lock covers {len(declared)} declared packages"]


def main() -> int:
    messages = []
    messages.extend(check_python_lock())
    messages.extend(check_npm_lock())
    print("Dependency audit OK: " + "; ".join(messages))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
