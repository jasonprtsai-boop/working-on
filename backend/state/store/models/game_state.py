from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum

class SystemPhase(Enum):
    IDLE = "IDLE"
    THINKING = "THINKING"
    APPLY_MOVE = "APPLY_MOVE"
    WAIT_MOVE = "WAIT_MOVE"
    EXECUTING = "EXECUTING"
    ERROR = "ERROR"

@dataclass(frozen=True)
class CoreGameState:
    board: List[List[Optional[str]]] = field(default_factory=lambda: [[None for _ in range(9)] for _ in range(10)])
    fen: str = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
    move_history: List[str] = field(default_factory=list)
    current_turn: str = "w"
    game_phase: str = "OPENING"
    game_status: str = "IDLE"
    last_notation: Optional[dict] = None
