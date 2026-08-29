import cv2
import threading
import time
from typing import Optional, Tuple
from backend.utils.logger import logger
from backend.utils import config
from .frame_buffer import frame_buffer

class CameraManager:
    """
    Manages camera lifecycle, frame buffering, and multi-threaded capture.
    """
    source = "opencv"

    def __init__(self, camera_index: int = None):
        self.camera_index = camera_index if camera_index is not None else self._configured_source()
        self.cap: Optional[cv2.VideoCapture] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self._cap_lock = threading.Lock()
        self._read_failures = 0
        self._last_failure_log_at = 0.0
        self._frames_captured = 0
        self._last_frame_at = None
        self._opened_backend = None

    def _configured_source(self):
        source = str(getattr(config, "VISION_OPENCV_SOURCE", "") or "").strip()
        if source:
            return self._coerce_source(source)
        return int(getattr(config, "CAMERA_INDEX", 0))

    def _coerce_source(self, source):
        if isinstance(source, str):
            text = source.strip()
            if text.lstrip("-").isdigit():
                return int(text)
            return text
        return source

    def _source_is_device_index(self) -> bool:
        return isinstance(self.camera_index, int)

    def _open_capture(self) -> Optional[cv2.VideoCapture]:
        """Open a VideoCapture for the current camera_index (best-effort)."""
        source = self._coerce_source(self.camera_index)
        backends = []
        if self._source_is_device_index():
            for name in ("CAP_DSHOW", "CAP_MSMF"):
                backend = getattr(cv2, name, None)
                if backend is not None:
                    backends.append((name, backend))
        else:
            backend = getattr(cv2, "CAP_FFMPEG", None)
            if backend is not None:
                backends.append(("CAP_FFMPEG", backend))
        backends.append(("default", None))

        for backend_name, backend in backends:
            cap = None
            try:
                cap = cv2.VideoCapture(source, backend) if backend is not None else cv2.VideoCapture(source)
                if not cap or not cap.isOpened():
                    try:
                        if cap:
                            cap.release()
                    except Exception:
                        pass
                    continue
                self._configure_capture(cap)
                self._opened_backend = backend_name
                logger.info(
                    "Camera source %s opened with %s backend at %sx%s fps=%s.",
                    source,
                    backend_name,
                    int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                    int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                    round(float(cap.get(cv2.CAP_PROP_FPS) or 0.0), 3),
                )
                return cap
            except Exception:
                logger.debug(f"Camera source {source} open failed with {backend_name} backend.", exc_info=True)
                try:
                    if cap:
                        cap.release()
                except Exception:
                    pass
        return None

    def _configure_capture(self, cap: cv2.VideoCapture) -> None:
        buffer_size = max(1, int(getattr(config, "VISION_CAPTURE_BUFFER_SIZE", 1) or 1))
        self._set_capture_property(cap, cv2.CAP_PROP_BUFFERSIZE, buffer_size)

        fourcc = str(getattr(config, "VISION_CAPTURE_FOURCC", "MJPG") or "").strip().upper()
        if fourcc and len(fourcc) == 4:
            self._set_capture_property(cap, cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))

        width = int(getattr(config, "VISION_CAPTURE_WIDTH", 0) or 0)
        height = int(getattr(config, "VISION_CAPTURE_HEIGHT", 0) or 0)
        fps = float(getattr(config, "VISION_CAPTURE_FPS", 0.0) or 0.0)
        if width > 0:
            self._set_capture_property(cap, cv2.CAP_PROP_FRAME_WIDTH, width)
        if height > 0:
            self._set_capture_property(cap, cv2.CAP_PROP_FRAME_HEIGHT, height)
        if fps > 0:
            self._set_capture_property(cap, cv2.CAP_PROP_FPS, fps)

    def _set_capture_property(self, cap: cv2.VideoCapture, prop, value) -> None:
        try:
            cap.set(prop, value)
        except Exception:
            logger.debug("[CameraManager] Failed to set capture property %s=%s", prop, value, exc_info=True)

    def start(self) -> bool:
        if self.running:
            return True

        logger.info(f"Initializing camera source {self.camera_index}...")
        cap = self._open_capture()
        if cap is None:
            logger.error(f"Failed to open camera source {self.camera_index}")
            return False
        with self._cap_lock:
            self.cap = cap
        self.running = True
        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()
        return True

    def stop(self):
        self.running = False
        # Avoid joining from within the capture thread itself.
        if self.thread and threading.current_thread() is not self.thread:
            self.thread.join(timeout=1.0)
        with self._cap_lock:
            if self.cap:
                try:
                    self.cap.release()
                except Exception:
                    pass
            self.cap = None

    def set_camera_index(self, camera_index: int) -> bool:
        """Switch camera device safely (stop -> re-open -> restart capture)."""
        camera_index = self._coerce_source(camera_index)

        was_running = self.running
        if was_running:
            self.stop()
        self.camera_index = camera_index
        if was_running:
            return self.start()
        return True

    def capture_once(self, timeout_sec: float = 1.5):
        """Open the configured source long enough to capture one diagnostic frame."""
        cap = self._open_capture()
        if cap is None:
            return None
        deadline = time.time() + max(0.1, float(timeout_sec or 0.0))
        try:
            while time.time() < deadline:
                ret, frame = cap.read()
                if ret and frame is not None and getattr(frame, "size", 0) > 0:
                    return frame
                time.sleep(0.03)
            return None
        finally:
            try:
                cap.release()
            except Exception:
                pass

    def _update(self):
        failure_count = 0
        fps_limit = float(getattr(config, "VISION_CAPTURE_THREAD_FPS_LIMIT", 0.0) or 0.0)
        min_interval = 1.0 / fps_limit if fps_limit > 0 else 0.0
        last_emit = 0.0
        while self.running:
            with self._cap_lock:
                cap = self.cap
            if cap is None or not cap.isOpened():
                logger.warning(f"Camera source {self.camera_index} lost. Attempting reconnect...")
                # Re-open capture in-place; do not call start() from within the worker thread.
                new_cap = self._open_capture()
                if new_cap is not None:
                    with self._cap_lock:
                        try:
                            if self.cap:
                                self.cap.release()
                        except Exception:
                            pass
                        self.cap = new_cap
                    failure_count = 0
                    self._read_failures = 0
                else:
                    failure_count += 1
                    time.sleep(min(failure_count * 2, 30)) # Backoff
                continue

            drain = max(0, int(getattr(config, "VISION_CAPTURE_GRAB_DRAIN", 0) or 0))
            if drain:
                for _ in range(drain):
                    if not cap.grab():
                        break
                ret, frame = cap.retrieve()
            else:
                ret, frame = cap.read()
            if ret:
                if min_interval > 0:
                    now = time.monotonic()
                    sleep_for = min_interval - (now - last_emit)
                    if sleep_for > 0:
                        time.sleep(sleep_for)
                    last_emit = time.monotonic()
                frame_buffer.put_raw(frame)
                self._frames_captured += 1
                self._last_frame_at = time.time()
                failure_count = 0
                self._read_failures = 0
            else:
                self._read_failures += 1
                now = time.monotonic()
                if self._read_failures <= 3 or now - self._last_failure_log_at >= 5.0:
                    logger.error(f"Failed to read frame from camera source {self.camera_index} (consecutive={self._read_failures}).")
                    self._last_failure_log_at = now
                failure_count += 1
                if failure_count > 10:
                    # Release capture and let the reconnect branch handle reopen.
                    with self._cap_lock:
                        try:
                            if self.cap:
                                self.cap.release()
                        except Exception:
                            pass
                        self.cap = None
                time.sleep(0.1)

    def get_resolution(self) -> Tuple[int, int]:
        """Returns (width, height)."""
        with self._cap_lock:
            cap = self.cap
        if cap:
            return (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                    int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        return (0, 0)

    def get_status(self) -> dict:
        with self._cap_lock:
            cap = self.cap
            opened = bool(cap and cap.isOpened())
            fps = float(cap.get(cv2.CAP_PROP_FPS)) if opened else 0.0
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) if opened else 0
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) if opened else 0
        return {
            "source": self.source,
            "index": int(self.camera_index) if self._source_is_device_index() else None,
            "capture_source": str(self.camera_index),
            "running": bool(self.running),
            "opened": opened,
            "backend": self._opened_backend,
            "resolution": (width, height),
            "fps": fps,
            "configured": {
                "width": int(getattr(config, "VISION_CAPTURE_WIDTH", 0) or 0),
                "height": int(getattr(config, "VISION_CAPTURE_HEIGHT", 0) or 0),
                "fps": float(getattr(config, "VISION_CAPTURE_FPS", 0.0) or 0.0),
                "fourcc": str(getattr(config, "VISION_CAPTURE_FOURCC", "") or ""),
                "buffer_size": int(getattr(config, "VISION_CAPTURE_BUFFER_SIZE", 1) or 1),
                "grab_drain": int(getattr(config, "VISION_CAPTURE_GRAB_DRAIN", 0) or 0),
                "thread_fps_limit": float(getattr(config, "VISION_CAPTURE_THREAD_FPS_LIMIT", 0.0) or 0.0),
            },
            "frames_captured": int(self._frames_captured),
            "last_frame_at": self._last_frame_at,
            "last_frame_age_sec": None if self._last_frame_at is None else max(0.0, time.time() - self._last_frame_at),
            "read_failures": int(self._read_failures),
            "buffer": frame_buffer.raw_stats(),
        }
