import atexit
import asyncio

from backend.events.bus.event_bus import bus
from backend.events.event_types import EventType
from backend.events.models.base_event import BaseEvent
from backend.state.store.manager.state_manager import state_manager
from backend.state.store.state_store import state_store
from backend.application.container import container
from backend.runtime.workers import initialize_workers
from backend.runtime.workers.worker_manager import worker_manager
from backend.runtime.workers.engine_worker import engine_worker
from backend.utils import config
from backend.utils.logger import logger
from backend.app.task_queue import task_queue
from backend.infrastructure.robot.queue.robot_queue import robot_queue
from backend.core.exceptions import FatalBootstrapError, ComponentDegradedError


def _register_shutdown_hooks(runtime, vision_system, tmflow_ingest_server=None):
    """Register exactly one best-effort process teardown hook."""
    if getattr(_register_shutdown_hooks, "_registered", False):
        return

    def _shutdown():
        try:
            worker_manager.shutdown_sync(runtime=runtime, timeout=5.0)
        except Exception as exc:
            logger.warning(f"[Bootstrap] worker shutdown degraded: {exc}", exc_info=True)
        try:
            engine = container.get("engine")
            if engine and hasattr(engine, "shutdown"):
                if getattr(runtime, "_loop", None) and runtime._loop.is_running():
                    runtime.run_task(engine.shutdown()).result(timeout=8.0)
                else:
                    asyncio.run(engine.shutdown())
            elif engine and hasattr(engine, "close"):
                if getattr(runtime, "_loop", None) and runtime._loop.is_running():
                    runtime.run_task(engine.close()).result(timeout=8.0)
                else:
                    asyncio.run(engine.close())
        except Exception as exc:
            logger.warning(f"[Bootstrap] engine shutdown degraded: {exc}", exc_info=True)
        try:
            if vision_system and hasattr(vision_system, "stop"):
                vision_system.stop()
        except Exception as exc:
            logger.warning(f"[Bootstrap] vision shutdown degraded: {exc}", exc_info=True)
        try:
            if tmflow_ingest_server and hasattr(tmflow_ingest_server, "stop"):
                tmflow_ingest_server.stop()
        except Exception as exc:
            logger.warning(f"[Bootstrap] TMflow ingest shutdown degraded: {exc}", exc_info=True)
        try:
            runtime.stop()
        except Exception as exc:
            logger.warning(f"[Bootstrap] runtime shutdown degraded: {exc}", exc_info=True)

    atexit.register(_shutdown)
    _register_shutdown_hooks._registered = True


def _register_optional_vision_pipeline(container, config):
    """Register queue-based vision pipeline services only when explicitly enabled."""
    if not getattr(config, "VISION_WORKER_PIPELINE_ENABLED", False):
        return

    from backend.infrastructure.vision.board.board_mapper import BoardMapper
    from backend.infrastructure.vision.board.coordinate_system import BoardCoordinateSystem, GridConfig
    from backend.infrastructure.vision.camera import Camera
    from backend.infrastructure.vision.detection.yolo_detector import YOLODetector
    from backend.infrastructure.vision.fen.fen_generator import FENGenerator
    from backend.infrastructure.vision.morphology import MorphologyOptimizer
    from backend.infrastructure.vision.perspective import PerspectiveTransformer
    from backend.infrastructure.vision.pipeline import VisionPipeline
    from backend.infrastructure.vision.preprocess.image_preprocessor import ImagePreprocessor

    grid_config = GridConfig(
        rows=config.BOARD_ROWS,
        cols=config.BOARD_COLS,
        width=config.WARP_WIDTH,
        height=config.WARP_HEIGHT,
    )
    mapper = BoardMapper(BoardCoordinateSystem(grid_config))
    pipeline = VisionPipeline(
        camera=None,
        preprocess=ImagePreprocessor(),
        perspective=PerspectiveTransformer(target_size=(config.WARP_WIDTH, config.WARP_HEIGHT)),
        morphology=MorphologyOptimizer(),
        detector=YOLODetector(model_path=config.YOLO_MODEL_PATH),
        fen_gen=FENGenerator(rows=config.BOARD_ROWS, cols=config.BOARD_COLS),
        board_mapper=mapper,
    )
    container.register("camera_hw", Camera(index=config.CAMERA_INDEX))
    container.register("vision_pipeline", pipeline)

