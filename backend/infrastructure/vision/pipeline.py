import dataclasses
import time
import asyncio
from typing import Optional, List
import numpy as np

# New Granular Modules
from .preprocess import Preprocessor
from .perspective import PerspectiveTransformer
from .morphology import MorphologyOptimizer
from .fen.fen_generator import DetectionFENGenerator as FenGenerator
from backend.application.dto.vision_dto import VisionResultDTO, DetectionDTO, BoundingBoxDTO
from backend.utils.logger import logger

class VisionPipeline:
    """
    [Architectural Orchestrator] Vision Pipeline
    描述 OpenCV 功能如何封裝成模組，並與 YOLO 推論及 FEN 生成串聯。
    """
    def __init__(self, camera, preprocess, perspective, morphology, detector, fen_gen, roi_opt=None):
        self.camera = camera
        self.preprocess = preprocess
        self.perspective = perspective
        self.morphology = morphology
        self.detector = detector
        self.fen_gen = fen_gen
        self.roi_opt = roi_opt
        self._last_result = None

    async def process(self, frame: np.ndarray, turn: str = "w") -> Optional[VisionResultDTO]:
        """
        論文推薦之主流程 (main.py logic):
        frame -> transform -> [ROI Check] -> preprocess -> optimize -> detect -> generate
        """
        if frame is None:
            return None

        start_time = time.time()

        # 1. perspective.py — 透視校正
        warped = self.perspective.transform(frame)

        # 2. ROI Optimizer — 變動偵測 (節省效能核心)
        if self.roi_opt:
            change = self.roi_opt.detect_change(warped)
            if change is None and self._last_result:
                # 無顯著變動，沿用上次辨識結果，跳過 YOLO 推論
                latency = (time.time() - start_time) * 1000
                return dataclasses.replace(self._last_result, latency_ms=latency, timestamp=time.time())

        # 3. preprocess.py — 影像前處理 (彩色增強用於偵測)
        enhanced = self.preprocess.enhance_color(warped)

        # 4. detector.py — YOLO 推論
        raw_detections = self.detector.detect(enhanced)

        # 5. fen_generator.py — 棋譜轉換
        fen = self.fen_gen.generate(raw_detections, turn=turn)

        latency = (time.time() - start_time) * 1000

        self._last_result = VisionResultDTO(
            timestamp=time.time(),
            raw_frame=frame,
            work_frame=warped,
            detections=[
                DetectionDTO(
                    class_name=d.class_name,
                    confidence=d.confidence,
                    bbox=BoundingBoxDTO(x1=d.bbox.x1, y1=d.bbox.y1, x2=d.bbox.x2, y2=d.bbox.y2)
                ) for d in raw_detections
            ],
            latency_ms=latency,
            fen=fen
        )
        return self._last_result

    def update_corners(self, corners):
        self.perspective.update_corners(corners)
