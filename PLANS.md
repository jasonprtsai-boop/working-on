# S.M.A.R.T. Chess Robot - Development Plan

This file is the short working plan for the current system. Use
`docs/ROADMAP.md` for the full phased roadmap and `docs/CHANGESET_TRIAGE.md`
when preparing a release or reviewing a large changeset.

## Current Baseline

| Area | Current state |
| --- | --- |
| Runtime | Flask + Socket.IO app with centralized bootstrap, async runtime, workers, state management, and SQLite persistence. |
| Frontend | Flask-rendered console/player/setup UI with modular board, state, websocket, and dashboard renderers. |
| Engine | Pikafish UCI integration with protected engine and NNUE asset validation. |
| Vision | OpenCV/YOLO model path, calibration, board mapping, FEN generation, MJPEG streaming, and regression fixtures. |
| Robot | Fake robot plus TMflow JSON, TechmanPy, and Modbus compatibility paths behind E-Stop and fail-closed checks. |
| Verification | `quality_gate.py`, `check_system.cmd`, Jest, Playwright smoke, protected asset checks, production preflight, and release/share dry-runs. |

## Immediate Connection Optimization Plan

Lab network baseline:

- Robot controller IP: `192.168.10.10`
- Suggested control PC Ethernet IP: `192.168.10.50`
- Subnet mask: `255.255.0.0`
- Robot command port: `5890`
- TMflow vision frame port: `5891`

Execution order:

1. Align source defaults, setup UI defaults, tests, `.env.example`, and runbooks to the lab network baseline.
2. Add a preflight network-shape check before socket communication: robot IP, PC IP, subnet mask, same subnet, and no duplicate IP.
3. Surface control-channel and vision-channel status separately in setup diagnostics.
4. Keep TMflow command traffic on `5890` and image/frame traffic on `5891`.
5. Add socket-level regression tests for TMflow vision frame reconnect, oversized payload, decode failure, and FPS limiting.
6. Require a configured TMflow vision ingest key before production or shared-network operation.

Current execution:

- Completed the lab IP baseline update.
- Added the preflight subnet consistency check.
- Removed inactive legacy robot compatibility controller modules and archived report/demo scripts.
- Reduced backend diagnostics monitoring refresh to a configurable `MONITORING_INTERVAL_SEC=1.0` default.
- Next implementation target is a compact setup diagnostics panel for command port, vision port, frame age, and reconnect count.

## Phase 1 - Baseline Stabilization

Goal: keep the current runnable system easy to review and safe to package.

Priority work:

- Keep `.env.example` safe: no real local password defaults and insecure switches off by default.
- Add tests that detect unclassified API routes before they become authorization gaps.
- Keep docs readable and aligned with the actual runtime.
- Track any quality-check side effects immediately; system checks should not modify tracked source files.
- Run `.\check_system.cmd` before handoff and `.\check_system_strict.cmd` before release.

Exit criteria:

- Working tree changes are intentional and grouped by feature area.
- Runtime artifacts remain ignored and excluded from release/share packages.
- Quality and system checks pass without mutating tracked files.

## Phase 2 - Runtime And Contract Refinement

Goal: reduce ambiguity in event, worker, and diagnostics ownership.

Priority work:

- Keep `EventBus.publish` accepting only `BaseEvent` internally; retire legacy dict paths behind explicit adapters.
- Keep worker lifecycle snapshots consistent across async and thread-based workers.
- Expand `DIAGNOSTICS.UPDATED` coverage for workers, queues, persistence, topology, and pipeline health.
- Decide whether legacy `VisionSystem` or queue-based `VisionPipeline` owns the long-term vision runtime.

Exit criteria:

- Production config disables legacy event ingress.
- Worker status exposes running, stopped, failed, blocked, and last-error states.
- Frontend contract tests cover every emitted stable event shape.

## Phase 3 - Vision Pipeline Hardening

Goal: make camera calibration, detection, mapping, and FEN generation observable and reproducible.

Priority work:

- Keep coordinate spaces explicit: `camera_frame`, `rectified_board`, and inverse-mapped raw coordinates.
- Persist calibration quality, reprojection error, detection confidence, and mapping distance.
- Expand synthetic fixtures for calibration, board mapping, and FEN generation.
- Keep model updates behind manifest validation and warmup checks.

Exit criteria:

- Vision regressions cover calibration, mapping, FEN, DTO payloads, and overlay metadata.
- Model warmup fails loudly when assets or runtime dependencies are invalid.

## Phase 4 - Robot Safety And Hardware Readiness

Goal: move from simulation to real TM5-700 validation without weakening safety gates.

Priority work:

- Document and test TMflow JSON HELLO/ACK/STARTED/DONE/ERROR behavior.
- Validate soft limits, capture dead zone, gripper feedback, motion timeouts, and halt behavior.
- Keep `AUTO_EXECUTE_ROBOT=false` as the safe default.
- Make every robot command traceable to vision, engine, state, persistence, replay, and export records.

Exit criteria:

- Fake and real robot paths fail closed on invalid moves, no-op moves, stale vision, busy robot, timeout, and E-Stop.
- Real hardware preflight rejects unsafe config before any motion is allowed.

## Phase 5 - Observability And Reproducibility

Goal: produce trustworthy experiment data for reports and future validation.

Priority work:

- Use stable session and trace IDs across vision, engine, robot, state, persistence, replay, and export.
- Add a clear timeline waterfall for Vision -> Engine -> Robot -> State -> Persistence.
- Export enough latency, confidence, calibration, engine, and robot fields to reconstruct a trial.
- Keep logs, database files, screenshots, and generated reports out of source/release unless explicitly included.

Exit criteria:

- A completed experiment can be replayed from persisted events.
- Excel/CSV exports include the data needed to explain each move and system decision.

## Immediate Next Actions

Completed:

- Add API authorization coverage tests.
- Verify quality checks do not mutate tracked files.

Next:

1. Split the frontend orchestrator into focused controllers.
2. Choose the long-term vision runtime owner.
3. Prepare the real robot validation checklist after the software baseline is stable.
