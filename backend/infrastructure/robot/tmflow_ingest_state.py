from __future__ import annotations

import copy
import math
import threading
import time
from typing import Any


_IMAGE_KEYS = {"image", "image_base64", "data"}
_SECRET_KEYS = {"key", "ingest_key", "tmflow_key", "vision_key", "token"}


class TMflowIngestState:
    """Thread-safe cache for telemetry pushed from TMflow Socket Send."""

    source = "tmflow_socket_ingest"

    def __init__(self):
        self._lock = threading.RLock()
        self._snapshot: dict[str, Any] | None = None

    def clear(self) -> None:
        with self._lock:
            self._snapshot = None

    def update(
        self,
        message: dict[str, Any],
        *,
        remote: tuple[str, int] | str | None = None,
        image_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body = _payload_body(message)
        now = time.time()
        position, orientation, tcp = _extract_pose(body)
        joint_angles = _extract_joints(body)
        io_state = _extract_io(body)
        speed = _optional_float(_first_present(body, ("speed", "tcp_speed", "velocity")))
        timestamp = _optional_float(_first_present(body, ("timestamp", "ts", "time"))) or now
        valid_image = bool(image_result and image_result.get("ok"))
        if not any((position, orientation, joint_angles, io_state, speed is not None, valid_image)):
            return {}

        telemetry = {
            "enabled": True,
            "source": self.source,
            "timestamp": timestamp,
            "updated_at": now,
            "remote": _remote_text(remote),
            "raw_type": str(body.get("type") or body.get("event") or "").strip(),
        }
        if tcp:
            telemetry["tcp"] = list(tcp)
            telemetry["pose"] = {
                "x": tcp[0],
                "y": tcp[1],
                "z": tcp[2],
                "rx": tcp[3],
                "ry": tcp[4],
                "rz": tcp[5],
            }
        elif position:
            telemetry["pose"] = dict(position)
        if joint_angles:
            telemetry["joint_angles"] = dict(joint_angles)
        if io_state:
            telemetry["io"] = dict(io_state)
        if speed is not None:
            telemetry["speed"] = speed
        if image_result:
            telemetry["image"] = _public_image_result(image_result)

        snapshot: dict[str, Any] = {
            "source": self.source,
            "updated_at": now,
            "timestamp": timestamp,
            "telemetry": telemetry,
        }
        if position:
            snapshot["position"] = dict(position)
        if orientation:
            snapshot["orientation"] = dict(orientation)
        if joint_angles:
            snapshot["joint_angles"] = dict(joint_angles)
        if io_state:
            snapshot["io"] = dict(io_state)
        if speed is not None:
            snapshot["speed"] = speed
        if image_result:
            public_image = _public_image_result(image_result)
            snapshot["image"] = public_image
            frame_id = public_image.get("last_frame_id") or public_image.get("frame_id")
            if frame_id:
                snapshot["last_frame_id"] = str(frame_id)
                telemetry["last_frame_id"] = str(frame_id)

        with self._lock:
            self._snapshot = copy.deepcopy(snapshot)
        return self.snapshot() or {}

    def snapshot(self, *, max_age_sec: float | None = None) -> dict[str, Any] | None:
        with self._lock:
            if self._snapshot is None:
                return None
            data = copy.deepcopy(self._snapshot)
        now = time.time()
        age_sec = max(0.0, now - float(data.get("updated_at") or now))
        data["age_sec"] = age_sec
        data["stale"] = bool(max_age_sec is not None and age_sec > float(max_age_sec))
        telemetry = data.get("telemetry")
        if isinstance(telemetry, dict):
            telemetry["age_sec"] = age_sec
            telemetry["stale"] = data["stale"]
        return data

    def merge_status(self, base_status: dict[str, Any], *, max_age_sec: float | None = None) -> dict[str, Any]:
        status = dict(base_status or {})
        snapshot = self.snapshot(max_age_sec=max_age_sec)
        if not snapshot or snapshot.get("stale"):
            return status

        for key in ("position", "orientation", "joint_angles", "speed"):
            if key in snapshot:
                status[key] = copy.deepcopy(snapshot[key])

        base_telemetry = status.get("telemetry") if isinstance(status.get("telemetry"), dict) else {}
        status["telemetry"] = {
            **dict(base_telemetry),
            **copy.deepcopy(snapshot.get("telemetry") or {}),
        }
        connection = status.get("connection") if isinstance(status.get("connection"), dict) else {}
        status["connection"] = {
            **dict(connection),
            "telemetry_source": self.source,
            "telemetry_connected": True,
            "telemetry_updated_at": snapshot.get("updated_at"),
        }
        return status

    def status(self, *, max_age_sec: float | None = None) -> dict[str, Any]:
        snapshot = self.snapshot(max_age_sec=max_age_sec)
        if not snapshot:
            return {
                "source": self.source,
                "available": False,
                "connected": False,
                "last_update_at": None,
            }
        return {
            "source": self.source,
            "available": True,
            "connected": not bool(snapshot.get("stale")),
            "last_update_at": snapshot.get("updated_at"),
            "last_update_age_sec": snapshot.get("age_sec"),
            "stale": bool(snapshot.get("stale")),
            "remote": (snapshot.get("telemetry") or {}).get("remote"),
            "has_pose": bool(snapshot.get("position")),
            "has_joints": bool(snapshot.get("joint_angles")),
            "has_image": bool(snapshot.get("image")),
        }


def _payload_body(message: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(message, dict):
        return {}
    nested = message.get("payload")
    if isinstance(nested, dict):
        body = dict(nested)
        for key in ("id", "frame_id", "timestamp", "ts", "type", "event"):
            if key in message and key not in body:
                body[key] = message[key]
        for key in _SECRET_KEYS:
            if key in message and key not in body:
                body[key] = message[key]
        return body
    return dict(message)


def _extract_pose(body: dict[str, Any]) -> tuple[dict[str, float] | None, dict[str, float] | None, list[float] | None]:
    source = _first_present(
        body,
        (
            "tcp",
            "pose",
            "current_tcp",
            "currentTCP",
            "tcp_pose",
            "tool_pose",
            "robot_position",
            "position",
            "pos",
        ),
    )
    if source is None and all(key in body for key in ("x", "y", "z")):
        source = body

    values = _pose_values(source)
    if values and len(values) >= 6:
        tcp = values[:6]
        return (
            {"x": tcp[0], "y": tcp[1], "z": tcp[2]},
            {"rx": tcp[3], "ry": tcp[4], "rz": tcp[5]},
            tcp,
        )
    if values and len(values) >= 3:
        pos = values[:3]
        return {"x": pos[0], "y": pos[1], "z": pos[2]}, None, None

    if isinstance(source, dict):
        position = _axis_dict(source, ("x", "y", "z"))
        orientation = _axis_dict(source, ("rx", "ry", "rz"))
        tcp = None
        if position and orientation:
            tcp = [
                position["x"],
                position["y"],
                position["z"],
                orientation["rx"],
                orientation["ry"],
                orientation["rz"],
            ]
        return position, orientation, tcp

    return None, None, None


def _extract_joints(body: dict[str, Any]) -> dict[str, float] | None:
    source = _first_present(body, ("joint_angles", "joint_angle", "joints", "joint"))
    if isinstance(source, (list, tuple)):
        result = {}
        for index, value in enumerate(source[:12], start=1):
            number = _optional_float(value)
            if number is not None:
                result[f"j{index}"] = number
        return result or None
    if isinstance(source, dict):
        result = {}
        for key, value in source.items():
            number = _optional_float(value)
            if number is not None:
                result[str(key).strip().lower()] = number
        return result or None
    return None


def _extract_io(body: dict[str, Any]) -> dict[str, Any] | None:
    source = _first_present(body, ("io", "digital_io", "digital_inputs", "digital_outputs"))
    if isinstance(source, dict):
        return dict(source)
    io_state = {}
    for key in ("di", "do", "si", "so"):
        value = body.get(key)
        if isinstance(value, (dict, list, tuple, bool, int, float, str)):
            io_state[key] = value
    return io_state or None


def _pose_values(source: Any) -> list[float] | None:
    if isinstance(source, (list, tuple)):
        values = []
        for value in source:
            number = _optional_float(value)
            if number is None:
                return None
            values.append(number)
        return values
    if isinstance(source, str):
        parts = [part for part in source.replace(";", ",").split(",") if part.strip()]
        values = []
        for part in parts:
            number = _optional_float(part)
            if number is None:
                return None
            values.append(number)
        return values or None
    return None


def _axis_dict(source: dict[str, Any], axes: tuple[str, ...]) -> dict[str, float] | None:
    result = {}
    for axis in axes:
        value = _optional_float(_case_insensitive_get(source, axis))
        if value is None:
            return None
        result[axis] = value
    return result


def _case_insensitive_get(source: dict[str, Any], key: str) -> Any:
    aliases = {
        "x": ("x", "X", "PosX", "pos_x"),
        "y": ("y", "Y", "PosY", "pos_y"),
        "z": ("z", "Z", "PosZ", "pos_z"),
        "rx": ("rx", "Rx", "RX", "PosRx", "pos_rx"),
        "ry": ("ry", "Ry", "RY", "PosRy", "pos_ry"),
        "rz": ("rz", "Rz", "RZ", "PosRz", "pos_rz"),
    }
    for name in aliases.get(key, (key,)):
        if name in source:
            return source[name]
    lowered = {str(name).strip().lower(): value for name, value in source.items()}
    return lowered.get(key.lower())


def _first_present(source: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in source and source[key] is not None:
            return source[key]
    return None


def _optional_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _remote_text(remote: tuple[str, int] | str | None) -> str:
    if isinstance(remote, tuple) and len(remote) >= 2:
        return f"{remote[0]}:{remote[1]}"
    return str(remote or "").strip()


def _public_image_result(image_result: dict[str, Any]) -> dict[str, Any]:
    public = {}
    for key, value in dict(image_result or {}).items():
        if key in _IMAGE_KEYS or key in _SECRET_KEYS:
            continue
        public[key] = value
    return public


tmflow_ingest_state = TMflowIngestState()
