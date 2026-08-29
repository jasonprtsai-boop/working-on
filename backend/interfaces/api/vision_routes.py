from __future__ import annotations

import time

from flask import Response, current_app, jsonify, request

from backend.interfaces.api.shared import (
    api_bp,
    bounded_int_arg,
    config,
    error_response,
    json_object_payload,
    runtime_vision_status,
    vision_system,
)
from backend.interfaces.api.vision_frame_io import (
    capture_opencv_snapshot_fallback as _capture_opencv_snapshot_fallback,
    detect_tmvision_frame as _detect_tmvision_frame,
    ingest_frame_payload as _ingest_frame_payload_io,
    ingest_tmvision_image_request as _ingest_tmvision_image_request,
    snapshot_max_age_sec as _snapshot_max_age_sec,
    snapshot_unavailable_details as _snapshot_unavailable_details,
    synthetic_vision_test_frame as _synthetic_vision_test_frame,
    tmvision_debug_response_enabled as _tmvision_debug_response_enabled,
    tmvision_detection_probe_annotations as _tmvision_detection_probe_annotations,
)
from backend.interfaces.api.vision_source_status_logic import (
    tmflow_frame_ingest_authorized as _tmflow_frame_ingest_authorized,
    vision_source_diagnostics as _vision_source_diagnostics,
)
from backend.infrastructure.vision.capture_session import vision_capture_session

_camera_discovery_cache = {"key": None, "expires_at": 0.0, "payload": None}


def _opencv_camera_backends(cv2):
    backends = []
    for name in ("CAP_DSHOW", "CAP_MSMF"):
        backend = getattr(cv2, name, None)
        if backend is not None:
            backends.append((name, backend))
    backends.append(("default", None))
    return backends


@api_bp.route("/vision/cameras", methods=["GET"])
def list_cameras():
    """List available camera indices (best-effort) for UI device selection."""
    try:
        import cv2
    except Exception:
        return error_response(
            "opencv_not_available",
            "OpenCV is not available for camera discovery.",
            503,
            details={
                "candidates": [],
                "current": getattr(config, "CAMERA_INDEX", 0),
                "source": str(getattr(config, "VISION_SOURCE", "opencv")),
            },
        )

    max_index = bounded_int_arg("max", 6, 1, 16)
    current = int(getattr(config, "CAMERA_INDEX", 0) or 0)
    probe_frames = str(request.args.get("probe_frames", "1")).strip().lower() not in {"0", "false", "no"}
    probe_active = str(request.args.get("probe_active", "0")).strip().lower() in {"1", "true", "yes"}
    cache_key = (max_index, current, probe_frames, probe_active)
    now = time.time()
    ttl = max(0.0, float(getattr(config, "CAMERA_DISCOVERY_CACHE_TTL_SEC", 10.0)))
    force_refresh = str(request.args.get("refresh", "")).strip().lower() in {"1", "true", "yes"}
    cached = _camera_discovery_cache.get("payload")
    if (
        not force_refresh
        and ttl > 0
        and _camera_discovery_cache.get("key") == cache_key
        and cached is not None
        and float(_camera_discovery_cache.get("expires_at") or 0) > now
    ):
        payload = dict(cached)
        payload["cached"] = True
        payload["cache_ttl_sec"] = ttl
        return jsonify(payload)

    candidates = []
    runtime_status = runtime_vision_status()
    active_camera = runtime_status.get("camera", {}) if isinstance(runtime_status, dict) else {}
    if not isinstance(active_camera, dict):
        active_camera = {}

    for i in range(max_index):
        candidate = _merge_active_camera_candidate({
            "index": i,
            "available": False,
            "backend": "",
            "frame_ready": None,
            "frame_size": None,
        }, active_camera)
        if candidate.get("active") and not probe_active:
            candidates.append(candidate)
            continue

        available = bool(candidate.get("available"))
        backend_used = str(candidate.get("backend") or "")
        frame_ready = candidate.get("frame_ready")
        frame_size = candidate.get("frame_size")
        cap = None
        for backend_name, backend in _opencv_camera_backends(cv2):
            try:
                cap = cv2.VideoCapture(i, backend) if backend is not None else cv2.VideoCapture(i)
                if cap is not None and cap.isOpened():
                    available = True
                    backend_used = backend_name
                    if probe_frames:
                        frame_ready, frame_size = _read_camera_probe_frame(cap)
                    break
            except Exception:
                current_app.logger.debug("Camera probe failed for index %s with %s", i, backend_name, exc_info=True)
            finally:
                try:
                    if cap is not None:
                        cap.release()
                except Exception:
                    current_app.logger.debug("Camera release failed for index %s", i, exc_info=True)
                cap = None
        candidates.append(_merge_active_camera_candidate({
            "index": i,
            "available": bool(available),
            "backend": backend_used,
            "frame_ready": frame_ready,
            "frame_size": frame_size,
        }, active_camera))

    payload = {
        "current": current,
        "source": str(getattr(config, "VISION_SOURCE", "opencv")),
        "sources": [
            {"id": "opencv", "label": "USB / OpenCV"},
            {"id": "tmvision_http", "label": "TMvision HTTP"},
            {"id": "tmflow_json", "label": "TMflow JSON"},
        ],
        "candidates": candidates,
        "frame_probe": probe_frames,
        "probe_active": probe_active,
        "active_camera": active_camera,
        "cached": False,
        "cache_ttl_sec": ttl,
    }
    if ttl > 0:
        _camera_discovery_cache.update({"key": cache_key, "expires_at": now + ttl, "payload": dict(payload)})
    return jsonify(payload)


