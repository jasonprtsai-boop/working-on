from __future__ import annotations

import asyncio
from backend.runtime.lifecycle.base_worker import BaseWorker
from backend.runtime.messaging.queues import queue_manager
from backend.infrastructure.vision.pipeline import VisionPipeline
from backend.events.bus.event_bus import bus
from backend.events.event_types import EventType
from backend.events.models.base_event import BaseEvent
from backend.infrastructure.vision.fen.fen_generator import normalize_fen_turn
from backend.infrastructure.vision.capture_session import vision_capture_session
from backend.utils.logger import logger

class VisionInferenceWorker(BaseWorker):
    """
    [Runtime Layer] Vision Inference Worker (Industrial Pipeline Step 2).
    Reads frames from queue, processes through pipeline, and publishes results.
    """
    def __init__(self, pipeline: VisionPipeline):
        super().__init__("VisionInference")
        self.pipeline = pipeline

    async def run(self):
        logger.info("[VisionInferenceWorker] Started.")

        while self.is_running:
            try:
                action, _capture_snapshot = vision_capture_session.tick()
                if action in {"idle", "waiting"}:
                    await asyncio.sleep(0.05)
                    continue
                if action == "expired":
                    vision_capture_session.publish_status(
                        source="vision_inference_worker",
                        toast="影像辨識逾時，請重新確認棋子位置後再啟動辨識。",
                        level="warning",
                    )
                    await asyncio.sleep(0.05)
                    continue

                # 1. Get latest frame from queue (Blocking wait)
                try:
                    frame = await asyncio.wait_for(queue_manager.frame_queue.get(), timeout=0.2)
                except asyncio.TimeoutError:
                    vision_capture_session.mark_frame_unavailable()
                    vision_capture_session.publish_status(source="vision_inference_worker")
                    await asyncio.sleep(0.05)
                    continue

                # 2. Execute High-Performance Pipeline
                turn = self._current_turn_for_fen()
                expected_pieces = self._expected_piece_count()
                result = await self.pipeline.process(frame, turn=turn, expected_pieces=expected_pieces)

                if result:
                    vision_capture_session.mark_processed(latency_ms=result.latency_ms)
                    # 3. Publish results as events
                    # This drives state updates and robot commands
                    bus.publish(BaseEvent.create(
                        event_type=EventType.VISION_BOARD_DETECTED,
                        source="vision_inference_worker",
                        payload=result.to_dict(),
                    ))

                    if result.fen:
                        detections = [item.to_dict() for item in result.detections]
                        confidences = [float(item.confidence) for item in result.detections]
                        avg_confidence = round(sum(confidences) / len(confidences), 4) if confidences else 0.0
                        min_confidence = round(min(confidences), 4) if confidences else 0.0
                        bus.publish(BaseEvent.create(
                            event_type=EventType.VISION_MOVE_DETECTED,
                            source="vision_inference_worker",
                            payload={
                                "timestamp": result.timestamp,
                                "fen": result.fen,
                                "fen_after": result.fen,
                                "ucci_position": f"position fen {result.fen}",
                                "detections": detections,
                                "detections_count": len(detections),
                                "avg_confidence": avg_confidence,
                                "min_confidence": min_confidence,
                                "confidence": avg_confidence,
                                "latency_ms": result.latency_ms,
                                "move": None,
                            },
                        ))
                        if vision_capture_session.is_active():
                            vision_capture_session.stop(
                                reason="stable_vision_result",
                                result={
                                    "fen": result.fen,
                                    "detections_count": len(detections),
                                    "latency_ms": result.latency_ms,
                                },
                            )
                            vision_capture_session.publish_status(source="vision_inference_worker")

                # Yield control
                await asyncio.sleep(0.01)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[VisionInferenceWorker] Error: {e}")
                await asyncio.sleep(0.5)

        logger.info("[VisionInferenceWorker] Stopped.")

    def _current_turn_for_fen(self) -> str:
        try:
            from backend.state.store.state_store import state_store

            snapshot = state_store.to_dict()
            return normalize_fen_turn((snapshot.get("game") or {}).get("current_turn"))
        except Exception:
            return "w"

    def _expected_piece_count(self) -> int | None:
        try:
            from backend.state.store.state_store import state_store

            snapshot = state_store.to_dict()
            fen = (snapshot.get("game") or {}).get("current_fen")
            if not fen:
                return None

            # 計算 FEN 中代表棋子的英文字母數量
            board_part = fen.split()[0]
            count = sum(1 for char in board_part if char.isalpha())
            return count
        except Exception:
            return None
