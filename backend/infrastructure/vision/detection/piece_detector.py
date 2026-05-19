from backend.infrastructure.vision.classifier import Classifier
import numpy as np

class PieceDetector:
    """Uses YOLO or specialized models to classify pieces on the board."""
    def __init__(self, model_path=None):
        self.classifier = Classifier()

    def detect_pieces(self, frame):
        """
        Returns a list of detected pieces with their grid coordinates.
        Uses a grid-based classification fallback if YOLO is not available.
        """
        detected = []
        h, w = frame.shape[:2]
        cell_h, cell_w = h / 10.0, w / 9.0

        for r in range(10):
            for c in range(9):
                y1, y2 = int(r * cell_h), int((r + 1) * cell_h)
                x1, x2 = int(c * cell_w), int((c + 1) * cell_w)
                cell = frame[y1:y2, x1:x2]

                if cell.size == 0: continue

                color = self.classifier.classify_color(cell)
                if color != "empty":
                    # We found something!
                    piece_type = self.classifier.match_piece(cell, color)
                    detected.append({
                        "row": r,
                        "col": c,
                        "color": color,
                        "type": piece_type,
                        "prob": 0.85 # Heuristic confidence for color match
                    })
        return detected
