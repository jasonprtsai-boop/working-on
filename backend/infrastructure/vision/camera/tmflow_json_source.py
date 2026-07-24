from __future__ import annotations

import base64
import json
import socket
import threading
import time
from typing import Any, Optional

import numpy as np

from backend.utils import config
from backend.utils.logger import logger

from .frame_buffer import frame_buffer


class TMflowJsonFrameSource:
    """
    Receives newline-delimited JSON JPEG frames from a dedicated TMflow vision port.

    This source intentionally does not reuse the robot command/status JSON socket. Large
    image payloads must stay isolated from motion control traffic.
    """

    source = "tmflow_json"

    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        timeout_sec: float | None = None,
        max_message_bytes: int | None = None,
        fps_limit: float | None = None,
    ):
        self.host = str(host if host is not None else getattr(config, "VISION_TMFLOW_IMAGE_HOST", "")).strip()
        self.port = int(port if port is not None else getattr(config, "VISION_TMFLOW_IMAGE_PORT", 5891))
        self.timeout_sec = float(
            timeout_sec if timeout_sec is not None else getattr(config, "VISION_TMFLOW_IMAGE_TIMEOUT_SEC", 2.0)
        )
        self.max_message_bytes = int(
            max_message_bytes
            if max_message_bytes is not None
            else getattr(config, "VISION_TMFLOW_IMAGE_MAX_MESSAGE_BYTES", 1_048_576)
        )
        self.fps_limit = float(fps_limit if fps_limit is not None else getattr(config, "VISION_TMFLOW_IMAGE_FPS_LIMIT", 2.0))

        self.running = False
        self.connected = False
        self.thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._socket_lock = threading.Lock()
        self._socket: Optional[socket.socket] = None

        self.frames_received = 0
        self.decode_failures = 0
        self.dropped_frames = 0
        self.reconnects = 0
        self.last_frame_at: Optional[float] = None
        self.last_frame_id: Optional[str] = None
        self.last_error: Optional[str] = None
        self.connected_at: Optional[float] = None
        self._last_accept_monotonic = 0.0

    def start(self) -> bool:
        if self.running:
            return True
        if not self.host or self.port <= 0:
            self.last_error = "TMflow vision host/port is not configured."
            logger.warning("[VisionSource] %s", self.last_error)
            return False

        self._stop.clear()
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True, name="TMflowJsonFrameSource")
        self.thread.start()
        logger.info("[VisionSource] TMflow JSON frame source starting on %s:%s", self.host, self.port)
        return True

    def stop(self):
        self.running = False
        self._stop.set()
        self._close_socket()
        if self.thread and threading.current_thread() is not self.thread:
            self.thread.join(timeout=2.0)
        self.thread = None
        self.connected = False

    def _run(self):
        backoff = 0.5
        while not self._stop.is_set():
            try:
                sock = socket.create_connection((self.host, self.port), timeout=max(0.1, self.timeout_sec))
                sock.settimeout(max(0.1, self.timeout_sec))
                with self._socket_lock:
                    self._socket = sock
                    self.connected = True
                    self.connected_at = time.time()
                self.last_error = None
                backoff = 0.5
                self._read_loop(sock)
            except OSError as exc:
                self.last_error = str(exc)
                self.reconnects += 1
                logger.debug("[VisionSource] TMflow frame source reconnect pending: %s", exc)
            except Exception as exc:
                self.last_error = str(exc)
                self.reconnects += 1
                logger.warning("[VisionSource] TMflow frame source failed: %s", exc, exc_info=True)
            finally:
                self.connected = False
                self.connected_at = None
                self._close_socket()

            if not self._stop.is_set():
                time.sleep(backoff)
                backoff = min(backoff * 1.7, 5.0)

    def _read_loop(self, sock: socket.socket):
        with sock.makefile("rb") as stream:
            while not self._stop.is_set():
                line = stream.readline(self.max_message_bytes + 1)
                if not line:
                    raise ConnectionError("TMflow vision stream closed.")
                if len(line) > self.max_message_bytes:
                    raise ValueError(
                        f"TMflow vision message exceeds {self.max_message_bytes} bytes; lower JPEG size or raise the vision limit."
                    )
                self._handle_line(line)

    def _handle_line(self, line: bytes) -> None:
        try:
            payload = json.loads(line.decode("utf-8"))
        except Exception as exc:
            self.decode_failures += 1
            self.last_error = f"Invalid JSON frame: {exc}"
            return
        self.ingest_payload(payload, apply_fps_limit=True)

    def ingest_payload(self, payload: dict[str, Any], *, apply_fps_limit: bool = False) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {"ok": False, "reason": "payload_not_object"}

        if not self._payload_has_image(payload):
            return {"ok": False, "reason": "missing_image"}

        now = time.monotonic()
        min_interval = 1.0 / self.fps_limit if self.fps_limit > 0 else 0.0
        if apply_fps_limit and min_interval > 0 and now - self._last_accept_monotonic < min_interval:
            self.dropped_frames += 1
            return {"ok": False, "dropped": True, "reason": "fps_limited"}

        frame = self.decode_payload(payload)
        if frame is None:
            self.decode_failures += 1
            self.last_error = "TMflow vision frame could not be decoded."
            return {"ok": False, "reason": "decode_failed"}

        frame_buffer.put_raw(frame)
        self.frames_received += 1
        self.last_frame_at = time.time()
        self.last_frame_id = str(payload.get("id") or payload.get("frame_id") or "")
        self._last_accept_monotonic = now
        self.last_error = None
        height, width = frame.shape[:2]
        return {
            "ok": True,
            "frame_size": [int(width), int(height)],
            "frames_received": int(self.frames_received),
            "last_frame_id": self.last_frame_id,
        }

    @staticmethod
    def _payload_has_image(payload: dict[str, Any]) -> bool:
        return any(isinstance(payload.get(key), str) and payload.get(key) for key in ("image", "image_base64", "data"))

    @staticmethod
    def decode_payload(payload: dict[str, Any]):
        encoded = payload.get("image") or payload.get("image_base64") or payload.get("data")
        if not isinstance(encoded, str) or not encoded.strip():
            return None
        encoded = encoded.strip()
        if encoded.lower().startswith("data:") and "," in encoded:
            encoded = encoded.split(",", 1)[1]
        try:
            import cv2

            raw = base64.b64decode(encoded, validate=False)
            image_bytes = np.frombuffer(raw, dtype=np.uint8)
            frame = cv2.imdecode(image_bytes, cv2.IMREAD_COLOR)
        except Exception:
            return None
        if frame is None or getattr(frame, "size", 0) <= 0:
            return None
        return frame

    def _close_socket(self):
        with self._socket_lock:
            sock = self._socket
            self._socket = None
        if sock is None:
            return
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            sock.close()
        except Exception:
            pass

    def get_resolution(self):
        return (0, 0)

    def get_status(self) -> dict:
        now = time.time()
        return {
            "source": self.source,
            "running": bool(self.running),
            "opened": bool(self.connected),
            "connected": bool(self.connected),
            "endpoint": f"{self.host}:{self.port}",
            "host": self.host,
            "port": int(self.port),
            "timeout_sec": float(self.timeout_sec),
            "max_message_bytes": int(self.max_message_bytes),
            "fps_limit": float(self.fps_limit),
            "frames_received": int(self.frames_received),
            "decode_failures": int(self.decode_failures),
            "dropped_frames": int(self.dropped_frames),
            "reconnects": int(self.reconnects),
            "last_frame_at": self.last_frame_at,
            "last_frame_age_sec": None if self.last_frame_at is None else max(0.0, now - self.last_frame_at),
            "last_frame_id": self.last_frame_id,
            "last_error": self.last_error,
        }
