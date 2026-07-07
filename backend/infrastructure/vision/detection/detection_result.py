from dataclasses import dataclass
import math
from typing import Any, Dict, List, Optional, Tuple

@dataclass
class BoundingBox:
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    @property
    def center(self) -> Tuple[float, float]:
        return (self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2

    @property
    def xyxy(self) -> List[float]:
        return [float(self.x1), float(self.y1), float(self.x2), float(self.y2)]

    @property
    def xywh(self) -> List[float]:
        return [float(self.x1), float(self.y1), float(self.width), float(self.height)]

    def anchor(self, x_ratio: float = 0.5, y_ratio: float = 0.5) -> Tuple[float, float]:
        x = _bounded_ratio(x_ratio, default=0.5)
        y = _bounded_ratio(y_ratio, default=0.5)
        return self.x1 + self.width * x, self.y1 + self.height * y

    def normalized(self, frame_width: int, frame_height: int) -> Optional[List[float]]:
        width = _positive_number(frame_width)
        height = _positive_number(frame_height)
        if width is None or height is None:
            return None
        return [
            float(self.x1) / width,
            float(self.y1) / height,
            float(self.x2) / width,
            float(self.y2) / height,
        ]

@dataclass
class Detection:
    class_id: int
    class_name: str
    confidence: float
    bbox: BoundingBox
    coordinate_space: str = "detector_input"
    frame_width: Optional[int] = None
    frame_height: Optional[int] = None

    def to_dict(
        self,
        *,
        anchor_ratio: Tuple[float, float] = (0.5, 0.5),
        coordinate_space: Optional[str] = None,
        frame_size: Optional[Tuple[int, int]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        width, height = self._resolve_frame_size(frame_size)
        anchor = self.bbox.anchor(*anchor_ratio)
        center = self.bbox.center
        payload: Dict[str, Any] = {
            "class_id": self.class_id,
            "class_name": self.class_name,
            "confidence": self.confidence,
            "bbox": self.bbox.xyxy,
            "bbox_xyxy": self.bbox.xyxy,
            "bbox_xywh": self.bbox.xywh,
            "bbox_center": [float(center[0]), float(center[1])],
            "anchor_point": [float(anchor[0]), float(anchor[1])],
            "anchor_ratio": [float(anchor_ratio[0]), float(anchor_ratio[1])],
            "coordinate_space": str(coordinate_space or self.coordinate_space or "detector_input"),
        }
        normalized = self.bbox.normalized(width, height) if width and height else None
        if normalized is not None:
            payload["frame_size"] = [int(width), int(height)]
            payload["bbox_normalized"] = normalized
        if extra:
            payload.update(extra)
        return payload

    def _resolve_frame_size(self, frame_size: Optional[Tuple[int, int]]) -> Tuple[Optional[int], Optional[int]]:
        if frame_size is None:
            return self.frame_width, self.frame_height
        try:
            width = int(frame_size[0])
            height = int(frame_size[1])
        except (TypeError, ValueError, IndexError):
            return self.frame_width, self.frame_height
        return width, height

@dataclass
class DetectionResult:
    frame_id: int
    detections: List[Detection]
    timestamp: float
    processing_time: float


def _bounded_ratio(value, *, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return max(0.0, min(number, 1.0))


def _positive_number(value) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0.0:
        return None
    return number
