"""
Coordinate conversion authority for board, engine, and robot spaces.

Canonical internal board coordinates are (row, col), with row 0 at the top
black side and col 0 at file "a". UCCI squares use file/rank such as "a0".
"""

from __future__ import annotations

from typing import Optional, Tuple

from backend.utils.fen.parser import board_to_fen, fen_to_board
from backend.utils.kinematics import kinematics


class CoordinateSystem:
    files = "abcdefghi"
    rows = 10
    cols = 9
    _square_lookup = {
        f"{file_char}{rank}": (col, rank)
        for col, file_char in enumerate("abcdefghi")
        for rank in range(10)
    }
    _internal_lookup = {
        (row, col): f"{'abcdefghi'[col]}{9 - row}"
        for row in range(10)
        for col in range(9)
    }

    def __init__(self, robot_kinematics=None):
        self.kinematics = robot_kinematics or kinematics

    def is_valid_square(self, square: str) -> bool:
        return self._square_indices(square) is not None

    def is_valid_move(self, move: str) -> bool:
        return (
            isinstance(move, str)
            and len(move) == 4
            and self.is_valid_square(move[:2])
            and self.is_valid_square(move[2:])
        )

    def uci_to_internal(self, uci: str) -> Optional[Tuple[int, int]]:
        """UCCI square, e.g. 'a0', -> internal (row, col)."""
        indices = self._square_indices(uci)
        if indices is None:
            return None
        col, rank = indices
        return 9 - rank, col

    def internal_to_uci(self, row: int, col: int) -> Optional[str]:
        """Internal (row, col) -> UCCI square, e.g. 'a0'."""
        try:
            row_idx = int(row)
            col_idx = int(col)
        except Exception:
            return None
        if row_idx < 0 or row_idx >= self.rows or col_idx < 0 or col_idx >= self.cols:
            return None
        return self._internal_lookup.get((row_idx, col_idx))

    def move_to_internal(self, move_uci: str) -> Optional[Tuple[Tuple[int, int], Tuple[int, int]]]:
        if not self.is_valid_move(move_uci):
            return None
        return self.uci_to_internal(move_uci[:2]), self.uci_to_internal(move_uci[2:])

    def internal_to_move(self, start_row: int, start_col: int, end_row: int, end_col: int) -> Optional[str]:
        start = self.internal_to_uci(start_row, start_col)
        end = self.internal_to_uci(end_row, end_col)
        if start is None or end is None:
            return None
        return f"{start}{end}"

    def engine_to_grid(self, move_uci: str):
        """Legacy alias for UCCI square -> internal coordinates."""
        return self.uci_to_internal(move_uci)

    def grid_to_uci(self, row: int, col: int):
        """Legacy alias for internal coordinates -> UCCI square."""
        return self.internal_to_uci(row, col)

    def uci_to_world(self, square: str) -> Optional[Tuple[float, float]]:
        """UCCI square -> robot XY."""
        if not self.is_valid_square(square):
            return None
        return self.kinematics.square_to_robot(square)

    def internal_to_world(self, row: int, col: int) -> Optional[Tuple[float, float]]:
        """Internal (row, col) -> robot XY."""
        return self.kinematics.internal_to_robot(row, col)

    def grid_to_world(self, row: int, col: int):
        """Legacy alias for internal coordinates -> robot XY."""
        return self.internal_to_world(row, col)

    def world_to_internal(self, x: float, y: float) -> Optional[Tuple[int, int]]:
        """Robot XY -> nearest internal (row, col)."""
        return self.kinematics.robot_to_internal(x, y)

    def world_to_uci(self, x: float, y: float) -> Optional[str]:
        """Robot XY -> nearest UCCI square."""
        return self.kinematics.robot_to_square(x, y)

    def _square_indices(self, square: str) -> Optional[Tuple[int, int]]:
        if not isinstance(square, str) or len(square) != 2:
            return None
        return self._square_lookup.get(square.lower())
