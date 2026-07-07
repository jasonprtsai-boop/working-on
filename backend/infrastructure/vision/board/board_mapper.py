import math
import re
from typing import Any, Dict, List, Optional

from backend.infrastructure.vision.detection.detection_result import Detection
from backend.utils.logger import logger
from backend.utils import config
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
        self._label_cache: Dict[str, Optional[str]] = {}
        self.anchor_x_ratio = self._bounded_ratio(getattr(config, "VISION_BBOX_ANCHOR_X", 0.5), default=0.5)
        self.anchor_y_ratio = self._bounded_ratio(getattr(config, "VISION_BBOX_ANCHOR_Y", 0.5), default=0.5)

    def map_detections(self, detections: List[Detection]) -> Dict[str, str]:
        """
        Maps detections to a board dictionary: {"col,row": "piece_char", ...}.
        Unknown class labels are skipped so they cannot poison downstream FEN.
        """
        board_state: Dict[str, str] = {}
        board_conf: Dict[str, float] = {}
        details = self.describe_detections(detections)

        for det, detail in zip(detections, details):
            if detail.get("mapping_status") != "mapped":
                continue

            key = detail.get("mapped_cell")
            piece_code = detail.get("piece_code")
            mapping = detail.get("board_mapping") or {}
            if not key or not piece_code:
                continue

            # Conflict resolution: keep the highest-confidence detection, then prefer
            # the one closest to the grid intersection when confidence ties.
            if key in board_state:
                prev = board_conf.get(key, -1.0)
                prev_distance = board_conf.get(f"{key}:distance", float("inf"))
                if det.confidence < prev:
                    continue
                if det.confidence == prev and float(mapping.get("distance_ratio", float("inf"))) >= prev_distance:
                    continue

            board_state[key] = piece_code
            board_conf[key] = float(det.confidence)
            board_conf[f"{key}:distance"] = float(mapping.get("distance_ratio", float("inf")))

        return board_state

    def describe_detections(
        self,
        detections: List[Detection],
        *,
        coordinate_space: str = "rectified_board",
        frame_size=None,
    ) -> List[Dict[str, Any]]:
        """Return detection payloads enriched with board-mapping metadata."""
        anchors = [self._detection_anchor(det) for det in detections]
        mappings = self.coord_system.pixels_to_cell_details(anchors)
        details: List[Dict[str, Any]] = []

        for det, mapping in zip(detections, mappings):
            piece_code = None
            mapped_cell = None
            status = "off_grid"
            mapping_payload = self._mapping_to_dict(mapping) if mapping is not None else None

            if mapping is None:
                logger.debug(
                    "[BoardMapper] Detection skipped because anchor is not near a board intersection: %s",
                    det.class_name,
                )
            else:
                piece_code = self._map_class_to_piece(det.class_name)
                if piece_code:
                    mapped_cell = mapping.key
                    status = "mapped"
                else:
                    status = "unknown_label"
                    self._warn_unknown_label(det.class_name)

            details.append(
                det.to_dict(
                    anchor_ratio=(self.anchor_x_ratio, self.anchor_y_ratio),
                    coordinate_space=coordinate_space,
                    frame_size=frame_size,
                    extra={
                        "piece_code": piece_code,
                        "mapped_cell": mapped_cell,
                        "board_mapping": mapping_payload,
                        "mapping_status": status,
                    },
                )
            )

        return details

    def _map_class_to_piece(self, class_name: str) -> Optional[str]:
        """Maps YOLO class names to Xiangqi FEN piece characters."""
        if not isinstance(class_name, str):
            return None

        raw = class_name.strip()
        if raw in self._label_cache:
            return self._label_cache[raw]

        chinese_code = _CHINESE_LABEL_MAP.get(self._normalize_chinese_label(raw))
        if chinese_code:
            self._label_cache[raw] = chinese_code
            return chinese_code

        if len(raw) == 1 and raw in _DIRECT_CODES:
            self._label_cache[raw] = raw
            return raw

        normalized = self._normalize_label(raw)
        if len(normalized) == 1 and normalized in _DIRECT_CODES:
            self._label_cache[raw] = normalized
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
            self._label_cache[raw] = None
            return None

        result = piece if color != "black" else piece.lower()
        self._label_cache[raw] = result
        return result

    def _detection_anchor(self, det: Detection):
        return det.bbox.anchor(self.anchor_x_ratio, self.anchor_y_ratio)

    def _mapping_to_dict(self, mapping) -> Optional[Dict[str, Any]]:
        if mapping is None:
            return None
        return {
            "key": mapping.key,
            "col": int(mapping.col),
            "row": int(mapping.row),
            "center": [float(mapping.center_x), float(mapping.center_y)],
            "distance_px": float(mapping.distance_px),
            "distance_ratio": float(mapping.distance_ratio),
            "dx_ratio": float(mapping.dx_ratio),
            "dy_ratio": float(mapping.dy_ratio),
        }

    def _bounded_ratio(self, value, *, default: float) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        if not math.isfinite(number):
            return default
        if number < 0.0:
            return 0.0
        if number > 1.0:
            return 1.0
        return number

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
