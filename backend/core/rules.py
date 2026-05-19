import re
from typing import Optional

from backend.utils.logger import logger


class ChessLogic:
    @staticmethod
    def validate_move(fen: str, move_str: str) -> bool:
        """Validate basic UCCI coordinate format and board bounds."""
        if not move_str or not re.match(r"^[a-i][0-9][a-i][0-9]$", move_str):
            logger.error(f"Invalid move format: {move_str}")
            return False

        return ChessLogic.is_in_board(move_str)

    @staticmethod
    def is_in_board(move_str: str) -> bool:
        if not move_str or len(move_str) < 4:
            return False
        return (
            move_str[0] in "abcdefghi"
            and move_str[2] in "abcdefghi"
            and move_str[1] in "0123456789"
            and move_str[3] in "0123456789"
        )

    @staticmethod
    def parse_move(fen: str, move_str: str) -> Optional[dict]:
        """Convert a UCCI move like h2e2 into a small move dictionary."""
        if not ChessLogic.validate_move(fen, move_str):
            return None

        try:
            board = ChessLogic._fen_to_board(fen)
            col_map = {c: i for i, c in enumerate("abcdefghi")}
            c1, r1 = col_map[move_str[0]], 9 - int(move_str[1])
            piece = board[r1][c1]
            return {
                "from": move_str[:2],
                "to": move_str[2:],
                "piece": piece,
            }
        except Exception as e:
            logger.error(f"parse_move failed: {e}")
            return None

    @staticmethod
    def apply_move(fen: str, move_str: str) -> str:
        """Apply a UCCI move to a Xiangqi FEN using basic board mutation."""
        if not ChessLogic.validate_move(fen, move_str):
            return fen

        try:
            parts = fen.split()
            board = ChessLogic._fen_to_board(fen)

            col_map = {c: i for i, c in enumerate("abcdefghi")}
            c1, r1 = col_map[move_str[0]], 9 - int(move_str[1])
            c2, r2 = col_map[move_str[2]], 9 - int(move_str[3])

            piece = board[r1][c1]
            board[r1][c1] = "."
            board[r2][c2] = piece

            parts[0] = "/".join(ChessLogic._board_to_fen_rows(board))
            if len(parts) > 1:
                parts[1] = "b" if parts[1] == "w" else "w"
            return " ".join(parts)
        except Exception as e:
            logger.error(f"apply_move failed: {e}")
            return fen

    @staticmethod
    def _fen_to_board(fen: str) -> list[list[str]]:
        rows = fen.split()[0].split("/")
        board = []
        for row in rows:
            full_row = []
            for char in row:
                if char.isdigit():
                    full_row.extend(["."] * int(char))
                else:
                    full_row.append(char)
            board.append(full_row)
        return board

    @staticmethod
    def _board_to_fen_rows(board: list[list[str]]) -> list[str]:
        new_rows = []
        for row in board:
            fen_row = ""
            empty_count = 0
            for cell in row:
                if cell == ".":
                    empty_count += 1
                else:
                    if empty_count > 0:
                        fen_row += str(empty_count)
                        empty_count = 0
                    fen_row += cell
            if empty_count > 0:
                fen_row += str(empty_count)
            new_rows.append(fen_row)
        return new_rows


chess_logic = ChessLogic()
