from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass(frozen=True)
class EngineState:
    bestmove: Optional[str] = None
    score: float = 0.0
    depth: int = 0
    nodes: int = 0
    nps: int = 0
    pv: List[str] = field(default_factory=list)
    multipv: List[Dict[str, Any]] = field(default_factory=list)
    engine_status: str = "READY"
    is_thinking: bool = False
