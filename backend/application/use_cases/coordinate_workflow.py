from __future__ import annotations

import time
from typing import Any, Dict, Optional

from backend.application.container import container
from backend.application.services.system_preflight import build_preflight_report
from backend.core.rules import ChessLogic
from backend.events.bus.event_bus import bus
from backend.events.event_types import EventType
from backend.events.models.base_event import BaseEvent
from backend.infrastructure.vision.capture_session import vision_capture_session
from backend.state.store.state_store import state_store
from backend.utils import config
from backend.utils.fen.parser import fen_to_board
from backend.utils.logger import logger


class WorkflowCoordinator:
    """
    Minimal game workflow coordinator.

    This intentionally keeps the orchestration readable:
    vision result -> validate player move -> ask engine -> execute robot -> verify.
    The website only starts the round; TMflow only executes robot commands.
    """

    def __init__(self):
        self.active_workflows: Dict[str, Dict[str, Any]] = {}
        self._is_enabled = True
        self._started = False

    def start(self):
        if self._started:
            return
        bus.subscribe(EventType.VISION_MOVE_DETECTED, self.on_vision_move)
        bus.subscribe(EventType.ENGINE_ANALYSIS_COMPLETED, self.on_engine_complete)
        bus.subscribe(EventType.ROBOT_MOVE_COMPLETED, self.on_robot_complete)
        self._started = True
        logger.info("[WorkflowCoordinator] Minimal chess workflow subscribed.")

    def player_done(self, payload: Optional[dict] = None) -> str:
        payload = dict(payload or {})
        event = BaseEvent.create(
            event_type=EventType.DIAGNOSTICS_UPDATED,
            source="minimal_chess_workflow",
            payload={
                "module": "state",
                "status": "player_done",
                "message": "Player reported that the move is complete.",
                "workflow": {
                    "status": "player_done",
                    "message": "Player reported that the move is complete.",
                    "details": {"source": payload.get("source")},
                },
            },
            trace_id=payload.get("trace_id"),
        )
        workflow = self._workflow(event.trace_id)
        workflow["player_done_time"] = event.timestamp
        workflow["steps"].append("player_done")
        bus.publish(event)
        return event.trace_id

    def on_vision_move(self, event: BaseEvent):
        if not self._is_enabled:
            return

        payload = event.payload or {}
        trace_id = event.trace_id
        if self.is_game_over():
            self._publish_status(
                trace_id,
                "vision_ignored_game_over",
                "Vision result ignored because the game has already ended.",
                severity="info",
            )
            return

        workflow = self._workflow(trace_id)
        workflow["vision_time"] = self._payload_time(payload, fallback=event.timestamp)
        workflow["steps"].append("vision")

        if workflow.get("verify_pending"):
            self._handle_robot_verification(event, workflow)
            return

        move = payload.get("move")
        if not move:
            self._publish_status(
                trace_id,
                "detect_failed",
                "Vision did not produce a player move.",
                severity="warning",
            )
            return

        fen_before = payload.get("fen_before") or self._current_fen()
        if not ChessLogic.validate_move(fen_before, str(move)):
            workflow["player_move"] = move
            workflow["move_valid"] = False
            self._publish_status(
                trace_id,
                "move_invalid",
                f"Illegal player move detected: {move}",
                severity="warning",
                details={"move": move},
            )
            return

        fen_after = payload.get("fen_after") or payload.get("fen")
        if not fen_after:
            fen_after = ChessLogic.apply_move(fen_before, str(move))

        workflow["player_move"] = move
        workflow["fen_after_player"] = fen_after
        workflow["move_valid"] = True
        self._publish_status(
            trace_id,
            "player_move_valid",
            f"Player move accepted: {move}",
            details={"move": move},
        )

        game_result = self._game_result(fen_after)
        if game_result.get("ended"):
            self._publish_game_over(
                trace_id,
                game_result,
                message="Player move ended the game.",
                details={"move": move, "fen": fen_after},
            )
            return

        bus.publish(BaseEvent.create(
            event_type=EventType.ENGINE_ANALYSIS_REQUESTED,
            source="minimal_chess_workflow",
            payload={"mode": "start", "reason": "player_move_valid", "fen": fen_after},
            trace_id=trace_id,
        ))

    def on_engine_complete(self, event: BaseEvent):
        payload = event.payload or {}
        if payload.get("final") is not True:
            return
        if self.is_game_over():
            self._publish_status(
                event.trace_id,
                "engine_ignored_game_over",
                "Engine result ignored because the game has already ended.",
                severity="info",
            )
            return

        trace_id = event.trace_id
        workflow = self._workflow(trace_id)
        workflow["engine_time"] = event.timestamp
        workflow["steps"].append("engine")

        best_move = payload.get("best_move") or payload.get("bestmove") or payload.get("move")
        if not best_move or best_move == "none":
            game_result = self._game_result(payload.get("fen") or self._current_fen())
            if game_result.get("ended"):
                self._publish_game_over(trace_id, game_result, message="No legal AI move remains.")
                return
            self._publish_status(trace_id, "ai_no_move", "AI did not return a robot move.", severity="warning")
            return

        workflow["ai_move"] = best_move
        if not getattr(config, "AUTO_EXECUTE_ROBOT", False):
            self._publish_status(
                trace_id,
                "robot_waiting_manual_enable",
                f"AI move ready but AUTO_EXECUTE_ROBOT=false: {best_move}",
                details={"move": best_move},
            )
            return

        preflight = build_preflight_report(require_auto_execute=True)
        workflow["robot_preflight"] = self._preflight_summary(preflight)
        if not bool(preflight.get("ready", preflight.get("ok", False))):
            self._publish_status(
                trace_id,
                "robot_blocked_preflight_failed",
                "Robot execution blocked by system preflight.",
                severity="error",
                details=workflow["robot_preflight"],
            )
            return

        if not self._fresh_enough_for_robot(workflow, event):
            self._publish_status(
                trace_id,
                "robot_blocked_stale_vision",
                "Robot execution blocked because the vision result is stale.",
                severity="warning",
                details={"max_age_sec": float(getattr(config, "VISION_RESULT_MAX_AGE_SEC", 3.0))},
            )
            return

        robot = container.get("robot")
        if not robot or not hasattr(robot, "execute_move"):
            self._publish_status(
                trace_id,
                "robot_interface_missing",
                "Robot service does not expose execute_move.",
                severity="error",
            )
            return

        is_capture = self._infer_capture(str(best_move), payload)
        workflow["is_capture"] = is_capture
        self._publish_status(
            trace_id,
            "robot_command_started",
            f"Sending robot move: {best_move}",
            details={"move": best_move, "is_capture": is_capture},
        )
        ok = bool(robot.execute_move(str(best_move), is_capture=is_capture))
        if not ok:
            self._publish_status(
                trace_id,
                "robot_command_failed",
                f"Robot rejected move: {best_move}",
                severity="error",
                details={"move": best_move, "is_capture": is_capture},
            )

    def on_robot_complete(self, event: BaseEvent):
        payload = event.payload or {}
        trace_id = event.trace_id
        workflow = self._workflow(trace_id)
        workflow["robot_time"] = event.timestamp
        workflow["steps"].append("robot")

        if self.is_game_over():
            self._publish_status(
                trace_id,
                "robot_verify_skipped_game_over",
                "Robot verification skipped because the game has already ended.",
                severity="warning",
            )
            return

        if str(payload.get("status") or "success").lower() not in {"success", "done", "completed"}:
            self._publish_status(trace_id, "robot_failed", "Robot move completed with failure.", severity="error")
            return

        workflow["verify_pending"] = True
        if not vision_capture_session.is_active():
            vision_capture_session.start(
                source="verify_after_robot",
                trace_id=trace_id,
                timeout_sec=float(getattr(config, "VISION_USER_CAPTURE_TIMEOUT_SEC", 30.0)),
            )
            vision_capture_session.publish_status(
                source="minimal_chess_workflow",
                toast="機械手臂完成，開始驗證棋盤。",
                level="info",
            )
        self._publish_status(trace_id, "verify_started", "Robot move done; verification capture started.")

    def end_game_by_player(self, payload: Optional[dict] = None) -> dict:
        payload = dict(payload or {})
        trace_id = payload.get("trace_id")
        result = {
            "ended": True,
            "reason": "player_ended",
            "winner": None,
            "legal_moves_count": 0,
        }
        for workflow in self.active_workflows.values():
            workflow["verify_pending"] = False
            workflow["ended"] = True
            workflow["end_reason"] = "player_ended"

        capture_snapshot = None
        if vision_capture_session.is_active():
            capture_snapshot = vision_capture_session.stop(
                reason="player_ended_game",
                result={"game_result": result},
            )
            vision_capture_session.publish_status(source="minimal_chess_workflow")

        bus.publish(BaseEvent.create(
            event_type=EventType.ENGINE_ANALYSIS_REQUESTED,
            source="minimal_chess_workflow",
            payload={"mode": "stop", "reason": "player_ended"},
            trace_id=trace_id,
        ))
        game_over_trace_id = self._publish_game_over(
            trace_id,
            result,
            message="Player ended the game from the player page.",
            details={"source": payload.get("source"), "capture_session": capture_snapshot or {}},
        )
        return {"trace_id": game_over_trace_id, "game_result": result, "capture_session": capture_snapshot or {}}

    def is_game_over(self) -> bool:
        if str(self._current_game_status()).upper() == "GAME_OVER":
            return True
        return bool(self._game_result(self._current_fen()).get("ended"))

    def current_game_result(self) -> dict:
        game_result = self._game_result(self._current_fen())
        if str(self._current_game_status()).upper() == "GAME_OVER":
            game_result["ended"] = True
        return game_result

    def _handle_robot_verification(self, event: BaseEvent, workflow: Dict[str, Any]) -> None:
        payload = event.payload or {}
        trace_id = event.trace_id
        workflow["verify_pending"] = False
        workflow["verify_time"] = event.timestamp
        workflow["steps"].append("verify")

        observed_move = payload.get("move")
        expected_move = workflow.get("ai_move")
        fen_after = payload.get("fen_after") or payload.get("fen") or self._current_fen()
        if observed_move and expected_move and str(observed_move).lower() != str(expected_move).lower():
            self._publish_status(
                trace_id,
                "robot_verification_mismatch",
                "Robot verification detected a different move than the AI command.",
                severity="warning",
                details={"expected": expected_move, "observed": observed_move},
            )

        game_result = self._game_result(fen_after)
        if game_result.get("ended"):
            self._publish_game_over(
                trace_id,
                game_result,
                message="Robot move verified and ended the game.",
                details={"move": observed_move or expected_move, "fen": fen_after},
            )
            return

        self._publish_status(
            trace_id,
            "round_ready_for_player",
            "Robot move verified; waiting for the next player move.",
            details={"move": observed_move or expected_move, "fen": fen_after},
        )

    def _workflow(self, trace_id: str) -> Dict[str, Any]:
        workflow = self.active_workflows.setdefault(
            trace_id,
            {
                "start_time": time.time(),
                "steps": [],
            },
        )
        return workflow

    def _publish_status(
        self,
        trace_id: str,
        status: str,
        message: str,
        *,
        severity: str = "info",
        details: Optional[dict] = None,
    ) -> None:
        bus.publish(BaseEvent.create(
            event_type=EventType.DIAGNOSTICS_UPDATED,
            source="minimal_chess_workflow",
            payload={
                "module": "state",
                "status": status,
                "severity": severity,
                "message": message,
                "workflow": {
                    "status": status,
                    "message": message,
                    "details": details or {},
                },
            },
            trace_id=trace_id,
        ))

    def _publish_game_over(
        self,
        trace_id: str,
        game_result: dict,
        *,
        message: str,
        details: Optional[dict] = None,
    ) -> str:
        result = dict(game_result or {})
        result["ended"] = True
        event = BaseEvent.create(
            event_type=EventType.GAME_OVER,
            source="minimal_chess_workflow",
            payload={
                "status": "game_over",
                "message": message,
                "game_result": result,
                "details": details or {},
            },
            trace_id=trace_id,
        )
        bus.publish(event)
        self._publish_status(
            event.trace_id,
            "game_over",
            message,
            severity="info",
            details={"game_result": result, **(details or {})},
        )
        bus.publish(BaseEvent.create(
            event_type=EventType.UI_TOAST,
            source="minimal_chess_workflow",
            payload={"text": self._game_over_message(result), "level": "success"},
            trace_id=event.trace_id,
        ))
        return event.trace_id

    def _current_fen(self) -> str:
        try:
            return str((state_store.to_dict().get("game") or {}).get("fen") or "")
        except Exception:
            return ""

    def _current_game_status(self) -> str:
        try:
            return str((state_store.to_dict().get("game") or {}).get("game_status") or "")
        except Exception:
            return ""

    def _game_result(self, fen: str) -> dict:
        return ChessLogic.game_result(str(fen or ""))

    def _game_over_message(self, game_result: dict) -> str:
        winner = str((game_result or {}).get("winner") or "").lower()
        winner_label = {"red": "紅方", "black": "黑方"}.get(winner, "棋局")
        reason = str((game_result or {}).get("reason") or "game_over")
        if reason == "player_ended":
            return "對局已由玩家結束。"
        if winner not in {"red", "black"}:
            return "棋局結束。"
        if reason.endswith("_general_missing"):
            return f"棋局結束，{winner_label}獲勝。"
        if reason == "no_legal_moves":
            return f"棋局結束，{winner_label}獲勝：對方沒有合法步。"
        return f"棋局結束，{winner_label}獲勝。"

    def _payload_time(self, payload: dict, *, fallback: float) -> float:
        for key in ("source_timestamp", "vision_time", "stable_timestamp", "timestamp"):
            try:
                value = float(payload.get(key))
                if value > 0:
                    return value
            except (TypeError, ValueError, AttributeError):
                continue
        return float(fallback or time.time())

    def _fresh_enough_for_robot(self, workflow: Dict[str, Any], event: BaseEvent) -> bool:
        source_time = workflow.get("vision_time")
        if source_time is None:
            source_time = self._payload_time(event.payload or {}, fallback=event.timestamp)
            workflow["vision_time"] = source_time
        max_age = float(getattr(config, "VISION_RESULT_MAX_AGE_SEC", 3.0))
        return max_age <= 0 or max(0.0, time.time() - float(source_time)) <= max_age

    def _infer_capture(self, move: str, payload: dict) -> bool:
        explicit = payload.get("is_capture", payload.get("capture"))
        if explicit is not None:
            return self._coerce_bool(explicit)

        target = self._move_target_square(move)
        if target is None:
            return False

        for key in ("board", "board_state"):
            piece = self._piece_from_board(payload.get(key), *target)
            if piece not in (None, ""):
                return True

        for key in ("fen", "fen_before", "position_fen"):
            fen = payload.get(key)
            if not fen:
                continue
            try:
                piece = self._piece_from_board(fen_to_board(str(fen), empty=""), *target)
                if piece not in (None, ""):
                    return True
            except Exception:
                continue
        return False

    def _move_target_square(self, move: str):
        if not isinstance(move, str) or len(move) < 4:
            return None
        file_char = move[2]
        rank_char = move[3]
        if file_char not in "abcdefghi" or not rank_char.isdigit():
            return None
        rank = int(rank_char)
        if rank < 0 or rank > 9:
            return None
        return 9 - rank, "abcdefghi".index(file_char)

    def _piece_from_board(self, board, row: int, col: int):
        if isinstance(board, list) and 0 <= row < len(board):
            row_data = board[row]
            if isinstance(row_data, list) and 0 <= col < len(row_data):
                return row_data[col]
        if isinstance(board, dict):
            for key in (f"{row},{col}", f"{col},{row}"):
                if key in board:
                    return board.get(key)
        return None

    def _coerce_bool(self, value) -> bool:
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on", "capture", "captured"}
        return bool(value)

    def _preflight_summary(self, preflight: Dict[str, Any]) -> Dict[str, Any]:
        failures = preflight.get("failures") or [
            item for item in preflight.get("checks", []) or []
            if not item.get("ok") and item.get("severity") == "error"
        ]
        warnings = preflight.get("warnings") or [
            item for item in preflight.get("checks", []) or []
            if not item.get("ok") and item.get("severity") == "warning"
        ]
        return {
            "ready": bool(preflight.get("ready", preflight.get("ok", False))),
            "failures": [self._preflight_item(item) for item in failures],
            "warnings": [self._preflight_item(item) for item in warnings],
        }

    def _preflight_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "key": item.get("key"),
            "label": item.get("label"),
            "message": item.get("message"),
            "severity": item.get("severity"),
        }


workflow_coordinator = WorkflowCoordinator()
