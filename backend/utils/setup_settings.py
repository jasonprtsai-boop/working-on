from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping


DEFAULT_SETUP_SETTINGS_PATH = Path(
    os.environ.get("SETUP_SETTINGS_FILE", os.path.join("data", "setup_settings.json"))
).resolve()


def load_settings(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    target = Path(path or DEFAULT_SETUP_SETTINGS_PATH)
    if not target.exists():
        return {}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def save_settings(data: Mapping[str, Any], path: str | os.PathLike[str] | None = None) -> Path:
    target = Path(path or DEFAULT_SETUP_SETTINGS_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(target)
    return target


def get_nested(data: Mapping[str, Any] | None, dotted_path: str, default: Any = None) -> Any:
    current: Any = data or {}
    for part in dotted_path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return default
        current = current[part]
    return current


def deep_merge(base: Mapping[str, Any] | None, update: Mapping[str, Any] | None) -> dict[str, Any]:
    result = deepcopy(dict(base or {}))
    for key, value in dict(update or {}).items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result
