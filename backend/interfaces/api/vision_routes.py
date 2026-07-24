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

_camera_discovery_cache = {"key": None, "expires_at": 0.0, "payload": None}


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
            details={"candidates": [], "current": getattr(config, "CAMERA_INDEX", 0)},
        )

    max_index = bounded_int_arg("max", 6, 1, 16)
    current = int(getattr(config, "CAMERA_INDEX", 0) or 0)
    cache_key = (max_index, current)
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

    for i in range(max_index):
        available = False
        cap = None
        try:
            try:
                cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            except Exception:
                current_app.logger.debug("CAP_DSHOW camera probe failed for index %s", i, exc_info=True)
                cap = cv2.VideoCapture(i)
            if cap is not None and cap.isOpened():
                available = True
        except Exception:
            current_app.logger.debug("Camera probe failed for index %s", i, exc_info=True)
            available = False
        finally:
            try:
                if cap is not None:
                    cap.release()
            except Exception:
                current_app.logger.debug("Camera release failed for index %s", i, exc_info=True)
        candidates.append({"index": i, "available": bool(available)})

    payload = {"current": current, "candidates": candidates, "cached": False, "cache_ttl_sec": ttl}
    if ttl > 0:
        _camera_discovery_cache.update({"key": cache_key, "expires_at": now + ttl, "payload": dict(payload)})
    return jsonify(payload)


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

    frame = frame_buffer.get_raw()
    if frame is None:
        return error_response("camera_feed_unavailable", "No camera feed is available.", 503)

    ret, buffer = cv2.imencode(".jpg", frame)
    if not ret:
        return error_response("snapshot_encoding_failed", "Snapshot encoding failed.", 500, recoverable=False)

    return Response(buffer.tobytes(), mimetype="image/jpeg")


@api_bp.route("/snapshot", methods=["GET"])
def legacy_snapshot():
    return snapshot()
