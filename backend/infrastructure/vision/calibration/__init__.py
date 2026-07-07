import json
import logging
import math
import os
import time
import numpy as np
from typing import Iterable, Optional, Tuple, List

logger = logging.getLogger("VisionCalibration")

DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "..", "calibration.json")


def normalize_corners(board_corners: List[List[float]]) -> List[List[float]]:
    """Validate and normalize four board corners in TL, TR, BR, BL order."""
    corners = np.array(board_corners, dtype=np.float32)
    if corners.shape != (4, 2):
        raise ValueError("board_corners must contain four [x, y] points")
    if not np.isfinite(corners).all():
        raise ValueError("board_corners must contain finite numbers")
    area = cv2_contour_area(corners)
    if area <= 1.0:
        raise ValueError("board_corners area is too small")
    return corners.astype(float).tolist()


def destination_points(output_size: Tuple[int, int]) -> np.ndarray:
    """Return destination corners for a rectified board image."""
    width, height = output_size
    width = int(width)
    height = int(height)
    if width <= 1 or height <= 1:
        raise ValueError("output_size must be greater than 1x1")
    return np.array(
        [
            [0, 0],
            [width - 1, 0],
            [width - 1, height - 1],
            [0, height - 1],
        ],
        dtype=np.float32,
    )


def cv2_contour_area(points: np.ndarray) -> float:
    import cv2

    return float(cv2.contourArea(np.array(points, dtype=np.float32)))


def save_calibration(
    warp_matrix: np.ndarray,
    board_corners: List[List[float]],
    path: str = DEFAULT_PATH,
    output_size: Tuple[int, int] = (1000, 1000),
    metadata: Optional[dict] = None,
):
    """Persist calibration data to JSON."""
    matrix = np.array(warp_matrix, dtype=np.float64)
    if matrix.shape != (3, 3) or not np.isfinite(matrix).all():
        raise ValueError("warp_matrix must be a finite 3x3 matrix")
    normalized_corners = normalize_corners(board_corners)
    payload_metadata = dict(metadata or {})
    payload_metadata.setdefault(
        "quality",
        compute_calibration_quality(normalized_corners, matrix, output_size),
    )
    data = {
        "version": 1,
        "created_at": time.time(),
        "output_size": [int(output_size[0]), int(output_size[1])],
        "warp_matrix": matrix.tolist(),
        "board_corners": normalized_corners,
        "metadata": payload_metadata,
    }
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    logger.info(f"Calibration saved to {path}")


def load_calibration_payload(path: str = DEFAULT_PATH) -> Optional[dict]:
    """Load persisted calibration JSON with validation."""
    if not os.path.exists(path):
        logger.warning(f"Calibration file not found: {path}")
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    matrix = np.array(data.get("warp_matrix"), dtype=np.float64)
    if matrix.shape != (3, 3) or not np.isfinite(matrix).all():
        raise ValueError("Invalid calibration warp_matrix")

    corners = normalize_corners(data.get("board_corners", []))
    output_size = data.get("output_size") or [1000, 1000]
    if not isinstance(output_size, list) or len(output_size) != 2:
        output_size = [1000, 1000]

    data["warp_matrix"] = matrix
    data["board_corners"] = corners
    data["output_size"] = [int(output_size[0]), int(output_size[1])]
    logger.info(f"Calibration loaded from {path}")
    return data


def load_calibration(path: str = DEFAULT_PATH) -> Optional[Tuple[np.ndarray, List]]:
    """Load persisted calibration data. Returns (warp_matrix, board_corners) or None."""
    payload = load_calibration_payload(path)
    if payload is None:
        return None
    return np.array(payload["warp_matrix"], dtype=np.float32), payload["board_corners"]

def compute_warp_matrix(
    src_corners: List[Tuple[float, float]],
    output_size: Tuple[int, int] = (540, 600)
) -> np.ndarray:
    """
    Compute perspective transform matrix from 4 board corners (TL, TR, BR, BL).
    output_size: (width, height) of the rectified board image.
    """
    src = np.array(normalize_corners(src_corners), dtype=np.float32)
    dst = destination_points(output_size)

    import cv2
    M = cv2.getPerspectiveTransform(src, dst)
    if M.shape != (3, 3) or not np.isfinite(M).all():
        raise ValueError("computed warp_matrix is invalid")
    return M


