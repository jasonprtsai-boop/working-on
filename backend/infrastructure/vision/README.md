# Vision Runtime Ownership

Current robot-authoritative owner: `VisionSystem` in `vision_system.py`.

`VisionSystem` owns the runtime camera source, calibration state, MJPEG stream,
temporal validation, and FEN generation used by the operator UI and robot flow.

`VisionPipeline` in `pipeline.py` remains the queue-based experimental pipeline.
It can be enabled through `VISION_WORKER_PIPELINE_ENABLED` for measurements and
incremental migration work, but it is not the default owner for robot
auto-execution.

Use `VISION_RUNTIME_OWNER=vision_pipeline` only after the pipeline has feature
parity for calibration, streaming, status reporting, and fail-closed safety
checks.
