from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Dict, List, Optional


ASSET_ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = ASSET_ROOT / "ASSET_MANIFEST.md"
_ROW_RE = re.compile(r"^\|\s*`(?P<path>[^`]+)`\s*\|\s*(?P<size>\d+)\s*\|\s*`(?P<sha>[A-Fa-f0-9]{64})`")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def read_manifest(manifest_path: Optional[Path] = None) -> List[Dict[str, object]]:
    path = manifest_path or MANIFEST_PATH
    rows: List[Dict[str, object]] = []
    if not path.exists():
        return rows

    for line in path.read_text(encoding="utf-8").splitlines():
        match = _ROW_RE.match(line.strip())
        if not match:
            continue
        rows.append(
            {
                "path": match.group("path").replace("\\", "/"),
                "size_bytes": int(match.group("size")),
                "sha256": match.group("sha").upper(),
            }
        )
    return rows


def validate_assets(root: Optional[Path] = None, manifest_path: Optional[Path] = None) -> Dict[str, object]:
    asset_root = root or ASSET_ROOT
    expected = read_manifest(manifest_path)
    results = []

    for item in expected:
        rel_path = str(item["path"])
        file_path = asset_root / rel_path
        exists = file_path.exists()
        actual_size = file_path.stat().st_size if exists else None
        actual_sha = _sha256(file_path) if exists else None
        size_ok = actual_size == item["size_bytes"]
        sha_ok = actual_sha == item["sha256"]
        results.append(
            {
                "path": rel_path,
                "exists": exists,
                "expected_size": item["size_bytes"],
                "actual_size": actual_size,
                "expected_sha256": item["sha256"],
                "actual_sha256": actual_sha,
                "ok": bool(exists and size_ok and sha_ok),
            }
        )

    return {
        "root": str(asset_root),
        "manifest": str(manifest_path or MANIFEST_PATH),
        "total": len(results),
        "ok": all(item["ok"] for item in results) and bool(results),
        "items": results,
    }
