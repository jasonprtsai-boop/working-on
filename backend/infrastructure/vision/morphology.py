import cv2
import numpy as np

class MorphologyOptimizer:
    """
    [Vision Module] morphology.py — 形態學優化模組
    負責透過侵蝕、擴張與開閉運算修復棋子輪廓與反光雜訊。
    """
    def __init__(self):
        self.kernel_3x3 = np.ones((3, 3), np.uint8)
        self.kernel_5x5 = np.ones((5, 5), np.uint8)

    def optimize(self, binary: np.ndarray) -> np.ndarray:
        """執行形態學優化。"""
        # 1. 開運算 (Opening) - 去除細小反光雜訊
        opening = cv2.morphologyEx(binary, cv2.MORPH_OPEN, self.kernel_3x3)

        # 2. 閉運算 (Closing) - 補足棋子字體缺口
        closing = cv2.morphologyEx(opening, cv2.MORPH_CLOSE, self.kernel_5x5)

        # 3. 輕微擴張 (Dilation) - 強化邊界完整性
        optimized = cv2.dilate(closing, self.kernel_3x3, iterations=1)

        return optimized
