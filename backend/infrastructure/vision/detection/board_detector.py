import cv2
import numpy as np

class BoardDetector:
    """Handles the detection and calibration of the physical Xiangqi board."""
    def __init__(self):
        self.aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        self.params = cv2.aruco.DetectorParameters()
        self.H = None

    def detect_markers(self, frame):
        corners, ids, _ = cv2.aruco.detectMarkers(frame, self.aruco_dict, parameters=self.params)
        return corners, ids

    def calibrate(self, img_pts, world_pts):
        self.H, _ = cv2.findHomography(
            np.array(img_pts, dtype=np.float32),
            np.array(world_pts, dtype=np.float32)
        )
        return self.H

    def transform_to_world(self, x, y):
        if self.H is None: return x, y
        p = np.array([x, y, 1], dtype=np.float32).reshape(3, 1)
        out = self.H @ p
        out /= out[2]
        return float(out[0][0]), float(out[1][0])
