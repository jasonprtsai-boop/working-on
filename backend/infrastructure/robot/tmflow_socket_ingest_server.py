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


class TMflowSocketIngestServer:
    """
    Accepts TMflow Socket Send messages on the PC side.

    Supported messages:
    - JSON object per line, with optional tcp/joint/io/image fields.
    - CSV pose per line: x,y,z,rx,ry,rz.
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
            payload = self._parse_message(message)
        except ValueError as exc:
            self.parse_failures += 1
            self.last_error = str(exc)
            return {"ok": False, "reason": "parse_failed", "error": str(exc)}

        if not self._authorized(payload, remote=remote):
            self.auth_failures += 1
            self.last_error = "unauthorized TMflow ingest message."
            return {"ok": False, "reason": "unauthorized"}

        image_result = self._ingest_image(payload)
        status_payload = tmflow_ingest_state.update(payload, remote=remote, image_result=image_result)
        has_telemetry = any(key in status_payload for key in ("position", "orientation", "joint_angles", "speed", "io"))
        image_ok = bool(image_result.get("ok")) if image_result else False
        if image_ok:
            self.frames_received += 1
        elif image_result:
            self.decode_failures += 1

        self.messages_received += 1
        self.last_message_at = time.time()
        self.last_remote = _remote_text(remote)
        self.last_error = None if (has_telemetry or image_ok) else "message did not contain telemetry or image."

        if has_telemetry:
            bus.publish(BaseEvent.create(
                event_type=EventType.ROBOT_STATUS_UPDATED,
                source=self.source,
                payload=status_payload,
            ))

        ok = bool(has_telemetry or image_ok)
        return {
            "ok": ok,
            "source": self.source,
            "telemetry_updated": has_telemetry,
            "image": image_result or {"ok": False, "reason": "missing_image"},
            "messages_received": int(self.messages_received),
            "frames_received": int(self.frames_received),
            "last_message_at": self.last_message_at,
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
        try:
            conn.settimeout(2.0)
            with conn:
                with conn.makefile("rb") as stream:
                    while not self._stop.is_set():
                        line = stream.readline(self.max_message_bytes + 1)
                        if not line:
                            break
                        if len(line) > self.max_message_bytes:
                            result = {
                                "ok": False,
                                "reason": "message_too_large",
                                "max_message_bytes": self.max_message_bytes,
                            }
                            self.parse_failures += 1
                            self.last_error = "TMflow ingest message exceeds limit."
                        else:
                            result = self.ingest_message(line, remote=addr)
                        if self.send_ack:
                            self._send_ack(conn, result)
        except Exception as exc:
            self.last_error = str(exc)
            logger.debug("[TMflowIngest] client handler failed: %s", exc, exc_info=True)
        finally:
            self.active_connections = max(0, self.active_connections - 1)

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
        if isinstance(message, dict):
            return dict(message)
        if isinstance(message, bytes):
            if len(message) > self.max_message_bytes:
                raise ValueError(f"message exceeds {self.max_message_bytes} bytes")
            text = message.decode("utf-8", errors="replace").strip()
        else:
            text = str(message or "").strip()
        if not text:
            raise ValueError("empty TMflow ingest message")
        if text.startswith("{"):
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise ValueError("JSON TMflow ingest message must be an object")
            return payload
        numbers = _parse_numeric_csv(text)
        if len(numbers) >= 6:
            return {"type": "TMFLOW_TELEMETRY", "tcp": numbers[:6], "raw_format": "csv"}
        raise ValueError("TMflow ingest message must be JSON or x,y,z,rx,ry,rz CSV")

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
    values = []
    for part in re.split(r"[\s,;]+", text.strip()):
        if not part:
            continue
        values.append(float(part))
    return values


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
