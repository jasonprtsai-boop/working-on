import cv2
import numpy as np
from typing import List
from backend.infrastructure.vision.detection.detection_result import Detection
from backend.infrastructure.vision.board.coordinate_system import BoardCoordinateSystem

class OverlayRenderer:
    """
    Renders debug information onto frames for visualization and recording.
    """
    def __init__(self, coord_system: BoardCoordinateSystem = None):
        self.coord_system = coord_system

    def draw_detections(self, frame: np.ndarray, detections: List[Detection]) -> np.ndarray:
        output = frame.copy()
        for det in detections:
            if isinstance(det, dict):
                bbox = det.get("bbox") or [0, 0, 0, 0]
                if isinstance(bbox, dict):
                    x1, y1, x2, y2 = bbox.get("x1", 0), bbox.get("y1", 0), bbox.get("x2", 0), bbox.get("y2", 0)
                else:
                    x1, y1, x2, y2 = (list(bbox) + [0, 0, 0, 0])[:4]
                class_name = det.get("class_name", "")
                confidence = float(det.get("confidence", 0.0) or 0.0)
            else:
                bbox = det.bbox
                x1, y1, x2, y2 = bbox.x1, bbox.y1, bbox.x2, bbox.y2
                class_name = det.class_name
                confidence = det.confidence
            x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)

            # Draw box
            cv2.rectangle(output, (x1, y1), (x2, y2), (0, 255, 0), 2)

            # Draw label
            label = f"{class_name} {confidence:.2f}"
            cv2.putText(output, label, (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        return output

    def draw_grid(self, frame: np.ndarray) -> np.ndarray:
        if self.coord_system is None:
            return frame

        output = frame.copy()
        config = self.coord_system.config

        # Draw vertical lines
        for c in range(config.cols):
            x = int(c * self.coord_system.cell_w)
            cv2.line(output, (x, 0), (x, config.height), (255, 0, 0), 1)

        # Draw horizontal lines
        for r in range(config.rows):
            y = int(r * self.coord_system.cell_h)
            cv2.line(output, (0, y), (config.width, y), (255, 0, 0), 1)

        return output

    def draw_status(self, frame: np.ndarray, status: str) -> np.ndarray:
        output = frame.copy()
        cv2.putText(output, f"Status: {status}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        return output
