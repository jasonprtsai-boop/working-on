import dataclasses
from backend.state.store.models.system_state import SystemState
from backend.state.store.models.game_state import CoreGameState
from backend.events.models.base_event import BaseEvent
from backend.utils.fen.parser import fen_to_board # Assuming this exists
from backend.utils.logger import logger

class MoveReducer:
    """
    [State Layer] Pure functional reducer for game move events.
    Transforms the current state into a new state based on vision or engine events.
    """

    @staticmethod
    def reduce(state: SystemState, event: BaseEvent) -> SystemState:
        payload = event.payload
        move = payload.get("move")
        new_fen = payload.get("fen", state.game.fen)

        # 1. Update Board Matrix from FEN if provided
        new_board = state.game.board
        if "fen" in payload:
            try:
                # Synchronize the 10x9 board array with the FEN string
                new_board = fen_to_board(new_fen)
            except Exception as e:
                logger.warning(f"[MoveReducer] FEN parsing failed: {e}")

        # 2. Chinese Chess Notation (Optional)
        notation_str = None
        if move:
            try:
                from backend.core.notation import move_to_chinese
                notation_str = move_to_chinese(move, state.game.fen, state.game.current_turn == "w")
            except Exception:
                notation_str = None

        # 3. Construct New Immutable Game State
        next_turn = "b" if state.game.current_turn == "w" else "w"
        new_game = CoreGameState(
            board=new_board,
            fen=new_fen,
            move_history=state.game.move_history + [move] if move else state.game.move_history,
            current_turn=next_turn if move else state.game.current_turn,
            game_phase=state.game.game_phase,
            game_status="STABLE",
            last_notation={
                "move": move,
                "chinese": notation_str,
                "step": len(state.game.move_history) + 1
            } if move else state.game.last_notation
        )

        # 4. Return new root state
        return dataclasses.replace(state, game=new_game, trace_id=event.trace_id)
