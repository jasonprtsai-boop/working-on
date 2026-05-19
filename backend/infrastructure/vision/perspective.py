import cv2
import numpy as np
from typing import List, Optional

class PerspectiveTransformer:
    """
    [Vision Module] perspective.py — 透視校正模組
    負責棋盤四角定位與單應性矩陣（Homography Matrix）計算。
    """
    def __init__(self, target_size: tuple = (600, 600)):
        self.target_size = target_size
        self.src_pts = None
        self.matrix = None

    def update_corners(self, corners: List[List[float]]):
        """更新棋盤四角座標。"""
        if len(corners) != 4:
            return

        self.src_pts = np.float32(corners)
        dst_pts = np.float32([
            [0, 0],
            [self.target_size[0], 0],
            [self.target_size[0], self.target_size[1]],
            [0, self.target_size[1]]
        ])

        # 計算單應性矩陣
        self.matrix = cv2.getPerspectiveTransform(self.src_pts, dst_pts)

    def transform(self, frame: np.ndarray) -> np.ndarray:
        """將原始斜視畫面轉換為標準俯視平面。"""
        if self.matrix is None:
            return frame

        warped = cv2.warpPerspective(
            frame,
            self.matrix,
            self.target_size
        )
        return warped
