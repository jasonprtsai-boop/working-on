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

## Simulation Fallback Policy

`FAKE_VISION=true` is the only default path into simulated vision. When
`FAKE_VISION=false`, startup failures in the real camera/model path leave the
runtime in `UnavailableVisionSystem` mode instead of silently emitting mock
detections.

Set `VISION_ALLOW_SIMULATION_FALLBACK=true` only for explicit lab drills where
operators intentionally want a real-vision startup failure to continue with
simulation. Production config rejects this flag.

Runtime inference errors are reported through worker failure counters and become
`degraded` only after both `VISION_DEGRADED_CONSECUTIVE_FAILURES` and
`VISION_DEGRADED_FAILURE_SECONDS` are reached. A single dropped frame or
temporary detector error should not change the system into simulation mode.

## TMflow Socket Send Ingest

The project supports TMflow sending robot telemetry and vision frames to the PC
without screen capture.

- `VISION_SOURCE=tmflow_json` keeps the existing Python-as-client frame source.
- `POST /api/vision/tmflow/frame` accepts HTTP JSON image pushes.
- `TMFLOW_INGEST_SERVER_ENABLED=1` starts a PC-side TCP server for TMflow
  Socket Send messages.

Default ingest endpoint:

```text
host = TMFLOW_INGEST_SERVER_HOST or ROBOT_PC_IP
port = TMFLOW_INGEST_SERVER_PORT or 5892
```

Recommended line-delimited JSON payload:

```json
{
  "timestamp": 123456,
  "tcp": [500.0, 200.0, 300.0, 180.0, 0.0, 90.0],
  "joint": [0.0, 20.0, -15.0, 90.0, 0.0, 45.0],
  "io": {"di1": true},
  "image": "<jpeg-base64>"
}
```

For quick TMflow 1.82 Socket Send tests, a single CSV line is also accepted:

```text
500.23,100.25,320.11,-179.98,0.12,90.00
```

The socket ingest updates shared robot telemetry, publishes
`ROBOT.STATUS_UPDATED`, and puts decoded JPEG frames into the same frame buffer
used by `/api/vision/stream`. Production mode requires `TMFLOW_INGEST_KEY` when
the socket ingest server is enabled.
