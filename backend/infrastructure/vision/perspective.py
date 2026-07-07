import cv2
import numpy as np
from typing import List

from backend.infrastructure.vision.calibration import (
    apply_homography_point,
    apply_homography_points,
    compute_warp_matrix,
    normalize_corners,
)


class PerspectiveTransformer:
    """
    Vision perspective correction helper.

    It stores four board corners, computes the homography matrix, and rectifies
    incoming frames into a fixed board image plane.
    """

    def __init__(self, target_size: tuple = (600, 600)):
        self.target_size = self._normalize_target_size(target_size)
        self.src_pts = None
        self.matrix = None
        self.inverse_matrix = None

    @property
    def is_calibrated(self) -> bool:
        return self.matrix is not None

    def update_corners(self, corners: List[List[float]]):
        """Update board corners in TL, TR, BR, BL order."""
        try:
            self.src_pts = np.array(normalize_corners(corners), dtype=np.float32)
            self.matrix = compute_warp_matrix(self.src_pts, self.target_size)
            self.inverse_matrix = np.linalg.inv(self.matrix).astype(np.float32)
        except Exception:
            self.src_pts = None
            self.matrix = None
            self.inverse_matrix = None

    def transform(self, frame: np.ndarray) -> np.ndarray:
        """Warp a frame into the rectified board plane."""
        if frame is None:
            return frame
        if self.matrix is None:
            return frame

        return cv2.warpPerspective(frame, self.matrix, self.target_size)

    def map_point(self, x: float, y: float):
        """Map a raw-frame point to rectified board coordinates."""
        if self.matrix is None:
            return float(x), float(y)
        return apply_homography_point(self.matrix, x, y)

    def map_points(self, points):
        """Map multiple raw-frame points to rectified board coordinates."""
        if self.matrix is None:
            return [(float(x), float(y)) for x, y in points]
        return apply_homography_points(self.matrix, points)

    def map_bbox(self, bbox) -> List[float]:
        """Map a raw-frame bbox to the rectified board plane."""
        if self.matrix is None:
            return self._bbox_values(bbox)
        return self._map_bbox_with_matrix(self.matrix, bbox)

    def inverse_map_point(self, x: float, y: float):
        """Map a rectified board point back to raw-frame coordinates."""
        if self.inverse_matrix is None:
            return float(x), float(y)
        return apply_homography_point(self.inverse_matrix, x, y)

    def inverse_map_points(self, points):
        """Map multiple rectified board points back to raw-frame coordinates."""
        if self.inverse_matrix is None:
            return [(float(x), float(y)) for x, y in points]
        return apply_homography_points(self.inverse_matrix, points)

    def inverse_map_bbox(self, bbox) -> List[float]:
        """Map a rectified-board bbox back to raw-frame coordinates."""
        if self.inverse_matrix is None:
            return self._bbox_values(bbox)
        return self._map_bbox_with_matrix(self.inverse_matrix, bbox)

    def _map_bbox_with_matrix(self, matrix: np.ndarray, bbox) -> List[float]:
        x1, y1, x2, y2 = self._bbox_values(bbox)
        corners = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
        mapped = apply_homography_points(matrix, corners)
        xs = [point[0] for point in mapped]
        ys = [point[1] for point in mapped]
        return [float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))]

    def _bbox_values(self, bbox) -> List[float]:
        if hasattr(bbox, "x1"):
            values = [bbox.x1, bbox.y1, bbox.x2, bbox.y2]
        elif isinstance(bbox, dict):
            values = bbox.get("bbox") or bbox.get("bbox_xyxy") or [
                bbox.get("x1"),
                bbox.get("y1"),
                bbox.get("x2"),
                bbox.get("y2"),
            ]
        else:
            values = bbox

        if not isinstance(values, (list, tuple)) or len(values) != 4:
            raise ValueError("bbox must contain [x1, y1, x2, y2]")
        x1, y1, x2, y2 = [float(value) for value in values]
        return [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]

    def _normalize_target_size(self, target_size: tuple) -> tuple:
        try:
            width = int(target_size[0])
            height = int(target_size[1])
        except (TypeError, ValueError, IndexError):
            width, height = 600, 600
        return max(width, 2), max(height, 2)
