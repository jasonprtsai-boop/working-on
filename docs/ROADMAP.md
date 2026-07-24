# Development Roadmap

This roadmap turns the current working system into a maintainable, verifiable,
and deployable Xiangqi robot research platform.

## Current Baseline

The system already includes:

- Flask and Socket.IO runtime.
- Web console and telemetry dashboard.
- Pikafish engine integration.
- YOLO/OpenCV vision with homography calibration.
- Robot facade with fake, TMflow TCP JSON, TechmanPy, and Modbus TCP compatibility modes.
- E-Stop, replay, telemetry, and export pipelines.

Latest verified command:

```powershell
.\check_system.cmd
```

The major current risk is not a single failing test. The major risk is change
volume. The working tree contains many active code, test, documentation, and
asset changes that need to be grouped before release.

## Phase 1 - Stabilize The Baseline

Goal: make the current system easy to review, test, and package.

Priority work:

- Classify all modified, deleted, and untracked files.
- Confirm whether removed detector and legacy docs are intentionally retired.
- Promote required untracked source, tests, protected assets, and scripts into
  the planned changeset.
- Keep runtime artifacts out of Git and release output.
- Preserve a repeatable verification command list.

Exit criteria:

- Every deleted file has an explicit keep-or-remove decision.
- Every untracked path is classified as keep, ignore, archive, or remove.
- `.\check_system.cmd` passes.
- Release dry-run excludes runtime artifacts and includes required source/tests.

## Phase 2 - Harden Vision And Coordinate Pipeline

Goal: make camera, YOLO, homography, board mapping, and FEN generation
observable and regression-tested.

Priority work:

- Keep coordinate spaces explicit: `camera_frame`, `rectified_board`, and raw
  inverse-mapped coordinates.
- Keep bounding-box output backward compatible while adding metadata for debug
  and replay.
- Expand synthetic calibration and detection fixtures.
- Decide the long-term owner between legacy `VisionSystem` and queue-based
  `VisionPipeline`.
- Add calibration quality and mapping-distance fields to diagnostics/export.

Exit criteria:

- Vision targeted tests cover calibration, mapping, FEN generation, and pipeline
  DTO output.
- Real model warmup is covered by `scripts/check_vision_models.py --warmup`.
- Vision failures report clear error state instead of silently changing detector
  modes.

## Phase 3 - Robot Safety And Real Hardware Readiness

Goal: safely move from simulation to controlled real robot validation.

Priority work:

- Document the TMflow TCP JSON flow, ACK/DONE lifecycle, fallback wire format, and motion profiles.
- Validate soft limits, capture dead zone, gripper actions, and timeouts.
- Keep `AUTO_EXECUTE_ROBOT=false` as the safe default.
- Require explicit operator action for real motion.
- Ensure every robot command is traceable to replay and telemetry events.

Exit criteria:

- Fake and real robot modes fail closed.
- E-Stop is verified before and during motion.
- Real robot preflight rejects unsafe config.
- Motion tests cover invalid, no-op, timeout, and gripper failure paths.

## Phase 4 - Security And Deployment Readiness

Goal: make the system safe enough for demonstration and controlled deployment.

Priority work:

- Review auth, control routes, Socket.IO roles, replay/export, file handling,
  and robot-control entry points.
- Keep production preflight mandatory for production mode.
- Enforce hardened secrets, CORS, bind host, fake-mode, and database settings.
- Keep protected assets under manifest validation.

Exit criteria:

- `scripts/check_production_config.py --current --require-production` passes
  for production config.
- Security scan findings are closed, suppressed with evidence, or tracked.
- Release zip contains only expected source, docs, tests, and protected assets.

## Phase 5 - Research Reproducibility

Goal: produce traceable experiment data for reports and future validation.

Priority work:

- Use stable session ids across vision, engine, robot, replay, and export.
- Keep pipeline latency and event timeline in telemetry.
- Export calibration quality, detection confidence, mapping distance, and robot
  execution status.
- Keep diagrams and report artifacts separate from runtime logs.

Exit criteria:

- A complete experiment can be replayed from persisted events.
- Excel/CSV export captures enough data to reconstruct the pipeline outcome.
- Report artifacts are documented, archived, and excluded from release unless
  intentionally included.

## Recommended Near-Term Order

1. Finish changeset triage.
2. Commit or otherwise preserve the stable baseline.
3. Expand vision pipeline regression coverage.
4. Run security review and close reportable issues.
5. Prepare real robot preflight and hardware validation checklist.
