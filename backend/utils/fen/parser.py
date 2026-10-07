from __future__ import annotations

from typing import Iterable, List, Mapping, Optional


ROWS = 10
COLS = 9
LEGAL_PIECES = set("KABRNCPkabrcnp")
RED_PIECES = set("KABRNCP")
BLACK_PIECES = set("kabrncp")
INITIAL_XIANGQI_PIECE_COUNT = 32

XIANGQI_PIECE_NAMES: dict[str, str] = {
    "K": "紅帥", "A": "紅仕", "B": "紅相", "R": "紅俥", "N": "紅傌", "C": "紅炮", "P": "紅兵",
    "k": "黑將", "a": "黑士", "b": "黑象", "r": "黑車", "n": "黑馬", "c": "黑砲", "p": "黑卒",
}

INITIAL_PIECE_COUNTS: dict[str, int] = {
    "K": 1, "A": 2, "B": 2, "R": 2, "N": 2, "C": 2, "P": 5,
    "k": 1, "a": 2, "b": 2, "r": 2, "n": 2, "c": 2, "p": 5,
}


class FENValidationError(ValueError):
    """Raised when a Xiangqi FEN payload is structurally invalid."""


def count_fen_pieces(fen: str) -> dict[str, int]:
    """Count red, black, and total pieces in a Xiangqi FEN string."""
    if not isinstance(fen, str) or not fen.strip():
        return {"total": 0, "red": 0, "black": 0}
    board_part = fen.strip().split()[0]
    red = sum(1 for c in board_part if c in RED_PIECES)
    black = sum(1 for c in board_part if c in BLACK_PIECES)
    return {"total": red + black, "red": red, "black": black}


def count_fen_piece_types(fen: str) -> dict[str, int]:
    """Count occurrences of each piece type in a Xiangqi FEN string."""
    counts = {p: 0 for p in LEGAL_PIECES}
    if not isinstance(fen, str) or not fen.strip():
        return counts
    board_part = fen.strip().split()[0]
    for char in board_part:
        if char in LEGAL_PIECES:
            counts[char] += 1
    return counts


def count_board_piece_types(board_state: Mapping[str, Optional[str]] | Iterable[Iterable[Optional[str]]]) -> dict[str, int]:
    """Count occurrences of each piece type from board_state (dict or 2D grid)."""
    counts = {p: 0 for p in LEGAL_PIECES}
    if not board_state:
        return counts
    if isinstance(board_state, Mapping):
        for piece in board_state.values():
            if piece and str(piece) in LEGAL_PIECES:
                counts[str(piece)] += 1
    else:
        for row in board_state:
            for cell in row:
                if cell and str(cell) in LEGAL_PIECES:
                    counts[str(cell)] += 1
    return counts


def validate_piece_count(actual_count: int, expected_count: int, *, allow_capture: bool = True) -> tuple[bool, str]:
    """
    Validates detected piece count against expected piece count.
    During a move, a capture decrements piece count by 1.
    """
    actual = int(actual_count)
    expected = max(1, int(expected_count))
    if actual == expected:
        return True, "count_match"
    if allow_capture and actual == expected - 1:
        return True, "capture_decremented"
    if actual < (expected - 1 if allow_capture else expected):
        diff = (expected - 1 if allow_capture else expected) - actual
        return False, f"missing_pieces_{diff}"
    diff = actual - expected
    return False, f"extra_pieces_{diff}"


