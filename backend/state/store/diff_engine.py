from typing import Dict, Any, List

class DiffEngine:
    """
    Computes delta between two state snapshots.
    """
    @staticmethod
    def compute_diff(old_state: Dict[str, Any], new_state: Dict[str, Any]) -> Dict[str, Any]:
        diff = {}
        for key, value in new_state.items():
            if old_state.get(key) != value:
                diff[key] = value

        # Specific logic for board differences if needed
        if "board" in diff:
            old_board = old_state.get("board")
            new_board = new_state.get("board")
            if isinstance(old_board, list) and isinstance(new_board, list):
                changes = []
                for r in range(min(len(old_board), len(new_board))):
                    row_old = old_board[r]
                    row_new = new_board[r]
                    if not isinstance(row_old, list) or not isinstance(row_new, list):
                        continue
                    for c in range(min(len(row_old), len(row_new))):
                        if row_old[c] != row_new[c]:
                            changes.append({"r": r, "c": c, "from": row_old[c], "to": row_new[c]})
                diff["board_diff"] = changes

        return diff

    @staticmethod
    def apply_diff(state: Dict[str, Any], diff: Dict[str, Any]) -> Dict[str, Any]:
        updated_state = state.copy()
        updated_state.update(diff)
        return updated_state
