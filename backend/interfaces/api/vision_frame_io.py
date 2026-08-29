from __future__ import annotations

import math
import time

from flask import current_app, request

from backend.interfaces.api.shared import config, runtime_vision_status


_ANNOTATION_PALETTE = (
    "#ef4444",
    "#f97316",
    "#eab308",
    "#22c55e",
    "#06b6d4",
    "#3b82f6",
    "#8b5cf6",
    "#ec4899",
)


def ingest_frame_payload(payload: dict, vision_system) -> dict:
    try:
        from backend.infrastructure.vision.camera.frame_buffer import frame_buffer
        from backend.infrastructure.vision.camera.tmflow_json_source import TMflowJsonFrameSource
    except Exception as exc:
        current_app.logger.debug("Vision frame ingest dependencies unavailable", exc_info=True)
        return {"ok": False, "reason": f"dependencies_unavailable: {exc}"}

    delegate = getattr(getattr(vision_system, "camera", None), "_delegate", None)
    if hasattr(delegate, "ingest_payload"):
        return dict(delegate.ingest_payload(payload, apply_fps_limit=False))

    frame = TMflowJsonFrameSource.decode_payload(payload)
    if frame is None:
        return {"ok": False, "reason": "decode_failed"}
    frame_buffer.put_raw(frame)
    height, width = frame.shape[:2]
    return {"ok": True, "frame_size": [int(width), int(height)], "frames_received": None}


def ingest_tmvision_image_request() -> dict:
    try:
        import cv2
        import numpy as np
        from backend.infrastructure.vision.camera.frame_buffer import frame_buffer
    except Exception as exc:
        current_app.logger.debug("TMvision ingest dependencies unavailable", exc_info=True)
        return {"ok": False, "reason": f"dependencies_unavailable: {exc}"}

    image_field = None
    raw = b""
    filename = ""
    for field in ("file", "image", "frame"):
        upload = request.files.get(field)
        if upload is None:
            continue
        raw = upload.read()
        filename = str(upload.filename or "")
        image_field = field
        break

    if not raw and str(request.mimetype or "").lower() in {"image/jpeg", "image/png", "application/octet-stream"}:
        raw = request.get_data(cache=False)
        image_field = "body"

    if not raw:
        current_app.logger.warning(
            "[TMvision] image ingest failed: missing image field remote=%s mimetype=%s files=%s",
            request.remote_addr,
            request.mimetype,
            sorted(request.files.keys()),
        )
        return {"ok": False, "reason": "missing_file_field"}

    max_bytes = int(getattr(config, "VISION_TMFLOW_IMAGE_MAX_MESSAGE_BYTES", 1_048_576))
    if max_bytes > 0 and len(raw) > max_bytes:
        current_app.logger.warning(
            "[TMvision] image ingest failed: image too large remote=%s field=%s bytes=%s max_bytes=%s",
            request.remote_addr,
            image_field,
            len(raw),
            max_bytes,
        )
        return {"ok": False, "reason": f"image_too_large: {len(raw)} > {max_bytes}"}

    try:
        image_bytes = np.frombuffer(raw, dtype=np.uint8)
        frame = cv2.imdecode(image_bytes, cv2.IMREAD_COLOR)
    except Exception as exc:
        current_app.logger.warning(
            "[TMvision] image ingest failed: decode exception remote=%s field=%s bytes=%s error=%s",
            request.remote_addr,
            image_field,
            len(raw),
            exc,
        )
        return {"ok": False, "reason": f"decode_failed: {exc}"}
    if frame is None or getattr(frame, "size", 0) <= 0:
        current_app.logger.warning(
            "[TMvision] image ingest failed: decode returned empty frame remote=%s field=%s bytes=%s",
            request.remote_addr,
            image_field,
            len(raw),
        )
        return {"ok": False, "reason": "decode_failed"}

    frame_buffer.put_raw(frame)
    height, width = frame.shape[:2]
    current_app.logger.info(
        "[TMvision] frame accepted remote=%s field=%s filename=%s bytes=%s frame_size=%sx%s",
        request.remote_addr,
        image_field,
        filename,
        len(raw),
        int(width),
        int(height),
    )
    return {
        "ok": True,
        "frame_size": [int(width), int(height)],
        "image_field": image_field,
        "filename": filename,
        "bytes": int(len(raw)),
        "_frame": frame,
    }


def tmvision_debug_response_enabled() -> bool:
    return str(request.args.get("debug") or "").strip().lower() in {"1", "true", "yes"}


