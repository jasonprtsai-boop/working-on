import base64
import os
import time
import threading
from typing import Optional

from backend.utils.logger import logger
from backend.utils import config


class _FallbackValidator:
    last_stable_state = None


class _FallbackFENGen:
    def generate(self, _state, turn="w") -> str:
        side = "b" if str(turn or "").strip().lower() in ("b", "black") else "w"
        return f"rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR {side} - - 0 1"


class MockVisionSystem:
    """
    [Simulation Layer] Interactive Mock Vision System.
    Emits simulated vision events triggered by UI actions.
    """
    def __init__(self):
        self.validator = _FallbackValidator()
        self.fen_gen = _FallbackFENGen()
        self._jpg_bytes = base64.b64decode(
            "/9j/4AAQSkZJRgABAQAAZABkAAD/2wCEABQQEBkSGScXFycyJh8mMi4mJiYmLj41NTU1NT5EQUFBQUFBREREREREREREREREREREREREREREREREREREQBFRkZIBwgJhgYJjYmICY2RDYrKzZERERCNUJERERERERERERERERERERERERERERERERERERERERERERERERERP/AABEIAAEAAQMBIgACEQEDEQH/xABMAAEBAAAAAAAAAAAAAAAAAAAABQEBAQAAAAAAAAAAAAAAAAAABQYQAQAAAAAAAAAAAAAAAAAAAAARAQAAAAAAAAAAAAAAAAAAAAD/2gALAwEAAhEDEQA/AJQA9Yv/2Q=="
        )
        self._pending_fen = None
        self._setup_subscriptions()

    def _setup_subscriptions(self):
        # We handle this via late import to avoid circular dependencies
        try:
            from backend.events.bus import bus
            from backend.events.event_types import EventType
            bus.subscribe(EventType.UI_ACTION, self.on_ui_action)
        except Exception:
            pass

    def on_ui_action(self, event):
        payload = event.payload or {}
        if payload.get("action") == "MOCK_VISION_MOVE":
            self._pending_fen = payload.get("fen")
            logger.info(f"[MockVision] Simulated move detected: {self._pending_fen}")

    def start(self) -> bool:
        logger.info("[VisionSystem] Running in INTERACTIVE MOCK mode.")
        return True

    def stop(self): pass
    def update_corners(self, _corners): pass

    def step(self) -> Optional[str]:
        if self._pending_fen:
            res = self._pending_fen
            self._pending_fen = None
            return res
        return None

    def get_video_stream(self):
        boundary = b"frame"
        header_prefix = b"--" + boundary + b"\r\nContent-Type: image/jpeg\r\nContent-Length: "
        try:
            while True:
                jpg = self._jpg_bytes
                yield header_prefix + str(len(jpg)).encode("ascii") + b"\r\n\r\n" + jpg + b"\r\n"
                time.sleep(1.0)
        except GeneratorExit:
            raise

    def get_status(self) -> dict:
        return {
            "system": "MockVisionSystem",
            "fallback": True,
            "running": True,
            "camera": {"running": True, "opened": True, "index": -1},
            "detector": {"name": "MockDetector", "loaded": True},
        }


