import cv2
import time
from typing import Generator
from backend.infrastructure.vision.overlay.overlay_manager import OverlayManager
import base64

class MJPEGStreamer:
    """
    Generates an MJPEG stream from the OverlayManager for frontend consumption.
    """
    def __init__(self, overlay_manager: OverlayManager):
        self.overlay_manager = overlay_manager
        # 1x1 red JPEG fallback to keep stream alive when no frames are available.
        self._fallback_jpg = base64.b64decode(
            "/9j/4AAQSkZJRgABAQAAZABkAAD/2wCEABQQEBkSGScXFycyJh8mMi4mJiYmLj41NTU1NT5EQUFBQUFBREREREREREREREREREREREREREREREREREREQBFRkZIBwgJhgYJjYmICY2RDYrKzZERERCNUJERERERERERERERERERERERERERERERERERERERERERERERERERP/AABEIAAEAAQMBIgACEQEDEQH/xABMAAEBAAAAAAAAAAAAAAAAAAAABQEBAQAAAAAAAAAAAAAAAAAABQYQAQAAAAAAAAAAAAAAAAAAAAARAQAAAAAAAAAAAAAAAAAAAAD/2gAMAwEAAhEDEQA/AJQA9Yv/2Q=="
        )

    def generate(self) -> Generator[bytes, None, None]:
        """
        Yields JPEG frames as a multipart stream.
        """
        try:
            while True:
                frame = self.overlay_manager.get_debug_frame()

                if frame is not None:
                    # Encode as JPEG
                    ret, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    if not ret:
                        time.sleep(0.1)
                        continue

                    frame_bytes = jpeg.tobytes()
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                else:
                    # Keep the HTTP connection alive even when camera/detections are unavailable.
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + self._fallback_jpg + b'\r\n')
                    time.sleep(0.1)
                    continue

                time.sleep(0.005)
        except GeneratorExit:
            return
