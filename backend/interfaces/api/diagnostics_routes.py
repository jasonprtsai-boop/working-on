from __future__ import annotations

import os

from flask import current_app, jsonify

from backend.interfaces.api.shared import (
    api_bp,
    asset_info,
    config,
    container,
    engine_worker,
    error_response,
    has_module,
    runtime_metrics_report,
    runtime_observability_report,
    runtime_vision_status,
    vision_system,
)
from backend.infrastructure.vision.model_assets import vision_model_report


@api_bp.route("/health", methods=["GET"])
def health():
    """Detailed local health and diagnostics report."""
    engine = container.get("engine")
    engine_path = os.path.abspath(getattr(config, "ENGINE_PATH", ""))
    nnue_path = os.path.abspath(getattr(config, "NNUE_PATH", ""))

    engine_proc = getattr(engine, "process", None) if engine else None
    engine_running = bool(engine_proc and getattr(engine_proc, "returncode", None) is None)
    probe_status = engine.get_probe_status() if engine and hasattr(engine, "get_probe_status") else {}
    try:
        bootstrap_status = container.get("bootstrap_status")
    except Exception:
        current_app.logger.debug("bootstrap_status lookup failed during health check", exc_info=True)
        bootstrap_status = {}

    runtime_vision = runtime_vision_status()
    vision_simulation = bool(runtime_vision.get("simulation") or getattr(config, "FAKE_VISION", False))
    vision_fallback = bool(runtime_vision.get("fallback") or runtime_vision.get("fallback_reason"))
    active_model_path = (
        ((runtime_vision.get("detector") or {}) if isinstance(runtime_vision, dict) else {}).get("model_path")
        or ((runtime_vision.get("model") or {}) if isinstance(runtime_vision, dict) else {}).get("path")
        or getattr(config, "YOLO_MODEL_PATH", "")
    )
    model_report = vision_model_report(active_path=active_model_path)

    report = {
        "ok": bool(bootstrap_status.get("ready", True)),
        "assets": {
            "engine": asset_info(getattr(config, "ENGINE_PATH", "")),
            "nnue": asset_info(getattr(config, "NNUE_PATH", "")),
            "vision_model": asset_info(getattr(config, "YOLO_MODEL_PATH", "")),
            "vision_models": model_report,
            "protected_root": asset_info(os.path.join("backend", "infrastructure", "protected_assets")),
        },
        "engine": {
            "enabled": engine_worker.is_enabled(),
            "worker_status": getattr(engine_worker, "status", "unknown"),
            "worker_failures": getattr(engine_worker, "failure_count", 0),
            "worker_backoff_sec": getattr(engine_worker, "backoff_sec", lambda: 0.0)(),
            "worker_last_error": getattr(engine_worker, "last_error", None),
            "worker_last_analysis_at": getattr(engine_worker, "last_analysis_at", 0.0),
            "path": engine_path,
            "path_exists": os.path.exists(engine_path),
            "nnue_path": nnue_path,
            "nnue_exists": os.path.exists(nnue_path),
            "process_running": engine_running,
            "startup_error": getattr(engine, "last_startup_error", None),
            "compatibility_status": probe_status.get("status"),
            "active_nnue_path": probe_status.get("active_nnue_path"),
            "candidate_count": len(probe_status.get("candidates", []) or []),
            "probe_report": probe_status.get("report", []),
        },
        "vision": {
            "fake_vision": bool(getattr(config, "FAKE_VISION", False)),
            "simulation": vision_simulation,
            "fallback": vision_fallback,
            "fallback_reason": runtime_vision.get("fallback_reason"),
            "detector": getattr(getattr(vision_system, "detector", None), "__class__", type("x", (), {})).__name__,
            "yolo_model_path": os.path.abspath(getattr(config, "YOLO_MODEL_PATH", "") or ""),
            "yolo_model_exists": os.path.exists(os.path.abspath(getattr(config, "YOLO_MODEL_PATH", "") or "")),
            "model_type": getattr(config, "YOLO_MODEL_TYPE", "yolo26"),
            "ultralytics_min_version": getattr(config, "ULTRALYTICS_MIN_VERSION", "8.4.55"),
            "device": getattr(config, "VISION_DEVICE", "cpu"),
            "runtime": runtime_vision,
            "models": model_report,
            "tf_model_dir": os.path.abspath(os.path.join("backend", "infrastructure", "vision", "models", "chess_pieces")),
            "tf_model_exists": os.path.exists(os.path.abspath(os.path.join("backend", "infrastructure", "vision", "models", "chess_pieces", "saved_model.pb"))),
        },
        "deps": {
            "numpy": has_module("numpy"),
            "cv2": has_module("cv2"),
            "tensorflow": has_module("tensorflow"),
            "ultralytics": has_module("ultralytics"),
        },
        "runtime": {
            "system_mode": getattr(config, "SYSTEM_MODE", "unknown"),
            "environment": getattr(config, "APP_ENV", "unknown"),
            **runtime_observability_report(),
        },
        "bootstrap": bootstrap_status,
    }
    return jsonify(report)


