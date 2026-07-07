import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from backend.application.dto.vision_dto import BoundingBoxDTO, DetectionDTO, VisionResultDTO
from backend.utils.logger import logger


class VisionPipeline:
    """
    OpenCV preprocessing and homography correction followed by YOLO detection and FEN generation.
    """

    def __init__(self, camera, preprocess, perspective, morphology, detector, fen_gen, board_mapper=None):
        self.camera = camera
        self.preprocess = preprocess
        self.perspective = perspective
        self.morphology = morphology
        self.detector = detector
        self.fen_gen = fen_gen
        self.board_mapper = board_mapper
        self._last_result = None

    async def process(self, frame: np.ndarray, turn: str = "w") -> Optional[VisionResultDTO]:
        """
        Process one frame:
        frame -> homography transform -> OpenCV preprocess -> YOLO detect -> FEN generate.
        """
        if frame is None:
            return None

        if not hasattr(frame, "shape") or getattr(frame, "size", 0) == 0:
            logger.warning("[VisionPipeline] empty or invalid frame skipped.")
            return None

        wall_timestamp = time.time()
        total_start = time.perf_counter()
        timings: Dict[str, float] = {}

        warped = self._timed("homography", timings, lambda: self._transform_frame(frame))
        if warped is None:
            warped = frame

        enhanced = self._timed("preprocess", timings, lambda: self._preprocess_frame(warped))
        if enhanced is None:
            enhanced = warped

        detector_input = self._timed("morphology", timings, lambda: self._apply_morphology_if_mask(enhanced))
        if detector_input is None:
            detector_input = enhanced

        raw_detections = self._timed("inference", timings, lambda: list(self.detector.detect(detector_input) or []))
        if raw_detections is None:
            raw_detections = []

        board_state = self._timed("board_mapping", timings, lambda: self._map_board_state(raw_detections)) or {}
        fen = self._timed("fen", timings, lambda: self._generate_fen(raw_detections, board_state, turn))

        latency = (time.perf_counter() - total_start) * 1000
        timings["total"] = round(latency, 3)
        coordinate_space = "rectified_board" if self._is_calibrated() else "camera_frame"
        frame_size = self._frame_size(detector_input)

        self._last_result = VisionResultDTO(
            timestamp=wall_timestamp,
            raw_frame=frame,
            work_frame=warped,
            detections=self._to_detection_dtos(raw_detections, coordinate_space=coordinate_space, frame_size=frame_size),
            latency_ms=latency,
            fen=fen,
            board_state=board_state,
            stage_timings_ms=timings,
            calibrated=self._is_calibrated(),
            coordinate_space=coordinate_space,
        )
        return self._last_result

    def update_corners(self, corners):
        self.perspective.update_corners(corners)

    def _timed(self, stage: str, timings: Dict[str, float], fn):
        start = time.perf_counter()
        try:
            return fn()
        except Exception as exc:
            logger.warning("[VisionPipeline] %s stage failed: %s", stage, exc, exc_info=True)
            return None
        finally:
            timings[stage] = round((time.perf_counter() - start) * 1000, 3)

    def _transform_frame(self, frame: np.ndarray) -> np.ndarray:
        if self.perspective is None or not hasattr(self.perspective, "transform"):
            return frame
        return self.perspective.transform(frame)

    def _preprocess_frame(self, frame: np.ndarray) -> np.ndarray:
        if self.preprocess is None:
            return frame
        if hasattr(self.preprocess, "process"):
            return self.preprocess.process(frame)
        if hasattr(self.preprocess, "enhance_color"):
            return self.preprocess.enhance_color(frame)
        return frame

    def _apply_morphology_if_mask(self, frame: np.ndarray) -> np.ndarray:
        if self.morphology is None or not hasattr(self.morphology, "optimize"):
            return frame
        if getattr(frame, "ndim", 0) != 2:
            return frame
        return self.morphology.optimize(frame)

    def _map_board_state(self, detections: List[Any]) -> Dict[str, str]:
        mapper = self.board_mapper
        if mapper is None:
            mapper = getattr(self.fen_gen, "mapper", None)
        if mapper is None or not hasattr(mapper, "map_detections"):
            return {}
        return dict(mapper.map_detections(detections) or {})

    def _generate_fen(self, detections: List[Any], board_state: Dict[str, str], turn: str) -> Optional[str]:
        if self.fen_gen is None or not hasattr(self.fen_gen, "generate"):
            return None
        if board_state and not hasattr(self.fen_gen, "mapper"):
            return self.fen_gen.generate(board_state, turn=turn)
        return self.fen_gen.generate(detections, turn=turn)

    def _to_detection_dtos(
        self,
        detections: List[Any],
        *,
        coordinate_space: str,
        frame_size: Optional[Tuple[int, int]],
    ) -> List[DetectionDTO]:
        if self.board_mapper is not None and hasattr(self.board_mapper, "describe_detections"):
            payloads = self.board_mapper.describe_detections(
                detections,
                coordinate_space=coordinate_space,
                frame_size=frame_size,
            )
        else:
            payloads = [
                det.to_dict(
                    coordinate_space=coordinate_space,
                    frame_size=frame_size,
                )
                if hasattr(det, "to_dict")
                else self._detection_payload(det, coordinate_space=coordinate_space, frame_size=frame_size)
                for det in detections
            ]

        return [self._payload_to_dto(payload) for payload in payloads]

    def _payload_to_dto(self, payload: Dict[str, Any]) -> DetectionDTO:
        bbox = payload.get("bbox_xyxy") or payload.get("bbox") or [0.0, 0.0, 0.0, 0.0]
        metadata = {
            key: value
            for key, value in payload.items()
            if key not in {"class_id", "class_name", "confidence", "bbox", "bbox_xyxy", "coordinate_space", "frame_size"}
        }
        return DetectionDTO(
            class_id=payload.get("class_id"),
            class_name=str(payload.get("class_name", "")),
            confidence=float(payload.get("confidence", 0.0) or 0.0),
            bbox=BoundingBoxDTO(x1=float(bbox[0]), y1=float(bbox[1]), x2=float(bbox[2]), y2=float(bbox[3])),
            coordinate_space=str(payload.get("coordinate_space") or "detector_input"),
            frame_size=list(payload.get("frame_size")) if isinstance(payload.get("frame_size"), (list, tuple)) else None,
            metadata=metadata,
        )

    def _detection_payload(
        self,
        detection,
        *,
        coordinate_space: str,
        frame_size: Optional[Tuple[int, int]],
    ) -> Dict[str, Any]:
        return {
            "class_name": str(getattr(detection, "class_name", "")),
            "confidence": float(getattr(detection, "confidence", 0.0) or 0.0),
            "bbox": [0.0, 0.0, 0.0, 0.0],
            "coordinate_space": coordinate_space,
            "frame_size": list(frame_size) if frame_size else None,
        }

    def _frame_size(self, frame: np.ndarray) -> Optional[Tuple[int, int]]:
        try:
            height, width = frame.shape[:2]
        except Exception:
            return None
        return int(width), int(height)

    def _is_calibrated(self) -> bool:
        return bool(
            self.perspective is not None
            and (
                getattr(self.perspective, "is_calibrated", False)
                or getattr(self.perspective, "matrix", None) is not None
            )
        )
