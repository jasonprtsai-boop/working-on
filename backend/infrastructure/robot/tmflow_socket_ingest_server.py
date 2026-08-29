from __future__ import annotations

import hmac
import ipaddress
import json
import re
import socket
import threading
import time
from typing import Any

from backend.events.bus.event_bus import bus
from backend.events.event_types import EventType
from backend.events.models.base_event import BaseEvent
from backend.infrastructure.robot.tmflow_ingest_state import tmflow_ingest_state
from backend.infrastructure.vision.camera.frame_buffer import frame_buffer
from backend.infrastructure.vision.camera.tmflow_json_source import TMflowJsonFrameSource
from backend.utils import config
from backend.utils.logger import logger


_STATUS_TAG_PATTERN = re.compile(r"(READY|HEARTBEAT|ERROR|BUSY|DONE|ERR|RDY|HB)(?=,|$)", re.IGNORECASE)
_POSE_CSV_PREFIXES = {
    "COORD_BASE",
    "COORD_ROBOT",
    "COORDBASE",
    "COORDROBOT",
    "POSE",
    "TCP",
    "TCPPOSE",
    "TCP_POSE",
}


class TMflowSocketIngestServer:
    """
    Accepts TMflow Socket Send messages on the PC side.

    Supported messages:
    - JSON object per line, with optional tcp/joint/io/image fields.
    - CSV pose per line: x,y,z,rx,ry,rz.
    - TMflow Network Node status CSV, e.g. HB,1 or DONE,42.
    """

    source = "tmflow_socket_ingest"

    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        max_message_bytes: int | None = None,
        send_ack: bool | None = None,
        ingest_key: str | None = None,
    ):
        self.host = str(host if host is not None else getattr(config, "TMFLOW_INGEST_SERVER_HOST", "127.0.0.1")).strip()
        self.port = int(port if port is not None else getattr(config, "TMFLOW_INGEST_SERVER_PORT", 5892))
        self.max_message_bytes = int(
            max_message_bytes
            if max_message_bytes is not None
            else getattr(config, "TMFLOW_INGEST_MAX_MESSAGE_BYTES", 1_048_576)
        )
        self.send_ack = bool(send_ack if send_ack is not None else getattr(config, "TMFLOW_INGEST_SEND_ACK", True))
        self.ingest_key = str(
            ingest_key if ingest_key is not None else getattr(config, "TMFLOW_INGEST_KEY", "")
        ).strip()

        self.running = False
        self.thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._socket_lock = threading.RLock()
        self._server_socket: socket.socket | None = None

        self.connections = 0
        self.active_connections = 0
        self.messages_received = 0
        self.frames_received = 0
        self.parse_failures = 0
        self.decode_failures = 0
        self.auth_failures = 0
        self.last_message_at: float | None = None
        self.last_error: str | None = None
        self.last_remote: str | None = None
        self.last_bad_message: str | None = None

    def start(self) -> bool:
        if self.running:
            return True
        if not self.host or self.port <= 0:
            self.last_error = "TMflow ingest host/port is not configured."
            logger.warning("[TMflowIngest] %s", self.last_error)
            return False

        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((self.host, self.port))
            server.listen(8)
            server.settimeout(0.5)
        except OSError as exc:
            self.last_error = str(exc)
            logger.error("[TMflowIngest] failed to listen on %s:%s: %s", self.host, self.port, exc)
            return False

        with self._socket_lock:
            self._server_socket = server
            self.running = True
            self._stop.clear()
        self.thread = threading.Thread(target=self._run, daemon=True, name="TMflowSocketIngestServer")
        self.thread.start()
        logger.info("[TMflowIngest] listening on %s:%s", self.host, self.port)
        return True

    def stop(self) -> None:
        self._stop.set()
        self.running = False
        with self._socket_lock:
            server = self._server_socket
            self._server_socket = None
        if server is not None:
            try:
                server.close()
            except Exception:
                pass
        if self.thread and threading.current_thread() is not self.thread:
            self.thread.join(timeout=2.0)
        self.thread = None
        self.active_connections = 0

    def ingest_message(
        self,
        message: bytes | str | dict[str, Any],
        *,
        remote: tuple[str, int] | str | None = None,
    ) -> dict[str, Any]:
        try:
            payloads = self._parse_messages(message)
        except ValueError as exc:
            self.parse_failures += 1
            self.last_error = str(exc)
            self.last_bad_message = _message_preview(message)
            return {"ok": False, "reason": "parse_failed", "error": str(exc)}

        telemetry_updated = False
        image_result: dict[str, Any] = {}
        image_updated = False
        processed = 0

        for payload in payloads:
            if not self._authorized(payload, remote=remote):
                self.auth_failures += 1
                self.last_error = "unauthorized TMflow ingest message."
                return {"ok": False, "reason": "unauthorized"}

            current_image_result = self._ingest_image(payload)
            status_payload = tmflow_ingest_state.update(payload, remote=remote, image_result=current_image_result)
            has_telemetry = any(
                key in status_payload
                for key in (
                    "position",
                    "orientation",
                    "joint_angles",
                    "speed",
                    "io",
                    "heartbeat_seen",
                    "robot_state_code",
                    "status_code",
                    "current_command_id",
                    "completed_command_id",
                    "error_code",
                )
            )
            image_ok = bool(current_image_result.get("ok")) if current_image_result else False
            if current_image_result:
                image_result = current_image_result
            if image_ok:
                self.frames_received += 1
                image_updated = True
            elif current_image_result:
                self.decode_failures += 1

            self.messages_received += 1
            processed += 1
            self.last_message_at = time.time()
            self.last_remote = _remote_text(remote)
            telemetry_updated = bool(telemetry_updated or has_telemetry)

            if has_telemetry:
                bus.publish(BaseEvent.create(
                    event_type=EventType.ROBOT_STATUS_UPDATED,
                    source=self.source,
                    payload=status_payload,
                ))

        ok = bool(telemetry_updated or image_updated)
        self.last_error = None if ok else "message did not contain telemetry or image."

        return {
            "ok": ok,
            "source": self.source,
            "telemetry_updated": telemetry_updated,
            "image": image_result or {"ok": False, "reason": "missing_image"},
            "messages_received": int(self.messages_received),
            "frames_received": int(self.frames_received),
            "last_message_at": self.last_message_at,
            "parsed_messages": int(processed),
            "reason": None if ok else "missing_telemetry_or_image",
        }

    def get_status(self) -> dict[str, Any]:
        now = time.time()
        max_age = float(getattr(config, "TMFLOW_INGEST_TELEMETRY_MAX_AGE_SEC", 3.0))
        return {
            "source": self.source,
            "enabled": bool(getattr(config, "TMFLOW_INGEST_SERVER_ENABLED", False)),
            "running": bool(self.running),
            "host": self.host,
            "port": int(self.port),
            "endpoint": f"{self.host}:{self.port}",
            "max_message_bytes": int(self.max_message_bytes),
            "send_ack": bool(self.send_ack),
            "key_configured": bool(self.ingest_key),
            "connections": int(self.connections),
            "active_connections": int(self.active_connections),
            "messages_received": int(self.messages_received),
            "frames_received": int(self.frames_received),
            "parse_failures": int(self.parse_failures),
            "decode_failures": int(self.decode_failures),
            "auth_failures": int(self.auth_failures),
            "last_message_at": self.last_message_at,
            "last_message_age_sec": None if self.last_message_at is None else max(0.0, now - self.last_message_at),
            "last_remote": self.last_remote,
            "last_error": self.last_error,
            "last_bad_message": self.last_bad_message,
            "telemetry": tmflow_ingest_state.status(max_age_sec=max_age),
        }

    def _run(self) -> None:
        while not self._stop.is_set():
            with self._socket_lock:
                server = self._server_socket
            if server is None:
                break
            try:
                conn, addr = server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            self.connections += 1
            self.active_connections += 1
            thread = threading.Thread(
                target=self._handle_client,
                args=(conn, addr),
                daemon=True,
                name="TMflowSocketIngestClient",
            )
            thread.start()
        self.running = False

    def _handle_client(self, conn: socket.socket, addr: tuple[str, int]) -> None:
        buffer = b""
        try:
            conn.settimeout(0.2)
            with conn:
                while not self._stop.is_set():
                    try:
                        chunk = conn.recv(min(4096, self.max_message_bytes + 1))
                    except socket.timeout:
                        buffer = self._ingest_ready_socket_buffer(conn, addr, buffer, force=False)
                        continue

                    if not chunk:
                        if buffer:
                            self._ingest_ready_socket_buffer(conn, addr, buffer, force=True)
                        break

                    buffer += chunk
                    if len(buffer) > self.max_message_bytes:
                        result = {
                            "ok": False,
                            "reason": "message_too_large",
                            "max_message_bytes": self.max_message_bytes,
                        }
                        self.parse_failures += 1
                        self.last_error = "TMflow ingest message exceeds limit."
                        self.last_bad_message = _message_preview(buffer)
                        if self.send_ack:
                            self._send_ack(conn, result)
                        break

                    buffer = self._ingest_ready_socket_buffer(conn, addr, buffer, force=False)
        except Exception as exc:
            self.last_error = str(exc)
            logger.debug("[TMflowIngest] client handler failed: %s", exc, exc_info=True)
        finally:
            self.active_connections = max(0, self.active_connections - 1)

    def _ingest_ready_socket_buffer(
        self,
        conn: socket.socket,
        addr: tuple[str, int],
        buffer: bytes,
        *,
        force: bool,
    ) -> bytes:
        messages, remainder = _ready_socket_messages(buffer, force=force)
        for message in messages:
            result = self.ingest_message(message, remote=addr)
            if self.send_ack:
                self._send_ack(conn, result)
        return remainder

    def _send_ack(self, conn: socket.socket, result: dict[str, Any]) -> None:
        try:
            ack = json.dumps(
                {
                    "ok": bool(result.get("ok")),
                    "reason": result.get("reason"),
                    "messages_received": result.get("messages_received"),
                    "frames_received": result.get("frames_received"),
                },
                separators=(",", ":"),
            ).encode("utf-8") + b"\n"
            conn.sendall(ack)
        except Exception:
            logger.debug("[TMflowIngest] failed to send ack", exc_info=True)

    def _parse_message(self, message: bytes | str | dict[str, Any]) -> dict[str, Any]:
        return self._parse_messages(message)[-1]

    def _parse_messages(self, message: bytes | str | dict[str, Any]) -> list[dict[str, Any]]:
        if isinstance(message, dict):
            return [dict(message)]
        if isinstance(message, bytes):
            if len(message) > self.max_message_bytes:
                raise ValueError(f"message exceeds {self.max_message_bytes} bytes")
            text = message.decode("utf-8", errors="replace").strip()
        else:
            text = str(message or "").strip()
        if not text:
            raise ValueError("empty TMflow ingest message")
        text = _strip_wrapping_quotes(text)
        if text.startswith("{"):
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise ValueError("JSON TMflow ingest message must be an object")
            return [payload]
        status_payloads = _parse_status_csv_records(text)
        if status_payloads:
            return status_payloads
        try:
            numbers = _parse_numeric_csv(text)
        except ValueError as exc:
            raise ValueError(
                "TMflow ingest message must be JSON, TMflow status CSV, or x,y,z,rx,ry,rz CSV"
            ) from exc
        if len(numbers) >= 6:
            return [{"type": "TMFLOW_TELEMETRY", "tcp": numbers[:6], "raw_format": "csv", "raw": text}]
        raise ValueError("TMflow ingest message must be JSON, TMflow status CSV, or x,y,z,rx,ry,rz CSV")

    def _authorized(self, payload: dict[str, Any], *, remote: tuple[str, int] | str | None) -> bool:
        expected_key = self.ingest_key
        if expected_key:
            provided = _provided_key(payload)
            return hmac.compare_digest(provided, expected_key)
        if bool(getattr(config, "IS_PRODUCTION", False)):
            return False
        if bool(getattr(config, "TMFLOW_INGEST_ALLOW_TRUSTED_LAB_IPS", True)):
            return _trusted_lab_remote(remote)
        return _loopback_remote(remote)

    def _ingest_image(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not TMflowJsonFrameSource._payload_has_image(payload):
            return {}
        frame = TMflowJsonFrameSource.decode_payload(payload)
        if frame is None:
            return {"ok": False, "reason": "decode_failed"}
        frame_buffer.put_raw(frame)
        height, width = frame.shape[:2]
        return {
            "ok": True,
            "frame_size": [int(width), int(height)],
            "last_frame_id": str(payload.get("id") or payload.get("frame_id") or ""),
        }


def _parse_numeric_csv(text: str) -> list[float]:
    text = _numeric_csv_body(text)
    values = []
    for part in re.split(r"[\s,;]+", text.strip()):
        if not part:
            continue
        values.append(float(part))
    return values


def _numeric_csv_body(text: str) -> str:
    value = _strip_wrapping_quotes(str(text or "").strip())
    if "=" in value:
        value = value.split("=", 1)[1].strip()
    value = _strip_wrapped_numeric_array(value)
    if "," in value:
        prefix, body = value.split(",", 1)
        normalized_prefix = re.sub(r"[^A-Za-z0-9_]", "", prefix).upper()
        if normalized_prefix in _POSE_CSV_PREFIXES:
            value = _strip_wrapped_numeric_array(body.strip())
    return value


def _strip_wrapped_numeric_array(value: str) -> str:
    if len(value) >= 2 and value[0] in "{[" and value[-1] in "}]":
        value = value[1:-1].strip()
    return value


def _message_preview(message: bytes | str | dict[str, Any], *, max_chars: int = 240) -> str:
    if isinstance(message, bytes):
        text = message.decode("utf-8", errors="replace")
    elif isinstance(message, dict):
        try:
            text = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            text = str(message)
    else:
        text = str(message or "")
    text = text.strip().replace("\r", r"\r").replace("\n", r"\n")
    if len(text) > max_chars:
        return text[:max_chars] + "..."
    return text


def _ready_socket_messages(buffer: bytes, *, force: bool = False) -> tuple[list[bytes], bytes]:
    if not buffer:
        return [], b""

    text = buffer.decode("utf-8", errors="replace")
    if _status_text_ready(text):
        return [buffer], b""

    newline_match = re.search(rb"[\r\n]", buffer)
    if newline_match:
        lines = re.split(rb"\r\n|\n|\r", buffer)
        ends_with_newline = bool(re.search(rb"[\r\n]$", buffer))
        complete = lines if ends_with_newline else lines[:-1]
        remainder = b"" if ends_with_newline else lines[-1]
        return [line for line in complete if line.strip()], remainder

    literal_records, literal_remainder = _split_literal_newline_messages(buffer)
    if literal_records:
        return literal_records, literal_remainder

    if force and buffer.strip():
        return [buffer], b""

    return [], buffer


def _split_literal_newline_messages(buffer: bytes) -> tuple[list[bytes], bytes]:
    text = buffer.decode("utf-8", errors="replace")
    delimiter_pattern = re.compile(r"\\r\\n|\\n|\\r")
    if not delimiter_pattern.search(text):
        return [], buffer

    parts = delimiter_pattern.split(text)
    ends_with_delimiter = bool(delimiter_pattern.search(text[-4:]))
    complete = parts if ends_with_delimiter else parts[:-1]
    remainder = "" if ends_with_delimiter else parts[-1]
    return [part.encode("utf-8") for part in complete if part.strip()], remainder.encode("utf-8")


def _status_text_ready(text: str) -> bool:
    normalized = _normalize_tmflow_text(text)
    if not _STATUS_TAG_PATTERN.search(normalized):
        return False
    records = _status_csv_records(normalized)
    if not records:
        return False
    return all(_status_record_complete(record) for record in records)


def _status_record_complete(record: str) -> bool:
    parts = [part.strip() for part in re.split(r"\s*,\s*", record.strip()) if part.strip()]
    if not parts:
        return False
    tag = parts[0].upper()
    if tag in {"READY", "RDY"}:
        return True
    if tag in {"HB", "HEARTBEAT"}:
        return len(parts) >= 2
    if tag in {"BUSY", "DONE"}:
        return len(parts) >= 2 and _optional_int(parts[1]) is not None
    if tag in {"ERR", "ERROR"}:
        return len(parts) >= 3 and _optional_int(parts[1]) is not None and _optional_int(parts[2]) is not None
    return False


def _parse_status_csv_records(text: str) -> list[dict[str, Any]]:
    payloads = []
    for record in _status_csv_records(text):
        payload = _parse_status_csv(record)
        if payload is not None:
            payloads.append(payload)
    return payloads


def _status_csv_records(text: str) -> list[str]:
    normalized = _normalize_tmflow_text(text)
    records = []
    for line in re.split(r"[\r\n]+", normalized):
        line = _strip_wrapping_quotes(line.strip())
        if not line:
            continue
        matches = list(_STATUS_TAG_PATTERN.finditer(line))
        if not matches:
            records.append(line)
            continue
        for index, match in enumerate(matches):
            start = match.start()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(line)
            record = line[start:end].strip(" ,;")
            if record:
                records.append(record)
    return records


def _normalize_tmflow_text(text: str) -> str:
    normalized = str(text or "").strip()
    normalized = _strip_wrapping_quotes(normalized)
    return (
        normalized
        .replace("\\r\\n", "\n")
        .replace("\\n", "\n")
        .replace("\\r", "\n")
    )


def _strip_wrapping_quotes(text: str) -> str:
    value = str(text or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1].strip()
    return value


def _parse_status_csv(text: str) -> dict[str, Any] | None:
    parts = [part.strip() for part in re.split(r"\s*,\s*", text.strip()) if part.strip()]
    if not parts:
        return None
    tag = parts[0].upper()
    payload: dict[str, Any] = {
        "raw_format": "tmflow_network_csv",
        "raw": text.strip(),
    }

    if tag in {"READY", "RDY"}:
        payload.update({
            "type": "TMFLOW_READY",
            "event": "ready",
            "heartbeat_seen": True,
            "robot_state_code": 1,
        })
        return payload

    if tag in {"HB", "HEARTBEAT"}:
        payload.update({
            "type": "TMFLOW_HEARTBEAT",
            "event": "heartbeat",
            "heartbeat_seen": True,
        })
        if len(parts) > 1:
            robot_state = _optional_int(parts[1])
            if robot_state is not None:
                payload["robot_state_code"] = robot_state
            else:
                payload["robot_state_label"] = parts[1]
        if len(parts) > 2:
            completed_id = _optional_int(parts[2])
            if completed_id is not None:
                payload["completed_command_id"] = completed_id
        return payload

    if tag == "BUSY":
        payload.update({
            "type": "TMFLOW_COMMAND_STATUS",
            "event": "busy",
            "status_code": 1,
            "status_label": "busy",
            "robot_state_code": 2,
        })
        if len(parts) > 1:
            command_id = _optional_int(parts[1])
            if command_id is not None:
                payload["current_command_id"] = command_id
        return payload

    if tag == "DONE":
        payload.update({
            "type": "TMFLOW_COMMAND_STATUS",
            "event": "done",
            "status_code": 2,
            "status_label": "done",
            "robot_state_code": 1,
        })
        if len(parts) > 1:
            completed_id = _optional_int(parts[1])
            if completed_id is not None:
                payload["completed_command_id"] = completed_id
        return payload

    if tag in {"ERR", "ERROR"}:
        payload.update({
            "type": "TMFLOW_COMMAND_STATUS",
            "event": "error",
            "status_code": 3,
            "status_label": "error",
            "robot_state_code": 3,
        })
        if len(parts) > 1:
            command_id = _optional_int(parts[1])
            if command_id is not None:
                payload["current_command_id"] = command_id
        if len(parts) > 2:
            error_code = _optional_int(parts[2])
            if error_code is not None:
                payload["error_code"] = error_code
        return payload

    return None


def _optional_int(value: Any) -> int | None:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _provided_key(payload: dict[str, Any]) -> str:
    for key in ("key", "ingest_key", "tmflow_key", "vision_key", "token"):
        value = payload.get(key)
        if value:
            return str(value).strip()
    meta = payload.get("meta")
    if isinstance(meta, dict):
        return _provided_key(meta)
    nested = payload.get("payload")
    if isinstance(nested, dict):
        return _provided_key(nested)
    return ""


def _trusted_lab_remote(remote: tuple[str, int] | str | None) -> bool:
    host = _remote_host(remote)
    if not host:
        return False
    trusted_hosts = {
        "127.0.0.1",
        "::1",
        str(getattr(config, "ROBOT_IP", "") or "").strip(),
        str(getattr(config, "ROBOT_PC_IP", "") or "").strip(),
    }
    if host in trusted_hosts:
        return True
    return _loopback_remote(remote)


def _loopback_remote(remote: tuple[str, int] | str | None) -> bool:
    host = _remote_host(remote)
    if not host:
        return False
    try:
        remote_ip = ipaddress.ip_address(host)
        return bool(remote_ip.is_loopback or remote_ip.is_link_local)
    except ValueError:
        return False


def _remote_host(remote: tuple[str, int] | str | None) -> str:
    if isinstance(remote, tuple) and remote:
        return str(remote[0] or "").strip()
    text = str(remote or "").strip()
    if not text:
        return ""
    if ":" in text and text.count(":") == 1:
        return text.split(":", 1)[0].strip()
    return text


def _remote_text(remote: tuple[str, int] | str | None) -> str:
    if isinstance(remote, tuple) and len(remote) >= 2:
        return f"{remote[0]}:{remote[1]}"
    return str(remote or "").strip()


tmflow_socket_ingest_server = TMflowSocketIngestServer()
