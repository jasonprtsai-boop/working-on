from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, Iterable, Optional

from backend.core.rules import ChessLogic
from backend.infrastructure.vision.fen.fen_generator import FENGenerator, normalize_fen_turn
from backend.utils.fen.parser import COLS, LEGAL_PIECES, ROWS, fen_to_board
from backend.utils.logger import logger


FILES = "abcdefghi"


@dataclass
class BoardReconciliation:
    accepted: bool
    board_state: Dict[str, str]
    method: str
    reason: str = ""
    move: Optional[str] = None
    piece: Optional[str] = None
    source: Optional[str] = None
    target: Optional[str] = None
    is_capture: bool = False
    score: float = 0.0
    margin: float = 0.0
    candidates: int = 0
    observed_count: int = 0
    filled_count: int = 0
    conflict_count: int = 0
    changed_count: int = 0

    def to_dict(self) -> dict:
        data = asdict(self)
        data.pop("board_state", None)
        return data


class BoardReconciler:
    """
    Repairs sparse board detections by comparing them with the last stable board.

    Observed cells are treated as positive evidence only: an absent cell can be a
    missed detection, but an observed piece that disagrees with a legal candidate
    rejects that candidate.
    """

    def __init__(
        self,
        *,
        rows: int = ROWS,
        cols: int = COLS,
        min_score: float = 12.0,
        min_margin: float = 2.0,
    ):
        self.rows = int(rows)
        self.cols = int(cols)
        self.min_score = float(min_score)
        self.min_margin = float(min_margin)
        self.fen_generator = FENGenerator(rows=self.rows, cols=self.cols)

    def reconcile(
        self,
        previous_board: Dict[str, str],
        observed_board: Dict[str, str],
        *,
        turn: str = "w",
    ) -> BoardReconciliation:
        previous = self._clean_board(previous_board)
        observed = self._clean_board(observed_board)

        if not previous:
            return BoardReconciliation(
                accepted=False,
                board_state=observed,
                method="no_previous",
                reason="missing_previous_stable_board",
                observed_count=len(observed),
            )

        if observed == previous:
            return BoardReconciliation(
                accepted=True,
                board_state=previous,
                method="unchanged",
                reason="observed_board_matches_previous",
                observed_count=len(observed),
            )

        turn = normalize_fen_turn(turn)
        try:
            previous_fen = self.fen_generator.generate(previous, turn=turn)
        except Exception as exc:
            logger.debug("[BoardReconciler] previous board cannot be converted to FEN: %s", exc, exc_info=True)
            return BoardReconciliation(
                accepted=False,
                board_state=observed,
                method="invalid_previous",
                reason="previous_board_fen_failed",
                observed_count=len(observed),
            )

        scored = []
        legal_count = 0
        for move in self._legal_moves(previous, previous_fen, turn):
            legal_count += 1
            next_fen = ChessLogic.apply_move(previous_fen, move)
            if next_fen == previous_fen:
                continue
            candidate = self._board_from_fen(next_fen)
            score = self._score_candidate(previous, candidate, observed, move)
            if score is not None:
                scored.append(score)

        if not scored:
            return BoardReconciliation(
                accepted=False,
                board_state=observed,
                method="no_legal_match",
                reason="no_legal_move_matches_observed_cells",
                candidates=legal_count,
                observed_count=len(observed),
            )

        scored.sort(key=lambda item: item["score"], reverse=True)
        best = scored[0]
        second_score = scored[1]["score"] if len(scored) > 1 else 0.0
        margin = float(best["score"] - second_score)

        if best["score"] < self.min_score:
            reason = "score_below_threshold"
        elif len(scored) > 1 and margin < self.min_margin:
            reason = "ambiguous_legal_moves"
        else:
            reason = ""

        accepted = not reason
        candidate_board = best["board_state"] if accepted else observed
        return BoardReconciliation(
            accepted=accepted,
            board_state=candidate_board,
            method="legal_move_repair" if accepted else "ambiguous",
            reason=reason,
            move=best["move"] if accepted else None,
            piece=best["piece"] if accepted else None,
            source=best["source"] if accepted else None,
            target=best["target"] if accepted else None,
            is_capture=bool(best["is_capture"]) if accepted else False,
            score=round(float(best["score"]), 3),
            margin=round(margin, 3),
            candidates=legal_count,
            observed_count=len(observed),
            filled_count=self._filled_count(candidate_board, observed),
            conflict_count=int(best["conflict_count"]),
            changed_count=int(best["changed_count"]),
        )

    def _legal_moves(self, board: Dict[str, str], fen: str, turn: str) -> Iterable[str]:
        for key, piece in board.items():
            if not self._is_own_piece(piece, turn):
                continue
            from_uci = self._key_to_uci(key)
            if not from_uci:
                continue
            for row in range(self.rows):
                for col in range(self.cols):
                    target_key = self._key(col, row)
                    if target_key == key:
                        continue
                    target = board.get(target_key)
                    if target and self._is_own_piece(target, turn):
                        continue
                    move = f"{from_uci}{FILES[col]}{9 - row}"
                    if ChessLogic.validate_move(fen, move):
                        yield move

    def _score_candidate(
        self,
        previous: Dict[str, str],
        candidate: Dict[str, str],
        observed: Dict[str, str],
        move: str,
    ) -> Optional[dict]:
        conflicts = 0
        observed_matches = 0
        for key, observed_piece in observed.items():
            if candidate.get(key) == observed_piece:
                observed_matches += 1
            else:
                conflicts += 1

        if conflicts:
            return None

        source_key = self._uci_to_key(move[:2])
        target_key = self._uci_to_key(move[2:])
        if not source_key or not target_key:
            return None

        previous_piece = previous.get(source_key)
        target_piece = candidate.get(target_key)
        source_disappeared = source_key not in observed and bool(previous_piece) and candidate.get(source_key) is None
        target_confirmed = (
            target_key in observed
            and bool(target_piece)
            and observed.get(target_key) == target_piece
            and previous.get(target_key) != target_piece
        )

        if not (source_disappeared and target_confirmed):
            return None

        changed_keys = {
            key
            for key in set(previous.keys()).union(candidate.keys())
            if previous.get(key) != candidate.get(key)
        }
        score = 6.0 + 9.0 + min(float(observed_matches), 32.0) * 0.1
        unsupported = 0
        for key in changed_keys:
            if key in {source_key, target_key}:
                continue
            if key in observed and observed.get(key) == candidate.get(key):
                score += 2.0
            elif key not in observed and candidate.get(key) is None:
                score += 0.5
            else:
                unsupported += 1
                score -= 1.0

        return {
            "score": score,
            "move": move,
            "piece": previous_piece,
            "source": source_key,
            "target": target_key,
            "is_capture": bool(previous.get(target_key)),
            "board_state": candidate,
            "conflict_count": conflicts,
            "changed_count": len(changed_keys),
            "unsupported": unsupported,
        }

    def _clean_board(self, board: Dict[str, str]) -> Dict[str, str]:
        clean: Dict[str, str] = {}
        if not isinstance(board, dict):
            return clean
        for key, piece in board.items():
            parsed = self._parse_key(key)
            if parsed is None:
                continue
            text = str(piece or "").strip()
            if text not in LEGAL_PIECES:
                continue
            clean[self._key(*parsed)] = text
        return clean

    def _board_from_fen(self, fen: str) -> Dict[str, str]:
        board = fen_to_board(fen, empty=None)
        state: Dict[str, str] = {}
        for row, row_data in enumerate(board):
            for col, piece in enumerate(row_data):
                if piece:
                    state[self._key(col, row)] = piece
        return state

    def _filled_count(self, board: Dict[str, str], observed: Dict[str, str]) -> int:
        return sum(1 for key, piece in board.items() if piece and key not in observed)

    def _is_own_piece(self, piece: str, turn: str) -> bool:
        return piece.isupper() if turn == "w" else piece.islower()

    def _parse_key(self, key) -> Optional[tuple[int, int]]:
        if not isinstance(key, str) or "," not in key:
            return None
        first, second = key.split(",", 1)
        try:
            col = int(first)
            row = int(second)
        except (TypeError, ValueError):
            return None
        if 0 <= col < self.cols and 0 <= row < self.rows:
            return col, row
        return None

    def _key_to_uci(self, key: str) -> Optional[str]:
        parsed = self._parse_key(key)
        if parsed is None:
            return None
        col, row = parsed
        return f"{FILES[col]}{9 - row}"

    def _uci_to_key(self, uci: str) -> Optional[str]:
        if not isinstance(uci, str) or len(uci) != 2:
            return None
        file_char, rank_char = uci[0], uci[1]
        if file_char not in FILES or not rank_char.isdigit():
            return None
        rank = int(rank_char)
        row = 9 - rank
        col = FILES.index(file_char)
        if 0 <= col < self.cols and 0 <= row < self.rows:
            return self._key(col, row)
        return None

    def _key(self, col: int, row: int) -> str:
        return f"{int(col)},{int(row)}"