def _read_camera_probe_frame(cap, timeout_sec: float = 0.35):
    deadline = time.time() + max(0.05, float(timeout_sec or 0.0))
    while time.time() < deadline:
        ret, frame = cap.read()
        if ret and frame is not None and getattr(frame, "size", 0) > 0:
            height, width = frame.shape[:2]
            return True, [int(width), int(height)]
        time.sleep(0.03)
    return False, None


def _merge_active_camera_candidate(candidate: dict, active_camera: dict) -> dict:
    result = dict(candidate)
    try:
        candidate_index = int(result.get("index"))
        active_index = int(active_camera.get("index"))
    except Exception:
        return result
    if candidate_index != active_index:
        return result

    active_source = str(active_camera.get("source") or getattr(config, "VISION_SOURCE", "opencv")).strip().lower()
    active_opened = bool(active_camera.get("opened") or active_camera.get("connected"))
    active_running = bool(active_camera.get("running"))
    if active_source == "opencv" and (active_opened or active_running):
        result["available"] = True
        result["active"] = True
        result["backend"] = result.get("backend") or active_camera.get("backend") or "active"
        if result.get("frame_ready") is None:
            frames_captured = int(active_camera.get("frames_captured") or 0)
            buffer = active_camera.get("buffer") if isinstance(active_camera.get("buffer"), dict) else {}
            result["frame_ready"] = bool(frames_captured > 0 or buffer.get("latest_frame_available"))
        if not result.get("frame_size"):
            resolution = active_camera.get("resolution")
            if isinstance(resolution, (list, tuple)) and len(resolution) >= 2:
                width, height = int(resolution[0] or 0), int(resolution[1] or 0)
                if width > 0 and height > 0:
                    result["frame_size"] = [width, height]
    return result


@api_bp.route("/vision/camera", methods=["POST"])
def set_camera():
    """Switch active camera device for the vision system."""
    try:
        payload = json_object_payload()
    except ValueError as exc:
        return error_response("validation_failed", str(exc), 400)
    try:
        idx = int(payload.get("index", getattr(config, "CAMERA_INDEX", 0)))
    except Exception:
        return error_response("invalid_index", "Camera index must be an integer.", 400)
    if idx < 0 or idx > 15:
        return error_response("invalid_index", "Camera index must be between 0 and 15.", 400)

    if hasattr(vision_system, "set_camera_index"):
        try:
            ok = bool(vision_system.set_camera_index(idx))
        except Exception as exc:
            return error_response("camera_switch_failed", str(exc), 500, recoverable=False)
        return jsonify({"ok": ok, "current": idx})

    return error_response("vision_system_no_camera", "Vision system does not support camera switching.", 409)


