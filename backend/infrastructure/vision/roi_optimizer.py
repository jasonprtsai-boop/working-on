import cv2
import numpy as np
from typing import Optional, Tuple

class ROIOptimizer:
    """
    [Vision Module] roi_optimizer.py — 變動區域偵測模組
    利用影格差異法 (Frame Differencing) 識別棋盤上的動作區域。
    """
    def __init__(self, threshold: int = 25, min_area: int = 500):
        self.prev_gray: Optional[np.ndarray] = None
        self.threshold = threshold
        self.min_area = min_area
        self.last_roi: Optional[Tuple[int, int, int, int]] = None

    def detect_change(self, frame: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
        """
        偵測影格中的變動區域並返回 Bounding Box (x, y, w, h)。
        若無顯著變動則返回 None。
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)

        if self.prev_gray is None:
            self.prev_gray = gray
            return None

        # 1. 計算影格差異
        frame_delta = cv2.absdiff(self.prev_gray, gray)
        thresh = cv2.threshold(frame_delta, self.threshold, 255, cv2.THRESH_BINARY)[1]

        # 2. 擴大差異區域以涵蓋整顆棋子
        thresh = cv2.dilate(thresh, None, iterations=2)

        # 3. 尋找輪廓
        cnts, _ = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        self.prev_gray = gray

        if not cnts:
            return None

        # 4. 找到最大的變動區域
        max_cnt = max(cnts, key=cv2.contourArea)
        if cv2.contourArea(max_cnt) < self.min_area:
            return None

        x, y, w, h = cv2.boundingRect(max_cnt)

        # 增加 Padding 以確保 YOLO 有足夠上下文
        padding = 50
        h_img, w_img = frame.shape[:2]
        x = max(0, x - padding)
        y = max(0, y - padding)
        w = min(w_img - x, w + 2 * padding)
        h = min(h_img - y, h + 2 * padding)

        self.last_roi = (x, y, w, h)
        return self.last_roi
