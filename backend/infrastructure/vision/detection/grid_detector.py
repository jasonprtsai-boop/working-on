from __future__ import annotations

from typing import List

import numpy as np

from backend.utils import config
from backend.infrastructure.vision.classifier import Classifier
from backend.infrastructure.vision.detection.detector import BaseDetector
from backend.infrastructure.vision.detection.detection_result import BoundingBox, Detection


class GridDetector(BaseDetector):
    """
    Fast grid-based detector.

    Splits the warped board frame into BOARD_ROWS x BOARD_COLS cells and uses the
    TensorFlow SavedModel classifier (if available) to classify pieces per cell.
    Produces Detection objects with cell-aligned bounding boxes so downstream
    mappers/overlays can remain unchanged.
    """

    def __init__(self, rows: int = None, cols: int = None):
        self.rows = int(rows if rows is not None else config.BOARD_ROWS)
        self.cols = int(cols if cols is not None else config.BOARD_COLS)
        self.classifier = Classifier()
        self.model_path = None
        self.last_error = None

    def load_model(self, model_path: str):
        """GridDetector uses the shared Classifier; kept for BaseDetector compatibility."""
        self.model_path = model_path
        return None

    def detect(self, frame: np.ndarray) -> List[Detection]:
        detections: List[Detection] = []
        if frame is None:
            return detections

        h, w = frame.shape[:2]
        if h <= 0 or w <= 0:
            return detections

        cell_h = h / float(self.rows)
        cell_w = w / float(self.cols)

        for r in range(self.rows):
            y1 = int(r * cell_h)
            y2 = int((r + 1) * cell_h)
            for c in range(self.cols):
                x1 = int(c * cell_w)
                x2 = int((c + 1) * cell_w)

                cell = frame[y1:y2, x1:x2]
                if cell.size == 0:
                    continue

                color = self.classifier.classify_color(cell)
                if color == "empty":
                    continue

                piece_code = self.classifier.match_piece(cell, color)

                detections.append(
                    Detection(
                        class_id=0,
                        class_name=str(piece_code),
                        confidence=0.85,
                        bbox=BoundingBox(x1=float(x1), y1=float(y1), x2=float(x2), y2=float(y2)),
                    )
                )

        return detections

    def get_status(self) -> dict:
        return {
            "loaded": True,
            "model_path": self.model_path,
            "rows": self.rows,
            "cols": self.cols,
            "classifier": self.classifier.__class__.__name__,
            "last_error": self.last_error,
        }
