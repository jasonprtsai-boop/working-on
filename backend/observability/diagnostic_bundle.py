from __future__ import annotations

import json
import os
import platform
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any, Mapping

from backend.utils import config


ROOT = Path(__file__).resolve().parents[2]
SENSITIVE_TOKENS = ("password", "secret", "token", "key", "credential", "authorization", "cookie")


def build_diagnostic_bundle(*, output_dir: str | Path | None = None, max_log_bytes: int = 512_000) -> tuple[Path, str]:
    """Create a redacted diagnostics zip that an operator can send back for support."""
    output_root = Path(output_dir or tempfile.gettempdir()).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    suffix = time.strftime("%Y%m%d-%H%M%S")
    path = output_root / f"smart-chess-diagnostics-{suffix}.zip"

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        _write_json(archive, "summary.json", _summary())
        _write_json(archive, "config/redacted_config.json", redacted_config_snapshot())
        _write_json(archive, "runtime/status.json", _runtime_status())
        _write_optional_json_file(archive, getattr(config, "SETUP_SETTINGS_FILE", ""), "config/setup_settings.redacted.json")
        _write_optional_json_file(archive, getattr(config, "COMMISSIONING_REPORT_FILE", ""), "commissioning/report.json")
        _write_recent_logs(archive, max_log_bytes=max_log_bytes)

    return path, path.name


def redacted_config_snapshot() -> dict[str, Any]:
    allowed_prefixes = (
        "APP_",
        "SYSTEM_",
        "BIND_",
        "PORT",
        "FAKE_",
        "AUTO_",
        "ROBOT_",
        "VISION_",
        "ENGINE_",
        "NNUE_",
        "DB_",
        "JWT_",
        "CORS_",
        "CONTROL_",
        "RATE_",
        "SOCKET_",
        "TRUST_",
        "SETUP_",
    )
    snapshot: dict[str, Any] = {}
    for name in dir(config):
        if not name.isupper() or not name.startswith(allowed_prefixes):
            continue
        value = getattr(config, name, None)
        if callable(value):
            continue
        snapshot[name] = _redact_value(name, value)
    return dict(sorted(snapshot.items()))


def redact_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): _redact_value(str(key), item) for key, item in value.items()}


def _summary() -> dict[str, Any]:
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cwd": str(ROOT),
    }


def _runtime_status() -> dict[str, Any]:
    try:
        from backend.interfaces.api.shared import runtime_observability_report, runtime_vision_status

        return {
            "observability": runtime_observability_report(),
            "vision": runtime_vision_status(),
        }
    except Exception as exc:
        return {"error": str(exc)}


def _write_json(archive: zipfile.ZipFile, name: str, payload: Any) -> None:
    archive.writestr(name, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _write_optional_json_file(archive: zipfile.ZipFile, source: str | os.PathLike[str], archive_name: str) -> None:
    if not source:
        return
    path = Path(source)
    if not path.is_absolute():
        path = ROOT / path
    try:
        if not path.is_file():
            return
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        _write_json(archive, archive_name, _redact_value(archive_name, payload))
    except Exception as exc:
        _write_json(archive, f"{archive_name}.error.json", {"error": str(exc), "path": str(path)})


def _write_recent_logs(archive: zipfile.ZipFile, *, max_log_bytes: int) -> None:
    logs_dir = ROOT / "logs"
    if not logs_dir.is_dir():
        return
    log_files = sorted(
        [path for path in logs_dir.rglob("*") if path.is_file() and path.suffix.lower() in {".log", ".txt"}],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )[:10]
    for path in log_files:
        try:
            data = path.read_bytes()
            if len(data) > max_log_bytes:
                data = data[-max_log_bytes:]
            rel = path.relative_to(logs_dir).as_posix()
            archive.writestr(f"logs/{rel}", data)
        except Exception:
            continue


def _redact_value(key: str, value: Any) -> Any:
    if _is_sensitive_key(key):
        return "<redacted>" if value not in (None, "") else value
    if isinstance(value, Mapping):
        return {str(item_key): _redact_value(str(item_key), item_value) for item_key, item_value in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_redact_value(key, item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _is_sensitive_key(key: str) -> bool:
    text = str(key or "").lower()
    return any(token in text for token in SENSITIVE_TOKENS)