def bootstrap_system():
    """
    [Architectural Authority] Centralized Wiring & Initialization.
    Follows strict dependency ordering:
    1. Runtime (Loop, Logging)
    2. Infrastructure (DB, Modbus, Bus)
    3. State (SSOT)
    4. Services (Vision, Engine, Robot)
    5. Workers (Background tasks)
    """
    # Idempotency guard: avoid duplicate booting.
    if getattr(bootstrap_system, "_booted", False):
        logger.info("[Bootstrap] Already bootstrapped; skipping.")
        return

    logger.info("[Bootstrap] Bootstrapping S.M.A.R.T. Chess System...")

    if getattr(config, "IS_PRODUCTION", False):
        from backend.infrastructure.protected_assets.manifest import validate_assets
        logger.info("[Bootstrap] Validating protected asset hashes for production...")
        report = validate_assets()
        failed = [item for item in report.get("items", []) if not item.get("ok")]
        if failed:
            msg = f"Protected asset hash verification failed for: {', '.join(f['path'] for f in failed)}"
            logger.error(f"[Bootstrap] {msg}")
            raise FatalBootstrapError(msg)

    bootstrap_status = {
        "booted": False,
        "ready": False,
        "errors": [],
        "runtime_started": False,
        "engine_registered": False,
        "vision_registered": False,
        "robot_registered": False,
        "robot_connected": False,
        "workers_started": False,
        "workflow_started": False,
        "telemetry_started": False,
        "tmflow_ingest_started": False,
        "persistence_started": False,
        "vision_started": False,
        "vision_fallback": False,
        "vision_fallback_reason": None,
        "vision_mode": "unknown",
        "vision_unavailable": False,
        "vision_runtime_owner": getattr(config, "VISION_RUNTIME_OWNER", "vision_system"),
        "vision_start_error": None,
    }
    container.register("bootstrap_status", bootstrap_status)

    def record_bootstrap_error(component: str, exc: Exception, level: str = "warning"):
        entry = {"component": component, "error": str(exc), "level": level}
        bootstrap_status["errors"].append(entry)
        if level == "error":
            logger.error(f"[Bootstrap] {component} failed: {exc}", exc_info=True)
        else:
            logger.warning(f"[Bootstrap] {component} degraded: {exc}", exc_info=True)

    # 1. Start Async Runtime (The foundation for all async tasks)
    try:
        from backend.runtime.async_runtime import runtime
        runtime.start()
        bootstrap_status["runtime_started"] = True
        container.register("runtime", runtime)
        container.register("loop", runtime._loop)
        container.register("state", state_store)
    except Exception as exc:
        record_bootstrap_error("runtime", exc, level="error")
        raise FatalBootstrapError(f"Failed to start AsyncRuntime: {exc}") from exc

    # 2. Instantiate minimal services
    from backend.application.services.engine_service import EngineService
    from backend.application.services.vision_service import VisionService
    from backend.application.services.robot_facade import RobotFacade

    engine_service = EngineService()
    vision_service = VisionService()
    robot = RobotFacade()

    try:
        robot_connected = bool(robot.connect())
        bootstrap_status["robot_connected"] = robot_connected
        if not robot_connected and not getattr(config, "FAKE_ROBOT", False):
            record_bootstrap_error("robot.connect", ComponentDegradedError("Robot connection failed in real hardware mode."), level="error")
    except Exception as exc:
        record_bootstrap_error("robot.connect", exc)

    # 3. Register in Authoritative Container
    container.register("bus", bus)
    container.register("engine", engine_service)
    container.register("vision", vision_service)
    container.register("robot", robot)
    bootstrap_status["engine_registered"] = True
    bootstrap_status["vision_registered"] = True
    bootstrap_status["robot_registered"] = True
    logger.info("[Bootstrap] Core services registered in Container.")

    try:
        _register_optional_vision_pipeline(container, config)
    except Exception as exc:
        record_bootstrap_error("vision_pipeline.register", exc)

    if getattr(config, "ENGINE_PROBE_ON_BOOT", True) and not getattr(config, "ENGINE_AUTO_ANALYZE", True):
        try:
            runtime.run_task(engine_service.probe_compatible_pair())
            logger.info("[Bootstrap] Scheduled engine/NNUE compatibility probe.")
        except Exception as exc:
            record_bootstrap_error("engine.probe", exc)

    # 4. Wire Reducers (DIP)
    from backend.state.store.manager.reducer_registry import reducer_registry
    from backend.state.reducers.move_reducer import MoveReducer
    from backend.state.reducers.engine_reducer import EngineReducer
    from backend.state.reducers.robot_reducer import RobotReducer
    from backend.state.reducers.system_reducer import SystemReducer

    reducer_registry.register(EventType.VISION_MOVE_DETECTED, MoveReducer)
    reducer_registry.register(EventType.MOVE_APPLIED, MoveReducer)
    reducer_registry.register(EventType.GAME_PLAYER_MOVE, MoveReducer)
    reducer_registry.register(EventType.ENGINE_ANALYSIS_COMPLETED, EngineReducer)
    reducer_registry.register(EventType.ROBOT_MOVE_STARTED, RobotReducer)
    reducer_registry.register(EventType.ROBOT_MOVE_COMPLETED, RobotReducer)
    reducer_registry.register(EventType.ROBOT_STATUS_UPDATED, RobotReducer)
    reducer_registry.register(EventType.SYSTEM_RESET, SystemReducer)
    reducer_registry.register(EventType.SYSTEM_ERROR, SystemReducer)
    reducer_registry.register(EventType.DIAGNOSTICS_UPDATED, SystemReducer)
    logger.info("[Bootstrap] Reducers registered in Global Registry.")

    # 5. Wire StateManager to EventBus (SSOT)
    # We use is_async=True to ensure state mutations happen on the background loop
    try:
        bus.subscribe_all(state_manager.dispatch, is_async=True)
        logger.info("[Bootstrap] StateManager wired to EventBus (Async).")
    except Exception as exc:
        record_bootstrap_error("state_manager.wire", exc, level="error")
        raise FatalBootstrapError(f"Failed to wire StateManager: {exc}") from exc

    # 5b. Start bounded observability sidecar before workers emit diagnostics.
    try:
        from backend.observability.telemetry import telemetry_service
        telemetry_service.start()
        container.register("telemetry_service", telemetry_service)
        bootstrap_status["telemetry_started"] = True
        logger.info("[Bootstrap] TelemetryService started.")
    except Exception as exc:
        record_bootstrap_error("telemetry_service", exc)

    # 6. Initialize and Start Workers
    # Start old VisionSystem (legacy MJPEG stream)
    from backend.infrastructure.vision.vision_system import vision_system
    tmflow_ingest_server = None
    if getattr(config, "TMFLOW_INGEST_SERVER_ENABLED", False):
        try:
            from backend.infrastructure.robot.tmflow_socket_ingest_server import tmflow_socket_ingest_server

            tmflow_ingest_server = tmflow_socket_ingest_server
            bootstrap_status["tmflow_ingest_started"] = bool(tmflow_ingest_server.start())
            container.register("tmflow_ingest_server", tmflow_ingest_server)
            if not bootstrap_status["tmflow_ingest_started"]:
                record_bootstrap_error(
                    "tmflow_ingest.start",
                    ComponentDegradedError("TMflow socket ingest server did not start."),
                    level="error",
                )
        except Exception as exc:
            record_bootstrap_error("tmflow_ingest.start", exc, level="error")
    _register_shutdown_hooks(runtime, vision_system, tmflow_ingest_server)
    vision_runtime_status = {}
    if hasattr(vision_system, "get_status"):
        try:
            vision_runtime_status = dict(vision_system.get_status() or {})
        except Exception as exc:
            vision_runtime_status = {"error": str(exc)}
    fallback_reason = (
        vision_runtime_status.get("fallback_reason")
        or getattr(vision_system, "_fallback_reason", None)
    )
    bootstrap_status["vision_fallback"] = bool(
        vision_runtime_status.get("fallback")
        or getattr(vision_system, "_fallback_from_real_vision", False)
        or fallback_reason
    )
    bootstrap_status["vision_fallback_reason"] = str(fallback_reason) if fallback_reason else None
    bootstrap_status["vision_unavailable"] = bool(
        vision_runtime_status.get("mode") == "unavailable"
        or vision_runtime_status.get("startup_failure")
        or vision_runtime_status.get("available") is False
    )
    bootstrap_status["vision_mode"] = str(
        vision_runtime_status.get("mode")
        or (
            "fallback"
            if bootstrap_status["vision_fallback"]
            else ("simulation" if getattr(config, "FAKE_VISION", False) else "real")
        )
    )
    try:
        bootstrap_status["vision_started"] = bool(vision_system.start())
    except Exception as e:
        bootstrap_status["vision_started"] = False
        bootstrap_status["vision_start_error"] = str(e)
        record_bootstrap_error("vision.start", e, level="error")
    if bootstrap_status["vision_unavailable"] and not bootstrap_status["vision_start_error"]:
        bootstrap_status["vision_start_error"] = str(vision_runtime_status.get("startup_error") or "vision unavailable")
    bus.publish(BaseEvent.create(
        event_type=EventType.DIAGNOSTICS_UPDATED,
        source="bootstrap",
        payload={
            "vision": {
                "mode": bootstrap_status["vision_mode"],
                "owner": bootstrap_status["vision_runtime_owner"],
                "fallback": bootstrap_status["vision_fallback"],
                "simulation": bool(vision_runtime_status.get("simulation") or getattr(config, "FAKE_VISION", False)),
                "available": not bootstrap_status["vision_unavailable"],
                "status": (
                    "UNAVAILABLE"
                    if bootstrap_status["vision_unavailable"] or not bootstrap_status["vision_started"]
                    else ("FALLBACK" if bootstrap_status["vision_fallback"] else "READY")
                ),
                "fallback_reason": bootstrap_status["vision_fallback_reason"],
                "start_error": bootstrap_status["vision_start_error"],
            }
        },
    ))

    # Register E-Stop clear hooks
    try:
        task_queue.register_clear_hook(engine_worker.stop)
    except Exception as exc:
        record_bootstrap_error("estop.engine_clear_hook", exc)
    try:
        task_queue.register_clear_hook(robot_queue.clear)
    except Exception as exc:
        record_bootstrap_error("estop.robot_queue_clear_hook", exc)

    worker_start_results = initialize_workers() or {}
    bootstrap_status["worker_start_results"] = worker_start_results
    critical_workers = ("engine", "robot_status", "monitoring")
    failed_critical_workers = [
        name for name in critical_workers
        if not (worker_start_results.get(name) or {}).get("started")
    ]
    bootstrap_status["workers_started"] = not failed_critical_workers
    if failed_critical_workers:
        record_bootstrap_error(
            "workers.start",
            ComponentDegradedError(f"Critical workers failed to start: {', '.join(failed_critical_workers)}"),
            level="error",
        )
    logger.info("[Bootstrap] Background workers started via AsyncRuntime.")

    # 6. Start High-Level Workflow Orchestration
    from backend.application.use_cases.coordinate_workflow import workflow_coordinator
    workflow_coordinator.start()
    bootstrap_status["workflow_started"] = True
    logger.info("[Bootstrap] WorkflowCoordinator started.")

    # 7. Start Observability & Persistence
    from backend.observability.timeline.timeline_tracer import timeline_tracer
    timeline_tracer.start()
    logger.info("[Bootstrap] TimelineTracer started.")

    from backend.runtime.workers.persistence_worker import persistence_worker
    container.register("persistence_worker", persistence_worker)
    worker_manager.register_worker("persistence", persistence_worker)
    try:
        persistence_worker.start()
        bootstrap_status["persistence_started"] = True
        logger.info("[Bootstrap] PersistenceWorker started.")
    except Exception as exc:
        record_bootstrap_error("persistence", exc, level="error")
        # Persistence is critical for research data integrity
        raise FatalBootstrapError(f"Failed to start PersistenceWorker: {exc}") from exc

    vision_uses_simulation = bool(
        getattr(config, "FAKE_VISION", False)
        or bootstrap_status["vision_fallback"]
        or bootstrap_status["vision_mode"] == "simulation"
    )
    vision_ready = bool(bootstrap_status["vision_started"]) and (
        not vision_uses_simulation or bool(getattr(config, "FAKE_ROBOT", False))
    ) and not bool(bootstrap_status["vision_unavailable"])
    bootstrap_status["ready"] = all(
        [
            bootstrap_status["runtime_started"],
            bootstrap_status["engine_registered"],
            bootstrap_status["vision_registered"],
            bootstrap_status["robot_registered"],
            bootstrap_status["robot_connected"] or getattr(config, "FAKE_ROBOT", False),
            bootstrap_status["workers_started"],
            bootstrap_status["workflow_started"],
            bootstrap_status["persistence_started"],
            vision_ready,
        ]
    )
    bootstrap_status["booted"] = True
    bootstrap_system._booted = True
    logger.info("[Bootstrap] System bootstrap complete.")
