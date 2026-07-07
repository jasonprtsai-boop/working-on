import re
from typing import Dict, Any, Optional
from backend.events.models.base_event import BaseEvent

class EngineParser:
    """
    [Phase 5] UCI/UCCI Engine Parser Layer
    Parses Pikafish info output and converts it to standardized ENGINE_ANALYSIS events.
    """

    @staticmethod
    def parse_info_line(line: str) -> Optional[Dict[str, Any]]:
        """
        Parses a single 'info' line from the UCI/UCCI engine.
        Example: info depth 16 score cp -52 time 800 nodes 130400 nps 163000 pv h2e2 e7e5
        """
        if not line.startswith("info "):
            return None

        data: Dict[str, Any] = {}

        # 1. Depth
        depth_match = re.search(r'\bdepth\s+(\d+)\b', line)
        if depth_match:
            data["depth"] = int(depth_match.group(1))

        # 2. Score
        score_cp_match = re.search(r'\bscore\s+cp\s+(-?\d+)\b', line)
        if score_cp_match:
            data["score"] = int(score_cp_match.group(1))
            data["eval_type"] = "cp"
        else:
            score_mate_match = re.search(r'\bscore\s+mate\s+(-?\d+)\b', line)
            if score_mate_match:
                data["score"] = int(score_mate_match.group(1))
                data["eval_type"] = "mate"

        # 3. Time
        time_match = re.search(r'\btime\s+(\d+)\b', line)
        if time_match:
            data["time"] = int(time_match.group(1))

        # 4. NPS
        nps_match = re.search(r'\bnps\s+(\d+)\b', line)
        if nps_match:
            data["nps"] = int(nps_match.group(1))

        # 5. Nodes
        nodes_match = re.search(r'\bnodes\s+(\d+)\b', line)
        nodes = int(nodes_match.group(1)) if nodes_match else 0

        # 6. PV (Principal Variation)
        pv_match = re.search(r'\bpv\s+(.*)$', line)
        pv = pv_match.group(1).strip().split() if pv_match else []

        if "eval_type" in data:
            # [Research Analytics] Convert CP/Mate to Win Rate %
            import math
            sval = data.get("score", 0)
            if data["eval_type"] == "mate":
                winrate = 1.0 if sval > 0 else 0.0
            else:
                winrate = 1 / (1 + math.exp(-sval / 400.0))

            return BaseEvent.create(
                event_type="ENGINE.INFO_UPDATED",
                source="AI_ENGINE",
                payload={
                    "depth": data.get("depth", 0),
                    "score": sval,
                    "eval_type": data["eval_type"],
                    "winrate": round(winrate, 4),
                    "time": data.get("time", 0),
                    "nodes": nodes,
                    "nps": data.get("nps", 0),
                    "move": pv[0] if pv else "",
                    "best_move": pv[0] if pv else "",
                    "pv": pv,
                },
            )

        return None