@api_bp.route("/vision/calibration", methods=["GET"])
def get_vision_calibration():
    """Return current perspective calibration state."""
    if not hasattr(vision_system, "get_calibration_status"):
        return error_response("vision_calibration_unavailable", "Vision calibration is not supported.", 409)
    return jsonify(vision_system.get_calibration_status())


@api_bp.route("/vision/calibration", methods=["POST"])
def set_vision_calibration():
    """
    Calibrate perspective correction.

    Payload options:
    - {"corners": [[x,y], [x,y], [x,y], [x,y]]} for manual TL/TR/BR/BL corners.
    - {"mode": "auto"} to detect corners from the latest camera frame.
    """
    try:
        payload = json_object_payload()
    except ValueError as exc:
        return error_response("validation_failed", str(exc), 400)
    persist = bool(payload.get("persist", True))

    try:
        corners = payload.get("corners")
        if corners is not None:
            if not hasattr(vision_system, "update_corners"):
                return error_response("vision_calibration_unavailable", "Vision calibration is not supported.", 409)
            result = vision_system.update_corners(corners, persist=persist)
            return jsonify(result)

        mode = str(payload.get("mode") or "auto").strip().lower()
        if mode != "auto":
            return error_response("invalid_calibration_mode", "Calibration mode must be 'auto' or provide corners.", 400)
        if not hasattr(vision_system, "calibrate_from_frame"):
            return error_response("vision_calibration_unavailable", "Vision calibration is not supported.", 409)

        result = vision_system.calibrate_from_frame(persist=persist)
        if not result.get("ok"):
            return error_response(
                "board_corners_not_detected",
                "Board corners could not be detected from the latest frame.",
                422,
                details=result,
            )
        return jsonify(result)
    except ValueError as exc:
        return error_response("invalid_board_corners", str(exc), 400)
    except Exception as exc:
        current_app.logger.warning("Vision calibration failed", exc_info=True)
        return error_response("vision_calibration_failed", str(exc), 500, recoverable=False)


@api_bp.route("/video_status", methods=["GET"])
def video_status():
    return jsonify(runtime_vision_status())


@api_bp.route("/vision/stream-token", methods=["POST"])
def issue_vision_stream_token():
    from backend.utils.auth import create_scoped_jwt

    ttl_seconds = 300
    return jsonify({
        "ok": True,
        "stream_token": create_scoped_jwt(
            "vision_stream",
            role="operator",
            subject="vision_stream",
            ttl_seconds=ttl_seconds,
        ),
        "expires_in": ttl_seconds,
    })


@api_bp.route("/vision/source/status", methods=["GET"])
def vision_source_status():
    """Return the active frame source status without requiring the MJPEG stream."""
    status = runtime_vision_status()
    camera = status.get("camera", {}) if isinstance(status, dict) else {}
    if not isinstance(camera, dict):
        camera = {}
    source = str(camera.get("source") or getattr(config, "VISION_SOURCE", "opencv"))
    diagnostics = _vision_source_diagnostics(camera, source)
    return jsonify({
        "ok": True,
        "source": source,
        "camera": camera,
        "diagnostics": diagnostics,
        "config": {
            "camera_index": int(getattr(config, "CAMERA_INDEX", 0) or 0),
            "tmflow_json": {
                "host": str(getattr(config, "VISION_TMFLOW_IMAGE_HOST", "")),
                "port": int(getattr(config, "VISION_TMFLOW_IMAGE_PORT", 5891)),
                "timeout_sec": float(getattr(config, "VISION_TMFLOW_IMAGE_TIMEOUT_SEC", 2.0)),
                "max_message_bytes": int(getattr(config, "VISION_TMFLOW_IMAGE_MAX_MESSAGE_BYTES", 1_048_576)),
                "fps_limit": float(getattr(config, "VISION_TMFLOW_IMAGE_FPS_LIMIT", 2.0)),
            },
            "tmvision_http": {
                "classify_path": "/api/vision/tmvision/classify",
                "detect_path": "/api/vision/tmvision/detect",
                "image_fields": ["file", "image", "frame"],
                "max_request_bytes": int(getattr(config, "MAX_REQUEST_BYTES", 1_048_576)),
                "max_image_bytes": int(getattr(config, "VISION_TMFLOW_IMAGE_MAX_MESSAGE_BYTES", 1_048_576)),
            },
            "tmflow_socket_ingest": {
                "enabled": bool(getattr(config, "TMFLOW_INGEST_SERVER_ENABLED", False)),
                "host": str(getattr(config, "TMFLOW_INGEST_SERVER_HOST", "")),
                "port": int(getattr(config, "TMFLOW_INGEST_SERVER_PORT", 5892)),
                "max_message_bytes": int(getattr(config, "TMFLOW_INGEST_MAX_MESSAGE_BYTES", 1_048_576)),
                "telemetry_max_age_sec": float(getattr(config, "TMFLOW_INGEST_TELEMETRY_MAX_AGE_SEC", 3.0)),
                "key_configured": bool(str(getattr(config, "TMFLOW_INGEST_KEY", "") or "").strip()),
            },
        },
        "vision": status,
    })


