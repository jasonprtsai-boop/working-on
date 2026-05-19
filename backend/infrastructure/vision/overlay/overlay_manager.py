import cv2
import numpy as np
from typing import Optional
from backend.infrastructure.vision.debug.overlay_renderer import OverlayRenderer
from backend.infrastructure.vision.camera.frame_buffer import frame_buffer

class OverlayManager:
    """
    Combines frames with AI overlays, status text, and performance metrics.
    """
    def __init__(self, renderer: OverlayRenderer):
        self.renderer = renderer
        self.last_overlay_frame: Optional[np.ndarray] = None

    def get_debug_frame(self) -> Optional[np.ndarray]:
        """
        Retrieves the latest detection result and renders a composite debug frame.
        """
        result = frame_buffer.get_detection(timeout=0.001)
        if result is None:
            raw_frame = frame_buffer.get_raw(timeout=0.001)
            if raw_frame is not None:
                self.last_overlay_frame = self.renderer.draw_grid(raw_frame)
            return self.last_overlay_frame

        work_frame = result["work_frame"]
        detections = result["detections"]
        latency = result["latency_ms"]

        # 1. Draw Detections
        overlay_frame = self.renderer.draw_detections(work_frame, detections)

        # 2. Draw Grid
        overlay_frame = self.renderer.draw_grid(overlay_frame)

        # 3. Draw Performance Metrics
        cv2.putText(overlay_frame, f"AI Latency: {latency:.1f}ms", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

        self.last_overlay_frame = overlay_frame
        return overlay_frame
