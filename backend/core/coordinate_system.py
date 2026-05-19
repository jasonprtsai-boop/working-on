"""
[Coordinate Authority Layer] CoordinateSystem
Rule: The ONLY source of truth for all spatial and state transformations.
Standard: (row, col) = (0-9, 0-8)
"""

class CoordinateSystem:
    def __init__(self, homography=None):
        self.homography = homography

    def uci_to_internal(self, uci):
        """UCI (e.g. 'a0') -> (row, col) (9-0, 0-8)"""
        if not uci or len(uci) < 2: return None
        col = ord(uci[0].lower()) - ord('a')
        row = 9 - int(uci[1:])
        return row, col

    def internal_to_uci(self, r, c):
        """(row, col) -> UCI (e.g. 'a0')"""
        col_str = chr(ord('a') + c)
        row_str = str(9 - r)
        return f"{col_str}{row_str}"

    def engine_to_grid(self, move_uci):
        """Legacy Alias for uci_to_internal"""
        return self.uci_to_internal(move_uci)

    def grid_to_uci(self, r, c):
        """Legacy Alias for internal_to_uci"""
        return self.internal_to_uci(r, c)

    def internal_to_world(self, r, c):
        """Internal (row, col) -> Physical World (mm)"""
        # Mapping logic for the robot arm (40mm cell width)
        if self.homography:
            # Assume homography expects (x, y) = (col, row)
            return self.homography.transform((c, r))
        return c * 40.0, r * 40.0

    def grid_to_world(self, r, c):
        """Legacy Alias for internal_to_world"""
        return self.internal_to_world(r, c)

    def world_to_internal(self, x, y):
        """Physical World (mm) -> Internal (row, col)"""
        # Inverse mapping
        return int(round(y / 40.0)), int(round(x / 40.0))

from backend.utils.fen.parser import fen_to_board, board_to_fen
