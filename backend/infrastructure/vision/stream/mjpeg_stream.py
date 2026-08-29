import time
from typing import Generator
import cv2
import numpy as np

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
                    # Create a blank black frame (1000x1000) so the stream doesn't drop
                    frame = np.zeros((1000, 1000, 3), dtype=np.uint8)
                    cv2.putText(frame, "No camera signal", (300, 500), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

                try:
                    ret, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
                except Exception as e:
                    import logging
                    logging.getLogger("mjpeg").error(f"imencode error: {e}")
                    time.sleep(0.1)
                    continue

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
        except Exception as e:
            import logging
            logging.getLogger("mjpeg").error(f"Stream aborted due to error: {e}")
