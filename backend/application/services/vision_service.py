import time
from backend.infrastructure.vision.vision_system import vision_system
from backend.infrastructure.vision.detection.detection_result import Detection, BoundingBox
from backend.infrastructure.vision.fen.fen_generator import normalize_fen_turn
from backend.utils.logger import logger
from backend.events.models.base_event import BaseEvent
from backend.events.event_types import EventType
from backend.events.bus.event_bus import bus
from backend.observability.error_reporter import publish_error_diagnostic
from backend.infrastructure.vision.capture_session import vision_capture_session
from backend.infrastructure.vision.confidence_estimator import ConfidenceEstimator
from backend.utils.fen.parser import (
    BLACK_PIECES,
    RED_PIECES,
    count_board_piece_types,
    count_fen_piece_types,
    count_fen_pieces,
    validate_piece_count,
    validate_piece_types,
)

class VisionService:
    """
    [Perception Layer] Reactive Vision Service.
    Subscribes to raw inference results and performs post-processing (mapping, validation).
    """
    def __init__(self):
        self._vision = vision_system
        self.is_running = False
        self._setup_subscriptions()

    def _setup_subscriptions(self):
        # Reactive: respond to raw board detections from InferenceWorker
        bus.subscribe(EventType.VISION_BOARD_DETECTED, self.on_board_detected)
        bus.subscribe(EventType.UI_ACTION, self.on_ui_action)

    def _vision_status(self) -> dict:
        if hasattr(self._vision, "get_status"):
            try:
                status = self._vision.get_status()
                return dict(status) if isinstance(status, dict) else {}
            except Exception:
                logger.debug("[VisionService] vision status unavailable", exc_info=True)
        return {}

    def _ensure_vision_available(self) -> dict:
        status = self._vision_status()
        unavailable = (
            status.get("mode") == "unavailable"
            or bool(status.get("startup_failure"))
            or status.get("available") is False
        )
        if unavailable:
            reason = status.get("startup_error") or status.get("last_error") or "real vision is unavailable"
            raise RuntimeError(f"Vision system unavailable: {reason}")
        return status

    def on_ui_action(self, event: BaseEvent):
        """Handles manual UI triggers like vision sync and emergency force sync."""
        payload = event.payload or {}
        action = payload.get("action")

        if action in ("SYNC_VISION", "FORCE_SYNC"):
            try:
                # 1. Reset temporal validator history so stale frames do not pollute
                if hasattr(self._vision, "validator") and hasattr(self._vision.validator, "reset"):
                    self._vision.validator.reset()

                fen = ""
                confidence = 0.95
                board_state = {}
                from backend.infrastructure.vision.camera.frame_buffer import frame_buffer

                frame = frame_buffer.peek_latest_raw()
                if frame is None:
                    frame = frame_buffer.get_latest_raw(timeout=0.2)
                if frame is not None and hasattr(self._vision, "worker") and hasattr(self._vision.worker, "process_frame"):
                    detection_payload = self._vision.worker.process_frame(frame, publish=False)
                    raw_items = detection_payload.get("detections", [])
                    normalized = [self._normalize_detection(d) for d in raw_items]
                    detections = [d for d in normalized if d is not None]
                    board_state = self._vision.mapper.map_detections(detections)
                    turn = self._turn_from_payload(allow_state_fallback=True)
                    fen = self._generate_fen(board_state, turn=turn)
                    if hasattr(self._vision, "validator"):
                        self._vision.validator.last_stable_state = dict(board_state)
                        self._vision.validator.last_confidence = confidence
                else:
                    fen, confidence = self.get_current_fen()
                    board_state = self.get_board_state()

                turn_val = self._turn_from_payload(allow_state_fallback=True)
                piece_eval = self._evaluate_detected_pieces(board_state, turn=turn_val)
                logger.info(f"[VisionService] Force sync requested. FEN: {fen} | Piece count: {piece_eval.get('total')}/{piece_eval.get('expected')} | {piece_eval.get('summary_message')}")

                # Broadcast detection event to update StateManager
                bus.publish(BaseEvent.create(
                    event_type=EventType.VISION_MOVE_DETECTED,
                    payload={
                        "fen": fen,
                        "fen_valid": self._fen_valid(fen),
                        "ucci_position": f"position fen {fen}",
                        "board_state": board_state,
                        "detections": [],
                        "detections_count": piece_eval.get("total", len(board_state)),
                        "avg_confidence": confidence,
                        "min_confidence": confidence,
                        "confidence": confidence,
                        "latency_ms": 0.0,
                        "fps": 0.0,
                        "timestamp": time.time(),
                        "piece_counts": piece_eval,
                        "force_sync": True,
                    },
                    source="vision_service"
                ))

                # Feedback to UI
                summary_text = piece_eval.get("summary_message", "")
                if piece_eval.get("valid", True):
                    toast_text = f"緊急棋局校正完成：{summary_text}" if summary_text else f"緊急棋局校正完成：共 {piece_eval.get('total')}/{piece_eval.get('expected')} 顆棋子，棋局已校準。"
                    toast_level = "success"
                else:
                    toast_text = f"緊急棋局校正提示：{summary_text}" if summary_text else f"緊急棋局校正提示：棋子數量不符（預期 {piece_eval.get('expected')}，目前 {piece_eval.get('total')} 顆），請檢查棋盤。"
                    toast_level = "warning"

                bus.publish(BaseEvent.create(
                    event_type=EventType.UI_TOAST,
                    payload={"text": toast_text, "level": toast_level},
                    source="vision_service"
                ))
            except Exception as e:
                logger.error(f"[VisionService] Sync failed: {e}", exc_info=True)
                publish_error_diagnostic(
                    source="vision_service",
                    module="vision",
                    code="manual_sync_failed",
                    message=str(e),
                    severity="warning",
                    status="warning",
                    recoverable=True,
                )
                bus.publish(BaseEvent.create(
                    event_type=EventType.UI_TOAST,
                    payload={"text": "視覺同步失敗。", "level": "error"},
                    source="vision_service"
                ))

    def on_board_detected(self, event: BaseEvent):
        """Processes raw detection results from the InferenceWorker."""
        result = event.payload
        if not result: return

        # 1. Map detections to board grid
        normalized_items = []
        for raw_item in result.get("detections", []):
            detection = self._normalize_detection(raw_item)
            if detection is not None:
                normalized_items.append((detection, raw_item))
        detections = [item for item, _raw_item in normalized_items]
        serialized_detections = [
            self._serialize_detection(item, source=raw_item)
            for item, raw_item in normalized_items
        ]
        avg_confidence, min_confidence = self._confidence_summary(detections)
        board_state = self._vision.mapper.map_detections(detections)
        turn = self._turn_from_payload(result, allow_state_fallback=True)

        # 1b. Evaluate piece counts and types against game expectation
        piece_eval = self._evaluate_detected_pieces(board_state, detections=detections, turn=turn)
        if not piece_eval.get("valid", True):
            publish_error_diagnostic(
                source="vision_service",
                module="vision",
                code="piece_count_mismatch",
                message=piece_eval.get("summary_message") or (
                    f"棋子種類或數量不符：預期 {piece_eval['expected']} 顆（吃子則為 {piece_eval['expected']-1} 顆），"
                    f"目前辨識到 {piece_eval['total']} 顆（紅 {piece_eval['red']} / 黑 {piece_eval['black']}）。"
                ),
                severity="warning",
                status="warning",
                recoverable=True,
                details=piece_eval,
            )

        # 2. Temporal validation (smoothing/stability)
        stable_state = self._vision.validator.validate(board_state, turn=turn)
        reconciliation = self._validator_reconciliation()

        # 3. If stable, generate FEN and publish event
        fen = result.get("fen") or ""
        stable_payload = None
        if stable_state:
            from backend.observability.tracing.trace_manager import TraceManager
            capture_session = vision_capture_session.snapshot()
            capture_trace_id = (
                capture_session.get("trace_id")
                if capture_session.get("active")
                else None
            )
            trace_id = capture_trace_id or getattr(event, "trace_id", None) or TraceManager.create_trace_id()
            fen = self._generate_fen(stable_state, turn=turn)
            fen_valid = self._fen_valid(fen)
            source_timestamp = self._coerce_timestamp(result.get("timestamp"), fallback=event.timestamp)
            timestamp = time.time()
            latency_ms = float(result.get("latency_ms", 0.0) or 0.0)
            stable_payload = {
                "timestamp": timestamp,
                "source_timestamp": source_timestamp,
                "stable_timestamp": timestamp,
                "vision_age_ms": round(max(0.0, timestamp - source_timestamp) * 1000.0, 3),
                "trace_id": trace_id,
                "fen": fen,
                "fen_after": fen,
                "fen_valid": fen_valid,
                "ucci_position": f"position fen {fen}",
                "board_state": stable_state,
                "detections": serialized_detections,
                "detections_count": len(serialized_detections),
                "avg_confidence": avg_confidence,
                "min_confidence": min_confidence,
                "confidence": avg_confidence,
                "latency_ms": latency_ms,
                "fps": self._fps_from_latency(latency_ms),
                "reconciliation": reconciliation,
                "piece_counts": piece_eval,
            }
            if reconciliation.get("accepted") and reconciliation.get("move"):
                stable_payload.update({
                    "move": reconciliation.get("move"),
                    "inferred_move": True,
                    "is_capture": bool(reconciliation.get("is_capture")),
                })
            logger.info(f"[VisionService] New stable FEN: {fen} | Trace: {trace_id} | Pieces: {piece_eval.get('total')}/{piece_eval.get('expected')}")

            bus.publish(BaseEvent.create(
                event_type=EventType.VISION_MOVE_DETECTED,
                source="vision_service",
                payload=stable_payload,
                trace_id=trace_id
            ))
            if vision_capture_session.is_active():
                vision_capture_session.stop(
                    reason="stable_vision_result",
                    result={
                        "fen": fen,
                        "trace_id": trace_id,
                        "move": stable_payload.get("move"),
                        "detections_count": len(serialized_detections),
                        "latency_ms": latency_ms,
                        "reconciliation": reconciliation,
                        "piece_counts": piece_eval,
                    },
                )
                vision_capture_session.publish_status(source="vision_service")

        # 4. Diagnostics/UI heartbeat
        timestamp = self._coerce_timestamp(result.get("timestamp"), fallback=time.time())
        latency_ms = float(result.get("latency_ms", 0.0) or 0.0)
        bus.publish(BaseEvent.create(
            event_type=EventType.VISION_FRAME_PROCESSED,
            source="vision_service",
            payload={
                "timestamp": timestamp,
                "processed_timestamp": time.time(),
                "trace_id": getattr(event, "trace_id", ""),
                "fen": fen,
                "fen_after": fen,
                "fen_valid": self._fen_valid(fen),
                "ucci_position": f"position fen {fen}" if fen else "",
                "board_state": stable_state or board_state,
                "latency_ms": latency_ms,
                "fps": self._fps_from_latency(latency_ms),
                "detections": serialized_detections,
                "detections_count": len(detections),
                "avg_confidence": avg_confidence,
                "min_confidence": min_confidence,
                "confidence": avg_confidence,
                "stable": stable_payload is not None,
                "reconciliation": reconciliation,
                "piece_counts": piece_eval,
            }
        ))

    def _normalize_detection(self, item):
        if isinstance(item, Detection):
            return item
        if not isinstance(item, dict):
            return None

        bbox = item.get("bbox")
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            return None

        return Detection(
            class_id=int(item.get("class_id", 0) or 0),
            class_name=str(item.get("class_name", "")),
            confidence=float(item.get("confidence", 0.0) or 0.0),
            bbox=BoundingBox(
                x1=float(bbox[0]),
                y1=float(bbox[1]),
                x2=float(bbox[2]),
                y2=float(bbox[3]),
            ),
        )

    def _serialize_detection(self, item: Detection, *, source=None) -> dict:
        bbox = getattr(item, "bbox", None)
        cell = self._cell_for_detection(item)
        payload = {
            "class_id": getattr(item, "class_id", 0),
            "class_name": getattr(item, "class_name", ""),
            "confidence": getattr(item, "confidence", 0.0),
            "bbox": [
                getattr(bbox, "x1", 0.0),
                getattr(bbox, "y1", 0.0),
                getattr(bbox, "x2", 0.0),
                getattr(bbox, "y2", 0.0),
            ],
            "cell": cell,
        }
        if isinstance(source, dict):
            for key in (
                "robot_anchor_point",
                "robot_coordinate_space",
                "vision_to_robot_coordinate_space",
                "raw_anchor_point",
                "raw_coordinate_space",
            ):
                if key in source:
                    payload[key] = source.get(key)
        return payload

    def _cell_for_detection(self, item: Detection):
        bbox = getattr(item, "bbox", None)
        mapper = getattr(self._vision, "mapper", None)
        coord_system = getattr(mapper, "coord_system", None)
        if bbox is None or coord_system is None:
            return None
        try:
            col, row = coord_system.pixel_to_cell(*bbox.center)
            return {"col": col, "row": row, "key": f"{col},{row}"}
        except Exception:
            return None

    def _confidence_summary(self, detections):
        values = []
        for item in detections:
            try:
                values.append(float(getattr(item, "confidence", 0.0) or 0.0))
            except (TypeError, ValueError):
                continue
        if not values:
            return 0.0, 0.0
        return round(sum(values) / len(values), 4), round(min(values), 4)

    def _validator_reconciliation(self) -> dict:
        report = getattr(self._vision.validator, "last_reconciliation", {})
        return dict(report) if isinstance(report, dict) else {}

    def _fen_valid(self, fen: str) -> bool:
        if not fen:
            return False
        try:
            from backend.state.store.validators.fen_validator import FENValidator
            return bool(FENValidator.validate(fen))
        except Exception:
            return False

    def _fps_from_latency(self, latency_ms: float) -> float:
        try:
            latency = float(latency_ms)
        except (TypeError, ValueError):
            return 0.0
        if latency <= 0:
            return 0.0
        return round(1000.0 / latency, 3)

    def _coerce_timestamp(self, value, *, fallback: float) -> float:
        try:
            timestamp = float(value)
            if timestamp > 0:
                return timestamp
        except (TypeError, ValueError):
            pass
        return float(fallback)

    def get_current_fen(self) -> tuple[str, float]:
        """Returns the last validated stable FEN string and confidence."""
        status = self._ensure_vision_available()
        state = self._vision.validator.last_stable_state
        confidence = getattr(self._vision.validator, "last_confidence", 0.95)
        if not state:
            if not bool(status.get("simulation")):
                raise RuntimeError("No stable real vision state is available yet.")
            turn = self._turn_from_payload(allow_state_fallback=True)
            return f"rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR {turn} - - 0 1", confidence
        return self._generate_fen(state, turn=self._turn_from_payload(allow_state_fallback=True)), confidence

    def get_board_state(self):
        return self._vision.validator.last_stable_state or {}

    def _generate_fen(self, board_state, turn: str = "w") -> str:
        try:
            return self._vision.fen_gen.generate(board_state, turn=turn)
        except TypeError:
            return self._vision.fen_gen.generate(board_state)

    def _turn_from_payload(self, payload=None, *, allow_state_fallback: bool = False) -> str:
        if isinstance(payload, dict):
            for key in ("current_turn", "turn", "side_to_move"):
                value = payload.get(key)
                if value:
                    return normalize_fen_turn(value)

            fen = payload.get("fen") or payload.get("fen_after") or payload.get("fen_before")
            if isinstance(fen, str):
                parts = fen.split()
                if len(parts) >= 2:
                    return normalize_fen_turn(parts[1])

        if not allow_state_fallback:
            return "w"

        try:
            from backend.state.store.state_store import state_store

            snapshot = state_store.to_dict()
            return normalize_fen_turn((snapshot.get("game") or {}).get("current_turn"))
        except Exception:
            return "w"

    def _get_expected_fen(self) -> str:
        try:
            from backend.state.store.state_store import state_store

            fen = getattr(getattr(state_store.current, "game", None), "fen", "")
            if fen and isinstance(fen, str) and fen.strip():
                return fen.strip()
        except Exception:
            pass
        return "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"

    def _get_expected_piece_count(self) -> int:
        fen = self._get_expected_fen()
        counted = count_fen_pieces(fen).get("total", 32)
        return int(counted) if counted > 0 else 32

    def _evaluate_detected_pieces(self, board_state: dict, detections=None, turn: str = "w") -> dict:
        expected_fen = self._get_expected_fen()
        expected_types = count_fen_piece_types(expected_fen)
        actual_types = count_board_piece_types(board_state)

        eval_result = validate_piece_types(
            actual_types,
            expected_types,
            moving_side=turn,
            allow_capture=True,
        )
        count_conf = ConfidenceEstimator.estimate(
            detections if detections is not None else eval_result["total"],
            expected_count=eval_result["expected"],
            allow_capture=True,
        )
        eval_result["confidence"] = count_conf
        return eval_result
