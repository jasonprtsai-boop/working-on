import cv2
import threading
import time
from typing import Optional, Tuple
import numpy as np
from backend.utils.logger import logger
from backend.utils import config
from .frame_buffer import frame_buffer

class CameraManager:
    """
    Manages camera lifecycle, frame buffering, and multi-threaded capture.
    """
    def __init__(self, camera_index: int = None):
        self.camera_index = camera_index if camera_index is not None else config.CAMERA_INDEX
        self.cap: Optional[cv2.VideoCapture] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self._cap_lock = threading.Lock()
        self._read_failures = 0
        self._last_failure_log_at = 0.0

    def _open_capture(self) -> Optional[cv2.VideoCapture]:
        """Open a VideoCapture for the current camera_index (best-effort)."""
        try:
            cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        except Exception:
            cap = cv2.VideoCapture(self.camera_index)

        try:
            if not cap or not cap.isOpened():
                try:
                    if cap:
                        cap.release()
                except Exception:
                    pass
                return None
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            return None
        return cap

    def start(self) -> bool:
        if self.running:
            return True

        logger.info(f"Initializing camera {self.camera_index}...")
        cap = self._open_capture()
        if cap is None:
            logger.error(f"Failed to open camera {self.camera_index}")
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
        try:
            camera_index = int(camera_index)
        except Exception:
            return False

        was_running = self.running
        if was_running:
            self.stop()
        self.camera_index = camera_index
        if was_running:
            return self.start()
        return True

    def _update(self):
        failure_count = 0
        while self.running:
            with self._cap_lock:
                cap = self.cap
            if cap is None or not cap.isOpened():
                logger.warning(f"Camera {self.camera_index} lost. Attempting reconnect...")
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

            ret, frame = cap.read()
            if ret:
                frame_buffer.put_raw(frame)
                failure_count = 0
                self._read_failures = 0
            else:
                self._read_failures += 1
                now = time.monotonic()
                if self._read_failures <= 3 or now - self._last_failure_log_at >= 5.0:
                    logger.error(f"Failed to read frame from camera {self.camera_index} (consecutive={self._read_failures}).")
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
        return {
            "index": int(self.camera_index),
            "running": bool(self.running),
            "opened": opened,
            "resolution": self.get_resolution(),
            "fps": fps,
            "read_failures": int(self._read_failures),
        }
