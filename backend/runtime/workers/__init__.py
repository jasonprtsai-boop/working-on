from .worker_manager import worker_manager
from .engine_worker import engine_worker
from .robot_status_worker import robot_status_worker
from .monitoring_worker import monitoring_worker
from .camera_worker import CameraWorker
from .vision_inference_worker import VisionInferenceWorker

def initialize_workers():
    """Register all core workers with the manager."""
    from backend.application.container import container
    import logging

    logger = logging.getLogger("workers.init")

    # Optional: legacy camera/pipeline workers (only when wired in container).
    try:
        camera = container.get("camera_hw")
        camera_worker = CameraWorker(camera)
        worker_manager.register_worker("camera", camera_worker)
    except Exception:
        logger.info("[workers] camera_hw not wired; skipping CameraWorker.")

    try:
        pipeline = container.get("vision_pipeline")
        inference_worker = VisionInferenceWorker(pipeline)
        worker_manager.register_worker("vision_inference", inference_worker)
    except Exception:
        logger.info("[workers] vision_pipeline not wired; skipping VisionInferenceWorker.")

    worker_manager.register_worker("engine", engine_worker)
    worker_manager.register_worker("robot_status", robot_status_worker)
    worker_manager.register_worker("monitoring", monitoring_worker)

    # Optional watchdogs (only start when available).
    try:
        from backend.runtime.watchdog.robot_watchdog import robot_watchdog
        robot_watchdog.start_monitoring()
        worker_manager.register_worker("robot_watchdog", robot_watchdog)
    except Exception:
        logger.info("[workers] robot_watchdog not available; skipping.")

    # Start all background threads
    worker_manager.start_all()
