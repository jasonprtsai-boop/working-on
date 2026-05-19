class RobotSafety:
    """[Robot Service] Enforcement of physical constraints and collision avoidance."""
    def __init__(self, config):
        self.limits_x = getattr(config, "SOFT_LIMIT_X", (config.ROBOT_MIN_X, config.ROBOT_MAX_X))
        self.limits_y = getattr(config, "SOFT_LIMIT_Y", (config.ROBOT_MIN_Y, config.ROBOT_MAX_Y))

    def validate_move(self, x, y):
        """Checks if the target coordinates are within safe operational bounds."""
        if not (self.limits_x[0] <= x <= self.limits_x[1]):
            return False, f"X coordinate {x} exceeds soft limits."

        if not (self.limits_y[0] <= y <= self.limits_y[1]):
            return False, f"Y coordinate {y} exceeds soft limits."

        return True, "Safe"
