import cv2
import numpy as np
from typing import Tuple

class ImagePreprocessor:
    """
    Handles image enhancement, noise reduction, and normalization.
    """
    def __init__(self):
        self.clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

    def process(self, frame: np.ndarray) -> np.ndarray:
        """
        Executes the preprocessing pipeline:
        1. Denoising
        2. CLAHE (Contrast Limited Adaptive Histogram Equalization)
        3. Sharpening
        """
        if frame is None:
            return None

        # 1. Denoise (Subtle)
        denoised = cv2.fastNlMeansDenoisingColored(frame, None, 10, 10, 7, 21)

        # 2. Lighting Normalization (CLAHE)
        lab = cv2.cvtColor(denoised, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        cl = self.clahe.apply(l)
        limg = cv2.merge((cl, a, b))
        normalized = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)

        # 3. Sharpening
        kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
        sharpened = cv2.filter2D(normalized, -1, kernel)

        return sharpened

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
    def warp(self, frame: np.ndarray, corners: np.ndarray, output_size: Tuple[int, int] = (1000, 1000)) -> np.ndarray:
        """
        Warps the frame based on four corners to normalize the board coordinate system.
        corners: np.ndarray of shape (4, 2) - [top-left, top-right, bottom-right, bottom-left]
        """
        if corners is None or len(corners) != 4:
            return frame

        width, height = output_size
        dst_pts = np.float32([
            [0, 0],
            [width, 0],
            [width, height],
            [0, height]
        ])
        src_pts = np.float32(corners)

        matrix = cv2.getPerspectiveTransform(src_pts, dst_pts)
        warped = cv2.warpPerspective(frame, matrix, (width, height))

        return warped


Preprocessor = ImagePreprocessor
