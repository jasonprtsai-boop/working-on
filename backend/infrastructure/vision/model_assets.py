from __future__ import annotations

import hashlib
import os
import stat
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path
from typing import Any

import yaml

from backend.utils import config


ROOT = Path(__file__).resolve().parents[3]
PROTECTED_ASSET_ROOT = ROOT / "backend" / "infrastructure" / "protected_assets"


def _abs_path(path: str | os.PathLike[str] | None) -> Path:
    value = str(path or "").strip()
    if not value:
        return Path("")
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate.resolve()
    return (ROOT / candidate).resolve()


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _is_readonly(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False
    return not bool(path.stat().st_mode & stat.S_IWRITE)


@lru_cache(maxsize=64)
def _sha256_cached(path: str, size: int, mtime_ns: int) -> str:
    del size, mtime_ns
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def file_status(path: str | os.PathLike[str] | None, *, include_hash: bool = True) -> dict[str, Any]:
    if not str(path or "").strip():
        return {
            "path": "",
            "exists": False,
            "is_file": False,
            "size_bytes": 0,
            "sha256": None,
            "extension": "",
            "protected": False,
            "readonly": False,
        }
    file_path = _abs_path(path)
    exists = bool(str(file_path) and file_path.exists())
    is_file = bool(exists and file_path.is_file())
    stat_result = file_path.stat() if exists else None
    sha256 = None
    if include_hash and is_file and stat_result is not None:
        sha256 = _sha256_cached(str(file_path), int(stat_result.st_size), int(stat_result.st_mtime_ns))
    return {
        "path": str(file_path) if str(file_path) else "",
        "exists": exists,
        "is_file": is_file,
        "size_bytes": int(stat_result.st_size) if stat_result is not None and is_file else 0,
        "sha256": sha256,
        "extension": file_path.suffix.lower() if str(file_path) else "",
        "protected": bool(str(file_path) and _is_under(file_path, PROTECTED_ASSET_ROOT)),
        "readonly": _is_readonly(file_path),
    }


def model_candidates() -> list[str]:
    """Return the single configured YOLO model path."""
    path = _abs_path(getattr(config, "YOLO_MODEL_PATH", ""))
    return [str(path)] if str(path) else []


def _installed_version(package_name: str) -> str | None:
    try:
        return package_version(package_name)
    except PackageNotFoundError:
        return None
    except Exception:
        return None


def _dataset_metadata(path: str | os.PathLike[str] | None) -> dict[str, Any]:
    status = file_status(path)
    metadata = {
        **status,
        "nc": None,
        "names_count": 0,
        "names_match_nc": False,
        "names": [],
    }
    if not status["exists"] or not status["is_file"]:
        return metadata

    try:
        data = yaml.safe_load(Path(status["path"]).read_text(encoding="utf-8")) or {}
    except Exception as exc:
        metadata["error"] = str(exc)
        return metadata

    names = data.get("names")
    if isinstance(names, dict):
        try:
            keys = sorted(names, key=lambda item: int(item))
        except Exception:
            keys = sorted(names)
        class_names = [str(names[key]) for key in keys]
    elif isinstance(names, list):
        class_names = [str(name) for name in names]
    else:
        class_names = []

    nc = data.get("nc")
    try:
        nc = int(nc)
    except Exception:
        nc = None

    metadata.update({
        "nc": nc,
        "names_count": len(class_names),
        "names_match_nc": bool(nc is not None and len(class_names) == nc),
        "names": class_names,
    })
    return metadata


def vision_model_report(*, active_path: str | None = None, include_hash: bool = True) -> dict[str, Any]:
    model_path = str(_abs_path(getattr(config, "YOLO_MODEL_PATH", "")))
    candidates = [
        {
            "order": index,
            "role": "active",
            **file_status(path, include_hash=include_hash),
        }
        for index, path in enumerate(model_candidates())
    ]
    active = file_status(active_path, include_hash=include_hash) if active_path else None
    dataset_mapping = _dataset_metadata(getattr(config, "YOLO_DATASET_MAPPING_PATH", ""))
    training_args = file_status(getattr(config, "YOLO_TRAINING_ARGS_PATH", ""), include_hash=include_hash)
    return {
        "model_type": getattr(config, "YOLO_MODEL_TYPE", "yolo26"),
        "model_path": model_path,
        "active_path": active["path"] if active else "",
        "active": active,
        "model": candidates[0] if candidates else file_status(model_path, include_hash=include_hash),
        "candidates": candidates,
        "dataset_mapping": dataset_mapping,
        "training_args": training_args,
        "class_count": len(getattr(config, "YOLO_CLASS_NAMES", ()) or ()),
        "class_names": list(getattr(config, "YOLO_CLASS_NAMES", ()) or ()),
        "ultralytics_version": _installed_version("ultralytics"),
        "ultralytics_min_version": getattr(config, "ULTRALYTICS_MIN_VERSION", "8.4.55"),
        "warmup_on_load": bool(getattr(config, "YOLO_WARMUP_ON_LOAD", True)),
        "protected_asset_root": str(PROTECTED_ASSET_ROOT),
    }