def tmvision_detection_probe_annotations(result: dict) -> list[dict]:
    enabled = str(request.args.get("probe_box") or "").strip().lower() in {"1", "true", "yes"}
    if not enabled:
        return []
    frame_size = result.get("frame_size")
    if not isinstance(frame_size, (list, tuple)) or len(frame_size) < 2:
        return []
    try:
        width = max(1, int(frame_size[0]))
        height = max(1, int(frame_size[1]))
    except Exception:
        return []
    box_w = max(20, int(width * 0.2))
    box_h = max(20, int(height * 0.2))
    x1 = float(width - box_w) / 2.0
    y1 = float(height - box_h) / 2.0
    x2 = x1 + float(box_w)
    y2 = y1 + float(box_h)
    color = _annotation_color("probe", 1)
    coordinates = _annotation_coordinates(x1, y1, x2, y2)
    return [{
        "id": 1,
        "index": 1,
        "box_cx": coordinates["cx"],
        "box_cy": coordinates["cy"],
        "center_point": [coordinates["cx"], coordinates["cy"]],
        "center_x": coordinates["cx"],
        "center_y": coordinates["cy"],
        "box_w": float(box_w),
        "box_h": float(box_h),
        "bbox_xyxy": [x1, y1, x2, y2],
        "bbox_xywh": [x1, y1, float(box_w), float(box_h)],
        "coordinates": coordinates,
        "label": "probe",
        "rotation": 0.0,
        "score": 0.99,
        "color": color,
        "box_color": color,
    }]


def detect_tmvision_frame(result: dict, vision_system) -> dict:
    frame = result.get("_frame") if isinstance(result, dict) else None
    if frame is None or getattr(frame, "size", 0) <= 0:
        return {"ok": False, "reason": "missing_decoded_frame", "status_code": 400, "annotations": []}
    if not hasattr(vision_system, "detect_frame"):
        return {"ok": False, "reason": "vision_system_detect_frame_unavailable", "status_code": 503, "annotations": []}

    try:
        detection_result = vision_system.detect_frame(frame, publish=True, source="tmvision_http")
    except Exception as exc:
        current_app.logger.warning("[TMvision] detection failed: %s", exc, exc_info=True)
        return {"ok": False, "reason": str(exc), "status_code": 503, "annotations": []}

    annotations = tmvision_detection_annotations(detection_result)
    annotations_count = len(annotations)
    return {
        "ok": True,
        "count": annotations_count,
        "annotations_count": annotations_count,
        "annotations": annotations,
        "detection": {
            "detections_count": len(detection_result.get("detections") or []),
            "annotations_count": annotations_count,
            "count": annotations_count,
            "latency_ms": float(detection_result.get("latency_ms", 0.0) or 0.0),
            "calibrated": bool(detection_result.get("calibrated")),
            "coordinate_space": detection_result.get("coordinate_space"),
            "source": detection_result.get("source"),
        },
    }


def tmvision_detection_annotations(detection_result: dict) -> list[dict]:
    annotations = []
    if not isinstance(detection_result, dict):
        return annotations
    for item in detection_result.get("detections") or []:
        if not isinstance(item, dict):
            continue
        bbox = _detection_bbox_for_tmvision(item)
        if bbox is None:
            continue
        x1, y1, x2, y2 = bbox
        width = max(0.0, x2 - x1)
        height = max(0.0, y2 - y1)
        if width <= 0.0 or height <= 0.0:
            continue
        index = len(annotations) + 1
        label = _detection_label(item)
        color = _annotation_color(label, index)
        coordinates = _annotation_coordinates(x1, y1, x2, y2)
        annotations.append({
            "id": index,
            "index": index,
            "box_cx": coordinates["cx"],
            "box_cy": coordinates["cy"],
            "center_point": [coordinates["cx"], coordinates["cy"]],
            "center_x": coordinates["cx"],
            "center_y": coordinates["cy"],
            "box_w": float(width),
            "box_h": float(height),
            "bbox_xyxy": [float(x1), float(y1), float(x2), float(y2)],
            "bbox_xywh": [float(x1), float(y1), float(width), float(height)],
            "coordinates": coordinates,
            "label": label,
            "rotation": _finite_float(item.get("rotation", item.get("rotate", 0.0)), default=0.0),
            "score": _score(item.get("score", item.get("confidence", 0.0))),
            "color": color,
            "box_color": color,
        })
    return annotations


def _detection_bbox_for_tmvision(item: dict):
    bbox = item.get("raw_bbox") or item.get("bbox_xyxy") or item.get("bbox")
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        bbox_xywh = item.get("bbox_xywh")
        if isinstance(bbox_xywh, (list, tuple)) and len(bbox_xywh) == 4:
            x, y, width, height = [_finite_float(value, default=None) for value in bbox_xywh]
            if None not in (x, y, width, height):
                bbox = [x, y, x + width, y + height]
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return None
    values = [_finite_float(value, default=None) for value in bbox]
    if any(value is None for value in values):
        return None
    x1, y1, x2, y2 = values
    return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)


