import cv2
import numpy as np

from backend.infrastructure.vision.calibration import apply_homography_point, compute_warp_matrix
from backend.infrastructure.vision.calibration.board_calibrator import BoardCalibrator


class BoardDetector:
    """Handles the detection and calibration of the physical Xiangqi board."""
    def __init__(self):
        self.aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        self.params = cv2.aruco.DetectorParameters()
        self.H = None
        self.corners = None
        self.calibrator = BoardCalibrator()

    def detect_markers(self, frame):
        if hasattr(cv2.aruco, "ArucoDetector"):
            detector = cv2.aruco.ArucoDetector(self.aruco_dict, self.params)
            corners, ids, _ = detector.detectMarkers(frame)
        else:
            corners, ids, _ = cv2.aruco.detectMarkers(frame, self.aruco_dict, parameters=self.params)
        return corners, ids

    def detect_corners(self, frame):
        self.corners = self.calibrator.detect_auto(frame)
        return self.corners

    def calibrate(self, img_pts, world_pts):
        self.H, _ = cv2.findHomography(
            np.array(img_pts, dtype=np.float32),
            np.array(world_pts, dtype=np.float32)
        )
        return self.H

    def calibrate_from_corners(self, corners, output_size=(1000, 1000)):
        self.corners = BoardCalibrator.order_corners(corners)
        self.H = compute_warp_matrix(self.corners, output_size)
        return self.H

    def transform_to_world(self, x, y):
        if self.H is None: return x, y
        return apply_homography_point(self.H, x, y)

    def transform_to_board(self, x, y):
        return self.transform_to_world(x, y)
