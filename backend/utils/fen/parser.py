from __future__ import annotations

from typing import Iterable, List, Mapping, Optional


ROWS = 10
COLS = 9
LEGAL_PIECES = set("KABRNCPkabrcnp")


class FENValidationError(ValueError):
    """Raised when a Xiangqi FEN payload is structurally invalid."""


def fen_to_board(fen: str, *, empty=None) -> List[List[Optional[str]]]:
    """Convert a Xiangqi FEN into a strict 10x9 row-major board array."""
    board_part, _turn = _split_fen(fen)
    rows = board_part.split("/")
    if len(rows) != ROWS:
        raise FENValidationError(f"FEN must contain {ROWS} rows")

    board = []
    for row_index, row in enumerate(rows):
        board_row = []
        for char in row:
            if char.isdigit():
                count = int(char)
                if count <= 0 or count > COLS:
                    raise FENValidationError(f"Invalid empty count in row {row_index + 1}")
                board_row.extend([empty] * count)
            elif char in LEGAL_PIECES:
                board_row.append(char)
            else:
                raise FENValidationError(f"Invalid FEN piece: {char!r}")
        if len(board_row) != COLS:
            raise FENValidationError(f"FEN row {row_index + 1} must contain {COLS} files")
        board.append(board_row)
    return board


def board_to_fen(board: Iterable[Iterable[Optional[str]]] | Mapping[str, Optional[str]], turn: str = "w") -> str:
    """Convert a strict 10x9 board array into a Xiangqi FEN."""
    rows = _coerce_board_rows(board)
    if len(rows) != ROWS:
        raise FENValidationError(f"board must contain {ROWS} rows")

    fen_rows = []
    for row_index, row in enumerate(rows):
        if len(row) != COLS:
            raise FENValidationError(f"board row {row_index + 1} must contain {COLS} files")
        empty_count = 0
        fen_row = ""
        for cell in row:
            if cell in (None, "", "."):
                empty_count += 1
                continue
            piece = str(cell)
            if piece not in LEGAL_PIECES:
                raise FENValidationError(f"Invalid board piece: {piece!r}")
            if empty_count:
                fen_row += str(empty_count)
                empty_count = 0
            fen_row += piece
        if empty_count:
            fen_row += str(empty_count)
        fen_rows.append(fen_row)

    side = normalize_turn(turn)
    return "/".join(fen_rows) + f" {side} - - 0 1"


def validate_fen(fen: str) -> bool:
    try:
        _board_part, turn = _split_fen(fen)
        fen_to_board(fen)
        normalize_turn(turn)
        return True
    except Exception:
        return False


def normalize_turn(turn: str) -> str:
    text = str(turn or "w").strip().lower()
    if text in {"w", "red", "white", "r"}:
        return "w"
    if text in {"b", "black"}:
        return "b"
    raise FENValidationError("FEN side-to-move must be w or b")


def _split_fen(fen: str):
    if not isinstance(fen, str) or not fen.strip():
        raise FENValidationError("FEN must be a non-empty string")
    parts = fen.strip().split()
    if not parts:
        raise FENValidationError("FEN must be a non-empty string")
    board_part = parts[0]
    turn = parts[1] if len(parts) > 1 else "w"
    return board_part, turn


def _coerce_board_rows(board) -> List[List[Optional[str]]]:
    if isinstance(board, Mapping):
        rows = [[None for _col in range(COLS)] for _row in range(ROWS)]
        for key, piece in board.items():
            if piece in (None, "", "."):
                continue
            if not isinstance(key, str) or "," not in key:
                raise FENValidationError(f"Invalid board mapping key: {key!r}")
            first, second = key.split(",", 1)
            try:
                col = int(first)
                row = int(second)
            except Exception as exc:
                raise FENValidationError(f"Invalid board mapping key: {key!r}") from exc
            if row < 0 or row >= ROWS or col < 0 or col >= COLS:
                raise FENValidationError(f"Board mapping key out of range: {key!r}")
            rows[row][col] = piece
        return rows
    return [list(row) for row in board]
