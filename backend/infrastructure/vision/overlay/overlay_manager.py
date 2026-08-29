import cv2
import numpy as np
from typing import Optional
from backend.infrastructure.vision.debug.overlay_renderer import OverlayRenderer
from backend.infrastructure.vision.camera.frame_buffer import frame_buffer

class OverlayManager:
    """
    Combines frames with AI overlays, status text, and performance metrics.
    """
    def __init__(self, renderer: OverlayRenderer, corrector=None):
        self.renderer = renderer
        self.corrector = corrector
        self.last_overlay_frame: Optional[np.ndarray] = None
        self.last_detections = None
        self.last_latency = 0.0

    def get_debug_frame(self) -> Optional[np.ndarray]:
        """
        Retrieves the latest detection result and renders a composite debug frame.
        """
        result = frame_buffer.get_detection(timeout=0.001)
        if result is not None:
            self.last_detections = result.get("detections", [])
            self.last_latency = result.get("latency_ms", 0.0)

        # Get the latest raw frame to overlay on
        raw_frame = frame_buffer.get_latest_raw(timeout=0.001)
        if raw_frame is None:
            return self.last_overlay_frame

        # If we have no AI results yet or no corrector, just show the raw frame with warmup text
        if self.last_detections is None or getattr(self.corrector, "inverse_matrix", None) is None:
            warmup_frame = raw_frame.copy()
            if self.last_detections is None:
                cv2.putText(warmup_frame, "Initializing AI Vision...", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            self.last_overlay_frame = warmup_frame
            return warmup_frame

        # Create a blank overlay in the warped perspective space
        warp_size = tuple(self.corrector.output_size) if hasattr(self.corrector, "output_size") else (1000, 1000)
        overlay = np.zeros((warp_size[1], warp_size[0], 3), dtype=np.uint8)

        # Draw detections and grid onto the blank overlay
        overlay = self.renderer.draw_detections(overlay, self.last_detections)
        overlay = self.renderer.draw_grid(overlay)

        # Warp the overlay back to the raw frame's perspective
        raw_h, raw_w = raw_frame.shape[:2]
        warped_overlay = cv2.warpPerspective(overlay, self.corrector.inverse_matrix, (raw_w, raw_h))

        # Composite the overlay onto the raw frame (non-black pixels)
        mask = cv2.cvtColor(warped_overlay, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(mask, 1, 255, cv2.THRESH_BINARY)
        raw_frame_bg = cv2.bitwise_and(raw_frame, raw_frame, mask=cv2.bitwise_not(mask))
        final_frame = cv2.add(raw_frame_bg, warped_overlay)

        # Draw Performance Metrics on the final composite frame
        cv2.putText(final_frame, f"AI Latency: {self.last_latency:.1f}ms", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

        self.last_overlay_frame = final_frame
        return final_frame
