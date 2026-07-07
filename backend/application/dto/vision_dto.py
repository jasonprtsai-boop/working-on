from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
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
    class_id: Optional[int] = None
    coordinate_space: str = "detector_input"
    frame_size: Optional[List[int]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        payload = {
            "class_name": self.class_name,
            "confidence": self.confidence,
            "bbox": self.bbox.to_list(),
            "bbox_xyxy": self.bbox.to_list(),
            "coordinate_space": self.coordinate_space,
        }
        if self.class_id is not None:
            payload["class_id"] = self.class_id
        if self.frame_size is not None:
            payload["frame_size"] = list(self.frame_size)
        payload.update(self.metadata)
        return payload

@dataclass(frozen=True)
class VisionResultDTO:
    timestamp: float
    raw_frame: Optional[np.ndarray] = field(default=None, repr=False)
    work_frame: Optional[np.ndarray] = field(default=None, repr=False)
    detections: List[DetectionDTO] = field(default_factory=list)
    latency_ms: float = 0.0
    fen: Optional[str] = None
    board_state: Dict[str, str] = field(default_factory=dict)
    stage_timings_ms: Dict[str, float] = field(default_factory=dict)
    calibrated: bool = False
    coordinate_space: str = "detector_input"

    def to_dict(self):
        return {
            "timestamp": self.timestamp,
            "detections": [item.to_dict() for item in self.detections],
            "latency_ms": self.latency_ms,
            "fen": self.fen or "",
            "board_state": dict(self.board_state),
            "stage_timings_ms": dict(self.stage_timings_ms),
            "calibrated": bool(self.calibrated),
            "coordinate_space": self.coordinate_space,
        }
