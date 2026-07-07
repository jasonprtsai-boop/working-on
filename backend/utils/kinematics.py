import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

from backend.utils import config
from backend.utils.logger import logger


class Kinematics:
    """Map Xiangqi board coordinates to robot XY coordinates."""

    files = "abcdefghi"
    _file_to_idx = {file_char: idx for idx, file_char in enumerate(files)}

    def __init__(self):
        self.origin_x = 0.0
        self.origin_y = float(getattr(config, "ROBOT_MIN_Y", 0.0))
        self.square_size_x = 40.0
        self.square_size_y = 40.0
        self.dead_zone = self._default_dead_zone()
        self.dead_zone_range = self._default_dead_zone_range()
        self.affine_matrix = None
        self.inverse_affine_matrix = None
        self.calibration_error = None
        self._square_cache: Dict[str, Tuple[float, float]] = {}
        self._load_calibration()

    def _finite_float(self, value, field_name: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"{field_name} must be finite")
        return number

    def _default_dead_zone(self) -> Tuple[float, float]:
        return (
            self.origin_x + (self.square_size_x * 10.5),
            self.origin_y,
        )

    def _default_dead_zone_range(self) -> Dict[str, float]:
        x, y = self._default_dead_zone()
        return {
            "x": float(x),
            "y": float(y),
            "width": float(self.square_size_x * 2.0),
            "height": float(self.square_size_y * 2.0),
            "slot_spacing": 25.0,
            "slot_count": 4,
        }

    def _load_calibration(self):
        path = Path(getattr(config, "CALIBRATION_FILE", "robot/calibration.json"))
        if not path.exists():
            self._refresh_affine()
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            origin_x = self._finite_float(data.get("origin_x", self.origin_x), "origin_x")
            origin_y = self._finite_float(data.get("origin_y", self.origin_y), "origin_y")
            square_size_x = self._finite_float(data.get("square_size_x", self.square_size_x), "square_size_x")
            square_size_y = self._finite_float(data.get("square_size_y", self.square_size_y), "square_size_y")
            if square_size_x <= 0 or square_size_y <= 0:
                raise ValueError("square sizes must be positive")

            default_dead_zone = (
                origin_x + (square_size_x * 10.5),
                origin_y,
            )
            dead_zone = data.get("dead_zone") or {}
            dead_zone_coords = (
                self._finite_float(dead_zone.get("x", default_dead_zone[0]), "dead_zone.x"),
                self._finite_float(dead_zone.get("y", default_dead_zone[1]), "dead_zone.y"),
            )
            dead_zone_range = data.get("dead_zone_range")
            if dead_zone_range is None and any(key in dead_zone for key in ("width", "height", "slot_spacing", "slot_count")):
                dead_zone_range = dead_zone

            self.origin_x = origin_x
            self.origin_y = origin_y
            self.square_size_x = square_size_x
            self.square_size_y = square_size_y
            self.dead_zone = dead_zone_coords
            self.dead_zone_range = self._normalize_dead_zone_range(dead_zone_range, default_coords=dead_zone_coords)
            affine = data.get("affine_matrix")
            if affine is not None:
                self._set_affine_matrix(affine)
            else:
                self._refresh_affine()
        except Exception:
            logger.warning("[Kinematics] failed to load calibration; using defaults", exc_info=True)
            self._refresh_affine()

    def grid_to_robot(self, file_char: str, rank: str) -> Optional[Tuple[float, float]]:
        """Map a UCCI square split as file/rank to robot XY."""
        try:
            file_idx = self._file_to_idx[str(file_char).lower()]
            rank_idx = int(rank)
            if rank_idx < 0 or rank_idx > 9:
                return None
        except Exception:
            return None
        x, y = self._apply_affine(file_idx, rank_idx)
        return float(x), float(y)

    def square_to_robot(self, square: str) -> Optional[Tuple[float, float]]:
        if not isinstance(square, str) or len(square) < 2:
            return None
        key = square.strip().lower()
        if key in self._square_cache:
            return self._square_cache[key]
        try:
            file_idx, rank_idx = self._square_indices(key)
        except Exception:
            return None
        x, y = self._apply_affine(file_idx, rank_idx)
        result = (float(x), float(y))
        self._square_cache[key] = result
        return result

    def internal_to_robot(self, row: int, col: int) -> Optional[Tuple[float, float]]:
        """Map internal row/col (row 0 top, col 0 left) to robot XY."""
        try:
            row_idx = int(row)
            col_idx = int(col)
        except Exception:
            return None
        if row_idx < 0 or row_idx > 9 or col_idx < 0 or col_idx > 8:
            return None
        rank = 9 - row_idx
        x, y = self._apply_affine(col_idx, rank)
        return float(x), float(y)

    def robot_to_grid(self, x: float, y: float, tolerance_ratio: float = 0.5) -> Optional[Tuple[str, str]]:
        """Map robot XY back to nearest UCCI file/rank when close to a board point."""
        try:
            x_value = float(x)
            y_value = float(y)
            if not math.isfinite(x_value) or not math.isfinite(y_value):
                return None
            file_float, rank_float = self._apply_inverse_affine(x_value, y_value)
        except Exception:
            return None
        file_idx = self._nearest_index(file_float)
        rank_idx = self._nearest_index(rank_float)
        if file_idx < 0 or file_idx > 8 or rank_idx < 0 or rank_idx > 9:
            return None

        tolerance = max(0.0, float(tolerance_ratio))
        distance = math.hypot(file_float - file_idx, rank_float - rank_idx)
        if distance > tolerance:
            return None
        return self.files[file_idx], str(rank_idx)

    def robot_to_square(self, x: float, y: float, tolerance_ratio: float = 0.5) -> Optional[str]:
        grid = self.robot_to_grid(x, y, tolerance_ratio=tolerance_ratio)
        if grid is None:
            return None
        file_char, rank = grid
        return f"{file_char}{rank}"

    def robot_to_internal(self, x: float, y: float, tolerance_ratio: float = 0.5) -> Optional[Tuple[int, int]]:
        grid = self.robot_to_grid(x, y, tolerance_ratio=tolerance_ratio)
        if grid is None:
            return None
        file_char, rank = grid
        return 9 - int(rank), self._file_to_idx[file_char]

    def get_dead_zone_coords(self, slot: int = 1) -> Tuple[float, float]:
        zone = self.dead_zone_range or self._default_dead_zone_range()
        slot_index = max(int(slot) - 1, 0)
        spacing = float(zone.get("slot_spacing", 25.0))
        count = max(int(zone.get("slot_count", 1) or 1), 1)
        slot_index = min(slot_index, count - 1)
        x = float(self.dead_zone[0]) + slot_index * spacing
        y = float(self.dead_zone[1])
        return x, y

    def update_calibration(
        self,
        *,
        origin_x=None,
        origin_y=None,
        square_size_x=None,
        square_size_y=None,
        dead_zone=None,
        affine_matrix=None,
        persist: bool = False,
        path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update robot board calibration and optionally persist it."""
        if origin_x is not None:
            self.origin_x = self._finite_float(origin_x, "origin_x")
        if origin_y is not None:
            self.origin_y = self._finite_float(origin_y, "origin_y")
        if square_size_x is not None:
            self.square_size_x = self._finite_float(square_size_x, "square_size_x")
        if square_size_y is not None:
            self.square_size_y = self._finite_float(square_size_y, "square_size_y")
        if self.square_size_x <= 0 or self.square_size_y <= 0:
            raise ValueError("square sizes must be positive")

        if dead_zone is not None:
            self.dead_zone = (
                self._finite_float((dead_zone or {}).get("x"), "dead_zone.x"),
                self._finite_float((dead_zone or {}).get("y"), "dead_zone.y"),
            )
            self.dead_zone_range = self._normalize_dead_zone_range(dead_zone, default_coords=self.dead_zone)
        elif any(value is not None for value in (origin_x, origin_y, square_size_x, square_size_y)):
            self.dead_zone = self._default_dead_zone()
            self.dead_zone_range = self._default_dead_zone_range()

        if affine_matrix is not None:
            self._set_affine_matrix(affine_matrix)
        else:
            self._refresh_affine()
        self.calibration_error = None

        if persist:
            self.save_calibration(path=path)
        return self.to_dict()

    def calibrate_from_points(
        self,
        points: Iterable[Dict[str, Any]],
        *,
        dead_zone=None,
        persist: bool = False,
        path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Calibrate from measured robot coordinates.

        Each point must contain a UCCI square plus x/y, for example:
        {"square": "a0", "x": 0, "y": 100}.
        Three or more non-collinear points produce a full affine transform;
        fewer points update the axis-aligned origin/square-size model.
        """
        samples = []
        for point in points or []:
            square = str(point.get("square") or point.get("ucci") or "").strip().lower()
            file_idx, rank_idx = self._square_indices(square)
            x = self._finite_float(point.get("x"), "point.x")
            y = self._finite_float(point.get("y"), "point.y")
            samples.append((file_idx, rank_idx, x, y))

        if len(samples) < 2:
            raise ValueError("At least two calibration points are required")

        if len(samples) >= 3 and self._has_non_collinear_samples(samples):
            affine = self._fit_affine(samples)
            self._set_affine_matrix(affine)
            self.calibration_error = self._calibration_error(samples)
            self.origin_x = float(self.affine_matrix[0][2])
            self.origin_y = float(self.affine_matrix[1][2])
            self.square_size_x = float(math.hypot(self.affine_matrix[0][0], self.affine_matrix[1][0]))
            self.square_size_y = float(math.hypot(self.affine_matrix[0][1], self.affine_matrix[1][1]))
        else:
            self.origin_x, self.square_size_x = self._fit_axis(
                [(file_idx, x) for file_idx, _rank_idx, x, _y in samples],
                self.origin_x,
                self.square_size_x,
            )
            self.origin_y, self.square_size_y = self._fit_axis(
                [(rank_idx, y) for _file_idx, rank_idx, _x, y in samples],
                self.origin_y,
                self.square_size_y,
            )
            self._refresh_affine()
            self.calibration_error = self._calibration_error(samples)

        if dead_zone is not None:
            self.dead_zone = (
                self._finite_float((dead_zone or {}).get("x"), "dead_zone.x"),
                self._finite_float((dead_zone or {}).get("y"), "dead_zone.y"),
            )
            self.dead_zone_range = self._normalize_dead_zone_range(dead_zone, default_coords=self.dead_zone)
        else:
            self.dead_zone = self._default_dead_zone()
            self.dead_zone_range = self._default_dead_zone_range()

        if persist:
            self.save_calibration(path=path)
        return self.to_dict()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "origin_x": float(self.origin_x),
            "origin_y": float(self.origin_y),
            "square_size_x": float(self.square_size_x),
            "square_size_y": float(self.square_size_y),
            "dead_zone": {"x": float(self.dead_zone[0]), "y": float(self.dead_zone[1])},
            "dead_zone_range": dict(self.dead_zone_range),
            "affine_matrix": [row[:] for row in self.affine_matrix] if self.affine_matrix else None,
            "calibration_error": dict(self.calibration_error) if self.calibration_error else None,
            "path": str(Path(getattr(config, "CALIBRATION_FILE", "robot/calibration.json"))),
        }

    def save_calibration(self, path: Optional[str] = None) -> None:
        target = Path(path or getattr(config, "CALIBRATION_FILE", "robot/calibration.json"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    def _square_indices(self, square: str) -> Tuple[int, int]:
        if not isinstance(square, str) or len(square) != 2:
            raise ValueError("square must be a UCCI coordinate like a0")
        file_char = square[0].lower()
        if file_char not in self._file_to_idx:
            raise ValueError(f"file must be one of {self.files}")
        rank_idx = int(square[1:])
        if rank_idx < 0 or rank_idx > 9:
            raise ValueError("rank must be between 0 and 9")
        return self._file_to_idx[file_char], rank_idx

    def _refresh_affine(self) -> None:
        self._set_affine_matrix([
            [float(self.square_size_x), 0.0, float(self.origin_x)],
            [0.0, float(self.square_size_y), float(self.origin_y)],
        ])

    def _set_affine_matrix(self, matrix) -> None:
        rows = [[self._finite_float(value, "affine_matrix") for value in row] for row in matrix]
        if len(rows) != 2 or any(len(row) != 3 for row in rows):
            raise ValueError("affine_matrix must be 2x3")
        a, b, _c = rows[0]
        d, e, _f = rows[1]
        det = a * e - b * d
        if abs(det) < 1e-9:
            raise ValueError("affine_matrix must be invertible")
        self.affine_matrix = rows
        self.inverse_affine_matrix = self._invert_affine(rows)
        self._clear_coordinate_cache()

    def _normalize_dead_zone_range(self, value, *, default_coords: Tuple[float, float]) -> Dict[str, float]:
        data = value if isinstance(value, dict) else {}
        x_default, y_default = default_coords
        width = self._finite_float(data.get("width", self.square_size_x * 2.0), "dead_zone.width")
        height = self._finite_float(data.get("height", self.square_size_y * 2.0), "dead_zone.height")
        slot_spacing = self._finite_float(data.get("slot_spacing", 25.0), "dead_zone.slot_spacing")
        slot_count = int(data.get("slot_count", 4))
        if width <= 0 or height <= 0:
            raise ValueError("dead_zone width and height must be positive")
        if slot_spacing <= 0:
            raise ValueError("dead_zone slot_spacing must be positive")
        if slot_count <= 0:
            raise ValueError("dead_zone slot_count must be positive")
        return {
            "x": self._finite_float(data.get("x", x_default), "dead_zone.x"),
            "y": self._finite_float(data.get("y", y_default), "dead_zone.y"),
            "width": float(width),
            "height": float(height),
            "slot_spacing": float(slot_spacing),
            "slot_count": int(slot_count),
        }

    def _apply_affine(self, file_idx: float, rank_idx: float) -> Tuple[float, float]:
        matrix = self.affine_matrix
        if matrix is None:
            self._refresh_affine()
            matrix = self.affine_matrix
        x = matrix[0][0] * file_idx + matrix[0][1] * rank_idx + matrix[0][2]
        y = matrix[1][0] * file_idx + matrix[1][1] * rank_idx + matrix[1][2]
        return x, y

    def _apply_inverse_affine(self, x: float, y: float) -> Tuple[float, float]:
        matrix = self.inverse_affine_matrix
        if matrix is None:
            self._refresh_affine()
            matrix = self.inverse_affine_matrix
        file_idx = matrix[0][0] * x + matrix[0][1] * y + matrix[0][2]
        rank_idx = matrix[1][0] * x + matrix[1][1] * y + matrix[1][2]
        return file_idx, rank_idx

    def _invert_affine(self, matrix):
        a, b, c = matrix[0]
        d, e, f = matrix[1]
        det = a * e - b * d
        inv_a = e / det
        inv_b = -b / det
        inv_d = -d / det
        inv_e = a / det
        inv_c = -(inv_a * c + inv_b * f)
        inv_f = -(inv_d * c + inv_e * f)
        return [[inv_a, inv_b, inv_c], [inv_d, inv_e, inv_f]]

    def _fit_axis(self, samples, default_origin: float, default_step: float) -> Tuple[float, float]:
        indices = [float(index) for index, _value in samples]
        values = [float(value) for _index, value in samples]
        if len(set(indices)) >= 2:
            mean_i = sum(indices) / len(indices)
            mean_v = sum(values) / len(values)
            variance = sum((index - mean_i) ** 2 for index in indices)
            step = sum((index - mean_i) * (value - mean_v) for index, value in zip(indices, values)) / variance
        else:
            step = default_step
        if step <= 0:
            raise ValueError("calibrated square size must be positive")
        origin = sum(value - index * step for index, value in zip(indices, values)) / len(values)
        return float(origin), float(step)

    def _has_non_collinear_samples(self, samples) -> bool:
        points = {(file_idx, rank_idx) for file_idx, rank_idx, _x, _y in samples}
        if len(points) < 3:
            return False
        pts = list(points)
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                for k in range(j + 1, len(pts)):
                    (x1, y1), (x2, y2), (x3, y3) = pts[i], pts[j], pts[k]
                    area2 = (x2 - x1) * (y3 - y1) - (y2 - y1) * (x3 - x1)
                    if abs(area2) > 1e-9:
                        return True
        return False

    def _fit_affine(self, samples):
        try:
            import numpy as np
        except Exception as exc:
            raise RuntimeError("numpy is required for affine robot calibration") from exc

        design = []
        target_x = []
        target_y = []
        for file_idx, rank_idx, x, y in samples:
            design.append([float(file_idx), float(rank_idx), 1.0])
            target_x.append(float(x))
            target_y.append(float(y))
        matrix = np.array(design, dtype=float)
        coeff_x, *_ = np.linalg.lstsq(matrix, np.array(target_x, dtype=float), rcond=None)
        coeff_y, *_ = np.linalg.lstsq(matrix, np.array(target_y, dtype=float), rcond=None)
        return [coeff_x.tolist(), coeff_y.tolist()]

    def _calibration_error(self, samples) -> Dict[str, float]:
        errors = []
        for file_idx, rank_idx, x, y in samples:
            px, py = self._apply_affine(file_idx, rank_idx)
            errors.append(math.hypot(float(px) - float(x), float(py) - float(y)))
        if not errors:
            return {"rms": 0.0, "max": 0.0}
        rms = math.sqrt(sum(error * error for error in errors) / len(errors))
        return {"rms": float(rms), "max": float(max(errors))}

    def _nearest_index(self, value: float) -> int:
        return int(math.floor(float(value) + 0.5))

    def _clear_coordinate_cache(self) -> None:
        self._square_cache.clear()


kinematics = Kinematics()