def _vision_capture_available_status() -> dict:
    status = runtime_vision_status()
    unavailable = (
        status.get("mode") == "unavailable"
        or bool(status.get("startup_failure"))
        or status.get("available") is False
    )
    if unavailable:
        raise RuntimeError(status.get("startup_error") or status.get("last_error") or "vision is unavailable")
    return status


def _vision_capture_response() -> dict:
    capture_session = vision_capture_session.snapshot()
    return {
        "ok": True,
        "capture_session": capture_session,
        "vision": vision_capture_session.vision_payload(),
    }


def _start_vision_capture(payload: dict, *, source: str) -> dict:
    _vision_capture_available_status()
    capture_session = vision_capture_session.start(
        source=source,
        trace_id=payload.get("trace_id"),
        interval_sec=payload.get("interval_sec"),
        timeout_sec=payload.get("timeout_sec"),
    )
    vision_capture_session.publish_status(
        source=source,
        toast="影像辨識已啟動，每 2 秒擷取一次最新畫面。",
        level="info",
    )
    return {
        "ok": True,
        "capture_session": capture_session,
        "vision": vision_capture_session.vision_payload(),
    }


def _stop_vision_capture(*, source: str, reason: str = "operator_stopped") -> dict:
    capture_session = vision_capture_session.stop(reason=reason)
    vision_capture_session.publish_status(
        source=source,
        toast="影像辨識已停止。",
        level="info",
    )
    return {
        "ok": True,
        "capture_session": capture_session,
        "vision": vision_capture_session.vision_payload(),
    }


@api_bp.route("/vision/capture/status", methods=["GET"])
def vision_capture_status():
    """Return the current operator-triggered recognition round status."""
    return jsonify(_vision_capture_response())


@api_bp.route("/vision/capture/start", methods=["POST"])
def vision_capture_start():
    """Start a recognition round that processes one frame per interval."""
    try:
        payload = json_object_payload()
    except ValueError as exc:
        return error_response("validation_failed", str(exc), 400)
    try:
        return jsonify(_start_vision_capture(payload, source="vision_capture_api"))
    except RuntimeError as exc:
        return error_response("vision_capture_unavailable", str(exc), 409)


@api_bp.route("/vision/capture/stop", methods=["POST"])
def vision_capture_stop():
    """Stop the current operator-triggered recognition round."""
    return jsonify(_stop_vision_capture(source="vision_capture_api"))


@api_bp.route("/player/vision-capture", methods=["POST"])
def player_vision_capture():
    """Public player-view control for post-move recognition."""
    try:
        payload = json_object_payload()
    except ValueError as exc:
        return error_response("validation_failed", str(exc), 400)

    action = str(payload.get("action") or "toggle").strip().lower()
    if action == "toggle":
        action = "stop" if vision_capture_session.is_active() else "start"

    if action == "start":
        try:
            return jsonify(_start_vision_capture(payload, source="player_vision_capture"))
        except RuntimeError as exc:
            return error_response("vision_capture_unavailable", str(exc), 409)
    if action == "stop":
        return jsonify(_stop_vision_capture(source="player_vision_capture"))

    return error_response("invalid_vision_capture_action", "Vision capture action must be start, stop, or toggle.", 400)


