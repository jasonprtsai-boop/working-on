import cv2
import numpy as np
from backend.utils.logger import logger

class BoardCalibrator:
    """
    [Vision Utility] Board Calibrator
    Handles manual and automatic board corner detection for perspective correction.
    """
    def __init__(self):
        self.corners = None

    def detect_auto(self, frame: np.ndarray):
        """
        Attempts to automatically detect board corners using ArUco markers.
        Expected markers at 4 corners (IDs 0, 1, 2, 3).
        """
        try:
            # ArUco detection in OpenCV 4.7+
            dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
            parameters = cv2.aruco.DetectorParameters()
            detector = cv2.aruco.ArucoDetector(dictionary, parameters)
            corners, ids, rejected = detector.detectMarkers(frame)

            if ids is not None and len(ids) >= 4:
                # Map corner IDs to points
                points = {id[0]: c[0][0] for id, c in zip(ids, corners)}
                # Ensure we have 0, 1, 2, 3
                if all(i in points for i in range(4)):
                    self.corners = np.array([points[0], points[1], points[2], points[3]], dtype=np.float32)
                    logger.info("Automatic board detection successful.")
                    return self.corners

            logger.warning("Could not find all 4 ArUco markers (0, 1, 2, 3).")
            return None
        except Exception as e:
            logger.error(f"ArUco detection failed: {e}")
            return None

    def get_default_corners(self, width: int, height: int):
        """Returns standard corners for a centered square board."""
        margin = 50
        return np.array([
            [margin, margin],
            [width - margin, margin],
            [width - margin, height - margin],
            [margin, height - margin]
        ], dtype=np.float32)
