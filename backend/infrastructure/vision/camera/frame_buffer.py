import queue
import threading
import time
import numpy as np
from typing import Optional

class FrameBuffer:
    """
    Thread-safe queues for decoupling Camera, Inference, and Streaming.
    """
    def __init__(self, maxsize: int = 3):
        self.raw_frame_queue = queue.Queue(maxsize=maxsize)
        self.processed_frame_queue = queue.Queue(maxsize=maxsize)
        self.detection_queue = queue.Queue(maxsize=maxsize)
        self.stream_queue = queue.Queue(maxsize=maxsize)
        self._raw_lock = threading.Lock()
        self._latest_raw_frame = None
        self.raw_put_count = 0
        self.raw_get_count = 0
        self.raw_drop_count = 0
        self.raw_last_put_at = None
        self.raw_last_get_at = None

    def put_raw(self, frame: np.ndarray):
        self._remember_latest_raw(frame)
        try:
            self.raw_frame_queue.put_nowait(frame)
            self.raw_put_count += 1
        except queue.Full:
            # Drop old frames to keep it real-time
            try:
                self.raw_frame_queue.get_nowait()
                self.raw_drop_count += 1
                self.raw_frame_queue.put_nowait(frame)
                self.raw_put_count += 1
            except queue.Empty:
                return

    def _remember_latest_raw(self, frame: np.ndarray):
        with self._raw_lock:
            self._latest_raw_frame = frame
            self.raw_last_put_at = time.time()

    def get_raw(self, timeout: float = 1.0) -> Optional[np.ndarray]:
        try:
            frame = self.raw_frame_queue.get(timeout=timeout)
            self.raw_get_count += 1
            self.raw_last_get_at = time.time()
            return frame
        except queue.Empty:
            return None

    def get_latest_raw(self, timeout: float = 1.0) -> Optional[np.ndarray]:
        """Return the newest raw frame and discard older queued frames."""
        frame = self.get_raw(timeout=timeout)
        if frame is None:
            return None

        while True:
            try:
                frame = self.raw_frame_queue.get_nowait()
                self.raw_drop_count += 1
            except queue.Empty:
                break

        self.raw_last_get_at = time.time()
        return frame

    def peek_latest_raw(self, max_age_sec: Optional[float] = None) -> Optional[np.ndarray]:
        """Return the newest raw frame without consuming it from the capture queue."""
        with self._raw_lock:
            frame = self._latest_raw_frame
            last_put_at = self.raw_last_put_at
        if frame is None:
            return None
        if max_age_sec is not None and last_put_at is not None:
            if time.time() - last_put_at > max(0.0, float(max_age_sec)):
                return None
        return frame

    def raw_stats(self) -> dict:
        now = time.time()
        last_put_at = self.raw_last_put_at
        last_get_at = self.raw_last_get_at
        return {
            "size": self.raw_frame_queue.qsize(),
            "maxsize": self.raw_frame_queue.maxsize,
            "put_count": int(self.raw_put_count),
            "get_count": int(self.raw_get_count),
            "dropped_oldest": int(self.raw_drop_count),
            "last_put_at": last_put_at,
            "last_get_at": last_get_at,
            "latest_frame_available": self.peek_latest_raw() is not None,
            "age_sec": None if last_put_at is None else max(0.0, now - last_put_at),
            "consumer_idle_sec": None if last_get_at is None else max(0.0, now - last_get_at),
        }

    def put_detection(self, detections):
        try:
            self.detection_queue.put_nowait(detections)
        except queue.Full:
            try:
                self.detection_queue.get_nowait()
                self.detection_queue.put_nowait(detections)
            except queue.Empty:
                return

    def get_detection(self, timeout: float = 1.0):
        try:
            return self.detection_queue.get(timeout=timeout)
        except queue.Empty:
            return None

# Global instance for shared access across modules
frame_buffer = FrameBuffer()
