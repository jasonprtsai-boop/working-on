from dataclasses import dataclass, field
from typing import List, Optional
import numpy as np

@dataclass(frozen=True)
class BoundingBoxDTO:
    x1: float
    y1: float
    x2: float
    y2: float

    def to_list(self):
        return [self.x1, self.y1, self.x2, self.y2]

@dataclass(frozen=True)
class DetectionDTO:
    class_name: str
    confidence: float
    bbox: BoundingBoxDTO

    def to_dict(self):
        return {
            "class_name": self.class_name,
            "confidence": self.confidence,
            "bbox": self.bbox.to_list(),
        }

@dataclass(frozen=True)
class VisionResultDTO:
    timestamp: float
    raw_frame: Optional[np.ndarray] = field(default=None, repr=False)
    work_frame: Optional[np.ndarray] = field(default=None, repr=False)
    detections: List[DetectionDTO] = field(default_factory=list)
    latency_ms: float = 0.0
    fen: Optional[str] = None

    def to_dict(self):
        return {
            "timestamp": self.timestamp,
            "detections": [item.to_dict() for item in self.detections],
            "latency_ms": self.latency_ms,
            "fen": self.fen or "",
        }
