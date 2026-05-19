from dataclasses import dataclass
from typing import List, Tuple
import numpy as np

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

@dataclass
class Detection:
    class_id: int
    class_name: str
    confidence: float
    bbox: BoundingBox

    def to_dict(self):
        return {
            "class_id": self.class_id,
            "class_name": self.class_name,
            "confidence": self.confidence,
            "bbox": [self.bbox.x1, self.bbox.y1, self.bbox.x2, self.bbox.y2]
        }

@dataclass
class DetectionResult:
    frame_id: int
    detections: List[Detection]
    timestamp: float
    processing_time: float
