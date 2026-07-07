import base64
import os
import time
import threading
from typing import Optional

from backend.utils.logger import logger
from backend.utils import config


class _SimulationValidator:
    last_stable_state = None


class _SimulationFENGen:
    def generate(self, _state, turn="w") -> str:
        side = "b" if str(turn or "").strip().lower() in ("b", "black") else "w"
        return f"rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR {side} - - 0 1"


class SimulationVisionSystem:
    """
    [Simulation Layer] Interactive Vision System.
    Emits simulated vision events triggered by UI actions.
    """
    def __init__(self):
        self.validator = _SimulationValidator()
        self.fen_gen = _SimulationFENGen()
        self._jpg_bytes = base64.b64decode(
            "/9j/4AAQSkZJRgABAQAAZABkAAD/2wCEABQQEBkSGScXFycyJh8mMi4mJiYmLj41NTU1NT5EQUFBQUFBREREREREREREREREREREREREREREREREREREQBFRkZIBwgJhgYJjYmICY2RDYrKzZERERCNUJERERERERERERERERERERERERERERERERERERERERERERERERERP/AABEIAAEAAQMBIgACEQEDEQH/xABMAAEBAAAAAAAAAAAAAAAAAAAABQEBAQAAAAAAAAAAAAAAAAAABQYQAQAAAAAAAAAAAAAAAAAAAAARAQAAAAAAAAAAAAAAAAAAAAD/2gALAwEAAhEDEQA/AJQA9Yv/2Q=="
        )
        self._pending_fen = None
        self.board_corners = None
        self.calibration_path = os.path.abspath(getattr(config, "VISION_CALIBRATION_FILE", "data/vision_calibration.json"))
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
            logger.info(f"[SimulationVision] Simulated move detected: {self._pending_fen}")

    def start(self) -> bool:
        logger.info("[VisionSystem] Running in explicit simulation mode.")
        return True

    def stop(self): pass
    def update_corners(self, corners, persist=True):
        self.board_corners = corners
        return {
            "ok": True,
            "calibrated": True,
            "simulation": True,
            "board_corners": corners,
            "persisted": False,
        }

    def calibrate_from_frame(self, frame=None, persist=True):
        return {
            "ok": False,
            "calibrated": False,
            "simulation": True,
            "reason": "mock vision has no camera frame calibration",
        }

    def get_calibration_status(self) -> dict:
        return {
            "calibrated": self.board_corners is not None,
            "board_corners": self.board_corners,
            "path": self.calibration_path,
            "path_exists": os.path.exists(self.calibration_path),
            "output_size": [getattr(config, "WARP_WIDTH", 1000), getattr(config, "WARP_HEIGHT", 1000)],
        }

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
            "system": "SimulationVisionSystem",
            "simulation": True,
            "running": True,
            "camera": {"running": True, "opened": True, "index": -1},
            "detector": {"name": "MockDetector", "loaded": True},
            "calibration": self.get_calibration_status(),
        }