def apply_homography_point(matrix: np.ndarray, x: float, y: float) -> Tuple[float, float]:
    """Apply a 3x3 homography matrix to one image point."""
    mapped = apply_homography_points(matrix, [(x, y)])
    return mapped[0]


def apply_homography_points(matrix: np.ndarray, points: Iterable[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Apply a 3x3 homography matrix to many image points in one vectorized pass."""
    mat = np.array(matrix, dtype=np.float64)
    if mat.shape != (3, 3):
        raise ValueError("matrix must be 3x3")
    pts = np.array(list(points), dtype=np.float64)
    if pts.size == 0:
        return []
    if pts.ndim != 2 or pts.shape[1] != 2 or not np.isfinite(pts).all():
        raise ValueError("points must be finite [x, y] pairs")

    ones = np.ones((pts.shape[0], 1), dtype=np.float64)
    homogeneous = np.hstack((pts, ones))
    mapped = homogeneous @ mat.T
    denom = mapped[:, 2]
    if np.any(np.abs(denom) < 1e-9):
        raise ValueError("homography mapped point to infinity")
    mapped = mapped[:, :2] / denom[:, None]
    return [(float(x), float(y)) for x, y in mapped]


def compute_calibration_quality(
    src_corners: List[Tuple[float, float]],
    matrix: Optional[np.ndarray] = None,
    output_size: Tuple[int, int] = (1000, 1000),
) -> dict:
    """Return geometry and reprojection quality metrics for board calibration."""
    corners = np.array(normalize_corners(src_corners), dtype=np.float64)
    target = destination_points(output_size).astype(np.float64)
    warp = np.array(matrix if matrix is not None else compute_warp_matrix(corners, output_size), dtype=np.float64)
    if warp.shape != (3, 3) or not np.isfinite(warp).all():
        raise ValueError("warp_matrix must be a finite 3x3 matrix")

    mapped = np.array(apply_homography_points(warp, corners), dtype=np.float64)
    errors = np.linalg.norm(mapped - target, axis=1)
    edge_lengths = np.linalg.norm(np.roll(corners, -1, axis=0) - corners, axis=1)
    min_edge = float(np.min(edge_lengths))
    max_edge = float(np.max(edge_lengths))
    angles = _corner_angles_degrees(corners)

    try:
        condition_number = float(np.linalg.cond(warp))
    except Exception:
        condition_number = float("inf")

    area_px = cv2_contour_area(corners.astype(np.float32))
    width, height = int(output_size[0]), int(output_size[1])
    return {
        "area_px": round(float(area_px), 3),
        "area_ratio": round(float(area_px) / max(float(width * height), 1.0), 6),
        "mean_reprojection_error_px": round(float(np.mean(errors)), 6),
        "max_reprojection_error_px": round(float(np.max(errors)), 6),
        "min_edge_px": round(min_edge, 3),
        "max_edge_px": round(max_edge, 3),
        "edge_ratio": round(max_edge / max(min_edge, 1e-9), 6),
        "min_angle_deg": round(float(np.min(angles)), 3),
        "max_angle_deg": round(float(np.max(angles)), 3),
        "condition_number": round(condition_number, 6) if math.isfinite(condition_number) else condition_number,
    }


def _corner_angles_degrees(corners: np.ndarray) -> np.ndarray:
    angles = []
    for idx in range(4):
        prev_pt = corners[(idx - 1) % 4]
        curr_pt = corners[idx]
        next_pt = corners[(idx + 1) % 4]
        a = prev_pt - curr_pt
        b = next_pt - curr_pt
        denom = max(float(np.linalg.norm(a) * np.linalg.norm(b)), 1e-9)
        cosine = float(np.dot(a, b) / denom)
        cosine = max(-1.0, min(1.0, cosine))
        angles.append(math.degrees(math.acos(cosine)))
    return np.array(angles, dtype=np.float64)