@api_bp.route("/runtime/status", methods=["GET"])
def runtime_status():
    return jsonify(runtime_observability_report())


@api_bp.route("/runtime/metrics", methods=["GET"])
def runtime_metrics():
    return jsonify(runtime_metrics_report())


@api_bp.route("/vision/status", methods=["GET"])
def vision_status():
    yolo_path = os.path.abspath(getattr(config, "YOLO_MODEL_PATH", "") or "")
    tf_saved_model = os.path.abspath(os.path.join("backend", "infrastructure", "vision", "models", "chess_pieces", "saved_model.pb"))
    runtime_status = runtime_vision_status()
    vision_simulation = bool(runtime_status.get("simulation") or getattr(config, "FAKE_VISION", False))
    vision_fallback = bool(runtime_status.get("fallback") or runtime_status.get("fallback_reason"))
    active_model_path = (
        ((runtime_status.get("detector") or {}) if isinstance(runtime_status, dict) else {}).get("model_path")
        or ((runtime_status.get("model") or {}) if isinstance(runtime_status, dict) else {}).get("path")
        or yolo_path
    )
    return jsonify({
        "fake_vision": bool(getattr(config, "FAKE_VISION", False)),
        "simulation": vision_simulation,
        "fallback": vision_fallback,
        "fallback_reason": runtime_status.get("fallback_reason"),
        "system": vision_system.__class__.__name__,
        "detector": getattr(getattr(vision_system, "detector", None), "__class__", type("x", (), {})).__name__,
        "camera_index": getattr(config, "CAMERA_INDEX", 0),
        "runtime": runtime_status,
        "models": {
            "yolo_model_path": yolo_path,
            "yolo_model_exists": bool(yolo_path and os.path.exists(yolo_path)),
            "yolo_model_type": getattr(config, "YOLO_MODEL_TYPE", "yolo26"),
            "ultralytics_min_version": getattr(config, "ULTRALYTICS_MIN_VERSION", "8.4.55"),
            "device": getattr(config, "VISION_DEVICE", "cpu"),
            "vision_models": vision_model_report(active_path=active_model_path),
            "tf_saved_model": tf_saved_model,
            "tf_saved_model_exists": os.path.exists(tf_saved_model),
        },
        "deps": {
            "numpy": has_module("numpy"),
            "cv2": has_module("cv2"),
            "tensorflow": has_module("tensorflow"),
            "ultralytics": has_module("ultralytics"),
        },
    })


@api_bp.route("/engine/status", methods=["GET"])
def engine_status():
    engine = container.get("engine")
    if not engine or not hasattr(engine, "get_probe_status"):
        return error_response("engine_not_available", "Engine service is not available.", 503)
    return jsonify(engine.get_probe_status())


@api_bp.route("/assets/status", methods=["GET"])
def assets_status():
    return jsonify({
        "engine": asset_info(getattr(config, "ENGINE_PATH", "")),
        "nnue": asset_info(getattr(config, "NNUE_PATH", "")),
        "vision_model": asset_info(getattr(config, "YOLO_MODEL_PATH", "")),
        "vision_models": vision_model_report(),
        "protected_root": asset_info(os.path.join("backend", "infrastructure", "protected_assets")),
    })


@api_bp.route("/ready", methods=["GET"])
def ready():
    try:
        engine = container.get("engine")
    except Exception:
        current_app.logger.debug("engine lookup failed during readiness check", exc_info=True)
        engine = None
    try:
        vision = container.get("vision")
    except Exception:
        current_app.logger.debug("vision lookup failed during readiness check", exc_info=True)
        vision = None
    try:
        bootstrap_status = container.get("bootstrap_status")
    except Exception:
        current_app.logger.debug("bootstrap_status lookup failed during readiness check", exc_info=True)
        bootstrap_status = {}
    return jsonify({
        "ready": bool(bootstrap_status.get("ready", engine is not None and vision is not None)),
        "engine_registered": engine is not None,
        "vision_registered": vision is not None,
        "robot_registered": bool(bootstrap_status.get("robot_registered", False)),
        "robot_connected": bool(bootstrap_status.get("robot_connected", False)),
        "bootstrap": bootstrap_status,
    })
