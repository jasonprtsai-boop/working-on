from __future__ import annotations

import os
from functools import lru_cache
from importlib.util import find_spec
from typing import Any, Mapping

from flask import request


def bounded_int_arg(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(request.args.get(name, default))
    except Exception:
        value = default
    return max(minimum, min(value, maximum))


def json_object_payload() -> dict[str, Any]:
    payload = request.get_json(silent=True)
    if payload is None:
        return {}
    if not isinstance(payload, Mapping):
        raise ValueError("Request JSON body must be an object.")
    return dict(payload)


def optional_json_object_payload() -> dict[str, Any]:
    payload = request.get_json(silent=True)
    return dict(payload) if isinstance(payload, Mapping) else {}


@lru_cache(maxsize=64)
def has_module(name: str) -> bool:
    try:
        return bool(name and find_spec(name) is not None)
    except (ImportError, ValueError, AttributeError):
        return False


def asset_info(path: str) -> dict:
    abs_path = os.path.abspath(path or "")
    exists = bool(abs_path and os.path.exists(abs_path))
    return {
        "path": abs_path,
        "exists": exists,
        "size_bytes": os.path.getsize(abs_path) if exists and os.path.isfile(abs_path) else 0,
    }