def _build_real_vision_system():
    # Local imports so the module can still be imported without numpy/opencv installed.
    import numpy as np  # noqa: F401

    from .camera.camera_manager import CameraManager
    from .camera.frame_buffer import frame_buffer
    from .preprocess.image_preprocessor import ImagePreprocessor, PerspectiveCorrector
    from .detection.sahi_detector import SAHIDetector
    from .detection.grid_detector import GridDetector
    from .board.board_mapper import BoardMapper
    from .board.coordinate_system import BoardCoordinateSystem, GridConfig
    from .validation.temporal_validator import TemporalValidator
    from .fen.fen_generator import FENGenerator
    from .debug.overlay_renderer import OverlayRenderer
    from .overlay.overlay_manager import OverlayManager
    from .stream.mjpeg_stream import MJPEGStreamer
    from backend.events.bus.event_bus import bus
    from backend.events.event_types import EventType
    from backend.events.models.base_event import BaseEvent

    class InferenceWorker:
        def __init__(self, detector, preprocessor, corrector):
            self.detector = detector
            self.preprocessor = preprocessor
            self.corrector = corrector
            self._corners = None
            self._thread: Optional[threading.Thread] = None
            self._stop = threading.Event()

        def start(self):
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, daemon=True, name="VisionInferenceLoop")
            self._thread.start()

        def stop(self):
            self._stop.set()
            if self._thread and threading.current_thread() is not self._thread:
                self._thread.join(timeout=3.0)
                if self._thread.is_alive():
                    logger.warning("[VisionSystem] inference worker did not stop within 3s.")
                else:
                    self._thread = None

        def update_corners(self, corners):
            self._corners = corners

        def _run(self):
            while not self._stop.is_set():
                frame = frame_buffer.get_raw(timeout=0.1)
                if frame is None:
                    time.sleep(0.02)
                    continue

                try:
                    start = time.time()
                    work_frame = frame
                    if self._corners is not None:
                        work_frame = self.corrector.warp(
                            frame,
                            self._corners,
                            output_size=(config.WARP_WIDTH, config.WARP_HEIGHT),
                        )

                    processed = self.preprocessor.process(work_frame)
                    detections = self.detector.detect(processed if processed is not None else work_frame)
                    latency_ms = (time.time() - start) * 1000.0
                    payload = {
                        "work_frame": work_frame,
                        "detections": [item.to_dict() for item in detections],
                        "latency_ms": latency_ms,
                    }
                    frame_buffer.put_detection(payload)
                    bus.publish(
                        BaseEvent.create(
                            event_type=EventType.VISION_BOARD_DETECTED,
                            source="vision_system",
                            payload={
                                "detections": payload["detections"],
                                "latency_ms": latency_ms,
                            },
                        )
                    )
                except Exception as exc:
                    logger.debug(f"[VisionSystem] inference loop failed: {exc}", exc_info=True)
                    time.sleep(0.2)

    class VisionSystem:
        """
        [Vision System v6.0]
        Real-time AI Vision Streaming Architecture.
        """

        def __init__(self):
            self.camera = CameraManager()
            self.preprocessor = ImagePreprocessor()
            self.corrector = PerspectiveCorrector()
            self.detector = self._select_detector()
            self.worker = InferenceWorker(self.detector, self.preprocessor, self.corrector)
            self.last_frame_processed = None

            grid_config = GridConfig(
                rows=config.BOARD_ROWS,
                cols=config.BOARD_COLS,
                width=config.WARP_WIDTH,
                height=config.WARP_HEIGHT,
            )
            self.coord_system = BoardCoordinateSystem(grid_config)
            self.mapper = BoardMapper(self.coord_system)
            self.validator = TemporalValidator(window_size=config.STABILITY_THRESHOLD)
            self.fen_gen = FENGenerator(rows=config.BOARD_ROWS, cols=config.BOARD_COLS)

            self.renderer = OverlayRenderer(self.coord_system)
            self.overlay_manager = OverlayManager(self.renderer)
            self.streamer = MJPEGStreamer(self.overlay_manager)
            self.board_corners = None

        def _select_detector(self):
            model_path = os.path.abspath(getattr(config, "YOLO_MODEL_PATH", "") or "")
            if getattr(SAHIDetector, "__name__", "") and getattr(SAHIDetector, "load_model", None):
                try:
                    from .detection.sahi_detector import SAHI_AVAILABLE  # type: ignore
                except Exception:
                    SAHI_AVAILABLE = False  # noqa: N806

                if SAHI_AVAILABLE and model_path and os.path.exists(model_path):
                    logger.info(f"[VisionSystem] Using SAHI detector with model: {model_path}")
                    detector = SAHIDetector(model_path=model_path)
                    if getattr(detector, "model", None) is not None:
                        return detector
                    logger.warning("[VisionSystem] SAHI model failed to load; falling back to GridDetector.")

            logger.info("[VisionSystem] Using GridDetector (TensorFlow SavedModel classifier when available).")
            return GridDetector()

        def start(self):
            if self.camera.start():
                self.worker.start()
                logger.info(f"Vision System started (detector={self.detector.__class__.__name__}).")
                return True
            return False

        def stop(self):
            self.worker.stop()
            self.camera.stop()
            logger.info("Vision System stopped.")

        def set_camera_index(self, camera_index: int) -> bool:
            ok = self.camera.set_camera_index(camera_index)
            if ok:
                try:
                    config.CAMERA_INDEX = int(camera_index)
                except Exception:
                    pass
            return bool(ok)

        def update_corners(self, corners):
            self.board_corners = corners
            self.worker.update_corners(corners)

        def get_video_stream(self):
            return self.streamer.generate()

        def get_status(self) -> dict:
            model_path = os.path.abspath(getattr(config, "YOLO_MODEL_PATH", "") or "")
            detector_status = {}
            if hasattr(self.detector, "get_status"):
                try:
                    detector_status = self.detector.get_status()
                except Exception as exc:
                    detector_status = {"last_error": str(exc)}
            camera_status = {}
            if hasattr(self.camera, "get_status"):
                try:
                    camera_status = self.camera.get_status()
                except Exception as exc:
                    camera_status = {"last_error": str(exc)}

            return {
                "system": self.__class__.__name__,
                "fallback": False,
                "running": bool(getattr(self.camera, "running", False)),
                "camera": camera_status,
                "detector": {
                    "name": self.detector.__class__.__name__,
                    **detector_status,
                },
                "model": {
                    "path": model_path,
                    "exists": bool(model_path and os.path.exists(model_path)),
                    "type": getattr(config, "YOLO_MODEL_TYPE", "yolov8"),
                    "device": getattr(config, "VISION_DEVICE", "cpu"),
                },
                "params": {
                    "confidence": getattr(config, "VISION_CONFIDENCE", 0.3),
                    "nms_iou": getattr(config, "VISION_NMS_IOU", 0.45),
                    "slice_width": getattr(config, "SAHI_SLICE_WIDTH", 640),
                    "slice_height": getattr(config, "SAHI_SLICE_HEIGHT", 640),
                    "overlap_ratio": getattr(config, "SAHI_OVERLAP_RATIO", 0.20),
                    "warp_width": getattr(config, "WARP_WIDTH", 1000),
                    "warp_height": getattr(config, "WARP_HEIGHT", 1000),
                    "stability_threshold": getattr(config, "STABILITY_THRESHOLD", 3),
                },
                "last_frame_processed": self.last_frame_processed,
            }

        def step(self) -> Optional[str]:
            result = frame_buffer.get_detection()
            if result is None:
                return None

            dets = result.get("detections") or []
            self.last_frame_processed = {
                "timestamp": time.time(),
                "latency_ms": float(result.get("latency_ms", 0.0) or 0.0),
                "detections": list(dets),
            }

            from .detection.detection_result import Detection, BoundingBox

            normalized = []
            for item in dets:
                if isinstance(item, Detection):
                    normalized.append(item)
                    continue
                bbox = item.get("bbox") if isinstance(item, dict) else None
                if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
                    continue
                normalized.append(
                    Detection(
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
                )

            board_state = self.mapper.map_detections(normalized)
            stable_state = self.validator.validate(board_state)

            if stable_state:
                fen = self.fen_gen.generate(stable_state, turn=self._current_turn_for_fen())
                return fen

            return None

        def _current_turn_for_fen(self) -> str:
            try:
                from .fen.fen_generator import normalize_fen_turn
                from backend.state.store.state_store import state_store

                snapshot = state_store.to_dict()
                return normalize_fen_turn((snapshot.get("game") or {}).get("current_turn"))
            except Exception:
                return "w"

    return VisionSystem()


# Global Instance
try:
    if getattr(config, "FAKE_VISION", False):
        vision_system = MockVisionSystem()
    else:
        vision_system = _build_real_vision_system()
except Exception as e:
    logger.error(f"[VisionSystem] Falling back due to import/startup error: {e}")
    vision_system = MockVisionSystem()
