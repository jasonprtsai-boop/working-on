import re
from typing import Dict, List, Optional

from backend.infrastructure.vision.detection.detection_result import Detection
from backend.utils.logger import logger
from .coordinate_system import BoardCoordinateSystem


_COLOR_ALIASES = {
    "red": "red",
    "r": "red",
    "hong": "red",
    "white": "red",
    "w": "red",
    "black": "black",
    "b": "black",
    "hei": "black",
}

_PIECE_ALIASES = {
    "king": "K",
    "general": "K",
    "jiang": "K",
    "shuai": "K",
    "rook": "R",
    "chariot": "R",
    "car": "R",
    "ju": "R",
    "che": "R",
    "horse": "N",
    "knight": "N",
    "ma": "N",
    "elephant": "B",
    "bishop": "B",
    "minister": "B",
    "xiang": "B",
    "advisor": "A",
    "adviser": "A",
    "guard": "A",
    "shi": "A",
    "cannon": "C",
    "canon": "C",
    "pao": "C",
    "soldier": "P",
    "pawn": "P",
    "bing": "P",
    "zu": "P",
}

_CHINESE_LABEL_MAP = {
    "紅色-帥": "K",
    "紅色-仕": "A",
    "紅色-士": "A",
    "紅色-相": "B",
    "紅色-車": "R",
    "紅色-馬": "N",
    "紅色-砲": "C",
    "紅色-炮": "C",
    "紅色-兵": "P",
    "黑色-將": "k",
    "黑色-士": "a",
    "黑色-仕": "a",
    "黑色-象": "b",
    "黑色-車": "r",
    "黑色-馬": "n",
    "黑色-砲": "c",
    "黑色-炮": "c",
    "黑色-包": "c",
    "黑色-卒": "p",
}

_DIRECT_CODES = set("RNBAKCPrnbakcp")


class BoardMapper:
    """
    Translates raw detections into board state (pieces in cells).
    """

    def __init__(self, coord_system: BoardCoordinateSystem = None):
        self.coord_system = coord_system or BoardCoordinateSystem()
        self._unknown_labels = set()

    def map_detections(self, detections: List[Detection]) -> Dict[str, str]:
        """
        Maps detections to a board dictionary: {"col,row": "piece_char", ...}.
        Unknown class labels are skipped so they cannot poison downstream FEN.
        """
        board_state: Dict[str, str] = {}
        board_conf: Dict[str, float] = {}

        for det in detections:
            piece_code = self._map_class_to_piece(det.class_name)
            if not piece_code:
                self._warn_unknown_label(det.class_name)
                continue

            cx, cy = det.bbox.center
            cell = self.coord_system.pixel_to_cell(cx, cy)
            if cell is None:
                logger.debug(
                    "[BoardMapper] Detection skipped because center is not near a board intersection: %s",
                    det.class_name,
                )
                continue

            col, row = cell
            key = f"{col},{row}"

            # Conflict resolution: keep highest-confidence detection for a cell.
            if key in board_state:
                prev = board_conf.get(key, -1.0)
                if det.confidence <= prev:
                    continue

            board_state[key] = piece_code
            board_conf[key] = float(det.confidence)

        return board_state

    def _map_class_to_piece(self, class_name: str) -> Optional[str]:
        """Maps YOLO/SAHI class names to Xiangqi FEN piece characters."""
        if not isinstance(class_name, str):
            return None

        raw = class_name.strip()
        chinese_code = _CHINESE_LABEL_MAP.get(self._normalize_chinese_label(raw))
        if chinese_code:
            return chinese_code

        if len(raw) == 1 and raw in _DIRECT_CODES:
            return raw

        normalized = self._normalize_label(raw)
        if len(normalized) == 1 and normalized in _DIRECT_CODES:
            return normalized

        tokens = [token for token in normalized.split("_") if token]
        color = next((_COLOR_ALIASES[token] for token in tokens if token in _COLOR_ALIASES), None)
        piece = next((_PIECE_ALIASES[token] for token in tokens if token in _PIECE_ALIASES), None)

        if not piece:
            # Common compact labels: redR, black_c, r_rook, b-cannon.
            compact = normalized.replace("_", "")
            for color_token, color_value in sorted(_COLOR_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
                if compact.startswith(color_token):
                    color = color or color_value
                    compact_piece = compact[len(color_token):]
                    if len(compact_piece) == 1 and compact_piece.upper() in _PIECE_ALIASES.values():
                        piece = compact_piece.upper()
                    elif compact_piece in _PIECE_ALIASES:
                        piece = _PIECE_ALIASES[compact_piece]
                    break

        if not piece:
            return None

        return piece if color != "black" else piece.lower()

    def _normalize_chinese_label(self, value: str) -> str:
        text = re.sub(r"\s+", "", value.strip())
        text = text.replace("_", "-")
        text = text.replace("－", "-").replace("—", "-").replace("–", "-")
        return text

    def _normalize_label(self, value: str) -> str:
        text = value.strip().lower()
        text = re.sub(r"[^a-z0-9]+", "_", text)
        text = re.sub(r"_+", "_", text).strip("_")
        text = re.sub(r"^(xiangqi|chess|piece)_", "", text)
        text = re.sub(r"_(piece|chess|xiangqi)$", "", text)
        return text

    def _warn_unknown_label(self, class_name: str) -> None:
        label = str(class_name or "").strip() or "<empty>"
        if label in self._unknown_labels:
            return
        self._unknown_labels.add(label)
        logger.warning("[BoardMapper] Unknown vision class label skipped: %s", label)
