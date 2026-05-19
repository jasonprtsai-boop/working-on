from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class TechnicalRecord:
    tid: str
    experiment_tag: str
    vision_latency: float
    yolo_confidence: float
    match_score: float = 0.0
    ai_decision_time: float = 0.0
    ai_score_cp: int = 0
    ai_depth: int = 0
    ai_chosen_rank: int = 1
    robot_move_time: float = 0.0
    delta_error: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class GameStateDTO:
    state: str
    fen: str
    is_admin: bool = False
    last_move: str = ""
    history: List[dict] = field(default_factory=list)
    perf: Dict[str, float] = field(default_factory=dict)


class MoveModel:
    def __init__(self, move_id, move, fen, timestamp):
        self.id = move_id
        self.move = move
        self.fen = fen
        self.timestamp = timestamp
