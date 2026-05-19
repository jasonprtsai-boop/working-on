import queue
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

    def put_raw(self, frame: np.ndarray):
        try:
            self.raw_frame_queue.put_nowait(frame)
        except queue.Full:
            # Drop old frames to keep it real-time
            try:
                self.raw_frame_queue.get_nowait()
                self.raw_frame_queue.put_nowait(frame)
            except queue.Empty:
                return

    def get_raw(self, timeout: float = 1.0) -> Optional[np.ndarray]:
        try:
            return self.raw_frame_queue.get(timeout=timeout)
        except queue.Empty:
            return None

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
