import os
import time
from typing import List

import numpy as np

from .detector import BaseDetector
from .detection_result import Detection, BoundingBox
from backend.utils.logger import logger
from backend.utils import config

try:
    from sahi import AutoDetectionModel
    from sahi.predict import get_sliced_prediction
    SAHI_AVAILABLE = True
except ImportError:
    SAHI_AVAILABLE = False
    logger.warning("SAHI not installed. SAHIDetector will not function.")

class SAHIDetector(BaseDetector):
    """
    Implements Sliced Aided Hyper Inference (SAHI) for detecting small chess pieces.
    """
    def __init__(
        self,
        model_path: str = config.YOLO_MODEL_PATH,
        confidence_threshold: float = config.VISION_CONFIDENCE,
        model_type: str = config.YOLO_MODEL_TYPE,
        device: str = config.VISION_DEVICE,
    ):
        self.model = None
        self.model_path = os.path.abspath(model_path) if model_path else ""
        self.model_type = model_type or "yolov8"
        self.device = device or "cpu"
        self.confidence_threshold = confidence_threshold
        self.last_error = None
        if model_path:
            self.load_model(model_path, model_type=self.model_type)

    def load_model(self, model_path: str, model_type: str = "yolov8"):
        self.model_path = os.path.abspath(model_path) if model_path else ""
        self.model_type = model_type or self.model_type or "yolov8"
        self.last_error = None

        if not SAHI_AVAILABLE:
            self.last_error = "sahi_not_available"
            logger.warning("SAHI not installed. Cannot load detection model.")
            return

        if not self.model_path or not os.path.exists(self.model_path):
            self.last_error = f"model_not_found: {self.model_path}"
            logger.error(f"SAHI model not found: {self.model_path}")
            return

        logger.info(f"Loading SAHI model: {self.model_path} ({self.model_type}, device={self.device})")
        try:
            self.model = AutoDetectionModel.from_pretrained(
                model_type=self.model_type,
                model_path=self.model_path,
                confidence_threshold=self.confidence_threshold,
                device=self.device,
            )
        except Exception as e:
            self.model = None
            self.last_error = str(e)
            logger.error(f"Failed to load SAHI model: {e}")

    def detect(self, frame: np.ndarray) -> List[Detection]:
        if not SAHI_AVAILABLE or self.model is None:
            return []

        start_time = time.time()

        try:
            result = get_sliced_prediction(
                np.ascontiguousarray(frame),
                self.model,
                slice_height=config.SAHI_SLICE_HEIGHT,
                slice_width=config.SAHI_SLICE_WIDTH,
                overlap_height_ratio=config.SAHI_OVERLAP_RATIO,
                overlap_width_ratio=config.SAHI_OVERLAP_RATIO,
                verbose=0,
            )
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"SAHI detection failed: {e}")
            return []

        detections = []
        for pred in result.object_prediction_list:
            bbox = pred.bbox.to_xyxy()
            detections.append(Detection(
                class_id=int(pred.category.id),
                class_name=str(pred.category.name),
                confidence=float(pred.score.value),
                bbox=BoundingBox(
                    x1=float(bbox[0]),
                    y1=float(bbox[1]),
                    x2=float(bbox[2]),
                    y2=float(bbox[3]),
                ),
            ))

        latency = (time.time() - start_time) * 1000
        logger.debug(f"SAHI Detection completed in {latency:.2f}ms. Found {len(detections)} objects.")

        return detections

    def get_status(self) -> dict:
        return {
            "available": bool(SAHI_AVAILABLE),
            "loaded": self.model is not None,
            "model_path": self.model_path,
            "model_exists": bool(self.model_path and os.path.exists(self.model_path)),
            "model_type": self.model_type,
            "device": self.device,
            "confidence_threshold": self.confidence_threshold,
            "slice_width": config.SAHI_SLICE_WIDTH,
            "slice_height": config.SAHI_SLICE_HEIGHT,
            "overlap_ratio": config.SAHI_OVERLAP_RATIO,
            "last_error": self.last_error,
        }
