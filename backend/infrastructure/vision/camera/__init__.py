import cv2
import numpy as np
from typing import Optional, Tuple
from backend.utils.logger import logger
from backend.utils import config

class Camera:
    """
    [Vision Module] camera/__init__.py — 影像擷取基礎類別
    負責管理 OpenCV 與攝影機之間的影像串流連線。
    """
    def __init__(self, index: int = config.CAMERA_INDEX):
        self.index = index
        self.cap: Optional[cv2.VideoCapture] = None

    def open(self) -> bool:
        """開啟攝影機連線。"""
        try:
            self.cap = cv2.VideoCapture(self.index, cv2.CAP_DSHOW)
            if not self.cap.isOpened():
                self.cap = cv2.VideoCapture(self.index)

            if self.cap.isOpened():
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                logger.info(f"[Camera] Connected to index {self.index}")
                return True
        except Exception as e:
            logger.error(f"[Camera] Connection failed: {e}")
        return False

    def get_frame(self) -> Optional[np.ndarray]:
        """持續擷取即時影格，並轉換為 NumPy 矩陣。"""
        if self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                return frame
        return None

    def release(self):
        """釋放攝影機資源。"""
        if self.cap:
            self.cap.release()
            self.cap = None

    def encode_mjpeg(self, frame: np.ndarray) -> bytes:
        """將處理後影像編碼為 JPEG 格式供串流推送。"""
        ret, buffer = cv2.imencode('.jpg', frame)
        if ret:
            return buffer.tobytes()
        return b""
