"""Pure helpers for parsing UCI engine analysis output."""

from typing import MutableMapping


PvLineMap = MutableMapping[int, dict[str, object]]


def update_search_progress(line: str, current_depth: int, pv_lines: PvLineMap) -> int:
    """Update search depth and MultiPV rows from one UCI info line."""
    parts = line.split()
    next_depth = current_depth

    if "depth" in parts:
        depth_index = parts.index("depth") + 1
        if depth_index < len(parts):
            try:
                depth_value = int(parts[depth_index])
            except ValueError:
                depth_value = current_depth
            if depth_value > next_depth:
                next_depth = depth_value

    if "multipv" in parts and "score" in parts and "pv" in parts:
        try:
            rank = int(parts[parts.index("multipv") + 1])
            score_idx = parts.index("score")
            score_type = parts[score_idx + 1]
            score_val = int(parts[score_idx + 2]) if score_type == "cp" else 9999
            move = parts[parts.index("pv") + 1]
        except (IndexError, ValueError):
            return next_depth
        pv_lines[rank] = {"rank": rank, "move": move, "score_cp": score_val}

    return next_depth


def build_analysis_result(pv_lines: PvLineMap, current_depth: int, final_best: str) -> dict:
    sorted_lines = sorted(pv_lines.values(), key=lambda item: item["rank"])
    return {
        "best_move": final_best,
        "score": pv_lines.get(1, {}).get("score_cp", 0),
        "depth": current_depth,
        "final": True,
        "is_thinking": False,
        "multi_pv": [
            {"move": line["move"], "score": line["score_cp"], "pv": [line["move"]]}
            for line in sorted_lines
        ],
    }
