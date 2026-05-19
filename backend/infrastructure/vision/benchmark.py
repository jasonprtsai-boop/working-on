from __future__ import annotations

import json
import statistics
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Optional

import numpy as np

from backend.events.models.base_event import BaseEvent
from backend.infrastructure.vision.board.board_mapper import BoardMapper
from backend.infrastructure.vision.detection.mode_factory import DEFAULT_DETECTION_MODES, DetectorModeFactory
from backend.infrastructure.vision.fen.fen_generator import FENGenerator
from backend.infrastructure.vision.validation.temporal_validator import TemporalValidator
from backend.state.store.validators.fen_validator import FENValidator
from backend.utils import config

BENCHMARK_EVENT_TYPE = "VISION_BENCHMARK_RESULT"


@dataclass
class BenchmarkResult:
    mode: str
    frame_id: int
    status: str
    skip_reason: str
    detections_count: int
    small_object_count: int
    small_object_rate: float
    fps: float
    inference_latency_ms: float
    end_to_end_latency_ms: float
    fen: str
    fen_valid: bool
    stable_update: bool
    detections_json: str
    board_state_json: str
    map_50: str
    recall: str
    metric_note: str
    requires_annotations: bool
    roi_applied: bool
    roi: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class VisionDetectionBenchmark:
    """
    Runtime comparison harness for full YOLO, SAHI, ROI+YOLO, and ROI+SAHI.

    It intentionally reports mAP/Recall as N/A when no annotation dataset is
    provided, because runtime detections alone cannot prove accuracy.
    """

    def __init__(
        self,
        modes: Optional[Iterable[str]] = None,
        factory: Optional[DetectorModeFactory] = None,
        mapper: Optional[BoardMapper] = None,
        fen_generator: Optional[FENGenerator] = None,
        stability_threshold: Optional[int] = None,
        small_object_area_ratio: Optional[float] = None,
        annotations_dir: Optional[str] = None,
    ):
        self.modes = [str(mode).strip().lower() for mode in (modes or DEFAULT_DETECTION_MODES)]
        self.factory = factory or DetectorModeFactory()
        self.detectors = self.factory.create_all(self.modes)
        self.mapper = mapper or BoardMapper()
        self.fen_generator = fen_generator or FENGenerator(rows=config.BOARD_ROWS, cols=config.BOARD_COLS)
        threshold = int(stability_threshold if stability_threshold is not None else config.STABILITY_THRESHOLD)
        self.validators = {mode: TemporalValidator(window_size=max(1, threshold)) for mode in self.modes}
        self.small_object_area_ratio = float(
            small_object_area_ratio
            if small_object_area_ratio is not None
            else getattr(config, "VISION_SMALL_OBJECT_AREA_RATIO", 0.01)
        )
        self.annotations_dir = annotations_dir
        self.has_annotations = bool(annotations_dir)

    def run_frames(self, frames: Iterable[np.ndarray]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for frame_id, frame in enumerate(frames):
            for mode in self.modes:
                rows.append(self.process_frame(frame, frame_id, mode).to_dict())
        return rows

    def process_frame(self, frame: np.ndarray, frame_id: int, mode: str) -> BenchmarkResult:
        if frame is None:
            return self._skipped_result(mode, frame_id, "empty_frame")

        detector = self.detectors[mode]
        start = time.perf_counter()
        inference_start = time.perf_counter()
        detections = detector.detect(frame)
        inference_latency_ms = (time.perf_counter() - inference_start) * 1000.0

        board_state = self.mapper.map_detections(detections)
        fen = self.fen_generator.generate(board_state) if board_state else ""
        fen_valid = bool(fen and FENValidator.validate(fen))
        stable_update = False
        if fen_valid:
            stable_update = self.validators[mode].validate(board_state) is not None

        end_to_end_latency_ms = (time.perf_counter() - start) * 1000.0
        fps = 1000.0 / end_to_end_latency_ms if end_to_end_latency_ms > 0 else 0.0

        small_object_count = self._small_object_count(frame, detections)
        detections_count = len(detections)
        small_object_rate = (small_object_count / detections_count) if detections_count else 0.0

        status = self._detector_status(detector)
        skip_reason = self._skip_reason(status, detections_count)
        benchmark_status = "skipped" if skip_reason else "ok"
        roi_applied, roi_text = self._roi_metadata(status)

        return BenchmarkResult(
            mode=mode,
            frame_id=int(frame_id),
            status=benchmark_status,
            skip_reason=skip_reason,
            detections_count=detections_count,
            small_object_count=small_object_count,
            small_object_rate=round(small_object_rate, 4),
            fps=round(fps, 3),
            inference_latency_ms=round(inference_latency_ms, 3),
            end_to_end_latency_ms=round(end_to_end_latency_ms, 3),
            fen=fen,
            fen_valid=fen_valid,
            stable_update=bool(stable_update),
            detections_json=json.dumps(self._serialize_detections(detections), ensure_ascii=False),
            board_state_json=json.dumps(board_state, ensure_ascii=False),
            map_50="N/A",
            recall="N/A",
            metric_note="requires_annotations" if not self.has_annotations else "annotation_metrics_not_implemented",
            requires_annotations=not self.has_annotations,
            roi_applied=roi_applied,
            roi=roi_text,
        )

    def publish_results(self, rows: Iterable[Dict[str, Any]], session_id: str = "vision-benchmark") -> None:
        from backend.events.bus.event_bus import bus

        for row in rows:
            payload = dict(row)
            payload.setdefault("session_id", session_id)
            bus.publish(BaseEvent.create(
                event_type=BENCHMARK_EVENT_TYPE,
                source="vision_benchmark",
                payload=payload,
            ))

    def summarize(self, rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(str(row.get("mode", "")), []).append(row)

        summaries = []
        for mode in self.modes:
            items = grouped.get(mode, [])
            ok_items = [item for item in items if item.get("status") == "ok"]
            source = ok_items or items
            summaries.append({
                "mode": mode,
                "frames": len(items),
                "ok_frames": len(ok_items),
                "avg_fps": self._avg(source, "fps"),
                "avg_inference_latency_ms": self._avg(source, "inference_latency_ms"),
                "avg_end_to_end_latency_ms": self._avg(source, "end_to_end_latency_ms"),
                "p95_end_to_end_latency_ms": self._p95(source, "end_to_end_latency_ms"),
                "avg_detections": self._avg(source, "detections_count"),
                "avg_small_object_rate": self._avg(source, "small_object_rate"),
                "fen_valid_rate": self._rate(source, "fen_valid"),
                "stable_update_rate": self._rate(source, "stable_update"),
                "map_50": "N/A",
                "recall": "N/A",
                "metric_note": "requires_annotations" if not self.has_annotations else "annotation_metrics_not_implemented",
            })
        return summaries

    def _small_object_count(self, frame: np.ndarray, detections: List[Any]) -> int:
        frame_h, frame_w = frame.shape[:2]
        frame_area = max(1.0, float(frame_h * frame_w))
        threshold = frame_area * self.small_object_area_ratio
        count = 0
        for det in detections:
            bbox = getattr(det, "bbox", None)
            if bbox is None:
                continue
            area = max(0.0, float(getattr(bbox, "width", 0.0))) * max(0.0, float(getattr(bbox, "height", 0.0)))
            if area <= threshold:
                count += 1
        return count

    def _serialize_detections(self, detections: List[Any]) -> List[Dict[str, Any]]:
        output = []
        for det in detections:
            bbox = getattr(det, "bbox", None)
            if bbox is None:
                continue
            output.append(
                {
                    "class_id": int(getattr(det, "class_id", 0) or 0),
                    "class_name": str(getattr(det, "class_name", "")),
                    "confidence": float(getattr(det, "confidence", 0.0) or 0.0),
                    "bbox": [
                        float(getattr(bbox, "x1", 0.0)),
                        float(getattr(bbox, "y1", 0.0)),
                        float(getattr(bbox, "x2", 0.0)),
                        float(getattr(bbox, "y2", 0.0)),
                    ],
                }
            )
        return output

    def _detector_status(self, detector) -> Dict[str, Any]:
        if hasattr(detector, "get_status"):
            try:
                status = detector.get_status()
                return status if isinstance(status, dict) else {}
            except Exception:
                return {"last_error": "status_unavailable"}
        return {}

    def _skip_reason(self, status: Dict[str, Any], detections_count: int) -> str:
        if detections_count:
            return ""
        if status.get("roi_enabled"):
            child = status.get("detector") if isinstance(status.get("detector"), dict) else {}
            reason = self._skip_reason(child, detections_count)
            return reason
        if status.get("available") is False:
            return str(status.get("last_error") or "detector_not_available")
        if status.get("loaded") is False:
            return str(status.get("last_error") or "detector_unloaded")
        return ""

    def _roi_metadata(self, status: Dict[str, Any]) -> tuple[bool, str]:
        if not status.get("roi_enabled"):
            return False, ""
        roi = status.get("last_roi")
        roi_text = ",".join(str(value) for value in roi) if isinstance(roi, list) else ""
        return bool(status.get("roi_applied")), roi_text

    def _skipped_result(self, mode: str, frame_id: int, reason: str) -> BenchmarkResult:
        return BenchmarkResult(
            mode=mode,
            frame_id=int(frame_id),
            status="skipped",
            skip_reason=reason,
            detections_count=0,
            small_object_count=0,
            small_object_rate=0.0,
            fps=0.0,
            inference_latency_ms=0.0,
            end_to_end_latency_ms=0.0,
            fen="",
            fen_valid=False,
            stable_update=False,
            detections_json="[]",
            board_state_json="{}",
            map_50="N/A",
            recall="N/A",
            metric_note="requires_annotations",
            requires_annotations=True,
            roi_applied=False,
            roi="",
        )

    def _avg(self, rows: List[Dict[str, Any]], key: str) -> float:
        values = [float(row.get(key) or 0.0) for row in rows if row.get(key) not in (None, "")]
        return round(sum(values) / len(values), 3) if values else 0.0

    def _p95(self, rows: List[Dict[str, Any]], key: str) -> float:
        values = sorted(float(row.get(key) or 0.0) for row in rows if row.get(key) not in (None, ""))
        if not values:
            return 0.0
        if len(values) == 1:
            return round(values[0], 3)
        try:
            return round(statistics.quantiles(values, n=20, method="inclusive")[18], 3)
        except Exception:
            index = min(len(values) - 1, int(round(0.95 * (len(values) - 1))))
            return round(values[index], 3)

    def _rate(self, rows: List[Dict[str, Any]], key: str) -> float:
        if not rows:
            return 0.0
        hits = sum(1 for row in rows if bool(row.get(key)))
        return round(hits / len(rows), 4)
