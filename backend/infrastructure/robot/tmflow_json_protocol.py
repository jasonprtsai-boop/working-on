from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping


PROTOCOL_VERSION = "1.0"
FINAL_STATUSES = {"DONE", "ERROR", "REJECTED", "BUSY"}
ERROR_STATUSES = {"ERROR", "REJECTED", "BUSY"}


class TMflowJsonProtocolError(RuntimeError):
    """Raised when the TMflow TCP JSON protocol returns an invalid message."""


class CommandIdGenerator:
    def __init__(self):
        self._sequence = 0
        self._lock = threading.Lock()

    def next(self) -> str:
        with self._lock:
            self._sequence = (self._sequence % 999) + 1
            sequence = self._sequence
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"CMD_{stamp}_{sequence:03d}"


def iso_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class RobotCommand:
    id: str
    command: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
    version: str = PROTOCOL_VERSION
    type: str = "COMMAND"

    def to_envelope(self) -> dict[str, Any]:
        data = {
            "version": self.version,
            "type": self.type,
            "id": self.id,
            "timestamp": iso_timestamp(),
            "payload": dict(self.payload),
        }
        if self.command:
            data["command"] = self.command
        if self.meta:
            data["meta"] = dict(self.meta)
        return data

    def to_flat_json(self) -> dict[str, Any]:
        data = {
            "id": self.id,
            "command": self.command or self.type,
        }
        for key, value in self.payload.items():
            if isinstance(value, Mapping):
                for nested_key, nested_value in value.items():
                    data[str(nested_key)] = nested_value
            else:
                data[str(key)] = value
        return data

    def to_json_line(self, *, wire_format: str = "envelope") -> bytes:
        wire_format = str(wire_format or "envelope").strip().lower()
        data = self.to_flat_json() if wire_format == "flat_json" else self.to_envelope()
        return (json.dumps(data, ensure_ascii=True, separators=(",", ":")) + "\n").encode("utf-8")


@dataclass(frozen=True)
class RobotResponse:
    raw: dict[str, Any]
    id: str
    type: str
    status: str
    state: str
    result: dict[str, Any]
    error: dict[str, Any] | None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "RobotResponse":
        if not isinstance(data, Mapping):
            raise TMflowJsonProtocolError("TMflow response must be a JSON object.")
        response_id = str(data.get("id") or "")
        if not response_id:
            raise TMflowJsonProtocolError("TMflow response is missing id.")
        result = data.get("result") if isinstance(data.get("result"), Mapping) else {}
        error = data.get("error") if isinstance(data.get("error"), Mapping) else None
        return cls(
            raw=dict(data),
            id=response_id,
            type=str(data.get("type") or "RESPONSE").upper(),
            status=str(data.get("status") or "").upper(),
            state=str(data.get("state") or ""),
            result=dict(result),
            error=dict(error) if error is not None else None,
        )

    @property
    def is_final(self) -> bool:
        return self.status in FINAL_STATUSES or self.type == "PONG"

    @property
    def is_error(self) -> bool:
        return self.status in ERROR_STATUSES or self.error is not None


def parse_json_line(raw: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise TMflowJsonProtocolError(f"Invalid TMflow JSON response: {exc}") from exc
    if not isinstance(payload, dict):
        raise TMflowJsonProtocolError("TMflow response must be a JSON object.")
    return payload