def validate_piece_types(
    actual_counts: dict[str, int],
    expected_counts: dict[str, int] | None = None,
    *,
    moving_side: str = "w",
    allow_capture: bool = True,
) -> dict:
    """
    Validates detected piece counts for EACH individual piece type against expectations.
    Checks whether piece counts per type correspond to the pieces on the board.
    Supports normal moves and capture moves under Xiangqi rules.
    """
    exp_counts = dict(expected_counts or INITIAL_PIECE_COUNTS)
    for p in LEGAL_PIECES:
        exp_counts.setdefault(p, 0)
    act_counts = dict(actual_counts or {})
    for p in LEGAL_PIECES:
        act_counts.setdefault(p, 0)

    actual_total = sum(act_counts[p] for p in LEGAL_PIECES)
    expected_total = sum(exp_counts[p] for p in LEGAL_PIECES)
    actual_red = sum(act_counts[p] for p in RED_PIECES)
    actual_black = sum(act_counts[p] for p in BLACK_PIECES)
    expected_red = sum(exp_counts[p] for p in RED_PIECES)
    expected_black = sum(exp_counts[p] for p in BLACK_PIECES)

    side = "w" if str(moving_side or "w").strip().lower() in {"w", "red", "white", "r"} else "b"
    mover_pieces = RED_PIECES if side == "w" else BLACK_PIECES
    opponent_pieces = BLACK_PIECES if side == "w" else RED_PIECES

    by_type: dict[str, dict] = {}
    mismatches: list[dict] = []
    diffs: dict[str, int] = {}

    for p in sorted(LEGAL_PIECES):
        act = act_counts[p]
        exp = exp_counts[p]
        diff = act - exp
        diffs[p] = diff
        status = "match" if diff == 0 else ("extra" if diff > 0 else "missing")
        by_type[p] = {
            "piece": p,
            "name": XIANGQI_PIECE_NAMES.get(p, p),
            "actual": act,
            "expected": exp,
            "diff": diff,
            "status": status,
        }
        if diff != 0:
            mismatches.append({
                "piece": p,
                "name": XIANGQI_PIECE_NAMES.get(p, p),
                "actual": act,
                "expected": exp,
                "diff": diff,
                "issue": status,
            })

    # Case 1: Exact match on every single piece type
    if len(mismatches) == 0:
        return {
            "valid": True,
            "status": "count_match",
            "total": actual_total,
            "expected": expected_total,
            "red": actual_red,
            "black": actual_black,
            "expected_red": expected_red,
            "expected_black": expected_black,
            "difference": 0,
            "by_type": by_type,
            "mismatches": [],
            "captured_piece": None,
            "summary_message": f"棋子種類與數量完全吻合：場上共 {actual_total} 顆（紅 {actual_red} / 黑 {actual_black}）。",
        }

    # Case 2: Check if this is a legal capture move
    # Mover cannot lose pieces on own turn. Exactly ONE opponent piece type decremented by 1.
    mover_diffs = {p: diffs[p] for p in mover_pieces}
    opp_diffs = {p: diffs[p] for p in opponent_pieces}

    is_legal_capture = False
    captured_piece = None

    if allow_capture:
        mover_ok = all(d == 0 for d in mover_diffs.values())
        opp_decrements = [p for p, d in opp_diffs.items() if d == -1]
        opp_others_ok = all(d == 0 for p, d in opp_diffs.items() if p not in opp_decrements)
        if mover_ok and len(opp_decrements) == 1 and opp_others_ok:
            is_legal_capture = True
            captured_piece = opp_decrements[0]

    if is_legal_capture and captured_piece:
        cap_name = XIANGQI_PIECE_NAMES.get(captured_piece, captured_piece)
        return {
            "valid": True,
            "status": "capture_decremented",
            "total": actual_total,
            "expected": expected_total,
            "red": actual_red,
            "black": actual_black,
            "expected_red": expected_red,
            "expected_black": expected_black,
            "difference": -1,
            "by_type": by_type,
            "mismatches": mismatches,
            "captured_piece": captured_piece,
            "summary_message": f"吃子正常：吃掉 {cap_name}，場上剩餘 {actual_total} 顆棋子，其餘種類完全吻合。",
        }

    # Case 3: Invalid / Mismatch
    mismatch_strs = []
    for m in mismatches:
        diff_val = m["diff"]
        d_str = f"多 {diff_val} 顆" if diff_val > 0 else f"少 {-diff_val} 顆"
        mismatch_strs.append(f"{m['name']}{d_str} (目前 {m['actual']}/預期 {m['expected']})")

    summary_msg = f"棋子種類數量不符（場上 {actual_total} 顆，預期 {expected_total} 顆）：" + "、".join(mismatch_strs)
    diff_total = actual_total - expected_total
    status_label = "missing_pieces" if diff_total < 0 else ("extra_pieces" if diff_total > 0 else "piece_type_mismatch")

    return {
        "valid": False,
        "status": status_label,
        "total": actual_total,
        "expected": expected_total,
        "red": actual_red,
        "black": actual_black,
        "expected_red": expected_red,
        "expected_black": expected_black,
        "difference": diff_total,
        "by_type": by_type,
        "mismatches": mismatches,
        "captured_piece": None,
        "summary_message": summary_msg,
    }


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
        board = fen_to_board(fen)
        normalize_turn(turn)

        from collections import Counter
        counts = Counter()
        for row in board:
            for piece in row:
                if piece:
                    counts[piece] += 1

        # 1. 將帥必須存在且只有一個
        if counts["K"] != 1 or counts["k"] != 1:
            return False

        # 3. 數量合理性
        max_counts = {
            "A": 2, "B": 2, "R": 2, "N": 2, "C": 2, "P": 5,
            "a": 2, "b": 2, "r": 2, "n": 2, "c": 2, "p": 5,
            "K": 1, "k": 1
        }
        for piece, count in counts.items():
            if count > max_counts.get(piece, 0):
                return False

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
