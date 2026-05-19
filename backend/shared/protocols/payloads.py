from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class MovePayload(BaseModel):
    move: str
    fen: str
    player: str = "Human"
    is_capture: bool = False
    timestamp: float = Field(default_factory=lambda: 0.0)

class EngineAnalysisPayload(BaseModel):
    move: str
    score: float
    depth: int
    pv: List[str] = Field(default_factory=list)
    latency: float = 0.0

class VisionDetectionPayload(BaseModel):
    fen: str
    confidence: float
    latency: float = 0.0
    image_path: Optional[str] = None

class SystemStatusPayload(BaseModel):
    phase: str
    status_text: str
    uptime: float
    health: Dict[str, Any] = Field(default_factory=dict)
