from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.infrastructure.protected_assets.manifest import validate_assets


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate protected engine and vision assets.")
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Report missing assets but do not fail the process.",
    )
    args = parser.parse_args()

    report = validate_assets()
    print(f"Protected asset root: {report['root']}")
    print(f"Manifest: {report['manifest']}")

    failed = []
    for item in report["items"]:
        status = "OK" if item["ok"] else "FAIL"
        print(
            f"[{status}] {item['path']} "
            f"size={item['actual_size']}/{item['expected_size']} "
            f"sha256={item['actual_sha256'] or 'missing'}"
        )
        if not item["ok"]:
            failed.append(item)

    if failed and not args.allow_missing:
        return 1
    if not report["items"] and not args.allow_missing:
        print("No protected assets were declared in the manifest.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
