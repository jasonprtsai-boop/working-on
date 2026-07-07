import time
from typing import Dict, Any, Optional
from backend.events.bus.event_bus import bus
from backend.events.event_types import EventType
from backend.events.models.base_event import BaseEvent
from backend.application.container import container
from backend.utils import config
from backend.utils.logger import logger

class WorkflowCoordinator:
    """
    [Application Layer] High-Level Orchestrator
    Manages the E2E execution pipeline: Vision -> AI -> Robot.
    Includes telemetry tracking and fault tolerance.
    """

    def __init__(self):
        self.active_workflows: Dict[str, Dict[str, Any]] = {}
        self._is_enabled = True

    def start(self):
        """Subscribe to core events to drive the automated loop."""
        bus.subscribe(EventType.VISION_MOVE_DETECTED, self.on_vision_move)
        bus.subscribe(EventType.ENGINE_ANALYSIS_COMPLETED, self.on_engine_complete)
        bus.subscribe(EventType.ROBOT_MOVE_COMPLETED, self.on_robot_complete)
        logger.info("[WorkflowCoordinator] Subscribed to automated pipeline events.")

    def on_vision_move(self, event: BaseEvent):
        """Step 1: Vision detected a move. Pipeline starts."""
        if not self._is_enabled: return

        trace_id = event.trace_id
        payload = event.payload or {}
        vision_time = self._event_source_timestamp(event)
        logger.info(f"[Workflow] Pipeline started. Trace: {trace_id}")

        self.active_workflows[trace_id] = {
            "start_time": time.time(),
            "vision_time": vision_time,
            "vision_event_time": event.timestamp,
            "vision_age_ms": payload.get("vision_age_ms"),
            "steps": ["vision"]
        }

        # In a fully automated system, we might trigger engine computation here,
        # but currently EngineWorker polls the state.
        # We'll wait for ENGINE_ANALYSIS_COMPLETED to act.

    def on_engine_complete(self, event: BaseEvent):
        """Step 2: AI analysis finished. Trigger robot if move found."""
        payload = event.payload or {}
        if payload.get("final") is not True:
            logger.info("[Workflow] Ignoring non-final engine analysis event.")
            return

        trace_id = event.trace_id
        if trace_id not in self.active_workflows:
            # Maybe it's a manual move or from a previous session
            self.active_workflows[trace_id] = {"start_time": time.time(), "steps": []}

        wf = self.active_workflows[trace_id]
        wf["engine_time"] = event.timestamp
        wf["steps"].append("engine")

        best_move = payload.get("best_move")
        if best_move and best_move != "none":
            if not getattr(config, "AUTO_EXECUTE_ROBOT", False):
                logger.info(f"[Workflow] AUTO_EXECUTE_ROBOT=false; robot execution skipped for {best_move}.")
                return
            if not self._is_fresh_enough_for_robot(wf, event):
                age = self._workflow_source_age(wf, event)
                logger.warning(
                    "[Workflow] Refusing robot execution for stale vision trace %s (age=%.2fs, limit=%.2fs).",
                    trace_id,
                    age,
                    float(getattr(config, "VISION_RESULT_MAX_AGE_SEC", 3.0)),
                )
                return

            logger.info(f"[Workflow] AI move found: {best_move}. Triggering Robot.")

            robot_service = container.get("robot")
            if robot_service and hasattr(robot_service, "execute_move"):
                is_capture = self._infer_capture(best_move, payload)
                wf["is_capture"] = is_capture
                if not robot_service.execute_move(best_move, is_capture=is_capture):
                    logger.warning("[Workflow] RobotFacade.execute_move returned false.")
            elif robot_service:
                logger.error("[Workflow] Robot service does not expose the active execute_move authority.")
            else:
                logger.warning("[Workflow] Robot service not found.")

    def _infer_capture(self, move: str, payload: dict) -> bool:
        explicit = payload.get("is_capture", payload.get("capture"))
        if explicit is not None:
            return self._coerce_bool(explicit)

        target = self._move_target_square(move)
        if target is None:
            return False

        try:
            piece = self._piece_at_square(*target, payload=payload)
            return piece not in (None, "")
        except Exception as exc:
            logger.debug(f"[Workflow] capture inference skipped for {move}: {exc}", exc_info=True)
            return False

    def _coerce_bool(self, value) -> bool:
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on", "capture", "captured"}
        return bool(value)

    def _event_source_timestamp(self, event: BaseEvent) -> float:
        source_timestamp = self._payload_source_timestamp(event)
        if source_timestamp is not None:
            return source_timestamp
        return float(event.timestamp or time.time())

    def _payload_source_timestamp(self, event: BaseEvent) -> Optional[float]:
        payload = event.payload or {}
        for key in ("source_timestamp", "vision_time", "stable_timestamp", "timestamp"):
            try:
                value = float(payload.get(key))
                if value > 0:
                    return value
            except (TypeError, ValueError, AttributeError):
                continue
        return None

    def _workflow_source_age(self, wf: Dict[str, Any], event: BaseEvent) -> float:
        source_time = wf.get("vision_time")
        if source_time is None:
            source_time = self._payload_source_timestamp(event)
        if source_time is None:
            return float("inf")
        try:
            return max(0.0, time.time() - float(source_time))
        except (TypeError, ValueError):
            return float("inf")

    def _is_fresh_enough_for_robot(self, wf: Dict[str, Any], event: BaseEvent) -> bool:
        if "vision_time" not in wf:
            source_time = self._payload_source_timestamp(event)
            if source_time is None:
                logger.warning("[Workflow] Refusing robot execution because no vision timestamp is attached to this trace.")
                return False
            wf["vision_time"] = source_time
        max_age = float(getattr(config, "VISION_RESULT_MAX_AGE_SEC", 3.0))
        if max_age <= 0:
            return True
        return self._workflow_source_age(wf, event) <= max_age

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

    def _piece_at_square(self, row: int, col: int, payload: Optional[dict] = None):
        if isinstance(payload, dict):
            for key in ("board", "board_state"):
                piece = self._piece_from_board(payload.get(key), row, col)
                if piece not in (None, ""):
                    return piece

            for key in ("fen", "fen_before", "position_fen"):
                fen = payload.get(key)
                if fen:
                    from backend.utils.fen.parser import fen_to_board

                    return self._piece_from_board(fen_to_board(fen), row, col)

            if not payload.get("infer_capture_from_state"):
                return None

        snapshot = self._state_snapshot()
        game = snapshot.get("game") if isinstance(snapshot, dict) else {}
        board = game.get("board") if isinstance(game, dict) else None
        piece = self._piece_from_board(board, row, col)
        if piece not in (None, ""):
            return piece

        fen = game.get("fen") if isinstance(game, dict) else None
        if fen:
            from backend.utils.fen.parser import fen_to_board

            return self._piece_from_board(fen_to_board(fen), row, col)
        return None

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

    def _state_snapshot(self):
        try:
            state = container.get("state")
            if hasattr(state, "to_dict"):
                return state.to_dict()
            if hasattr(state, "current") and hasattr(state.current, "to_dict"):
                return state.current.to_dict()
        except Exception:
            return {}

        return {}

    def on_robot_complete(self, event: BaseEvent):
        """Step 3: Robot finished moving. Workflow complete."""
        trace_id = event.trace_id
        if trace_id in self.active_workflows:
            wf = self.active_workflows[trace_id]
            wf["robot_time"] = event.timestamp
            wf["steps"].append("robot")

            duration = time.time() - wf["start_time"]
            logger.info(f"[Workflow] Pipeline COMPLETE. Trace: {trace_id}. Total Latency: {duration:.2f}s")

            # Publish Telemetry Event
            bus.publish(BaseEvent.create(
                event_type="TELEMETRY.PIPELINE_COMPLETE",
                source="workflow_coordinator",
                payload={
                    "total_duration": duration,
                    "steps": wf["steps"],
                    "trace_id": trace_id
                }
            ))

            # Cleanup
            del self.active_workflows[trace_id]

workflow_coordinator = WorkflowCoordinator()
