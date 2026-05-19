from __future__ import annotations

import os
import time
from typing import List

import numpy as np

from backend.infrastructure.vision.detection.detection_result import BoundingBox, Detection
from backend.infrastructure.vision.detection.detector import BaseDetector
from backend.utils import config
from backend.utils.logger import logger

try:
    from ultralytics import YOLO

    ULTRALYTICS_AVAILABLE = True
except Exception:
    YOLO = None
    ULTRALYTICS_AVAILABLE = False


class YOLODetector(BaseDetector):
    """
    Ultralytics YOLO detector for full-frame runtime inference.

    The OpenCV DNN detector remains available for ONNX deployments. This class
    gives the benchmark a direct full-image YOLO path for protected .pt models.
    """

    def __init__(
        self,
        model_path: str = config.YOLO_MODEL_PATH,
        confidence_threshold: float = config.VISION_CONFIDENCE,
        nms_iou: float = config.VISION_NMS_IOU,
        device: str = config.VISION_DEVICE,
    ):
        self.model = None
        self.model_path = os.path.abspath(model_path) if model_path else ""
        self.confidence_threshold = float(confidence_threshold)
        self.nms_iou = float(nms_iou)
        self.device = device or "cpu"
        self.last_error = None
        if model_path:
            self.load_model(model_path)

    def load_model(self, model_path: str):
        self.model_path = os.path.abspath(model_path) if model_path else ""
        self.model = None
        self.last_error = None

        if not ULTRALYTICS_AVAILABLE:
            self.last_error = "ultralytics_not_available"
            logger.warning("Ultralytics is not installed. YOLODetector cannot load a model.")
            return

        if not self.model_path or not os.path.exists(self.model_path):
            self.last_error = f"model_not_found: {self.model_path}"
            logger.error("[YOLODetector] Model not found: %s", self.model_path)
            return

        try:
            self.model = YOLO(self.model_path)
            logger.info("[YOLODetector] Model loaded: %s", self.model_path)
        except Exception as exc:
            self.model = None
            self.last_error = str(exc)
            logger.error("[YOLODetector] Failed to load model: %s", exc)

    def detect(self, frame: np.ndarray) -> List[Detection]:
        if self.model is None or frame is None:
            return []

        start = time.time()
        try:
            results = self.model.predict(
                source=np.ascontiguousarray(frame),
                conf=self.confidence_threshold,
                iou=self.nms_iou,
                device=self.device,
                verbose=False,
            )
        except Exception as exc:
            self.last_error = str(exc)
            logger.error("[YOLODetector] Inference failed: %s", exc)
            return []

        detections: List[Detection] = []
        for result in results or []:
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue

            xyxy = self._to_numpy(getattr(boxes, "xyxy", []))
            conf = self._to_numpy(getattr(boxes, "conf", []))
            cls = self._to_numpy(getattr(boxes, "cls", []))
            names = getattr(result, "names", {}) or {}

            for idx, bbox in enumerate(xyxy):
                class_id = int(cls[idx]) if idx < len(cls) else 0
                class_name = str(names.get(class_id, class_id)) if isinstance(names, dict) else str(class_id)
                score = float(conf[idx]) if idx < len(conf) else 0.0
                detections.append(
                    Detection(
                        class_id=class_id,
                        class_name=class_name,
                        confidence=score,
                        bbox=BoundingBox(
                            x1=float(bbox[0]),
                            y1=float(bbox[1]),
                            x2=float(bbox[2]),
                            y2=float(bbox[3]),
                        ),
                    )
                )

        latency_ms = (time.time() - start) * 1000.0
        logger.debug("[YOLODetector] inference=%.2fms detections=%s", latency_ms, len(detections))
        return detections

    def _to_numpy(self, value):
        try:
            if hasattr(value, "detach"):
                value = value.detach()
            if hasattr(value, "cpu"):
                value = value.cpu()
            if hasattr(value, "numpy"):
                return value.numpy()
        except Exception:
            logger.debug("[YOLODetector] failed tensor conversion", exc_info=True)
        return np.asarray(value)

    def get_status(self) -> dict:
        return {
            "available": bool(ULTRALYTICS_AVAILABLE),
            "loaded": self.model is not None,
            "model_path": self.model_path,
            "model_exists": bool(self.model_path and os.path.exists(self.model_path)),
            "confidence_threshold": self.confidence_threshold,
            "nms_iou": self.nms_iou,
            "device": self.device,
            "last_error": self.last_error,
        }
