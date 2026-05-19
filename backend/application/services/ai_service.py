from backend.utils.logger import logger


class AiService:
    """
    [Phase 2/5] AI Decision Service.
    Wraps the core EngineService with game-specific logic.
    """
    def __init__(self, engine_service=None):
        self.engine = engine_service
        self.is_enabled = True
        self.depth = 12  # Default depth

    def set_difficulty(self, value):
        try:
            self.depth = int(value)
            logger.info(f"AI Depth set to {self.depth}")
        except (TypeError, ValueError):
            logger.error(f"Invalid difficulty value: {value}")

    async def calculate_move(self, state):
        """Calculates the best move based on current state."""
        if not self.is_enabled or not self.engine:
            return None

        try:
            fen = state.get("fen", "startpos")
            if "rnbakabnr" not in fen.lower(): fen = "startpos"

            result = await self.engine.compute(fen, depth=self.depth)
            if result:
                return {
                    "move": result["best_move"],
                    "score": result["score"] / 100.0,
                    "depth": result["depth"],
                    "pv": [m["move"] for m in result["multi_pv"]] if "multi_pv" in result else []
                }
            return None
        except Exception as e:
            logger.error(f"AI Service Error: {e}", exc_info=True)
            return None
