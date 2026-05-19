"""
Vision Calibration Module
Stores and loads the perspective warp matrix and board origin.
Data is persisted to calibration.json.
"""
import json
import logging
import os
import numpy as np
from typing import Optional, Tuple, List

logger = logging.getLogger("VisionCalibration")

DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "..", "calibration.json")

def save_calibration(
    warp_matrix: np.ndarray,
    board_corners: List[List[float]],
    path: str = DEFAULT_PATH
):
    """Persist calibration data to JSON."""
    data = {
        "warp_matrix": warp_matrix.tolist(),
        "board_corners": board_corners,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    logger.info(f"Calibration saved to {path}")

def load_calibration(path: str = DEFAULT_PATH) -> Optional[Tuple[np.ndarray, List]]:
    """Load persisted calibration data. Returns (warp_matrix, board_corners) or None."""
    if not os.path.exists(path):
        logger.warning(f"Calibration file not found: {path}")
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    warp_matrix = np.array(data["warp_matrix"], dtype=np.float32)
    corners = data.get("board_corners", [])
    logger.info(f"Calibration loaded from {path}")
    return warp_matrix, corners

def compute_warp_matrix(
    src_corners: List[Tuple[float, float]],
    output_size: Tuple[int, int] = (540, 600)
) -> np.ndarray:
    """
    Compute perspective transform matrix from 4 board corners (TL, TR, BR, BL).
    output_size: (width, height) of the rectified board image.
    """
    w, h = output_size
    dst = np.array([
        [0, 0],
        [w - 1, 0],
        [w - 1, h - 1],
        [0, h - 1],
    ], dtype=np.float32)

    src = np.array(src_corners, dtype=np.float32)

    import cv2
    M = cv2.getPerspectiveTransform(src, dst)
    return M
