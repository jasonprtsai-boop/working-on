from __future__ import annotations

import hmac
import ipaddress
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
        backend_used = ""
        cap = None
        for backend_name, backend in _opencv_camera_backends(cv2):
            try:
                cap = cv2.VideoCapture(i, backend) if backend is not None else cv2.VideoCapture(i)
                if cap is not None and cap.isOpened():
                    available = True
                    backend_used = backend_name
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
        candidates.append({"index": i, "available": bool(available), "backend": backend_used})

    payload = {
        "current": current,
        "source": str(getattr(config, "VISION_SOURCE", "opencv")),
        "sources": [
            {"id": "opencv", "label": "USB / OpenCV"},
            {"id": "tmflow_json", "label": "TMflow JSON"},
        ],
        "candidates": candidates,
        "cached": False,
        "cache_ttl_sec": ttl,
    }
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


def _vision_source_diagnostics(camera: dict, source: str) -> dict:
    robot_status = _robot_control_status()
    control_connected = bool(robot_status.get("connected") or robot_status.get("is_connected"))
    fake_robot = bool(getattr(config, "FAKE_ROBOT", True))
    control_status = "simulation" if fake_robot else ("connected" if control_connected else "offline")
    vision_connected = bool(camera.get("connected") or camera.get("opened"))
    vision_running = bool(camera.get("running"))
    key_configured = bool(str(getattr(config, "VISION_TMFLOW_INGEST_KEY", "") or "").strip())
    key_status = _tmflow_vision_ingest_key_status(source=source, key_configured=key_configured)

    return {
        "control_channel": {
            "label": "5890 control",
            "adapter": str(getattr(config, "ROBOT_ADAPTER", "tmflow_json")),
            "host": str(getattr(config, "ROBOT_IP", "")),
            "port": int(getattr(config, "ROBOT_PORT", 5890)),
            "endpoint": f"{getattr(config, 'ROBOT_IP', '')}:{getattr(config, 'ROBOT_PORT', 5890)}",
            "connected": control_connected,
            "status": control_status,
            "fake_robot": fake_robot,
            "last_error": robot_status.get("last_error") or robot_status.get("error"),
        },
        "vision_channel": {
            "label": "5891 vision",
            "source": source,
            "host": str(getattr(config, "VISION_TMFLOW_IMAGE_HOST", "")),
            "port": int(getattr(config, "VISION_TMFLOW_IMAGE_PORT", 5891)),
            "endpoint": camera.get("endpoint")
            or f"{getattr(config, 'VISION_TMFLOW_IMAGE_HOST', '')}:{getattr(config, 'VISION_TMFLOW_IMAGE_PORT', 5891)}",
            "connected": vision_connected,
            "running": vision_running,
            "status": "connected" if vision_connected else ("starting" if vision_running else "offline"),
            "frames_received": int(camera.get("frames_received") or 0),
            "last_frame_age_sec": camera.get("last_frame_age_sec"),
            "last_frame_at": camera.get("last_frame_at"),
            "reconnects": int(camera.get("reconnects") or 0),
            "decode_failures": int(camera.get("decode_failures") or 0),
            "dropped_frames": int(camera.get("dropped_frames") or 0),
            "fps_limit": float(camera.get("fps_limit") or getattr(config, "VISION_TMFLOW_IMAGE_FPS_LIMIT", 2.0)),
            "last_error": camera.get("last_error"),
        },
        "socket_ingest_channel": _tmflow_socket_ingest_status(),
        "ingest_key": key_status,
    }


