from typing import Dict, List, Optional
from dataclasses import dataclass
from backend.application.services.engine_service import EngineService
from backend.events.bus.event_bus import bus
from backend.events.event_types import EventType
from backend.events.models.base_event import BaseEvent

@dataclass
class StrategyAnalysis:
    score: int
    best_move: str
    game_phase: str
    threat_level: str
    material_balance: int
    suggestions: List[Dict]

class StrategyAnalyzer:
    """
    [Application Layer] Advanced Strategy Analyzer.
    Interprets raw engine data to provide high-level strategic insights.
    """
    def __init__(self, engine_service: EngineService):
        self.engine = engine_service

    async def analyze_position(self, fen: str) -> StrategyAnalysis:
        # 1. Deep Engine Analysis
        result = await self.engine.compute(fen, depth=16, multipv=3)

        # 2. Material Calculation
        balance = self._calculate_material(fen)

        # 3. Game Phase Detection
        phase = self._detect_phase(fen)

        # 4. Threat Interpretation
        threat = "LOW"
        score = result.get("score", 0)
        if abs(score) > 300: threat = "CRITICAL"
        elif abs(score) > 100: threat = "MODERATE"

        analysis = StrategyAnalysis(
            score=score,
            best_move=result.get("best_move", ""),
            game_phase=phase,
            threat_level=threat,
            material_balance=balance,
            suggestions=result.get("multi_pv", [])
        )

        # 5. Broadcast insights
        bus.publish(BaseEvent.create(
            event_type=EventType.ENGINE_MOVE_GENERATED,
            source="strategy_analyzer",
            payload=vars(analysis)
        ))

        return analysis

    def _calculate_material(self, fen: str) -> int:
        weights = {'p': 1, 'n': 3, 'b': 3, 'r': 5, 'c': 4.5, 'a': 2, 'k': 0}
        board_part = fen.split(' ')[0]
        balance = 0
        for char in board_part:
            if char.lower() in weights:
                val = weights[char.lower()]
                balance += val if char.isupper() else -val
        return balance

    def _detect_phase(self, fen: str) -> str:
        # Count pieces to determine phase
        piece_count = sum(1 for c in fen.split(' ')[0] if c.isalpha())
        if piece_count > 20: return "OPENING"
        if piece_count > 10: return "MIDGAME"
        return "ENDGAME"
