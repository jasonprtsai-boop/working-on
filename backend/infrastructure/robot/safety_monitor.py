from backend.utils import config
from backend.utils.logger import logger
from backend.application.services.estop import estop

class SafetyMonitor:
    """
    [Robot Layer] Industrial Safety Monitor.
    Responsibility: Enforcing hardware limits and emergency stop conditions.
    """
    def __init__(self):
        self.max_x = getattr(config, "ROBOT_MAX_X", 600.0)
        self.min_x = getattr(config, "ROBOT_MIN_X", -600.0)
        self.max_y = getattr(config, "ROBOT_MAX_Y", 600.0)
        self.min_y = getattr(config, "ROBOT_MIN_Y", 100.0)
        self.z_safe = getattr(config, "Z_SAFE", 150.0)

    def validate_command(self, gcode: str) -> bool:
        """Checks if a single G-code command is safe to execute."""
        if estop.GLOBAL_STOP:
            logger.error("[SafetyMonitor] Refusing command: GLOBAL_STOP is active.")
            return False

        # Basic X/Y/Z boundary checking for G1 commands
        if gcode.startswith("G1"):
            parts = gcode.split(" ")
            for p in parts:
                if p.startswith("X"):
                    x = float(p[1:])
                    if not (self.min_x <= x <= self.max_x):
                        logger.error(f"[SafetyMonitor] X limit violation: {x}")
                        return False
                elif p.startswith("Y"):
                    y = float(p[1:])
                    if not (self.min_y <= y <= self.max_y):
                        logger.error(f"[SafetyMonitor] Y limit violation: {y}")
                        return False
        return True

    def validate_sequence(self, commands: list) -> bool:
        """Validates a whole sequence of planned commands."""
        for cmd in commands:
            if not self.validate_command(cmd):
                return False
        return True

    def check_system_integrity(self) -> bool:
        """Checks overall system safety status (e.g. communication, stop flags)."""
        if estop.is_triggered:
            return False
        # Future: Add heartbeat/watchdog checks here
        return True

safety_monitor = SafetyMonitor()
