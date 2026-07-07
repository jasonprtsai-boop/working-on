from __future__ import annotations

import json
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from backend.utils import config


REPORT_VERSION = 1


def _report_path(path: str | Path | None = None) -> Path:
    return Path(path or getattr(config, "COMMISSIONING_REPORT_FILE", "data/commissioning_report.json"))


def _now() -> float:
    return time.time()


def _empty_report() -> dict[str, Any]:
    return {
        "ok": True,
        "version": REPORT_VERSION,
        "updated_at": None,
        "steps": {
            "settings_saved": {"ok": False, "last_at": None, "message": "Setup settings have not been saved."},
            "preflight": {"ok": False, "last_at": None, "message": "Preflight has not been run."},
            "hardware": {"ok": False, "last_at": None, "message": "Hardware tests have not been run.", "actions": {}},
        },
        "latest_preflight": None,
        "latest_hardware_test": None,
    }


def load_commissioning_report(path: str | Path | None = None) -> dict[str, Any]:
    target = _report_path(path)
    if not target.exists():
        return _empty_report()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return _empty_report()
    if not isinstance(data, dict):
        return _empty_report()
    report = _empty_report()
    report.update(data)
    report["steps"] = _merge_steps(report.get("steps"))
    return report


def save_commissioning_report(report: Mapping[str, Any], path: str | Path | None = None) -> Path:
    target = _report_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(target)
    return target


def mark_settings_saved(settings: Mapping[str, Any] | None = None) -> dict[str, Any]:
    report = load_commissioning_report()
    ts = _now()
    report["updated_at"] = ts
    report["steps"]["settings_saved"] = {
        "ok": True,
        "last_at": ts,
        "message": "Setup settings saved.",
        "snapshot": {
            "fake_robot": _nested(settings, "robot.runtime.fake_robot"),
            "auto_execute_robot": _nested(settings, "robot.runtime.auto_execute_robot"),
            "camera_index": _nested(settings, "vision.camera_index"),
        },
    }
    save_commissioning_report(report)
    return report


def record_preflight(report_payload: Mapping[str, Any]) -> dict[str, Any]:
    report = load_commissioning_report()
    ts = _now()
    failures = list(report_payload.get("failures") or [])
    warnings = list(report_payload.get("warnings") or [])
    ready = bool(report_payload.get("ready"))
    report["updated_at"] = ts
    report["latest_preflight"] = _json_safe(report_payload)
    report["steps"]["preflight"] = {
        "ok": ready,
        "last_at": ts,
        "message": "Preflight passed." if ready else f"Preflight blocked by {len(failures)} failure(s).",
        "failures": len(failures),
        "warnings": len(warnings),
    }
    save_commissioning_report(report)
    return report


def record_hardware_test(action: str, result: Mapping[str, Any]) -> dict[str, Any]:
    report = load_commissioning_report()
    ts = _now()
    action_key = str(action or "unknown").strip().lower() or "unknown"
    ok = bool(result.get("ok", False))
    entry = {
        "ok": ok,
        "last_at": ts,
        "message": str(result.get("message") or ("Passed" if ok else "Failed")),
        "dry_run": bool(result.get("dry_run", False)),
        "result": _json_safe(result),
    }
    hardware = dict(report["steps"].get("hardware") or {})
    actions = dict(hardware.get("actions") or {})
    actions[action_key] = entry
    report["updated_at"] = ts
    report["latest_hardware_test"] = {"action": action_key, **entry}
    report["steps"]["hardware"] = {
        "ok": any(bool(item.get("ok")) for item in actions.values()),
        "last_at": ts,
        "message": f"Last hardware test: {action_key} {'passed' if ok else 'failed'}.",
        "actions": actions,
    }
    save_commissioning_report(report)
    return report


def _merge_steps(steps: Any) -> dict[str, Any]:
    merged = deepcopy(_empty_report()["steps"])
    if isinstance(steps, Mapping):
        for key, value in steps.items():
            if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
                merged[key].update(value)
            else:
                merged[key] = deepcopy(value)
    return merged


def _nested(data: Mapping[str, Any] | None, path: str) -> Any:
    current: Any = data or {}
    for part in path.split("."):
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        if isinstance(value, Mapping):
            return {str(key): _json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [_json_safe(item) for item in value]
        return str(value)
