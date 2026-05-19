from __future__ import annotations

import os
import time
from typing import List

import cv2
import numpy as np

from backend.infrastructure.vision.detection.detection_result import BoundingBox, Detection
from backend.utils import config
from backend.utils.logger import logger


class Detector:
    """
    OpenCV DNN detector for exported ONNX YOLO models.

    Runtime uses SAHI+Ultralytics for the protected best.pt model. This class is
    kept as a lightweight ONNX path for deployments that export the model later.
    """

    def __init__(self, model_path: str = config.YOLO_MODEL_PATH):
        self.net = None
        self.model_path = os.path.abspath(model_path) if model_path else ""
        self.input_size = int(getattr(config, "YOLO_DNN_INPUT_SIZE", 640))
        self.confidence_threshold = float(getattr(config, "VISION_CONFIDENCE", 0.3))
        self.nms_iou = float(getattr(config, "VISION_NMS_IOU", 0.45))
        self.output_has_objectness = bool(getattr(config, "YOLO_OUTPUT_HAS_OBJECTNESS", False))
        self.last_error = None
        if model_path:
            self.load_model(model_path)

    def load_model(self, model_path: str):
        self.model_path = os.path.abspath(model_path) if model_path else ""
        self.last_error = None
        self.net = None

        if not self.model_path or not os.path.exists(self.model_path):
            self.last_error = f"model_not_found: {self.model_path}"
            logger.error(f"[Detector] Model not found: {self.model_path}")
            return

        if not self.model_path.lower().endswith(".onnx"):
            self.last_error = "opencv_dnn_requires_onnx"
            logger.warning(f"[Detector] OpenCV DNN expects ONNX, got: {self.model_path}")
            return

        try:
            model_bytes = np.fromfile(self.model_path, dtype=np.uint8)
            self.net = cv2.dnn.readNetFromONNX(model_bytes)
            self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
            logger.info(f"[Detector] ONNX model loaded: {self.model_path}")
            self.detect(np.zeros((self.input_size, self.input_size, 3), dtype=np.uint8))
        except Exception as e:
            self.net = None
            self.last_error = str(e)
            logger.error(f"[Detector] Failed to load ONNX model: {e}")

    def detect(self, image: np.ndarray) -> List[Detection]:
        if self.net is None or image is None:
            return []

        blob = cv2.dnn.blobFromImage(
            np.ascontiguousarray(image),
            1 / 255.0,
            (self.input_size, self.input_size),
            swapRB=True,
            crop=False,
        )

        start = time.time()
        try:
            self.net.setInput(blob)
            outputs = self.net.forward()
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"[Detector] Inference failed: {e}")
            return []

        detections = self._parse_yolo_output(outputs, image.shape[:2])
        latency_ms = (time.time() - start) * 1000.0
        logger.debug(f"[Detector] inference={latency_ms:.2f}ms detections={len(detections)}")
        return detections

    def _parse_yolo_output(self, outputs, image_shape) -> List[Detection]:
        h, w = image_shape
        raw = np.asarray(outputs)
        raw = np.squeeze(raw)

        if raw.ndim != 2:
            return []

        if raw.shape[0] < raw.shape[1] and raw.shape[0] <= 128:
            raw = raw.T

        boxes = []
        confidences = []
        class_ids = []

        for row in raw:
            if len(row) < 5:
                continue

            cx, cy, bw, bh = row[:4]
            class_scores = row[5:] if self.output_has_objectness and len(row) > 5 else row[4:]
            objectness = float(row[4]) if self.output_has_objectness else 1.0
            if len(class_scores) == 0:
                continue

            class_id = int(np.argmax(class_scores))
            confidence = float(class_scores[class_id]) * objectness
            if confidence < self.confidence_threshold:
                continue

            x_scale = w / float(self.input_size)
            y_scale = h / float(self.input_size)
            x1 = max(0.0, (float(cx) - float(bw) / 2.0) * x_scale)
            y1 = max(0.0, (float(cy) - float(bh) / 2.0) * y_scale)
            x2 = min(float(w), (float(cx) + float(bw) / 2.0) * x_scale)
            y2 = min(float(h), (float(cy) + float(bh) / 2.0) * y_scale)
            boxes.append([int(x1), int(y1), int(max(1.0, x2 - x1)), int(max(1.0, y2 - y1))])
            confidences.append(confidence)
            class_ids.append(class_id)

        keep = cv2.dnn.NMSBoxes(boxes, confidences, self.confidence_threshold, self.nms_iou)
        if len(keep) == 0:
            return []

        detections = []
        for index in np.array(keep).flatten():
            x, y, bw, bh = boxes[int(index)]
            class_id = class_ids[int(index)]
            detections.append(
                Detection(
                    class_id=class_id,
                    class_name=str(class_id),
                    confidence=float(confidences[int(index)]),
                    bbox=BoundingBox(x1=float(x), y1=float(y), x2=float(x + bw), y2=float(y + bh)),
                )
            )
        return detections

    def get_status(self) -> dict:
        return {
            "loaded": self.net is not None,
            "model_path": self.model_path,
            "model_exists": bool(self.model_path and os.path.exists(self.model_path)),
            "input_size": self.input_size,
            "confidence_threshold": self.confidence_threshold,
            "nms_iou": self.nms_iou,
            "output_has_objectness": self.output_has_objectness,
            "last_error": self.last_error,
        }
