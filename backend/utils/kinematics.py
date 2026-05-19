import json
from pathlib import Path
from typing import Optional, Tuple

from backend.utils import config
from backend.utils.logger import logger


class Kinematics:
    """Map Xiangqi board coordinates to robot XY coordinates."""

    def __init__(self):
        self.origin_x = 0.0
        self.origin_y = 0.0
        self.square_size_x = 40.0
        self.square_size_y = 40.0
        self.dead_zone = (420.0, 40.0)
        self._load_calibration()

    def _load_calibration(self):
        path = Path(getattr(config, "CALIBRATION_FILE", "robot/calibration.json"))
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.origin_x = float(data.get("origin_x", self.origin_x))
            self.origin_y = float(data.get("origin_y", self.origin_y))
            self.square_size_x = float(data.get("square_size_x", self.square_size_x))
            self.square_size_y = float(data.get("square_size_y", self.square_size_y))
            dead_zone = data.get("dead_zone") or {}
            self.dead_zone = (
                float(dead_zone.get("x", self.dead_zone[0])),
                float(dead_zone.get("y", self.dead_zone[1])),
            )
        except Exception:
            logger.warning("[Kinematics] failed to load calibration; using defaults", exc_info=True)

    def grid_to_robot(self, file_char: str, rank: str) -> Optional[Tuple[float, float]]:
        files = "abcdefghi"
        if file_char not in files:
            return None
        try:
            rank_idx = int(rank)
        except Exception:
            return None
        if rank_idx < 0 or rank_idx > 9:
            return None
        file_idx = files.index(file_char)
        x = self.origin_x + file_idx * self.square_size_x
        y = self.origin_y + rank_idx * self.square_size_y
        return float(x), float(y)

    def get_dead_zone_coords(self, slot: int = 1) -> Tuple[float, float]:
        return float(self.dead_zone[0] + max(slot - 1, 0) * 25.0), float(self.dead_zone[1])


kinematics = Kinematics()
