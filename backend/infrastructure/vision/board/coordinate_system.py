from dataclasses import dataclass
import math
from typing import List, Optional, Tuple

@dataclass
class GridConfig:
    rows: int = 10
    cols: int = 9
    width: int = 1000
    height: int = 1000
    intersection_tolerance_px: Optional[float] = None
    intersection_tolerance_ratio: float = 0.65

class BoardCoordinateSystem:
    """
    Maps pixel coordinates to Xiangqi board intersections.
    """
    def __init__(self, config: GridConfig = GridConfig()):
        self.config = config
        self.cell_w = self._span(config.width) / max(config.cols - 1, 1)
        self.cell_h = self._span(config.height) / max(config.rows - 1, 1)

    def pixel_to_cell(self, px: float, py: float) -> Optional[Tuple[int, int]]:
        """Maps pixel (x, y) to nearest 0-indexed board intersection."""
        try:
            x = float(px)
            y = float(py)
        except (TypeError, ValueError):
            return None

        col = int(round(x / self.cell_w)) if self.config.cols > 1 else 0
        row = int(round(y / self.cell_h)) if self.config.rows > 1 else 0
        col = max(0, min(col, self.config.cols - 1))
        row = max(0, min(row, self.config.rows - 1))

        nearest_x = col * self.cell_w
        nearest_y = row * self.cell_h
        distance = math.hypot(x - nearest_x, y - nearest_y)
        if distance > self._intersection_tolerance():
            return None

        return col, row

    def cell_to_pixel_center(self, col: int, row: int) -> Tuple[float, float]:
        """Maps (col, row) to its board-intersection pixel coordinate."""
        px = col * self.cell_w
        py = row * self.cell_h
        return px, py

    def get_grid_points(self) -> List[Tuple[float, float]]:
        """Returns all intersection points for visualization."""
        points = []
        for r in range(self.config.rows):
            for c in range(self.config.cols):
                points.append((c * self.cell_w, r * self.cell_h))
        return points

    def _intersection_tolerance(self) -> float:
        if self.config.intersection_tolerance_px is not None:
            return max(0.0, float(self.config.intersection_tolerance_px))
        return max(0.0, float(self.config.intersection_tolerance_ratio)) * min(self.cell_w, self.cell_h)

    def _span(self, value: int) -> float:
        return max(float(value) - 1.0, 1.0)
