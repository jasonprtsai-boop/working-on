import cv2
import numpy as np
from typing import List, Optional, Tuple

from backend.utils import config
from backend.infrastructure.vision.calibration import (
    apply_homography_point,
    apply_homography_points,
    compute_warp_matrix,
    normalize_corners,
)

class ImagePreprocessor:
    """
    Handles image enhancement, noise reduction, and normalization.
    """
    def __init__(self):
        self.mode = str(getattr(config, "VISION_PREPROCESS_MODE", "fast") or "fast").strip().lower()
        self.clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        self.sharpen_kernel = np.array(
            [[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]],
            dtype=np.float32,
        )

    def process(self, frame: np.ndarray) -> np.ndarray:
        """
        Executes the preprocessing pipeline.

        Modes:
        - fast/light: CLAHE + sharpening, no expensive denoising.
        - balanced: small Gaussian blur + CLAHE + sharpening.
        - full/quality: original NLM denoising + CLAHE + sharpening.
        - off/raw/none: return frame unchanged.
        """
        if frame is None:
            return None

        mode = self.mode
        if mode in {"off", "raw", "none"}:
            return frame

        work_frame = frame
        if mode in {"full", "quality"}:
            work_frame = cv2.fastNlMeansDenoisingColored(frame, None, 10, 10, 7, 21)
        elif mode == "balanced":
            work_frame = cv2.GaussianBlur(frame, (3, 3), 0)

        normalized = self.enhance_color(work_frame)
        return cv2.filter2D(normalized, -1, self.sharpen_kernel)

    def enhance_color(self, frame: np.ndarray) -> np.ndarray:
        """Compatibility-friendly color enhancement used by VisionPipeline."""
        if frame is None:
            return None

        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)
        enhanced_l = self.clahe.apply(l_channel)
        enhanced_lab = cv2.merge((enhanced_l, a_channel, b_channel))
        return cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)

class PerspectiveCorrector:
    """
    Handles board localization and perspective warping.
    """
    def __init__(self, output_size: Tuple[int, int] = (1000, 1000)):
        self.output_size = output_size
        self.corners = None
        self.matrix = None
        self.inverse_matrix = None

    @property
    def is_calibrated(self) -> bool:
        return self.matrix is not None

    def set_corners(self, corners: np.ndarray, output_size: Optional[Tuple[int, int]] = None) -> np.ndarray:
        """Set board corners and precompute the homography matrix."""
        target_size = output_size or self.output_size
        normalized = np.array(normalize_corners(corners), dtype=np.float32)
        matrix = compute_warp_matrix(normalized, target_size)
        self.output_size = target_size
        self.corners = normalized
        self.matrix = matrix.astype(np.float32)
        self.inverse_matrix = np.linalg.inv(self.matrix).astype(np.float32)
        return self.matrix

    def set_matrix(
        self,
        matrix: np.ndarray,
        corners: Optional[np.ndarray] = None,
        output_size: Optional[Tuple[int, int]] = None,
    ) -> np.ndarray:
        """Load a persisted homography matrix."""
        mat = np.array(matrix, dtype=np.float32)
        if mat.shape != (3, 3) or not np.isfinite(mat).all():
            raise ValueError("matrix must be a finite 3x3 homography")
        self.output_size = output_size or self.output_size
        self.matrix = mat
        self.inverse_matrix = np.linalg.inv(mat).astype(np.float32)
        self.corners = np.array(normalize_corners(corners), dtype=np.float32) if corners is not None else None
        return self.matrix

    def warp(
        self,
        frame: np.ndarray,
        corners: Optional[np.ndarray] = None,
        output_size: Tuple[int, int] = (1000, 1000),
    ) -> np.ndarray:
        """
        Warps the frame based on four corners to normalize the board coordinate system.
        corners: np.ndarray of shape (4, 2) - [top-left, top-right, bottom-right, bottom-left]
        """
        if frame is None:
            return frame

        if corners is not None:
            matrix = self.set_corners(corners, output_size=output_size)
            target_size = output_size
        elif self.matrix is not None:
            matrix = self.matrix
            target_size = self.output_size
        else:
            return frame

        width, height = int(target_size[0]), int(target_size[1])
        warped = cv2.warpPerspective(frame, matrix, (width, height))

        return warped

    def map_point(self, x: float, y: float) -> Tuple[float, float]:
        """Map a raw-frame pixel to the rectified board image."""
        if self.matrix is None:
            return float(x), float(y)
        return apply_homography_point(self.matrix, x, y)

    def map_points(self, points):
        """Map many raw-frame pixels to the rectified board image."""
        if self.matrix is None:
            return [(float(x), float(y)) for x, y in points]
        return apply_homography_points(self.matrix, points)

    def map_bbox(self, bbox) -> List[float]:
        """Map a raw-frame bbox to a rectified-board bbox."""
        if self.matrix is None:
            return self._bbox_values(bbox)
        return self._map_bbox_with_matrix(self.matrix, bbox)

    def inverse_map_point(self, x: float, y: float) -> Tuple[float, float]:
        """Map a rectified-board pixel back to the raw camera frame."""
        if self.inverse_matrix is None:
            return float(x), float(y)
        return apply_homography_point(self.inverse_matrix, x, y)

    def inverse_map_points(self, points):
        """Map many rectified-board pixels back to the raw camera frame."""
        if self.inverse_matrix is None:
            return [(float(x), float(y)) for x, y in points]
        return apply_homography_points(self.inverse_matrix, points)

    def inverse_map_bbox(self, bbox) -> List[float]:
        """Map a rectified-board bbox back to the raw camera frame."""
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


Preprocessor = ImagePreprocessor
