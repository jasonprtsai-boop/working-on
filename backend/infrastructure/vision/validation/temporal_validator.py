from collections import Counter, deque
from typing import Dict, Optional
import logging

from backend.infrastructure.vision.validation.board_reconciler import BoardReconciler
from backend.utils.fen.parser import COLS, LEGAL_PIECES, ROWS

logger = logging.getLogger(__name__)

class TemporalValidator:
    """
    Stabilizes board detections across frames.

    The first stable board still requires identical consecutive frames. Once a
    stable baseline exists, sparse frames are fused and reconciled against legal
    Xiangqi moves so missed pieces can be filled from the previous board.
    """
    def __init__(
        self,
        window_size: int = 3,
        *,
        fusion_min_votes: Optional[int] = None,
        reconcile_enabled: Optional[bool] = None,
    ):
        self.window_size = max(1, int(window_size))
        self.history = deque(maxlen=self.window_size)
        self.last_stable_state: Optional[Dict[str, str]] = None
        self.last_reconciliation: Dict[str, object] = {}
        self.last_confidence = 0.0

        try:
            from backend.utils import config

            default_fusion_votes = getattr(config, "VISION_BOARD_FUSION_MIN_VOTES", 1)
            default_enabled = bool(getattr(config, "VISION_BOARD_RECONCILE_ENABLED", True))
            min_score = float(getattr(config, "VISION_BOARD_RECONCILE_MIN_SCORE", 12.0))
            min_margin = float(getattr(config, "VISION_BOARD_RECONCILE_MIN_MARGIN", 2.0))
        except Exception:
            default_fusion_votes = 1
            default_enabled = True
            min_score = 12.0
            min_margin = 2.0

        self.fusion_min_votes = max(1, int(fusion_min_votes or default_fusion_votes))
        self.reconcile_enabled = default_enabled if reconcile_enabled is None else bool(reconcile_enabled)
        self.reconciler = BoardReconciler(
            rows=ROWS,
            cols=COLS,
            min_score=min_score,
            min_margin=min_margin,
        )

    def validate(self, current_state: Dict[str, str], turn: str = "w") -> Optional[Dict[str, str]]:
        """
        Returns the stable state if consensus is reached, else None.
        """
        current_state = self._clean_state(current_state)
        self.history.append(current_state)
        self.last_reconciliation = {
            "accepted": False,
            "method": "collecting",
            "reason": "waiting_for_stability_window",
            "frames": len(self.history),
            "window_size": self.window_size,
        }

        if len(self.history) < self.window_size:
            return None

        exact_state = self._exact_consensus()
        fused_state, fusion = self._fuse_history()

        if self.last_stable_state is None:
            if exact_state is None:
                self.last_reconciliation.update({
                    "method": "initial_consensus",
                    "reason": "initial_board_requires_identical_frames",
                    "fusion": fusion,
                })
                return None
            return self._commit(
                exact_state,
                {
                    "accepted": True,
                    "method": "initial_consensus",
                    "reason": "first_stable_board",
                    "fusion": fusion,
                },
            )

        if self.reconcile_enabled:
            reconciliation = self.reconciler.reconcile(self.last_stable_state, fused_state, turn=turn)
            report = reconciliation.to_dict()
            report["fusion"] = fusion
            self.last_reconciliation = report
            if reconciliation.accepted and reconciliation.board_state != self.last_stable_state:
                self._warn_if_large_diff(reconciliation.board_state)
                return self._commit(reconciliation.board_state, report)

        if exact_state is not None and exact_state != self.last_stable_state:
            if self.reconcile_enabled:
                return None
            self._warn_if_large_diff(exact_state)
            return self._commit(
                exact_state,
                {
                    "accepted": True,
                    "method": "exact_consensus",
                    "reason": "all_frames_match",
                    "fusion": fusion,
                },
            )

        return None

    def reset(self):
        self.history.clear()
        self.last_stable_state = None
        self.last_reconciliation = {}
        self.last_confidence = 0.0

    def _commit(self, state: Dict[str, str], reconciliation: Dict[str, object]) -> Dict[str, str]:
        stable = dict(state)
        self.last_stable_state = stable
        self.last_reconciliation = dict(reconciliation)
        self.last_confidence = 0.95 if reconciliation.get("accepted") else 0.0
        return stable

    def _exact_consensus(self) -> Optional[Dict[str, str]]:
        first = self.history[0]
        for item in list(self.history)[1:]:
            if item != first:
                return None
        return dict(first)

    def _fuse_history(self) -> tuple[Dict[str, str], dict]:
        votes: Dict[str, Counter] = {}
        for state in self.history:
            for key, piece in state.items():
                votes.setdefault(key, Counter())[piece] += 1

        required_votes = min(self.fusion_min_votes, len(self.history))
        fused: Dict[str, str] = {}
        conflict_cells = []
        for key, counter in votes.items():
            common = counter.most_common()
            if not common:
                continue
            piece, count = common[0]
            if count < required_votes:
                continue
            if len(common) > 1 and common[1][1] == count:
                conflict_cells.append(key)
                continue
            fused[key] = piece

        return fused, {
            "frames": len(self.history),
            "window_size": self.window_size,
            "min_votes": required_votes,
            "observed_cells": len(fused),
            "conflict_cells": conflict_cells[:10],
            "conflict_count": len(conflict_cells),
        }

    def _clean_state(self, state: Dict[str, str]) -> Dict[str, str]:
        clean: Dict[str, str] = {}
        if not isinstance(state, dict):
            return clean
        for key, piece in state.items():
            parsed = self._parse_key(key)
            text = str(piece or "").strip()
            if parsed is None or text not in LEGAL_PIECES:
                continue
            col, row = parsed
            clean[f"{col},{row}"] = text
        return clean

    def _parse_key(self, key) -> Optional[tuple[int, int]]:
        if not isinstance(key, str) or "," not in key:
            return None
        first, second = key.split(",", 1)
        try:
            col = int(first)
            row = int(second)
        except (TypeError, ValueError):
            return None
        if 0 <= col < COLS and 0 <= row < ROWS:
            return col, row
        return None

    def _warn_if_large_diff(self, state: Dict[str, str]):
        if self.last_stable_state is None:
            return
        diff_count = 0
        all_keys = set(state.keys()).union(set(self.last_stable_state.keys()))
        for key in all_keys:
            if state.get(key) != self.last_stable_state.get(key):
                diff_count += 1

        if diff_count > 6:
            logger.warning(
                "Board state differs too much from previous stable frame: %s pieces changed.",
                diff_count,
            )
