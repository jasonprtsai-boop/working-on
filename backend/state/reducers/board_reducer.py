from datetime import datetime
import uuid
from backend.state.store.legacy_models import GameState, BoardState

class BoardReducer:
    """
    [Pure Function] Handles board-related state transitions.
    Rule: Never mutate existing state. Always return a new GameState instance.
    """
    @staticmethod
    def apply_move(state: GameState, move: str, next_fen: str) -> GameState:
        old_board = state.board

        new_board = BoardState(
            fen=next_fen,
            turn=("black" if old_board.turn == "red" else "red"),
            move_number=old_board.move_number + 1,
            pieces=old_board.pieces,
            move_history=old_board.move_history + (move,),
        )

        new_state = GameState(
            snapshot_id=str(uuid.uuid4()),
            version=state.version + 1,
            board=new_board,
            vision=state.vision,
            robot=state.robot,
            engine=state.engine,
            created_at=datetime.utcnow(),
            state_hash="",
        )

        return new_state.with_hash()