def _detection_label(item: dict) -> str:
    for key in ("class_name", "label", "piece_code", "mapped_cell"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return str(item.get("class_id", "unknown"))


def _score(value) -> float:
    number = _finite_float(value, default=0.0)
    return max(0.0, min(1.0, float(number)))


def _annotation_coordinates(x1: float, y1: float, x2: float, y2: float) -> dict:
    width = max(0.0, x2 - x1)
    height = max(0.0, y2 - y1)
    return {
        "x1": float(x1),
        "y1": float(y1),
        "x2": float(x2),
        "y2": float(y2),
        "cx": float(x1 + width / 2.0),
        "cy": float(y1 + height / 2.0),
        "width": float(width),
        "height": float(height),
    }


def _annotation_color(label: str, index: int) -> str:
    key = sum((position + 1) * ord(char) for position, char in enumerate(str(label or "")))
    return _ANNOTATION_PALETTE[(key + int(index)) % len(_ANNOTATION_PALETTE)]


def _finite_float(value, *, default):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return number


def synthetic_vision_test_frame(payload: dict):
    import cv2
    import numpy as np

    width = int(payload.get("width") or 960)
    height = int(payload.get("height") or 540)
    width = max(320, min(width, 1920))
    height = max(240, min(height, 1080))
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:] = (24, 31, 42)

    margin = 48
    cv2.rectangle(frame, (margin, margin), (width - margin, height - margin), (32, 164, 243), 3)
    for col in range(1, 9):
        x = margin + int((width - margin * 2) * col / 9)
        cv2.line(frame, (x, margin), (x, height - margin), (80, 100, 120), 1)
    for row in range(1, 10):
        y = margin + int((height - margin * 2) * row / 10)
        cv2.line(frame, (margin, y), (width - margin, y), (80, 100, 120), 1)

    label = f"VISION SOURCE TEST - {getattr(config, 'VISION_SOURCE', 'opencv')}"
    endpoint = f"{getattr(config, 'VISION_TMFLOW_IMAGE_HOST', '')}:{getattr(config, 'VISION_TMFLOW_IMAGE_PORT', 5891)}"
    cv2.putText(frame, label, (margin + 8, margin + 36), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (250, 250, 250), 2)
    cv2.putText(frame, endpoint, (margin + 8, margin + 72), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (147, 197, 253), 2)
    cv2.putText(
        frame,
        time.strftime("%Y-%m-%d %H:%M:%S"),
        (margin + 8, height - margin - 18),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (203, 213, 225),
        2,
    )
    return frame


def snapshot_max_age_sec() -> float:
    try:
        return max(0.1, min(float(request.args.get("max_age_sec", 5.0)), 60.0))
    except Exception:
        return 5.0


def capture_opencv_snapshot_fallback():
    source = str(getattr(config, "VISION_SOURCE", "opencv") or "opencv").strip().lower()
    if bool(getattr(config, "FAKE_VISION", False)) or source != "opencv":
        return None
    try:
        from backend.infrastructure.vision.camera.camera_manager import CameraManager
    except Exception:
        current_app.logger.debug("OpenCV snapshot fallback dependencies unavailable", exc_info=True)
        return None

    try:
        timeout_sec = max(0.1, min(float(request.args.get("capture_timeout_sec", 1.5)), 5.0))
    except Exception:
        timeout_sec = 1.5
    try:
        return CameraManager().capture_once(timeout_sec=timeout_sec)
    except Exception:
        current_app.logger.debug("OpenCV snapshot fallback failed", exc_info=True)
        return None


def snapshot_unavailable_details(frame_buffer) -> dict:
    status = runtime_vision_status()
    camera = status.get("camera", {}) if isinstance(status, dict) else {}
    buffer_stats = frame_buffer.raw_stats() if hasattr(frame_buffer, "raw_stats") else {}
    fake_vision = bool(getattr(config, "FAKE_VISION", False))
    source = str(getattr(config, "VISION_SOURCE", "opencv") or "opencv").strip().lower()
    if fake_vision:
        hint = "Set FAKE_VISION=false before testing a real camera snapshot."
    elif source == "tmvision_http":
        hint = "Trigger TMvision External Classification/Detection first, then retry snapshot; check ingest key, Flask bind host, and request size limits."
    elif source == "tmflow_json":
        hint = "Trigger TMflow/TMvision image ingest first, then retry snapshot; check ingest key, robot IP, and frame size limits."
    else:
        hint = (
            "For EIH camera tests, trigger TMvision External Classification/Detection first; "
            "for USB fallback, check Windows camera privacy, camera ownership by other apps, and CAMERA_INDEX."
        )
    return {
        "source": source,
        "fake_vision": fake_vision,
        "simulation": bool(status.get("simulation")) if isinstance(status, dict) else False,
        "fallback": bool(status.get("fallback")) if isinstance(status, dict) else False,
        "camera": camera if isinstance(camera, dict) else {},
        "buffer": buffer_stats,
        "hint": hint,
    }
