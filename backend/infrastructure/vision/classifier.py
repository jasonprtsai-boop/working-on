import cv2
import numpy as np
import os
from typing import Dict, Optional, List
from backend.utils.logger import logger
from backend.infrastructure.vision.piece_predictor import PiecePredictor

# --- Default HSV Thresholds ---
HSV_RED_LO1 = np.array([0,   60,  60])
HSV_RED_HI1 = np.array([10, 255, 255])
HSV_RED_LO2 = np.array([160, 60,  60])
HSV_RED_HI2 = np.array([180, 255, 255])
HSV_BLACK_LO = np.array([0,   0,   0])
HSV_BLACK_HI = np.array([180, 70, 90])

class Classifier:
    """
    [Vision Layer] Rule-based + AI Classifier.
    Responsibility: Color detection, Template matching, and AI orchestration.
    """
    def __init__(self, templates=None):
        self._templates = templates or {}
        self._empty_hsv_baseline = None
        self._predictor = PiecePredictor()

    @property
    def is_ai_loaded(self) -> bool:
        return self._predictor.is_ready

    def classify_color(self, cell: np.ndarray) -> str:
        hsv = cv2.cvtColor(cell, cv2.COLOR_BGR2HSV)
        # Red pieces detection
        red_mask = cv2.inRange(hsv, HSV_RED_LO1, HSV_RED_HI1) | cv2.inRange(hsv, HSV_RED_LO2, HSV_RED_HI2)
        if cv2.countNonZero(red_mask) / (cell.size / 3) > 0.03: # size includes 3 channels
            return "red"

        # Black pieces detection
        avg_hsv = cv2.mean(hsv)[:3]
        if self._empty_hsv_baseline is not None:
            dist = np.linalg.norm(np.array(avg_hsv) - self._empty_hsv_baseline)
            if dist > 45 or avg_hsv[2] < (self._empty_hsv_baseline[2] * 0.7):
                return "black"
        else:
            black_mask = cv2.inRange(hsv, HSV_BLACK_LO, HSV_BLACK_HI)
            if cv2.countNonZero(black_mask) / (cell.size / 3) > 0.05:
                return "black"
        return "empty"

    def match_piece(self, cell: np.ndarray, color: str) -> str:
        """Identify piece using AI or Template Matching."""
        if self._predictor.is_ready:
            return self._predictor.predict(cell, color)

        # Template matching path for classifier-only tests/tools.
        gray = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY)
        best_score, best_code = -1.0, "P" if color == "red" else "p"
        prefix = "RNBAKCP" if color == "red" else "rnbakcp"

        for code in prefix:
            tmpl = self._templates.get(code)
            if tmpl is None: continue
            resized_tmpl = cv2.resize(tmpl, (gray.shape[1], gray.shape[0]))
            result = cv2.matchTemplate(gray, resized_tmpl, cv2.TM_CCOEFF_NORMED)
            _, score, _, _ = cv2.minMaxLoc(result)
            if score > best_score:
                best_score, best_code = score, code
        return best_code if best_score > 0.25 else ("P" if color == "red" else "p")

    def phash(self, cell: np.ndarray) -> str:
        small = cv2.resize(cell, (8, 8), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        avg = gray.mean()
        return "".join(["1" if b > avg else "0" for b in gray.flatten()])

    def set_hsv_baseline(self, hsv):
        self._empty_hsv_baseline = hsv
