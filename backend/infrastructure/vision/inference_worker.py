from __future__ import annotations

import threading
import time
from typing import Optional

from backend.events.bus.event_bus import bus
from backend.events.event_types import EventType
from backend.events.models.base_event import BaseEvent
from backend.utils import config
from backend.utils.logger import logger

from .camera.frame_buffer import frame_buffer
from .capture_session import vision_capture_session


class InferenceWorker:
    """Background worker that turns raw frames into mapped detection payloads."""

    def __init__(self, detector, preprocessor, corrector, mapper=None):
        self.detector = detector
        self.preprocessor = preprocessor
        self.corrector = corrector
        self.mapper = mapper
        self._corners = None
        self._lock = threading.Lock()
        self._inference_lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.failure_count = 0
        self.consecutive_failures = 0
        self.first_failure_at = None
        self.last_error = None
        self.last_error_at = None

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
            action, _capture_snapshot = vision_capture_session.tick()
            if action in {"idle", "waiting"}:
                time.sleep(0.05)
                continue
            if action == "expired":
                vision_capture_session.publish_status(
                    source="vision_system",
                    toast="影像辨識逾時，請重新確認棋子位置後再啟動辨識。",
                    level="warning",
                )
                time.sleep(0.05)
                continue

            frame = frame_buffer.get_latest_raw(timeout=0.1)
            if frame is None:
                vision_capture_session.mark_frame_unavailable()
                vision_capture_session.publish_status(source="vision_system")
                time.sleep(0.02)
                continue

            try:
                self.process_frame(frame, publish=True, source="vision_system")
                self.consecutive_failures = 0
                self.first_failure_at = None
            except Exception as exc:
                now = time.time()
                if self.consecutive_failures == 0:
                    self.first_failure_at = now
                self.failure_count += 1
                self.consecutive_failures += 1
                self.last_error = str(exc)
                self.last_error_at = now
                logger.warning(f"[VisionSystem] inference loop failed: {exc}", exc_info=True)
                time.sleep(0.2)

    def process_frame(self, frame, *, publish: bool = True, source: str = "vision_system") -> dict:
        """Process one frame through the active detector and optional board mapping."""
        if frame is None or getattr(frame, "size", 0) <= 0:
            raise ValueError("frame must be a non-empty image")

        start = time.time()
        with self._inference_lock:
            with self._lock:
                calibrated = self.corrector.is_calibrated
                work_frame = self.corrector.warp(frame) if calibrated else frame
                board_corners = list(self._corners) if self._corners is not None else None

            processed = self.preprocessor.process(work_frame)
            detector_input = processed if processed is not None else work_frame
            detections = self.detector.detect(detector_input) or []
            coordinate_space = "rectified_board" if calibrated else "camera_frame"
            detections_payload = self._serialize_detections(
                detections,
                work_frame=work_frame,
                coordinate_space=coordinate_space,
                calibrated=calibrated,
            )

        height, width = work_frame.shape[:2]
        latency_ms = (time.time() - start) * 1000.0
        if vision_capture_session.is_active():
            vision_capture_session.mark_processed(latency_ms=latency_ms)
        payload = {
            "timestamp": start,
            "work_frame": work_frame,
            "frame_size": [int(width), int(height)],
            "detections": detections_payload,
            "latency_ms": latency_ms,
            "calibrated": calibrated,
            "board_corners": board_corners,
            "coordinate_space": coordinate_space,
            "source": str(source or "vision_system"),
        }
        frame_buffer.put_detection(payload)
        if publish:
            bus.publish(
                BaseEvent.create(
                    event_type=EventType.VISION_BOARD_DETECTED,
                    source=str(source or "vision_system"),
                    payload={
                        "timestamp": payload["timestamp"],
                        "detections": payload["detections"],
                        "latency_ms": latency_ms,
                        "calibrated": calibrated,
                        "board_corners": board_corners,
                    },
                )
            )
        return payload

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
            self._attach_robot_anchor_points(payloads, coordinate_space=coordinate_space)
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
        self._attach_robot_anchor_points(payloads, coordinate_space=coordinate_space)
        return payloads

    def _attach_robot_anchor_points(self, payloads, *, coordinate_space: str) -> None:
        try:
            from backend.utils.kinematics import kinematics

            calibration = kinematics.to_dict().get("vision_to_robot") or {}
            if not calibration.get("calibrated"):
                return
            target_space = str(calibration.get("coordinate_space") or "rectified_board")
            for payload in payloads:
                anchor = self._anchor_for_robot_mapping(payload, target_space=target_space, coordinate_space=coordinate_space)
                if anchor is None:
                    continue
                robot_xy = kinematics.vision_point_to_robot(anchor[0], anchor[1], coordinate_space=target_space)
                if robot_xy is None:
                    continue
                payload["robot_anchor_point"] = [float(robot_xy[0]), float(robot_xy[1])]
                payload["robot_coordinate_space"] = "robot_base_xy"
                payload["vision_to_robot_coordinate_space"] = target_space
        except Exception:
            logger.debug("[VisionSystem] failed to attach robot anchor points", exc_info=True)

    def _anchor_for_robot_mapping(self, payload: dict, *, target_space: str, coordinate_space: str):
        anchor = payload.get("anchor_point")
        if target_space == coordinate_space and isinstance(anchor, (list, tuple)) and len(anchor) == 2:
            return anchor
        if target_space == "camera_frame":
            raw_anchor = payload.get("raw_anchor_point")
            if isinstance(raw_anchor, (list, tuple)) and len(raw_anchor) == 2:
                return raw_anchor
            if coordinate_space == "camera_frame" and isinstance(anchor, (list, tuple)) and len(anchor) == 2:
                return anchor
        if target_space == "rectified_board" and coordinate_space == "camera_frame":
            if isinstance(anchor, (list, tuple)) and len(anchor) == 2 and self.corrector.is_calibrated:
                return self.corrector.map_point(anchor[0], anchor[1])
        return None
