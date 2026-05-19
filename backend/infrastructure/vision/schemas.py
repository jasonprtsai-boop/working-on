from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime

class DetectionResult(BaseModel):
    """[Production Architecture] Normalized vision detection output."""
    board_matrix: List[List[Optional[str]]]
    fen: str
    confidence: float
    piece_confidence_map: Dict[str, float] = {} # [Industrial] Per-piece confidence
    timestamp: datetime = Field(default_factory=datetime.now)
    frame_id: str
    latency_ms: float

class VisionTrace(BaseModel):
    """[Industrial] Latency tracing for vision stages."""
    capture_ms: float
    preprocess_ms: float
    inference_ms: float
    verification_ms: float
    total_ms: float
