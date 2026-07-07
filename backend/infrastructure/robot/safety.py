import math


class RobotSafety:
    """[Robot Service] Enforcement of physical constraints and collision avoidance."""
    def __init__(self, config):
        self.limits_x = getattr(config, "SOFT_LIMIT_X", (config.ROBOT_MIN_X, config.ROBOT_MAX_X))
        self.limits_y = getattr(config, "SOFT_LIMIT_Y", (config.ROBOT_MIN_Y, config.ROBOT_MAX_Y))
        self.limits_z = getattr(
            config,
            "SOFT_LIMIT_Z",
            (
                float(getattr(config, "ROBOT_MIN_Z", 0.0)),
                float(getattr(config, "ROBOT_MAX_Z", max(config.Z_SAFE, config.Z_GRAB) + 100.0)),
            ),
        )

    def _finite(self, value, axis: str):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None, f"{axis} coordinate must be numeric."
        if not math.isfinite(number):
            return None, f"{axis} coordinate must be finite."
        return number, None

    def validate_move(self, x, y):
        """Checks if the target coordinates are within safe operational bounds."""
        x, err = self._finite(x, "X")
        if err:
            return False, err
        y, err = self._finite(y, "Y")
        if err:
            return False, err

        if not (self.limits_x[0] <= x <= self.limits_x[1]):
            return False, f"X coordinate {x} exceeds soft limits."

        if not (self.limits_y[0] <= y <= self.limits_y[1]):
            return False, f"Y coordinate {y} exceeds soft limits."

        return True, "Safe"

    def validate_position(self, x, y, z=None):
        ok, msg = self.validate_move(x, y)
        if not ok or z is None:
            return ok, msg

        z, err = self._finite(z, "Z")
        if err:
            return False, err
        if not (self.limits_z[0] <= z <= self.limits_z[1]):
            return False, f"Z coordinate {z} exceeds soft limits."

        return True, "Safe"
