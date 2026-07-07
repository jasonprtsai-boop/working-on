from dataclasses import dataclass
import math
from typing import Iterable, List, Optional, Tuple

@dataclass
class GridConfig:
    rows: int = 10
    cols: int = 9
    width: int = 1000
    height: int = 1000
    intersection_tolerance_px: Optional[float] = None
    intersection_tolerance_ratio: float = 0.65

@dataclass(frozen=True)
class CellMapping:
    col: int
    row: int
    key: str
    center_x: float
    center_y: float
    distance_px: float
    distance_ratio: float
    dx_ratio: float
    dy_ratio: float


class BoardCoordinateSystem:
    """
    Maps pixel coordinates to Xiangqi board intersections.
    """
    def __init__(self, config: GridConfig = GridConfig()):
        self.config = config
        self.span_x = self._span(config.width)
        self.span_y = self._span(config.height)
        self.cell_w = self.span_x / max(config.cols - 1, 1)
        self.cell_h = self.span_y / max(config.rows - 1, 1)
        self.inv_cell_w = 1.0 / self.cell_w if self.cell_w else 0.0
        self.inv_cell_h = 1.0 / self.cell_h if self.cell_h else 0.0
        self._tolerance_px = self._compute_tolerance_px()
        self._tolerance_ratio = self._compute_tolerance_ratio()
        self._grid_points = tuple(
            (c * self.cell_w, r * self.cell_h)
            for r in range(self.config.rows)
            for c in range(self.config.cols)
        )

    def pixel_to_cell(self, px: float, py: float) -> Optional[Tuple[int, int]]:
        """Maps pixel (x, y) to nearest 0-indexed board intersection."""
        mapping = self.pixel_to_cell_detail(px, py)
        if mapping is None:
            return None
        return mapping.col, mapping.row

    def pixel_to_cell_detail(self, px: float, py: float) -> Optional[CellMapping]:
        """Map pixel (x, y) to the nearest intersection with quality metadata."""
        try:
            x = float(px)
            y = float(py)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(x) or not math.isfinite(y):
            return None

        col = self._nearest_index(x * self.inv_cell_w) if self.config.cols > 1 else 0
        row = self._nearest_index(y * self.inv_cell_h) if self.config.rows > 1 else 0
        col = max(0, min(col, self.config.cols - 1))
        row = max(0, min(row, self.config.rows - 1))

        nearest_x = col * self.cell_w
        nearest_y = row * self.cell_h
        dx = x - nearest_x
        dy = y - nearest_y
        dx_ratio = dx * self.inv_cell_w if self.cell_w else 0.0
        dy_ratio = dy * self.inv_cell_h if self.cell_h else 0.0
        distance_sq = dx * dx + dy * dy
        ratio_sq = dx_ratio * dx_ratio + dy_ratio * dy_ratio
        if self.config.intersection_tolerance_px is not None:
            if distance_sq > self._tolerance_px * self._tolerance_px:
                return None
        elif ratio_sq > self._tolerance_ratio * self._tolerance_ratio:
            return None
        distance_px = math.sqrt(distance_sq)
        distance_ratio = math.sqrt(ratio_sq)

        return CellMapping(
            col=col,
            row=row,
            key=self.cell_to_key(col, row),
            center_x=nearest_x,
            center_y=nearest_y,
            distance_px=distance_px,
            distance_ratio=distance_ratio,
            dx_ratio=dx_ratio,
            dy_ratio=dy_ratio,
        )

    def pixel_to_key(self, px: float, py: float) -> Optional[str]:
        """Maps pixel (x, y) to a stable 'col,row' board key."""
        mapping = self.pixel_to_cell_detail(px, py)
        if mapping is None:
            return None
        return mapping.key

    def cell_to_key(self, col: int, row: int) -> str:
        return f"{int(col)},{int(row)}"

    def cell_to_pixel_center(self, col: int, row: int) -> Tuple[float, float]:
        """Maps (col, row) to its board-intersection pixel coordinate."""
        px = col * self.cell_w
        py = row * self.cell_h
        return px, py

    def key_to_pixel_center(self, key: str) -> Optional[Tuple[float, float]]:
        """Maps a 'col,row' board key back to a rectified-board pixel point."""
        try:
            col_text, row_text = str(key).split(",", 1)
            col = int(col_text)
            row = int(row_text)
        except Exception:
            return None
        if col < 0 or col >= self.config.cols or row < 0 or row >= self.config.rows:
            return None
        return self.cell_to_pixel_center(col, row)

    def pixel_to_normalized(self, px: float, py: float) -> Tuple[float, float]:
        """Map pixel coordinates to normalized board-plane coordinates in [0, 1]."""
        x = self._finite_or_zero(px)
        y = self._finite_or_zero(py)
        x = max(0.0, min(x, self.span_x)) / self.span_x
        y = max(0.0, min(y, self.span_y)) / self.span_y
        return x, y

    def get_grid_points(self) -> List[Tuple[float, float]]:
        """Returns all intersection points for visualization."""
        return list(self._grid_points)

    def pixels_to_cells(self, points: Iterable[Tuple[float, float]]) -> List[Optional[Tuple[int, int]]]:
        """Batch helper for converting many points with the same precomputed grid."""
        return [self.pixel_to_cell(px, py) for px, py in points]

    def pixels_to_cell_details(self, points: Iterable[Tuple[float, float]]) -> List[Optional[CellMapping]]:
        """Batch helper returning mapping quality metadata for many points."""
        return [self.pixel_to_cell_detail(px, py) for px, py in points]

    def _intersection_tolerance(self) -> float:
        return self._tolerance_px

    def _compute_tolerance_px(self) -> float:
        if self.config.intersection_tolerance_px is not None:
            return max(0.0, float(self.config.intersection_tolerance_px))
        return max(0.0, float(self.config.intersection_tolerance_ratio)) * min(self.cell_w, self.cell_h)

    def _compute_tolerance_ratio(self) -> float:
        if self.config.intersection_tolerance_px is not None:
            return self._compute_tolerance_px() / max(min(self.cell_w, self.cell_h), 1e-9)
        return max(0.0, float(self.config.intersection_tolerance_ratio))

    def _span(self, value: int) -> float:
        return max(float(value) - 1.0, 1.0)

    def _nearest_index(self, value: float) -> int:
        return int(math.floor(value + 0.5))

    def _finite_or_zero(self, value) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.0
        return number if math.isfinite(number) else 0.0