def _tmflow_socket_ingest_status() -> dict:
    max_age = float(getattr(config, "TMFLOW_INGEST_TELEMETRY_MAX_AGE_SEC", 3.0))
    status = {
        "label": "5892 TMflow push",
        "enabled": bool(getattr(config, "TMFLOW_INGEST_SERVER_ENABLED", False)),
        "host": str(getattr(config, "TMFLOW_INGEST_SERVER_HOST", "")),
        "port": int(getattr(config, "TMFLOW_INGEST_SERVER_PORT", 5892)),
        "endpoint": f"{getattr(config, 'TMFLOW_INGEST_SERVER_HOST', '')}:{getattr(config, 'TMFLOW_INGEST_SERVER_PORT', 5892)}",
        "key_configured": bool(str(getattr(config, "TMFLOW_INGEST_KEY", "") or "").strip()),
    }
    if not status["enabled"]:
        try:
            from backend.infrastructure.robot.tmflow_ingest_state import tmflow_ingest_state

            status["running"] = False
            status["telemetry"] = tmflow_ingest_state.status(max_age_sec=max_age)
        except Exception:
            status["running"] = False
        status["status"] = "disabled"
        return status
    try:
        from backend.application.container import container
        from backend.infrastructure.robot.tmflow_ingest_state import tmflow_ingest_state

        server = container.get("tmflow_ingest_server")
        if server and hasattr(server, "get_status"):
            status.update(dict(server.get_status()))
        else:
            status["running"] = False
            status["telemetry"] = tmflow_ingest_state.status(max_age_sec=max_age)
    except Exception as exc:
        status.update({"running": False, "last_error": str(exc)})
    status["status"] = (
        "connected"
        if (status.get("running") and (status.get("telemetry") or {}).get("connected"))
        else ("listening" if status.get("running") else ("disabled" if not status.get("enabled") else "offline"))
    )
    return status


def _robot_control_status() -> dict:
    try:
        from backend.application.container import container

        robot = container.get("robot")
        if robot and hasattr(robot, "get_status"):
            status = robot.get_status() or {}
            if isinstance(status, dict):
                return dict(status)
    except Exception as exc:
        return {"connected": False, "error": str(exc)}
    return {"connected": False}


def _tmflow_vision_ingest_key_status(*, source: str, key_configured: bool) -> dict:
    source = str(source or "").strip().lower()
    bind_host = str(getattr(config, "BIND_HOST", "127.0.0.1") or "").strip()
    fake_robot = bool(getattr(config, "FAKE_ROBOT", True))
    exposed_network = bind_host in {"0.0.0.0", "::"}
    required = source == "tmflow_json" and (
        bool(getattr(config, "IS_PRODUCTION", False)) or exposed_network or not fake_robot
    )
    return {
        "configured": bool(key_configured),
        "required": bool(required),
        "ok": bool((not required) or key_configured),
        "exposed_network": bool(exposed_network),
        "fake_robot": fake_robot,
    }


def _tmflow_frame_ingest_authorized() -> bool:
    try:
        from backend.utils.auth import verify_request_token

        claims = verify_request_token()
        if str((claims or {}).get("role") or "").lower() in {"operator", "setup", "admin"}:
            return True
    except Exception:
        pass

    expected_key = str(getattr(config, "VISION_TMFLOW_INGEST_KEY", "") or "").strip()
    provided_key = str(
        request.headers.get("X-TMflow-Key")
        or request.headers.get("X-TMflow-Vision-Key")
        or request.args.get("key")
        or request.args.get("stream_key")
        or ""
    ).strip()
    if expected_key:
        return hmac.compare_digest(provided_key, expected_key)

    if getattr(config, "IS_PRODUCTION", False):
        return False

    remote = str(request.remote_addr or "").strip()
    trusted_hosts = {
        "127.0.0.1",
        "::1",
        str(getattr(config, "ROBOT_IP", "") or "").strip(),
        str(getattr(config, "ROBOT_PC_IP", "") or "").strip(),
    }
    if remote in trusted_hosts:
        return True
    try:
        remote_ip = ipaddress.ip_address(remote)
        return bool(remote_ip.is_loopback or remote_ip.is_link_local)
    except ValueError:
        return False


def _synthetic_vision_test_frame(payload: dict):
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
    cv2.putText(frame, time.strftime("%Y-%m-%d %H:%M:%S"), (margin + 8, height - margin - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (203, 213, 225), 2)
    return frame


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