def _build_real_vision_system():
    # Local imports so the module can still be imported without numpy/opencv installed.
    import numpy as np  # noqa: F401

    from .camera.camera_manager import CameraManager
    from .camera.frame_buffer import frame_buffer
    from .preprocess.image_preprocessor import ImagePreprocessor, PerspectiveCorrector
    from .detection.yolo_detector import YOLODetector
    from .board.board_mapper import BoardMapper
    from .board.coordinate_system import BoardCoordinateSystem, GridConfig
    from .validation.temporal_validator import TemporalValidator
    from .fen.fen_generator import FENGenerator
    from .debug.overlay_renderer import OverlayRenderer
    from .overlay.overlay_manager import OverlayManager
    from .stream.mjpeg_stream import MJPEGStreamer
    from .calibration import compute_calibration_quality, load_calibration_payload, save_calibration
    from .calibration.board_calibrator import BoardCalibrator
    from backend.events.bus.event_bus import bus
    from backend.events.event_types import EventType
    from backend.events.models.base_event import BaseEvent

    class InferenceWorker:
        def __init__(self, detector, preprocessor, corrector, mapper=None):
            self.detector = detector
            self.preprocessor = preprocessor
            self.corrector = corrector
            self.mapper = mapper
            self._corners = None
            self._lock = threading.Lock()
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

        def set_calibration(self, matrix, corners=None, output_size=None):
            with self._lock:
                self.corrector.set_matrix(
                    matrix,
                    corners=corners,
                    output_size=output_size or (config.WARP_WIDTH, config.WARP_HEIGHT),
                )
                self._corners = self.corrector.corners.tolist() if self.corrector.corners is not None else corners
                return self.corrector.matrix

        def update_corners(self, corners):
            with self._lock:
                matrix = self.corrector.set_corners(
                    corners,
                    output_size=(config.WARP_WIDTH, config.WARP_HEIGHT),
                )
                self._corners = self.corrector.corners.tolist()
                return matrix

        def _run(self):
            while not self._stop.is_set():
                frame = frame_buffer.get_raw(timeout=0.1)
                if frame is None:
                    time.sleep(0.02)
                    continue

                try:
                    start = time.time()
                    with self._lock:
                        calibrated = self.corrector.is_calibrated
                        work_frame = self.corrector.warp(frame) if calibrated else frame
                        board_corners = list(self._corners) if self._corners is not None else None

                    processed = self.preprocessor.process(work_frame)
                    detections = self.detector.detect(processed if processed is not None else work_frame)
                    coordinate_space = "rectified_board" if calibrated else "camera_frame"
                    detections_payload = self._serialize_detections(
                        detections,
                        work_frame=work_frame,
                        coordinate_space=coordinate_space,
                        calibrated=calibrated,
                    )
                    latency_ms = (time.time() - start) * 1000.0
                    payload = {
                        "timestamp": start,
                        "work_frame": work_frame,
                        "detections": detections_payload,
                        "latency_ms": latency_ms,
                        "calibrated": calibrated,
                        "board_corners": board_corners,
                        "coordinate_space": coordinate_space,
                    }
                    frame_buffer.put_detection(payload)
                    bus.publish(
                        BaseEvent.create(
                            event_type=EventType.VISION_BOARD_DETECTED,
                            source="vision_system",
                            payload={
                                "timestamp": payload["timestamp"],
                                "detections": payload["detections"],
                                "latency_ms": latency_ms,
                                "calibrated": calibrated,
                                "board_corners": board_corners,
                            },
                        )
                    )
                except Exception as exc:
                    logger.debug(f"[VisionSystem] inference loop failed: {exc}", exc_info=True)
                    time.sleep(0.2)

        def _serialize_detections(self, detections, *, work_frame, coordinate_space: str, calibrated: bool):
            height, width = work_frame.shape[:2]
            frame_size = (int(width), int(height))
            if self.mapper is not None:
                payloads = self.mapper.describe_detections(
                    detections,
                    coordinate_space=coordinate_space,
                    frame_size=frame_size,
                )
            else:
                payloads = [
                    item.to_dict(
                        coordinate_space=coordinate_space,
                        frame_size=frame_size,
                    )
                    for item in detections
                ]

            if not calibrated:
                return payloads

            for payload in payloads:
                try:
                    bbox = payload.get("bbox_xyxy") or payload.get("bbox")
                    anchor = payload.get("anchor_point")
                    payload["raw_bbox"] = self.corrector.inverse_map_bbox(bbox)
                    if isinstance(anchor, (list, tuple)) and len(anchor) == 2:
                        raw_anchor = self.corrector.inverse_map_point(anchor[0], anchor[1])
                        payload["raw_anchor_point"] = [float(raw_anchor[0]), float(raw_anchor[1])]
                    payload["raw_coordinate_space"] = "camera_frame"
                except Exception:
                    logger.debug("[VisionSystem] failed to inverse-map detection bbox", exc_info=True)
            return payloads

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
            self.last_frame_processed = None

            grid_config = GridConfig(
                rows=config.BOARD_ROWS,
                cols=config.BOARD_COLS,
                width=config.WARP_WIDTH,
                height=config.WARP_HEIGHT,
            )
            self.coord_system = BoardCoordinateSystem(grid_config)
            self.mapper = BoardMapper(self.coord_system)
            self.worker = InferenceWorker(self.detector, self.preprocessor, self.corrector, self.mapper)
            self.validator = TemporalValidator(window_size=config.STABILITY_THRESHOLD)
            self.fen_gen = FENGenerator(rows=config.BOARD_ROWS, cols=config.BOARD_COLS)

            self.renderer = OverlayRenderer(self.coord_system)
            self.overlay_manager = OverlayManager(self.renderer)
            self.streamer = MJPEGStreamer(self.overlay_manager)
            self.board_corners = None
            self.calibrator = BoardCalibrator(
                max_detection_dim=getattr(config, "VISION_CALIBRATION_MAX_DIM", 960)
            )
            self.calibration_path = os.path.abspath(
                getattr(config, "VISION_CALIBRATION_FILE", "data/vision_calibration.json")
            )
            self.calibration_loaded = False
            self.calibration_quality = None
            self.calibration_source = None
            self._load_calibration()

        def _load_calibration(self) -> bool:
            try:
                payload = load_calibration_payload(self.calibration_path)
                if payload is None:
                    return False
                target_size = (config.WARP_WIDTH, config.WARP_HEIGHT)
                output_size = tuple(payload.get("output_size") or target_size)
                corners = payload["board_corners"]
                if output_size == target_size:
                    self.worker.set_calibration(payload["warp_matrix"], corners=corners, output_size=target_size)
                else:
                    self.worker.update_corners(corners)
                self.board_corners = corners
                metadata = payload.get("metadata") or {}
                self.calibration_quality = metadata.get("quality") or compute_calibration_quality(
                    corners,
                    payload["warp_matrix"],
                    target_size,
                )
                self.calibration_source = metadata.get("source") or "file"
                self.calibration_loaded = True
                logger.info("[VisionSystem] Loaded vision calibration from %s", self.calibration_path)
                return True
            except Exception as exc:
                self.calibration_loaded = False
                logger.warning("[VisionSystem] Failed to load vision calibration: %s", exc, exc_info=True)
                return False

        def update_corners(self, corners, persist=True, source="manual_or_api"):
            matrix = self.worker.update_corners(corners)
            self.board_corners = self.corrector.corners.tolist()
            self.calibration_quality = compute_calibration_quality(
                self.board_corners,
                matrix,
                output_size=(config.WARP_WIDTH, config.WARP_HEIGHT),
            )
            self.calibration_source = str(source or "manual_or_api")
            persisted = False
            if persist:
                save_calibration(
                    matrix,
                    self.board_corners,
                    path=self.calibration_path,
                    output_size=(config.WARP_WIDTH, config.WARP_HEIGHT),
                    metadata={
                        "source": self.calibration_source,
                        "quality": self.calibration_quality,
                    },
                )
                persisted = True
            self.calibration_loaded = True
            return {
                "ok": True,
                "calibrated": True,
                "board_corners": self.board_corners,
                "path": self.calibration_path,
                "persisted": persisted,
                "output_size": [config.WARP_WIDTH, config.WARP_HEIGHT],
                "quality": self.calibration_quality,
                "source": self.calibration_source,
            }

        def detect_board_corners(self, frame=None):
            if frame is None:
                frame = frame_buffer.get_raw(timeout=0.2)
            if frame is None:
                return None
            corners = self.calibrator.detect_auto(frame)
            if corners is None:
                return None
            return corners.tolist()

        def calibrate_from_frame(self, frame=None, persist=True):
            corners = self.detect_board_corners(frame=frame)
            if corners is None:
                return {
                    "ok": False,
                    "calibrated": False,
                    "reason": "board corners were not detected",
                    "path": self.calibration_path,
                }
            result = self.update_corners(corners, persist=persist, source="auto")
            if self.calibrator.last_quality:
                self.calibration_quality = {
                    **self.calibration_quality,
                    "detection": self.calibrator.last_quality,
                }
                result["quality"] = self.calibration_quality
            return result

        def get_calibration_status(self) -> dict:
            return {
                "calibrated": bool(self.corrector.is_calibrated),
                "loaded_from_file": bool(self.calibration_loaded),
                "board_corners": self.board_corners,
                "path": self.calibration_path,
                "path_exists": os.path.exists(self.calibration_path),
                "output_size": [config.WARP_WIDTH, config.WARP_HEIGHT],
                "matrix": self.corrector.matrix.tolist() if self.corrector.matrix is not None else None,
                "quality": self.calibration_quality,
                "source": self.calibration_source,
            }

        def _select_detector(self):
            model_path = os.path.abspath(getattr(config, "YOLO_MODEL_PATH", "") or "")
            logger.info(f"[VisionSystem] Loading YOLO detector with model: {model_path}")
            detector = YOLODetector(model_path=model_path)
            if getattr(detector, "model", None) is None:
                raise RuntimeError(f"YOLO model failed to load: {getattr(detector, 'last_error', None)}")
            logger.info(f"[VisionSystem] Using YOLO detector with model: {model_path}")
            return detector

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
            active_model_path = str(detector_status.get("model_path") or model_path)
            camera_status = {}
            if hasattr(self.camera, "get_status"):
                try:
                    camera_status = self.camera.get_status()
                except Exception as exc:
                    camera_status = {"last_error": str(exc)}

            return {
                "system": self.__class__.__name__,
                "simulation": False,
                "running": bool(getattr(self.camera, "running", False)),
                "camera": camera_status,
                "detector": {
                    "name": self.detector.__class__.__name__,
                    **detector_status,
                },
                "model": {
                    "path": active_model_path,
                    "exists": bool(active_model_path and os.path.exists(active_model_path)),
                    "type": getattr(config, "YOLO_MODEL_TYPE", "yolo26"),
                    "device": getattr(config, "VISION_DEVICE", "cpu"),
                },
                "params": {
                    "confidence": getattr(config, "VISION_CONFIDENCE", 0.3),
                    "nms_iou": getattr(config, "VISION_NMS_IOU", 0.45),
                    "warp_width": getattr(config, "WARP_WIDTH", 1000),
                    "warp_height": getattr(config, "WARP_HEIGHT", 1000),
                    "calibration_max_dim": getattr(config, "VISION_CALIBRATION_MAX_DIM", 960),
                    "stability_threshold": getattr(config, "STABILITY_THRESHOLD", 3),
                },
                "calibration": self.get_calibration_status(),
                "last_frame_processed": self.last_frame_processed,
            }

        def step(self) -> Optional[str]:
            result = frame_buffer.get_detection()
            if result is None:
                return None

            dets = result.get("detections") or []
            calibrated = bool(result.get("calibrated"))
            self.last_frame_processed = {
                "timestamp": time.time(),
                "latency_ms": float(result.get("latency_ms", 0.0) or 0.0),
                "detections": list(dets),
                "calibrated": calibrated,
                "coordinate_space": result.get("coordinate_space") or ("rectified_board" if calibrated else "camera_frame"),
                "board_corners": result.get("board_corners"),
            }

            if not calibrated:
                self.last_frame_processed["mapping_status"] = "uncalibrated"
                return None

            from .detection.detection_result import Detection, BoundingBox

            normalized = []
            for item in dets:
                if isinstance(item, Detection):
                    normalized.append(item)
                    continue
                bbox = (item.get("bbox_xyxy") or item.get("bbox")) if isinstance(item, dict) else None
                if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
                    continue
                frame_size = item.get("frame_size") if isinstance(item, dict) else None
                try:
                    frame_width = int(frame_size[0]) if isinstance(frame_size, (list, tuple)) else None
                    frame_height = int(frame_size[1]) if isinstance(frame_size, (list, tuple)) else None
                except (TypeError, ValueError, IndexError):
                    frame_width = None
                    frame_height = None
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
                        coordinate_space=str(item.get("coordinate_space") or "rectified_board"),
                        frame_width=frame_width,
                        frame_height=frame_height,
                    )
                )

            board_state = self.mapper.map_detections(normalized)
            self.last_frame_processed["board_state"] = dict(board_state)
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
if getattr(config, "FAKE_VISION", False):
    vision_system = SimulationVisionSystem()
else:
    try:
        vision_system = _build_real_vision_system()
    except Exception as e:
        logger.error(f"[VisionSystem] Startup failed: {e}. Falling back to SimulationVisionSystem.", exc_info=True)
        vision_system = SimulationVisionSystem()
        vision_system._fallback_reason = str(e)
