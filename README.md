# S.M.A.R.T. Chess Robot

Local Chinese chess robot system with a Flask web UI, Socket.IO state sync,
Pikafish engine analysis, optional OpenCV/YOLO vision, robot control adapters,
runtime diagnostics, replay, and Excel export.

## Quickstart

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.runtime.txt
.\.venv\Scripts\python.exe main.py
```

Open `http://127.0.0.1:5000/`.

Install the heavier vision stack only when real camera/model inference is needed:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.vision.txt
```

## Main Capabilities

- Web UI rendered by Flask templates with modular frontend JavaScript.
- Stable frontend contract over Socket.IO through `SYSTEM_STATE_UPDATE`.
- Engine analysis through the protected Pikafish executable and NNUE file.
- Vision stream through MJPEG, with a safe fallback when camera or ML deps are missing.
- Robot real/mock path behind service and hardware adapter boundaries.
- E-Stop, diagnostics, event persistence, replay, and Excel export.

## Important Endpoints

| Purpose | Endpoint |
| --- | --- |
| Web UI | `GET /` |
| Health | `GET /api/health` |
| Readiness | `GET /api/ready` |
| Login token | `POST /api/login` |
| State snapshot | `GET /api/state` |
| Vision stream | `GET /api/vision/stream` or `GET /api/video_feed` |
| Vision status | `GET /api/vision/status` |
| Camera list | `GET /api/vision/cameras` |
| E-Stop status | `GET /api/estop/status` |
| Trigger E-Stop | `POST /api/estop/trigger` |
| Reset E-Stop | `POST /api/estop/reset` |
| Replay list | `GET /api/replay/steps` |
| Replay snapshot | `GET /api/replay/step/<index>` |

Control-plane endpoints require a JWT bearer token from `POST /api/login`.

## Runtime Contract

Frontend code should consume only the stable `SYSTEM_STATE_UPDATE` envelope and
these contract event types:

- `STATE_UPDATE`
- `ENGINE.INFO_UPDATED`
- `DIAGNOSTICS.UPDATED`
- `VISION.FRAME_PROCESSED`
- `ROBOT.STATUS_UPDATED`
- `UI_TOAST`

Contract code lives in:

- `backend/runtime/contract.py`
- `backend/runtime/contract_schema.py`
- `backend/interfaces/websocket/socket_handler.py`
- `scripts/check_contract.py`

## Project Map

| Path | Role |
| --- | --- |
| `main.py` | Local entry point, delegates to the backend app factory. |
| `backend/` | Flask app, services, state, events, runtime workers, adapters, diagnostics. |
| `frontend/` | Templates, CSS, browser modules, and Jest tests. |
| `engine/` | Python chess engine/reference implementation and UCI path. |
| `scripts/` | Quality gate, diagnostics, contract checks, asset checks, release tooling. |
| `tests/` | Unit, integration, simulation, and performance tests. |
| `backend/infrastructure/protected_assets/` | Runtime-critical engine, NNUE, and vision model assets. |
| `docs/PROJECT_GUIDE.md` | Consolidated architecture, flow, testing, cleanup, and risk notes. |

## Quality And Release

```powershell
npm run check:system
npm test
npm run quality
npm run smoke:frontend
npm run release:zip
```

`npm run check:system` is the preferred pre-demo gate. It checks Git hygiene,
tracked-file safety, the quality gate, diagnostics, authenticated health, HTTP
smoke, and frontend Playwright smoke. The `pyModbusTCP not installed` warning is
expected in fake/simulation robot mode; real robot mode requires that dependency.

The release zip excludes local secrets, dependency folders, runtime databases,
logs, replay data, reports, Python caches, and Excel artifacts.

## Documentation Policy

The Markdown set was consolidated on 2026-05-15 to reduce duplicate and stale
docs. Keep long-lived project knowledge in:

- `README.md` for quickstart and operating summary.
- `docs/PROJECT_GUIDE.md` for architecture, flow, test, and maintenance details.
- `backend/infrastructure/protected_assets/ASSET_MANIFEST.md` for protected asset rules and hashes.

Generated audits, security scan outputs, temporary planning notes, and old
reports should be treated as artifacts, not permanent documentation.

## Version Notes

- `3.0.0` - Industrial modularization: backend layers, `EngineService`, stable `SYSTEM_STATE_UPDATE`, frontend modules, root `main.py`.
- `2.5.0` - SSOT and digital twin implementation: centralized game state and event-driven UI updates.
