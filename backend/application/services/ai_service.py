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
            if fen != "startpos":
                try:
                    from backend.utils.fen.parser import validate_fen

                    if not validate_fen(fen):
                        logger.warning("AI received invalid FEN; falling back to startpos.")
                        fen = "startpos"
                except Exception:
                    logger.warning("AI FEN validation failed; falling back to startpos.", exc_info=True)
                    fen = "startpos"

            result = await self.engine.compute(fen, depth=self.depth)
            if result:
                best_move = result["best_move"]
                
                # Validation: 確保 AI move 能夠轉成實體座標
                if best_move and best_move != "none":
                    try:
                        from backend.utils.kinematics import kinematics
                        if len(best_move) >= 4:
                            src, dst = best_move[:2], best_move[2:4]
                            if kinematics.square_to_robot(src) is None or kinematics.square_to_robot(dst) is None:
                                logger.warning(f"AI returned invalid coordinate move: {best_move}")
                                return None
                    except Exception as e:
                        logger.error(f"Error validating AI move coords: {e}", exc_info=True)

                return {
                    "move": best_move,
                    "score": result["score"] / 100.0,
                    "depth": result["depth"],
                    "pv": [m["move"] for m in result["multi_pv"]] if "multi_pv" in result else []
                }
            return None
        except Exception as e:
            logger.error(f"AI Service Error: {e}", exc_info=True)
            return None