@api_bp.route("/player-done", methods=["POST"])
def player_done():
    """Player-facing button: the player has moved and Python should start recognition."""
    try:
        payload = json_object_payload()
    except ValueError as exc:
        return error_response("validation_failed", str(exc), 400)

    from backend.application.use_cases.coordinate_workflow import workflow_coordinator

    trace_id = workflow_coordinator.player_done(payload)
    payload = {**payload, "trace_id": trace_id}

    if vision_capture_session.is_active():
        response = _vision_capture_response()
        response["action"] = "player_done"
        response["status"] = "already_active"
        response["trace_id"] = trace_id
        return jsonify(response)

    try:
        response = _start_vision_capture(payload, source="player_done")
    except RuntimeError as exc:
        return error_response("vision_capture_unavailable", str(exc), 409)
    response["action"] = "player_done"
    response["trace_id"] = trace_id
    return jsonify(response)


@api_bp.route("/vision/tmflow/frame", methods=["POST"])
def ingest_tmflow_frame():
    """Receive a TMflow-pushed JPEG/base64 frame over HTTP JSON."""
    if not _tmflow_frame_ingest_authorized():
        return error_response(
            "tmflow_frame_ingest_unauthorized",
            "TMflow frame ingest requires a valid bearer token, configured ingest key, or trusted lab robot IP.",
            401,
        )
    try:
        payload = json_object_payload()
    except ValueError as exc:
        return error_response("validation_failed", str(exc), 400)

    result = _ingest_frame_payload(payload)
    if not result.get("ok"):
        return error_response(
            "tmflow_frame_ingest_failed",
            result.get("reason") or "TMflow frame could not be decoded.",
            400,
            details=result,
        )
    return jsonify({
        "ok": True,
        "mode": "tmflow_http_push",
        **result,
        "source": str(getattr(config, "VISION_SOURCE", "opencv")),
    })


@api_bp.route("/vision/tmvision/classify", methods=["POST"])
def ingest_tmvision_classification_frame():
    """Receive TMvision External Classification image POSTs from the EIH camera."""
    if not _tmflow_frame_ingest_authorized():
        return error_response(
            "tmvision_frame_ingest_unauthorized",
            "TMvision frame ingest requires a valid ingest key or trusted lab robot IP.",
            401,
        )

    result = _ingest_tmvision_image_request()
    if not result.get("ok"):
        return jsonify({
            "message": result.get("reason") or "frame_decode_failed",
            "result": "error",
            "score": 0.0,
        }), 400

    payload = {
        "message": "success",
        "result": "frame_received",
        "score": 1.0,
    }
    if _tmvision_debug_response_enabled():
        payload.update({
            "mode": "tmvision_external_classification",
            "frame_size": result.get("frame_size"),
            "image_field": result.get("image_field"),
        })
    return jsonify(payload)


@api_bp.route("/vision/tmvision/detect", methods=["POST"])
def ingest_tmvision_detection_frame():
    """Receive TMvision External Detection image POSTs from the EIH camera."""
    if not _tmflow_frame_ingest_authorized():
        return error_response(
            "tmvision_frame_ingest_unauthorized",
            "TMvision frame ingest requires a valid ingest key or trusted lab robot IP.",
            401,
        )

    result = _ingest_tmvision_image_request()
    if not result.get("ok"):
        return jsonify({
            "message": result.get("reason") or "frame_decode_failed",
            "annotations": [],
        }), 400

    annotations = _tmvision_detection_probe_annotations(result)
    detection = None
    mode = "tmvision_external_detection_probe" if annotations else "tmvision_external_detection_yolo"
    if not annotations:
        detection = _detect_tmvision_frame(result, vision_system)
        if not detection.get("ok"):
            return jsonify({
                "message": detection.get("reason") or "vision_detection_failed",
                "annotations": [],
            }), int(detection.get("status_code") or 503)
        annotations = detection.get("annotations") or []

    payload = {
        "message": "success",
        "count": len(annotations),
        "annotations_count": len(annotations),
        "annotations": annotations,
    }
    if _tmvision_debug_response_enabled():
        payload.update({
            "mode": mode,
            "frame_size": result.get("frame_size"),
            "image_field": result.get("image_field"),
            "detection": detection.get("detection") if isinstance(detection, dict) else None,
        })
    return jsonify(payload)


