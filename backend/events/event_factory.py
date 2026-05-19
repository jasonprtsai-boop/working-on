from typing import Dict, Any
from backend.events.event_model import Event
from backend.events.event_domains import Domains
from backend.events.event_types import GameEvents, EngineEvents, VisionEvents, SystemEvents

class EventFactory:
    """[Production Architecture] Centralized Factory for all System Events."""

    @staticmethod
    def vision_detect(fen: str, confidence: float, latency: float) -> Event:
        return Event(
            domain=Domains.VISION,
            event_type=VisionEvents.FRAME_PROCESSED.value,
            source="vision",
            payload={"fen": fen, "confidence": confidence, "latency": latency}
        )

    @staticmethod
    def ai_result(move: str, score: float, depth: int, latency: float) -> Event:
        return Event(
            domain=Domains.ENGINE,
            event_type=EngineEvents.ANALYSIS_COMPLETED.value,
            source="ai",
            payload={"move": move, "score": score, "depth": depth, "latency": latency}
        )

    @staticmethod
    def game_move(move: str, fen: str, player: str) -> Event:
        return Event(
            domain=Domains.GAME,
            event_type=GameEvents.MOVE_APPLIED.value,
            source="internal",
            payload={"move": move, "fen": fen, "player": player}
        )

    @staticmethod
    def state_updated(state: Dict[str, Any]) -> Event:
        return Event(
            domain=Domains.SYSTEM,
            event_type=SystemEvents.STATE_SYNCHRONIZED.value,
            source="internal",
            payload=state
        )
