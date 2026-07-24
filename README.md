# S.M.A.R.T. Chess Robot

Local Flask + Socket.IO control system for a Xiangqi robot research setup.

The current runtime includes:
- Flask-rendered web UI and static frontend modules.
- Socket.IO state sync with a stable frontend event contract.
- Pikafish engine analysis through protected engine and NNUE assets.
- OpenCV / YOLO26-compatible vision pipeline with MJPEG streaming.
- Robot facade with fake, TMflow TCP JSON, TechmanPy, and Modbus compatibility modes behind E-Stop safety guards.
- SQLite-backed event persistence, replay, telemetry, and Excel/CSV exports.

## Quickstart

Windows / PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.runtime.txt -r requirements.vision.txt
.\scripts\npm24.cmd ci
Copy-Item .env.example .env
.\.venv\Scripts\python.exe main.py
```

Alternatively, use the setup helper:

```powershell
powershell.exe -ExecutionPolicy Bypass -File setup_env.ps1
```

Open:
- Console UI: `http://127.0.0.1:5000/`
- Mission Control / Telemetry Dashboard: `http://127.0.0.1:5000/dashboard`

The dashboard requires a bearer token from `POST /api/login` with the configured `ADMIN_PASSWORD`.

Recommended Windows system check:

```powershell
.\check_system.cmd
```

Use `.\check_system_strict.cmd` before release packaging or handoff. The `.cmd`
wrappers intentionally bypass local PowerShell script policy for this project
only, then call `scripts\check_system.ps1`.

## Common Commands

Run these from the project root in PowerShell. Prefer `.\scripts\npm24.cmd` for
Node/npm commands on this project; it uses the project-local Node 24 runtime and
avoids accidentally running unsupported Node 25+.

