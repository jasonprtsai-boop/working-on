from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass(frozen=True)
class VisionState:
    camera_status: str = "OFFLINE"
    mode: str = "unknown"
    simulation: bool = False
    confidence: float = 0.0
    last_detection_time: float = 0.0
    board_mapping: Dict[str, Any] = field(default_factory=dict)
    fps: float = 0.0
    piece_counts: Dict[str, int] = field(default_factory=dict)
