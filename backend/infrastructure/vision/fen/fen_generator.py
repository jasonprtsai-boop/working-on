from typing import Dict, List, Optional

from backend.infrastructure.vision.board.board_mapper import BoardMapper

_TURN_ALIASES = {
    "w": "w",
    "white": "w",
    "red": "w",
    "r": "w",
    "b": "b",
    "black": "b",
}


def normalize_fen_turn(turn, default: str = "w") -> str:
    text = str(turn or "").strip().lower()
    return _TURN_ALIASES.get(text, default)


class FENGenerator:
    """
    Converts a validated board state (Dict[str, str]) to a standard FEN string.
    Supports Xiangqi (10x9) or Shogi (9x9) based on configuration.
    """
    def __init__(self, rows: int = 10, cols: int = 9):
        self.rows = rows
        self.cols = cols

    def generate(self, board_state: Dict[str, str], turn: str = 'w') -> str:
        """
        board_state: {"col,row": "piece_char", ...}
        """
        rows_str = []
        for r in range(self.rows):
            row_pieces = []
            empty_count = 0
            for c in range(self.cols):
                key = f"{c},{r}"
                piece = board_state.get(key)
                if piece:
                    if empty_count > 0:
                        row_pieces.append(str(empty_count))
                        empty_count = 0
                    row_pieces.append(piece)
                else:
                    empty_count += 1

            if empty_count > 0:
                row_pieces.append(str(empty_count))

            rows_str.append("".join(row_pieces))

        fen_body = "/".join(rows_str)
        side_to_move = normalize_fen_turn(turn)
        return f"{fen_body} {side_to_move} - - 0 1"


class DetectionFENGenerator:
    """Maps detector outputs into board cells, then renders a FEN string."""

    def __init__(self, mapper: BoardMapper, fen_generator: FENGenerator):
        self.mapper = mapper
        self.fen_generator = fen_generator

    def generate(self, detections: List, turn: str = "w") -> Optional[str]:
        board_state = self.mapper.map_detections(detections)
        if not board_state:
            return None
        return self.fen_generator.generate(board_state, turn=turn)