@api_bp.route("/vision/source/test-frame", methods=["POST"])
def inject_vision_source_test_frame():
    """Inject a diagnostic frame into the current vision pipeline."""
    try:
        payload = json_object_payload()
    except ValueError as exc:
        return error_response("validation_failed", str(exc), 400)

    try:
        from backend.infrastructure.vision.camera.frame_buffer import frame_buffer
        from backend.infrastructure.vision.camera.tmflow_json_source import TMflowJsonFrameSource
    except Exception:
        current_app.logger.debug("Vision source test dependencies unavailable", exc_info=True)
        return error_response("vision_dependencies_unavailable", "Vision dependencies are not available.", 503)

    frame = None
    mode = "synthetic"
    if any(isinstance(payload.get(key), str) and payload.get(key) for key in ("image", "image_base64", "data")):
        frame = TMflowJsonFrameSource.decode_payload(payload)
        mode = "decoded_payload"
        if frame is None:
            return error_response("invalid_test_frame", "Image payload could not be decoded as JPEG/base64.", 400)
    else:
        try:
            frame = _synthetic_vision_test_frame(payload)
        except Exception as exc:
            current_app.logger.debug("Synthetic vision test frame failed", exc_info=True)
            return error_response("test_frame_generation_failed", str(exc), 500, recoverable=False)

    for _ in range(3):
        try:
            frame_buffer.put_raw(frame.copy())
        except Exception:
            frame_buffer.put_raw(frame)

    height, width = frame.shape[:2]
    return jsonify({
        "ok": True,
        "mode": mode,
        "frames_injected": 3,
        "frame_size": [int(width), int(height)],
        "source": str(getattr(config, "VISION_SOURCE", "opencv")),
        "status": runtime_vision_status(),
    })


def _ingest_frame_payload(payload: dict) -> dict:
    return _ingest_frame_payload_io(payload, vision_system)


@api_bp.route("/vision/stream")
def video_feed():
    """Real-time AI Vision MJPEG Stream."""
    return Response(
        vision_system.get_video_stream(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@api_bp.route("/video_feed")
def legacy_video_feed():
    return video_feed()


@api_bp.route("/vision/snapshot", methods=["GET"])
def snapshot():
    """Captures a single frame from the current vision system."""
    try:
        import cv2
        from backend.infrastructure.vision.camera.frame_buffer import frame_buffer
    except Exception:
        current_app.logger.debug("Vision snapshot dependencies unavailable", exc_info=True)
        return error_response("vision_dependencies_unavailable", "Vision dependencies are not available.", 503)

    frame_source = "buffer"
    if hasattr(frame_buffer, "peek_latest_raw"):
        frame = frame_buffer.peek_latest_raw(max_age_sec=_snapshot_max_age_sec())
    else:
        frame = None
    if frame is None:
        frame = frame_buffer.get_latest_raw(timeout=0.2) if hasattr(frame_buffer, "get_latest_raw") else frame_buffer.get_raw(timeout=0.2)

    if frame is None:
        frame = _capture_opencv_snapshot_fallback()
        frame_source = "direct_opencv" if frame is not None else frame_source
        if frame is not None:
            try:
                frame_buffer.put_raw(frame)
            except Exception:
                current_app.logger.debug("Failed to cache direct OpenCV snapshot frame", exc_info=True)

    if frame is None:
        return error_response(
            "camera_feed_unavailable",
            "No camera feed is available.",
            503,
            details=_snapshot_unavailable_details(frame_buffer),
        )

    ret, buffer = cv2.imencode(".jpg", frame)
    if not ret:
        return error_response("snapshot_encoding_failed", "Snapshot encoding failed.", 500, recoverable=False)

    response = Response(buffer.tobytes(), mimetype="image/jpeg")
    response.headers["X-Vision-Frame-Source"] = frame_source
    return response


@api_bp.route("/snapshot", methods=["GET"])
def legacy_snapshot():
    return snapshot()


@api_bp.route("/camera/latest", methods=["GET"])
def camera_latest():
    """Minimal monitor API alias for the latest backend-provided camera image."""
    return snapshot()
