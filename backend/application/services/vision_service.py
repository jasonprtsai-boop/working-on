import os
import time
from backend.infrastructure.vision.vision_system import vision_system
from backend.infrastructure.vision.detection.detection_result import Detection, BoundingBox
from backend.infrastructure.vision.fen.fen_generator import normalize_fen_turn
from backend.utils.logger import logger
from backend.events.models.base_event import BaseEvent
from backend.events.event_types import EventType
from backend.events.bus.event_bus import bus
from backend.observability.error_reporter import publish_error_diagnostic

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

    def on_ui_action(self, event: BaseEvent):
        """Handles manual UI triggers like vision sync."""
        payload = event.payload or {}
        action = payload.get("action")

        if action == "SYNC_VISION":
            try:
                fen, confidence = self.get_current_fen()
                board_state = self.get_board_state()
                logger.info(f"[VisionService] Manual sync requested. FEN: {fen}")

                # Broadast detection event to update StateManager
                bus.publish(BaseEvent.create(
                    event_type=EventType.VISION_MOVE_DETECTED,
                    payload={
                        "fen": fen,
                        "fen_valid": self._fen_valid(fen),
                        "ucci_position": f"position fen {fen}",
                        "board_state": board_state,
                        "detections": [],
                        "detections_count": 0,
                        "avg_confidence": confidence,
                        "min_confidence": confidence,
                        "confidence": confidence,
                        "latency_ms": 0.0,
                        "fps": 0.0,
                        "timestamp": time.time(),
                    },
                    source="vision_service"
                ))

                # Feedback to UI
                bus.publish(BaseEvent.create(
                    event_type=EventType.UI_TOAST,
                    payload={"text": "視覺同步完成。", "level": "success"},
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
        detections = [self._normalize_detection(item) for item in result.get("detections", [])]
        detections = [item for item in detections if item is not None]
        serialized_detections = [self._serialize_detection(item) for item in detections]
        avg_confidence, min_confidence = self._confidence_summary(detections)
        board_state = self._vision.mapper.map_detections(detections)
        turn = self._turn_from_payload(result)

        # 2. Temporal validation (smoothing/stability)
        stable_state = self._vision.validator.validate(board_state)

        # 3. If stable, generate FEN and publish event
        fen = result.get("fen") or ""
        stable_payload = None
        if stable_state:
            from backend.observability.tracing.trace_manager import TraceManager
            trace_id = getattr(event, "trace_id", None) or TraceManager.create_trace_id()
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
            }
            logger.info(f"[VisionService] New stable FEN: {fen} | Trace: {trace_id}")

            bus.publish(BaseEvent.create(
                event_type=EventType.VISION_MOVE_DETECTED,
                source="vision_service",
                payload=stable_payload,
                trace_id=trace_id
            ))

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

    def _serialize_detection(self, item: Detection) -> dict:
        bbox = getattr(item, "bbox", None)
        cell = self._cell_for_detection(item)
        return {
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
        state = self._vision.validator.last_stable_state
        confidence = getattr(self._vision.validator, "last_confidence", 0.95)
        if not state:
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
