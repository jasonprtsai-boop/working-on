from backend.utils import config
from backend.utils.logger import logger

class MotionPlanner:
    """
    [Robot Service] Converts logical moves (UCI) to physical robot commands (G-code).
    Handles path interpolation and gripper logic.
    """
    def __init__(self, coordinate_system):
        self.coords = coordinate_system
        self.z_safe = config.Z_SAFE
        self.z_grab = config.Z_GRAB

    def plan_move(self, move_str: str):
        """
        Generates a sequence of G-code commands for a chess move.
        Example: 'e2e4' -> [G1 Z150, G1 X10 Y20, ...]
        """
        if len(move_str) < 4:
            logger.error(f"Invalid move format: {move_str}")
            return []

        start_uci = move_str[0:2]
        end_uci = move_str[2:4]

        # 1. Map UCI to Grid (Col, Row)
        # This assumes the coordinate_system has mapping methods
        try:
            # Physical coordinates from the robot's coordinate system
            x1, y1 = self.coords.uci_to_world(start_uci)
            x2, y2 = self.coords.uci_to_world(end_uci)
        except Exception as e:
            logger.error(f"Coordinate mapping failed for {move_str}: {e}")
            return []

        # 2. Generate Motion Sequence
        commands = [
            f"G1 Z{self.z_safe} F3000",      # Lift to safe height
            f"G1 X{x1:.2f} Y{y1:.2f} F3000", # Move over start piece
            f"G1 Z{self.z_grab} F1500",      # Lower to grab
            "M10",                           # Close Gripper / Turn on Vacuum
            "G4 P500",                       # Dwell 500ms
            f"G1 Z{self.z_safe} F3000",      # Lift piece
            f"G1 X{x2:.2f} Y{y2:.2f} F3000", # Move over destination
            f"G1 Z{self.z_grab} F1500",      # Lower to place
            "M11",                           # Open Gripper / Turn off Vacuum
            "G4 P500",                       # Dwell 500ms
            f"G1 Z{self.z_safe} F3000"       # Final lift
        ]

        logger.info(f"Planned move {move_str}: {len(commands)} G-code lines.")
        return commands
