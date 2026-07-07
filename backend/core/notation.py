from __future__ import annotations

from backend.core.coordinate_system import CoordinateSystem
from backend.utils.fen.parser import fen_to_board


_NUM = [
    "\u96f6",
    "\u4e00",
    "\u4e8c",
    "\u4e09",
    "\u56db",
    "\u4e94",
    "\u516d",
    "\u4e03",
    "\u516b",
    "\u4e5d",
]
_PIECE_NAMES = {
    "K": "\u5e25",
    "A": "\u4ed5",
    "B": "\u76f8",
    "N": "\u99ac",
    "R": "\u8eca",
    "C": "\u70ae",
    "P": "\u5175",
    "k": "\u5c07",
    "a": "\u58eb",
    "b": "\u8c61",
    "n": "\u99ac",
    "r": "\u8eca",
    "c": "\u7832",
    "p": "\u5352",
}
_STRAIGHT_PIECES = set("KkRrCcPp")
_FRONT = "\u524d"
_BACK = "\u5f8c"
_HORIZONTAL = "\u5e73"
_ADVANCE = "\u9032"
_RETREAT = "\u9000"


def move_to_chinese(move_str: str, fen: str, is_red: bool) -> str:
    """
    Convert a UCCI move into stable Xiangqi-style Chinese notation.

    Covers file numbering from each side's perspective, advance/retreat/flat
    actions, and front/back disambiguation when identical pieces share a file.
    """
    coord = CoordinateSystem()
    internal = coord.move_to_internal(move_str)
    if internal is None:
        return str(move_str)

    (from_row, from_col), (to_row, to_col) = internal
    try:
        board = fen_to_board(fen)
        piece = board[from_row][from_col]
    except Exception:
        board = None
        piece = None

    red_side = _is_red_piece(piece) if piece else bool(is_red)
    piece_name = _PIECE_NAMES.get(piece, "\u5b50")
    source = _source_label(board, piece, from_row, from_col, red_side)
    action = _action_label(from_row, to_row, from_col, to_col, red_side)
    target = _target_label(piece, from_row, to_row, from_col, to_col, red_side, action)
    return f"{piece_name}{source}{action}{target}"


def _is_red_piece(piece: str) -> bool:
    return str(piece).isupper()


def _side_file_number(col: int, red_side: bool) -> int:
    return 9 - int(col) if red_side else int(col) + 1


def _cn_number(value: int) -> str:
    if 0 <= int(value) < len(_NUM):
        return _NUM[int(value)]
    return str(value)


def _source_label(board, piece, row: int, col: int, red_side: bool) -> str:
    if not board or not piece:
        return _cn_number(_side_file_number(col, red_side))

    same_file = []
    for candidate_row, board_row in enumerate(board):
        if 0 <= col < len(board_row) and board_row[col] == piece:
            same_file.append(candidate_row)

    if len(same_file) < 2:
        return _cn_number(_side_file_number(col, red_side))

    front_row = min(same_file) if red_side else max(same_file)
    back_row = max(same_file) if red_side else min(same_file)
    if row == front_row:
        return _FRONT
    if row == back_row:
        return _BACK
    return _cn_number(_side_file_number(col, red_side))


def _action_label(from_row: int, to_row: int, from_col: int, to_col: int, red_side: bool) -> str:
    if from_row == to_row:
        return _HORIZONTAL
    advancing = to_row < from_row if red_side else to_row > from_row
    return _ADVANCE if advancing else _RETREAT


def _target_label(piece, from_row: int, to_row: int, from_col: int, to_col: int, red_side: bool, action: str) -> str:
    if action == _HORIZONTAL:
        return _cn_number(_side_file_number(to_col, red_side))
    if piece in _STRAIGHT_PIECES and from_col == to_col:
        return _cn_number(abs(int(to_row) - int(from_row)))
    return _cn_number(_side_file_number(to_col, red_side))
