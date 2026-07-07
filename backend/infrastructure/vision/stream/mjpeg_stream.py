import time
from typing import Generator

import cv2

from backend.infrastructure.vision.overlay.overlay_manager import OverlayManager
from backend.utils import config


class MJPEGStreamer:
    """
    Generates an MJPEG stream from real OpenCV frames.
    """

    def __init__(self, overlay_manager: OverlayManager):
        self.overlay_manager = overlay_manager
        self.jpeg_quality = max(30, min(95, int(getattr(config, "VISION_MJPEG_QUALITY", 75))))
        self.max_fps = max(1, min(30, int(getattr(config, "VISION_MJPEG_FPS", 15))))
        self.frame_interval = 1.0 / float(self.max_fps)

    def generate(self) -> Generator[bytes, None, None]:
        """
        Yield JPEG frames as a multipart stream. No placeholder frames are emitted.
        """
        last_emit_at = 0.0
        try:
            while True:
                elapsed = time.monotonic() - last_emit_at
                if elapsed < self.frame_interval:
                    time.sleep(self.frame_interval - elapsed)

                frame = self.overlay_manager.get_debug_frame()
                if frame is None:
                    time.sleep(0.1)
                    continue

                ret, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
                if not ret:
                    time.sleep(0.1)
                    continue

                jpeg_bytes = jpeg.tobytes()
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Cache-Control: no-store\r\n"
                    b"Content-Length: " + str(len(jpeg_bytes)).encode("ascii") + b"\r\n\r\n"
                    + jpeg_bytes + b"\r\n"
                )
                last_emit_at = time.monotonic()
        except GeneratorExit:
            return