Environment setup:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\scripts\npm24.cmd ci
Copy-Item .env.example .env
```

Start the app:

```powershell
.\.venv\Scripts\python.exe main.py
.\.venv\Scripts\python.exe scripts\run_web_simulation.py
powershell.exe -ExecutionPolicy Bypass -File scripts\run_dev.ps1
```

Version and dependency checks:

```powershell
.\scripts\npm24.cmd run check:versions
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe scripts\audit_dependencies.py
```

Quality and test commands:

```powershell
.\.venv\Scripts\python.exe scripts\quality_gate.py
.\check_system.cmd
.\check_system_strict.cmd
.\scripts\npm24.cmd test
.\.venv\Scripts\python.exe -m unittest discover tests -v
```

Vision and camera commands:

```powershell
.\.venv\Scripts\python.exe scripts\test_camera.py
.\.venv\Scripts\python.exe scripts\test_vision_pipeline.py
.\.venv\Scripts\python.exe scripts\check_vision_models.py --warmup
.\.venv\Scripts\python.exe scripts\vision_benchmark.py
.\.venv\Scripts\python.exe scripts\update_vision_model.py <source-folder> --warmup
```

Database, export, and report commands:

```powershell
.\.venv\Scripts\python.exe -m backend.infrastructure.database.init_db
.\.venv\Scripts\python.exe scripts\migrate_db.py
.\.venv\Scripts\python.exe scripts\check_db.py
.\.venv\Scripts\python.exe scripts\test_export.py
.\.venv\Scripts\python.exe scripts\repair_excel_workbook.py
```

Cleanup and packaging:

```powershell
.\scripts\npm24.cmd run cleanup:dry-run
.\scripts\npm24.cmd run release:zip
.\scripts\npm24.cmd run share:zip
```

Troubleshooting:

```powershell
.\.venv\Scripts\python.exe -m pip check
.\scripts\node24.cmd --version
.\scripts\npm24.cmd --version
rg -n "[ \t]+$" .
git diff --check
```

Real TM5-700 robot network check:

```powershell
Test-NetConnection 169.254.47.64 -Port 5890
```

## Installation And Runbooks

Use these documents when moving the project to a different computer or preparing the lab PC:

| File | Purpose |
| --- | --- |
| `INSTALL_WINDOWS.md` | Standard Windows setup and dependency reset. |
| `INSTALL_LAB_PC.md` | Lab computer setup for camera and TM5-700 validation. |
| `RUN_SIMULATION.md` | Safe first-run mode without real hardware. |
| `RUN_REAL_ROBOT.md` | TM5-700 commissioning order and safety checklist. |
| `TROUBLESHOOTING.md` | Common Python, npm, camera, robot, and quality-gate fixes. |

## Configuration

Use `.env.example` as the documented local-development baseline, then copy it to `.env`.

Important defaults:

| Setting | Local default | Notes |
| --- | --- | --- |
| `APP_ENV` | `development` | Set `production` only with hardened settings. |
| `SYSTEM_MODE` | `simulation` | Production must not use `simulation`, `test`, or `demo`. |
| `SMART_CHESS_HOST` / `PORT` | `127.0.0.1` / `5000` | Bind-all requires `SMART_CHESS_BIND_ALL=true` and hardened secrets/CORS. |
| `CHESS_SECRET_KEY` | placeholder | Must be a random 32+ character value before deployment. |
| `ADMIN_PASSWORD` | placeholder | Must not be `888888` outside explicit insecure test mode. |
| `SETUP_PASSWORD` | placeholder | Must not be the default `login` in production. |
| `FAKE_ROBOT` / `FAKE_AI` | `true` / `true` | Safe local defaults. Production requires both `false`. |
| `FAKE_VISION` | `true` | Use `false` for real camera/model runtime. Production requires `false`. |
| `ROBOT_ADAPTER` | `tmflow_json` | Primary real robot path for the TMflow 1.82 newline-delimited TCP JSON protocol. Use `techmanpy` or `modbus` only for compatibility. |
| `ROBOT_IP` / `ROBOT_PORT` | `169.254.47.64` / `5890` | TM5-700 controller baseline confirmed for the lab. |
| `CONTROL_AUTH_REQUIRED` | `true` | Control-plane API routes require JWT auth. |
| `RATE_LIMITS_ENABLED` | `true` | Applies to login, control, and socket actions. |
| `DB_PATH` | `data/runtime/app.db` | Production requires an explicit absolute path. |
| `YOLO_CONFIG_DIR` | `logs/ultralytics` | Keeps Ultralytics settings inside ignored runtime logs. |

Production preflight:

```powershell
.\.venv\Scripts\python.exe scripts\check_production_config.py --self-test
.\.venv\Scripts\python.exe scripts\check_production_config.py --current --require-production
```

## Verified Environment

Last local verification: 2026-07-15 via `.\.venv\Scripts\python.exe scripts\quality_gate.py`.

Recommended install baseline:
- Python 3.11.9 64-bit for lab PCs. Python 3.9-3.12 are supported; Python 3.13 is not supported yet.
- Node.js 24 LTS with npm 11 or newer. `.nvmrc` and `.node-version` are set to Node 24.

| Item | Verified version |
| --- | --- |
| Python | 3.9.13 |
| Flask | 3.1.3 |
| Flask-SocketIO | 5.6.1 |
| OpenCV | 4.11.0 (`opencv-python==4.11.0.86`) |
| Ultralytics | 8.4.55 |
| YOLO model | `backend/infrastructure/protected_assets/vision/best.onnx` |
| ONNX Runtime | 1.19.2 |
| Pikafish | 2026-01-31 (`pikafish-avx2.exe`) |
| Node test stack | Node 24.18.0 via `scripts\npm24.cmd`, Jest 30.4.1, Playwright 1.60.0 |

Primary dependency files:

| File | Purpose |
| --- | --- |
| `requirements.runtime.txt` | Minimal web, websocket, auth, engine, TMflow TCP JSON, TechmanPy, and Modbus compatibility runtime. |
| `requirements.vision.txt` | Camera, ML vision, ONNX, benchmark, and report tooling. |
| `requirements.txt` | Consolidated research environment. |
| `requirements.lock.txt` | Reproducible Python baseline from the verified `.venv`. |
| `package-lock.json` | Reproducible Node/Jest/Playwright baseline. |

## Vision

- Active model slot: `backend/infrastructure/protected_assets/vision/best.onnx`
- Optional source weights: `backend/infrastructure/protected_assets/vision/best.pt`
- Dataset metadata: `backend/infrastructure/protected_assets/vision/dataset_mapping.yaml`
- Training metadata: `backend/infrastructure/protected_assets/vision/args.yaml`
- Calibration file: `data/vision_calibration.json`

Useful commands:

```powershell
.\.venv\Scripts\python.exe scripts\check_vision_models.py --warmup
.\.venv\Scripts\python.exe scripts\update_vision_model.py <source-folder> --warmup
.\.venv\Scripts\python.exe scripts\vision_benchmark.py
```

Vision endpoints:
- `GET /api/vision/status`
- `GET /api/vision/cameras`
- `POST /api/vision/camera` with `{"index": 0}`
- `GET /api/vision/calibration`
- `POST /api/vision/calibration`
- `GET /api/vision/stream`
- `GET /api/video_feed`
- `GET /api/vision/snapshot`

If the camera or YOLO model cannot be opened, the runtime reports the error instead of silently switching detector modes.

## Engine And Robot

Protected engine assets:
- `backend/infrastructure/protected_assets/engine/pikafish-avx2.exe`
- `backend/infrastructure/protected_assets/engine/pikafish.nnue`

Key engine parameters:
- `ENGINE_PROBE_ON_BOOT=false`
- `ENGINE_AUTO_ANALYZE=false` (player mode starts analysis after pressing 開始對局)
- `ENGINE_OUTPUT_QUEUE_SIZE=2000`

Robot mode defaults are safe for development:
- `FAKE_ROBOT=true`
- `AUTO_EXECUTE_ROBOT=false`
- `ROBOT_ADAPTER=tmflow_json`
- `ROBOT_IP=169.254.47.64`
- `ROBOT_PORT=5890`
- `ROBOT_COMMAND_QUEUE_SIZE=200`
- Conservative first-run speed defaults: `ROBOT_MAX_SPEED=80`, `ROBOT_TRAVEL_SPEED=30`, `ROBOT_LIFT_SPEED=30`, `ROBOT_APPROACH_SPEED=15`

Real robot mode requires `FAKE_ROBOT=false`, `ROBOT_ADAPTER=tmflow_json`, a reachable TMflow TCP JSON socket server on TCP `5890`, and ACK/DONE/ERROR responses that follow the Part 2 protocol.
Follow `RUN_REAL_ROBOT.md` before enabling `AUTO_EXECUTE_ROBOT=true`; TMflow/controller TCP speed limits, force/collision detection, G-Sensor, safety zones, virtual walls, and a tested physical E-Stop are required for human-facing operation.

## API Summary

Authentication:
- `POST /api/login`
- `POST /api/logout`

Health and diagnostics:
- `GET /api/ready`
- `GET /api/health`
- `GET /api/runtime/status`
- `GET /api/runtime/metrics`
- `GET /api/assets/status`
- `GET /api/engine/status`

State and control:
- `GET /api/state`
- `POST /api/control`
- `POST /api/control/<action>`
- `POST /api/move`
- `POST /api/reset`
- `POST /api/simulation`
- `GET /api/runtime/control`
- `POST /api/runtime/engine-depth`
- `POST /api/runtime/safe-mode`
- `POST /api/runtime/session/start`
- `POST /api/runtime/session/end`

Safety:
- `GET /api/estop/status`
- `POST /api/estop/trigger` with `{"reason": "..."}`
- `POST /api/estop/reset`

Replay and export:
- `GET /api/replay/sessions`
- `GET /api/replay/steps`
- `GET /api/replay/step/<index>`
- `GET /api/replay/export`
- `GET /api/export/excel`
- `GET /api/export/csv`
- `GET /api/export_json`
- `GET /api/export_kpi`

Robot calibration:
- `GET /api/robot/calibration`
- `POST /api/robot/calibration`

## Runtime Contract

Frontend code should rely on these stable backend-to-frontend event names:
- `STATE_UPDATE`
- `ENGINE.INFO_UPDATED`
- `DIAGNOSTICS.UPDATED`
- `VISION.FRAME_PROCESSED`
- `ROBOT.STATUS_UPDATED`

Contract code:
- `backend/runtime/contract.py`
- `backend/runtime/contract_schema.py`
- `scripts/check_contract.py`

## Quality Checks

Fast targeted checks:

```powershell
.\.venv\Scripts\python.exe scripts\check_artifact_hygiene.py
.\.venv\Scripts\python.exe scripts\check_legacy_events.py
.\.venv\Scripts\python.exe scripts\audit_dependencies.py
.\.venv\Scripts\python.exe scripts\quality_gate.py
.\scripts\npm24.cmd test
```

If the Node wrapper cannot find the project-local Node 24 runtime, install Node.js 24 LTS
or extract the Node 24 portable build into `.tools\node-v24.18.0-win-x64`. If tests
cannot find Jest after copying the folder to another computer, remove `node_modules`
and run `.\scripts\npm24.cmd ci` from the project root. Keep `package-lock.json`.

Full local system check:

```powershell
.\check_system.cmd
```

Strict clean-tree system check:

```powershell
.\check_system_strict.cmd
```

The non-strict check intentionally skips the clean Git tree requirement and is useful while the working tree contains active development changes.

## Development Planning

Current planning and changeset triage:
- `docs/ROADMAP.md`
- `docs/CHANGESET_TRIAGE.md`

Use the roadmap for phased development priorities. Use the triage document to
decide which modified, deleted, and untracked files belong in the next stable
baseline.

## Cleanup And Release

Dry-run cleanup:

```powershell
.\scripts\npm24.cmd run cleanup:dry-run
```

Build release zip:

```powershell
.\scripts\npm24.cmd run release:zip
```

Build a sanitized source-review/share zip without local runtime data or protected
binary/model assets:

```powershell
.\scripts\npm24.cmd run share:zip
```

Runtime artifacts are intentionally excluded from Git and release output:
- `.env`
- `.venv/`
- `.tools/`
- `node_modules/`
- `build/`
- `logs/`
- `data/`
- `backend/data/`
- `reports/`
- `analysis_artifacts/`
- `*.db`, `*.log`, `*.xlsx`
- model/engine binaries outside protected release handling
