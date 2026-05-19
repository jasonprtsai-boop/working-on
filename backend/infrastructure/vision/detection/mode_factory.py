from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

import numpy as np

from backend.infrastructure.vision.detection.detection_result import BoundingBox, Detection
from backend.infrastructure.vision.roi_optimizer import ROIOptimizer
from backend.utils import config


@dataclass(frozen=True)
class DetectionModeConfig:
    mode: str
    use_sahi: bool
    use_roi: bool
    description: str


DETECTION_MODE_CONFIGS: Dict[str, DetectionModeConfig] = {
    "full_yolo": DetectionModeConfig(
        mode="full_yolo",
        use_sahi=False,
        use_roi=False,
        description="YOLO full-frame inference",
    ),
    "sahi": DetectionModeConfig(
        mode="sahi",
        use_sahi=True,
        use_roi=False,
        description="YOLO with SAHI sliced inference",
    ),
    "roi_yolo": DetectionModeConfig(
        mode="roi_yolo",
        use_sahi=False,
        use_roi=True,
        description="ROI prefilter followed by YOLO inference",
    ),
    "roi_sahi": DetectionModeConfig(
        mode="roi_sahi",
        use_sahi=True,
        use_roi=True,
        description="ROI prefilter followed by SAHI sliced inference",
    ),
}

DEFAULT_DETECTION_MODES = tuple(DETECTION_MODE_CONFIGS.keys())


class ROIAdjustedDetector:
    """
    Applies an ROI crop before inference and maps detector bboxes back to frame coordinates.
    """

    def __init__(self, detector, roi_optimizer: Optional[ROIOptimizer] = None, fallback_to_full_frame: bool = True):
        self.detector = detector
        self.roi_optimizer = roi_optimizer or ROIOptimizer()
        self.fallback_to_full_frame = bool(fallback_to_full_frame)
        self.last_roi = None
        self.last_roi_applied = False

    def load_model(self, model_path: str):
        if hasattr(self.detector, "load_model"):
            return self.detector.load_model(model_path)
        return None

    def detect(self, frame: np.ndarray) -> List[Detection]:
        if frame is None:
            self.last_roi = None
            self.last_roi_applied = False
            return []

        roi = self.roi_optimizer.detect_change(frame)
        crop = frame
        offset_x = 0
        offset_y = 0
        self.last_roi = roi
        self.last_roi_applied = False

        if roi is not None:
            x, y, w, h = [int(round(float(value))) for value in roi]
            frame_h, frame_w = frame.shape[:2]
            x = max(0, min(x, frame_w))
            y = max(0, min(y, frame_h))
            w = max(0, min(w, frame_w - x))
            h = max(0, min(h, frame_h - y))
            if w > 0 and h > 0:
                crop = frame[y : y + h, x : x + w]
                offset_x = x
                offset_y = y
                self.last_roi = (x, y, w, h)
                self.last_roi_applied = True

        if not self.last_roi_applied and not self.fallback_to_full_frame:
            return []

        detections = self.detector.detect(crop)
        if not self.last_roi_applied:
            return detections

        return [self._offset_detection(det, offset_x, offset_y) for det in detections]

    def _offset_detection(self, detection: Detection, offset_x: int, offset_y: int) -> Detection:
        bbox = detection.bbox
        return Detection(
            class_id=detection.class_id,
            class_name=detection.class_name,
            confidence=detection.confidence,
            bbox=BoundingBox(
                x1=float(bbox.x1 + offset_x),
                y1=float(bbox.y1 + offset_y),
                x2=float(bbox.x2 + offset_x),
                y2=float(bbox.y2 + offset_y),
            ),
        )

    def get_status(self) -> dict:
        status = self.detector.get_status() if hasattr(self.detector, "get_status") else {}
        return {
            "roi_enabled": True,
            "roi_applied": self.last_roi_applied,
            "last_roi": list(self.last_roi) if self.last_roi else None,
            "fallback_to_full_frame": self.fallback_to_full_frame,
            "detector": status,
        }


class DetectorModeFactory:
    """
    Builds detector pipelines for the benchmark A-D comparison modes.
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        yolo_builder: Optional[Callable[[], object]] = None,
        sahi_builder: Optional[Callable[[], object]] = None,
        roi_builder: Optional[Callable[[], ROIOptimizer]] = None,
    ):
        self.model_path = os.path.abspath(model_path or config.YOLO_MODEL_PATH)
        self.yolo_builder = yolo_builder or self._build_yolo_detector
        self.sahi_builder = sahi_builder or self._build_sahi_detector
        self.roi_builder = roi_builder or ROIOptimizer

    def create(self, mode: str):
        mode_config = self.mode_config(mode)
        detector = self.sahi_builder() if mode_config.use_sahi else self.yolo_builder()
        if mode_config.use_roi:
            detector = ROIAdjustedDetector(detector, roi_optimizer=self.roi_builder())
        return detector

    def create_all(self, modes=None) -> Dict[str, object]:
        selected = list(modes or DEFAULT_DETECTION_MODES)
        return {mode: self.create(mode) for mode in selected}

    def mode_config(self, mode: str) -> DetectionModeConfig:
        normalized = str(mode or "").strip().lower()
        if normalized not in DETECTION_MODE_CONFIGS:
            raise ValueError(f"Unsupported detection mode: {mode}")
        return DETECTION_MODE_CONFIGS[normalized]

    def _build_yolo_detector(self):
        if self.model_path.lower().endswith(".onnx"):
            from backend.infrastructure.vision.detection.opencv_dnn_detector import Detector

            return Detector(model_path=self.model_path)

        from backend.infrastructure.vision.detection.yolo_detector import YOLODetector

        return YOLODetector(model_path=self.model_path)

    def _build_sahi_detector(self):
        from backend.infrastructure.vision.detection.sahi_detector import SAHIDetector

        return SAHIDetector(model_path=self.model_path)
