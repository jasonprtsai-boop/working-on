import cv2
import numpy as np
from typing import Optional

from backend.infrastructure.vision.calibration import compute_calibration_quality
from backend.utils.logger import logger

class BoardCalibrator:
    """
    [Vision Utility] Board Calibrator
    Handles manual and automatic board corner detection for perspective correction.
    """
    def __init__(self, max_detection_dim: int = 960):
        self.corners = None
        try:
            max_dim = int(max_detection_dim)
        except (TypeError, ValueError):
            max_dim = 960
        self.max_detection_dim = max_dim if max_dim > 0 else 960
        self.last_method = None
        self.last_quality = None

    @staticmethod
    def order_corners(points) -> np.ndarray:
        """Return four points ordered as top-left, top-right, bottom-right, bottom-left."""
        pts = np.array(points, dtype=np.float32).reshape(-1, 2)
        if pts.shape[0] != 4:
            raise ValueError("Exactly four points are required")

        sums = pts.sum(axis=1)
        diffs = np.diff(pts, axis=1).reshape(-1)
        ordered = np.array(
            [
                pts[np.argmin(sums)],
                pts[np.argmin(diffs)],
                pts[np.argmax(sums)],
                pts[np.argmax(diffs)],
            ],
            dtype=np.float32,
        )
        return ordered

    @staticmethod
    def validate_corners(points, min_area: float = 1000.0) -> bool:
        try:
            ordered = BoardCalibrator.order_corners(points)
        except Exception:
            return False
        if not np.isfinite(ordered).all():
            return False
        area = float(cv2.contourArea(ordered))
        return area >= float(min_area)

    def detect_auto(self, frame: np.ndarray):
        """
        Attempts to automatically detect board corners.

        Uses ArUco markers with IDs 0, 1, 2, 3 when available; otherwise it
        uses OpenCV contour quadrilateral detection for calibration.
        """
        if frame is None or getattr(frame, "size", 0) == 0:
            return None

        work_frame, scale = self._resize_for_detection(frame)
        method = None
        corners = self._detect_aruco(work_frame)
        if corners is not None:
            method = "aruco"
        if corners is None:
            corners = self._detect_contour(work_frame)
            if corners is not None:
                method = "contour"

        if corners is None:
            logger.warning("Could not detect board corners automatically.")
            return None

        if scale != 1.0:
            corners = corners.astype(np.float32) / np.float32(scale)
        corners = self._refine_corners(frame, corners)

        self.corners = corners.astype(np.float32)
        self.last_method = method
        self.last_quality = self._quality(self.corners)
        logger.info("Automatic board detection successful (method=%s, quality=%s).", method, self.last_quality)
        return self.corners

    def _detect_aruco(self, frame: np.ndarray) -> Optional[np.ndarray]:
        try:
            if not hasattr(cv2, "aruco"):
                return None

            dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
            parameters = cv2.aruco.DetectorParameters()
            if hasattr(cv2.aruco, "ArucoDetector"):
                detector = cv2.aruco.ArucoDetector(dictionary, parameters)
                marker_corners, ids, _rejected = detector.detectMarkers(frame)
            else:
                marker_corners, ids, _rejected = cv2.aruco.detectMarkers(
                    frame,
                    dictionary,
                    parameters=parameters,
                )

            if ids is None or len(ids) < 4:
                return None

            centers = {}
            for marker_id, marker in zip(ids.flatten(), marker_corners):
                centers[int(marker_id)] = np.array(marker, dtype=np.float32).reshape(4, 2).mean(axis=0)

            if all(marker_id in centers for marker_id in range(4)):
                points = np.array([centers[0], centers[1], centers[2], centers[3]], dtype=np.float32)
            else:
                points = np.array(list(centers.values())[:4], dtype=np.float32)

            ordered = self.order_corners(points)
            if self.validate_corners(ordered, min_area=100.0):
                return ordered
            return None
        except Exception as e:
            logger.error(f"ArUco detection failed: {e}")
            return None

    def _detect_contour(self, frame: np.ndarray) -> Optional[np.ndarray]:
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            kernel = np.ones((3, 3), dtype=np.uint8)
            edges = cv2.Canny(blurred, 50, 150)
            edges = cv2.dilate(edges, kernel, iterations=1)
            thresh = cv2.adaptiveThreshold(
                blurred,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                31,
                2,
            )

            contours = []
            for mask in (edges, thresh):
                found, _hierarchy = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                contours.extend(found)

            frame_area = float(frame.shape[0] * frame.shape[1])
            min_area = max(1000.0, frame_area * 0.05)
            best = None
            best_score = -1.0

            for contour in contours:
                area = float(cv2.contourArea(contour))
                if area < min_area:
                    continue
                perimeter = cv2.arcLength(contour, True)
                approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
                if len(approx) != 4:
                    continue
                ordered = self.order_corners(approx.reshape(4, 2))
                if not cv2.isContourConvex(ordered.astype(np.float32)):
                    continue
                if not self.validate_corners(ordered, min_area=min_area):
                    continue
                score = self._quad_score(ordered, area=area, frame_area=frame_area)
                if score <= best_score:
                    continue
                best = ordered
                best_score = score

            return best
        except Exception as e:
            logger.error(f"Contour board detection failed: {e}")
            return None

    def _resize_for_detection(self, frame: np.ndarray):
        height, width = frame.shape[:2]
        max_dim = max(width, height)
        if max_dim <= self.max_detection_dim:
            return frame, 1.0
        scale = float(self.max_detection_dim) / float(max_dim)
        resized = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        return resized, scale

    def _refine_corners(self, frame: np.ndarray, corners: np.ndarray) -> np.ndarray:
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
            points = np.array(corners, dtype=np.float32).reshape(-1, 1, 2)
            h, w = gray.shape[:2]
            points[:, 0, 0] = np.clip(points[:, 0, 0], 1, max(w - 2, 1))
            points[:, 0, 1] = np.clip(points[:, 0, 1], 1, max(h - 2, 1))
            criteria = (
                cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
                30,
                0.01,
            )
            refined = cv2.cornerSubPix(gray, points, (5, 5), (-1, -1), criteria)
            ordered = self.order_corners(refined.reshape(4, 2))
            if self.validate_corners(ordered, min_area=100.0):
                return ordered.astype(np.float32)
        except Exception:
            logger.debug("Corner sub-pixel refinement skipped.", exc_info=True)
        return self.order_corners(corners).astype(np.float32)

    def _quad_score(self, ordered: np.ndarray, *, area: float, frame_area: float) -> float:
        rect = cv2.minAreaRect(ordered.astype(np.float32))
        rect_w, rect_h = rect[1]
        rect_area = max(float(rect_w) * float(rect_h), 1.0)
        rectangularity = min(float(area) / rect_area, 1.0)
        area_score = min(float(area) / max(frame_area, 1.0), 1.0)
        edge_lengths = np.linalg.norm(np.roll(ordered, -1, axis=0) - ordered, axis=1)
        edge_ratio = float(np.max(edge_lengths) / max(np.min(edge_lengths), 1e-9))
        balance_score = 1.0 / max(edge_ratio, 1.0)
        return area_score * 0.55 + rectangularity * 0.30 + balance_score * 0.15

    def _quality(self, corners: np.ndarray) -> dict:
        try:
            quality = compute_calibration_quality(corners.tolist())
            quality["method"] = self.last_method
            return quality
        except Exception:
            return {"method": self.last_method}

    def get_default_corners(self, width: int, height: int):
        """Returns standard corners for a centered square board."""
        margin = 50
        return np.array([
            [margin, margin],
            [width - margin, margin],
            [width - margin, height - margin],
            [margin, height - margin]
        ], dtype=np.float32)
