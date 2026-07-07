from __future__ import annotations

import os
import re
import time
from importlib.metadata import PackageNotFoundError, version as package_version
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

ULTRALYTICS_MIN_VERSION = getattr(config, "ULTRALYTICS_MIN_VERSION", "8.4.55")


def _installed_version(package_name: str) -> str | None:
    try:
        return package_version(package_name)
    except PackageNotFoundError:
        return None
    except Exception:
        logger.debug("[YOLODetector] failed to read package version for %s", package_name, exc_info=True)
        return None


def _version_tuple(value: str | None) -> tuple[int, int, int]:
    parts = [int(part) for part in re.findall(r"\d+", str(value or ""))[:3]]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def _version_at_least(installed: str | None, minimum: str) -> bool:
    return bool(installed) and _version_tuple(installed) >= _version_tuple(minimum)


ULTRALYTICS_VERSION = _installed_version("ultralytics")
ULTRALYTICS_VERSION_OK = _version_at_least(ULTRALYTICS_VERSION, ULTRALYTICS_MIN_VERSION)


class YOLODetector(BaseDetector):
    """
    Ultralytics YOLO detector for full-frame runtime inference.

    Ultralytics can run the configured YOLO model path directly.
    """

    def __init__(
        self,
        model_path: str = config.YOLO_MODEL_PATH,
        confidence_threshold: float = config.VISION_CONFIDENCE,
        nms_iou: float = config.VISION_NMS_IOU,
        device: str = config.VISION_DEVICE,
        warmup_on_load: bool = config.YOLO_WARMUP_ON_LOAD,
    ):
        self.model = None
        self.model_path = os.path.abspath(model_path) if model_path else ""
        self.confidence_threshold = float(confidence_threshold)
        self.nms_iou = float(nms_iou)
        self.device = device or "cpu"
        self.warmup_on_load = bool(warmup_on_load)
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

        if not ULTRALYTICS_VERSION_OK:
            self.last_error = f"ultralytics_version_unsupported: {ULTRALYTICS_VERSION or 'missing'} < {ULTRALYTICS_MIN_VERSION}"
            logger.error("[YOLODetector] Ultralytics %s is required for YOLO26 support.", ULTRALYTICS_MIN_VERSION)
            return

        if not self.model_path or not os.path.exists(self.model_path):
            self.last_error = f"model_not_found: {self.model_path}"
            logger.error("[YOLODetector] Model not found: %s", self.model_path)
            return

        try:
            kwargs = {"task": "detect"} if self.model_path.lower().endswith(".onnx") else {}
            self.model = YOLO(self.model_path, **kwargs)
            if self.warmup_on_load:
                self._warmup_model()
            logger.info("[YOLODetector] Model loaded: %s", self.model_path)
        except Exception as exc:
            self.model = None
            self.last_error = str(exc)
            logger.error("[YOLODetector] Failed to load model: %s", exc)

    def _warmup_model(self) -> None:
        if self.model is None:
            return
        input_size = int(getattr(config, "YOLO_DNN_INPUT_SIZE", 640))
        frame = np.zeros((input_size, input_size, 3), dtype=np.uint8)
        self.model.predict(
            source=np.ascontiguousarray(frame),
            conf=self.confidence_threshold,
            iou=self.nms_iou,
            device=self.device,
            verbose=False,
        )

    def detect(self, frame: np.ndarray) -> List[Detection]:
        if self.model is None or frame is None:
            return []

        frame_height, frame_width = frame.shape[:2]
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
                        coordinate_space="detector_input",
                        frame_width=int(frame_width),
                        frame_height=int(frame_height),
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
            "ultralytics_version": ULTRALYTICS_VERSION,
            "ultralytics_min_version": ULTRALYTICS_MIN_VERSION,
            "ultralytics_version_ok": ULTRALYTICS_VERSION_OK,
            "loaded": self.model is not None,
            "model_path": self.model_path,
            "model_type": getattr(config, "YOLO_MODEL_TYPE", "yolo26"),
            "model_exists": bool(self.model_path and os.path.exists(self.model_path)),
            "confidence_threshold": self.confidence_threshold,
            "nms_iou": self.nms_iou,
            "device": self.device,
            "warmup_on_load": self.warmup_on_load,
            "last_error": self.last_error,
        }
