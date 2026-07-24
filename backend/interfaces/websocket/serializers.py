from typing import Any, Dict

from backend.runtime.contract import CONTRACT_VERSION


def _board_from_fen(fen: str):
    try:
        from backend.utils.fen.parser import fen_to_board
        return fen_to_board(fen)
    except Exception:
        return []


def _pieces_from_board(board) -> list[dict]:
    if not isinstance(board, list):
        return []

    counters: Dict[str, int] = {}
    pieces = []
    for row_index, row in enumerate(board[:10]):
        if not isinstance(row, list):
            continue
        for col_index, piece_type in enumerate(row[:9]):
            if not piece_type:
                continue
            piece_text = str(piece_type)
            counters[piece_text] = counters.get(piece_text, 0) + 1
            pos = f"{chr(ord('a') + col_index)}{9 - row_index}"
            pieces.append({
                "id": f"{piece_text}-{counters[piece_text]}",
                "type": piece_text,
                "pos": pos,
            })
    return pieces


def _frontend_turn(turn: str) -> str:
    normalized = str(turn or "").strip().lower()
    if normalized in {"w", "red", "white"}:
        return "red"
    if normalized in {"b", "black"}:
        return "black"
    return "red"


class StateSerializer:
    """
    [Interface Layer] Serializes backend SystemState into frontend-compatible schemas.
    Enforces the 'Frontend Contract' for real-time synchronization.
    """

    @staticmethod
    def serialize(raw: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert backend SystemState shape into the frontend `STATE_UPDATE` schema.
        Frontend expects keys: board/engine/robot/sync/ui/notation.
        """
        if not isinstance(raw, dict):
            return {}

        game = raw.get("game", {}) if isinstance(raw.get("game"), dict) else {}
        engine = raw.get("engine", {}) if isinstance(raw.get("engine"), dict) else {}
        robot = raw.get("robot", {}) if isinstance(raw.get("robot"), dict) else {}
        vision = raw.get("vision", {}) if isinstance(raw.get("vision"), dict) else {}
        health = raw.get("health", {}) if isinstance(raw.get("health"), dict) else {}
        fen = game.get("fen", "")
        board = game.get("board")
        pieces = game.get("pieces")
        if not pieces:
            pieces = _pieces_from_board(board if isinstance(board, list) else _board_from_fen(fen))
        if not pieces and fen:
            pieces = _pieces_from_board(_board_from_fen(fen))

        robot_payload = {
            "connected": robot.get("connected", False),
            "is_connected": robot.get("is_connected", robot.get("connected", False)),
            "busy": robot.get("busy", False),
            "error": robot.get("error"),
            "last_action": robot.get("last_action", ""),
            "queue_size": robot.get("queue_size", 0),
            "position": robot.get("position") or {"x": 0, "y": 0, "z": 0},
        }
        for key in (
            "orientation",
            "joint_angles",
            "speed",
            "ip",
            "port",
            "connection",
            "telemetry",
            "status_code",
            "status_label",
            "error_code",
            "gripper_status_code",
            "fake_robot",
        ):
            if key in robot:
                robot_payload[key] = robot.get(key)

        return {
            "board": {
                "fen": fen,
                "pieces": pieces or [],
                "turn": _frontend_turn(game.get("current_turn", "w")),
                "move_count": len(game.get("move_history", []) or []),
                "last_move": (game.get("move_history") or [None])[-1],
            },
            "engine": EngineInfoSerializer.serialize(engine),
            "robot": robot_payload,
            "sync": {
                "version": raw.get("trace_id", "root"),
                "contract_version": CONTRACT_VERSION,
                "latency": 0,
                "fps": health.get("fps", 0),
                "timeline": {"vision": {"duration": 0}, "engine": {"duration": 0}, "robot": {"duration": 0}},
            },
            "vision": vision,
            "ui": {},
            "notation": game.get("last_notation"),
            "game": game,
        }

class EngineInfoSerializer:
    """Serializes engine-specific events into the frontend engine contract."""

    @staticmethod
    def serialize(raw: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(raw, dict):
            return {}

        best_move = raw.get("best_move") or raw.get("bestmove") or raw.get("move") or ""
        pv = raw.get("pv") or []
        if isinstance(pv, str):
            pv = [p for p in pv.strip().split() if p]
        multi_pv = raw.get("multiPv") or raw.get("multi_pv") or raw.get("multipv") or raw.get("suggestions") or []

        return {
            "score": raw.get("score", raw.get("score_cp", 0)),
            "depth": raw.get("depth", 0),
            "nodes": raw.get("nodes", 0),
            "nps": raw.get("nps", 0),
            "best_move": str(best_move),
            "bestMove": str(best_move),
            "pv": pv if isinstance(pv, list) else [],
            "multiPv": multi_pv if isinstance(multi_pv, list) else [],
            "is_thinking": bool(raw.get("is_thinking", False)),
            "status": raw.get("status", "IDLE"),
        }
