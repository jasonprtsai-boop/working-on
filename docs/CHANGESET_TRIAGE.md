# Changeset Triage

This document classifies the current working tree so cleanup and release work
can proceed without losing active development changes.

Last observed status:

```text
modified=153 deleted=8 untracked=35 total=196
```

## Summary By Area

| Area | Count | Decision |
| --- | ---: | --- |
| Backend | 92 | Review as active architecture/runtime changes. |
| Frontend | 30 | Review as active dashboard/UI changes. |
| Tests | 39 | Keep if they cover current contracts and new behavior. |
| Scripts | 20 | Keep if referenced by README, quality gate, or release flow. |
| Docs | 4 deleted + new docs | Replace old inventory docs with current roadmap/triage docs. |
| Requirements/package/config | 9 | Keep if verified by dependency audit and system check. |

## Deleted Paths To Confirm

These paths are deleted in Git. Current code search found no direct references,
but each removal should still be confirmed as intentional.

| Path | Proposed decision | Reason |
| --- | --- | --- |
| `backend/infrastructure/vision/detection/grid_detector.py` | Remove | Active detector factory now uses full-frame YOLO only. |
| `backend/infrastructure/vision/detection/piece_detector.py` | Remove | No direct references found. |
| `backend/infrastructure/vision/detection/sahi_detector.py` | Remove | SAHI mode appears retired from active detector factory. |
| `backend/infrastructure/vision/roi_optimizer.py` | Remove | No direct references found. |
| `docs/01_file_inventory.md` | Replace | Superseded by current README and roadmap. |
| `docs/02_data_flow.md` | Replace | Superseded by current README and roadmap. |
| `docs/03_architecture_and_runtime.md` | Replace | Superseded by current README and roadmap. |
| `docs/PROJECT_GUIDE.md` | Replace | Superseded by current README and roadmap. |

## Untracked Paths To Keep

These untracked paths look like source, tests, scripts, or protected assets that
should be included in the planned changeset.

| Path | Why keep |
| --- | --- |
| `backend/events/adapters/` | Legacy event adapter support. |
| `backend/infrastructure/protected_assets/vision/` | Verified YOLO model, weights, dataset metadata, and training args. |
| `backend/infrastructure/vision/model_assets.py` | Vision model asset discovery/status helper. |
| `backend/interfaces/api/robot_routes.py` | Robot API route module. |
| `backend/observability/error_reporter.py` | Diagnostics/error reporting support. |
| `backend/observability/telemetry.py` | Runtime telemetry support. |
| `frontend/static/js/modules/ui/system_status_strip.js` | Dashboard/status UI module. |
| `frontend/templates/components/system_status_strip.html` | Dashboard/status template. |
| `frontend/tests/board_mapper.test.js` | Frontend board mapper coverage. |
| `frontend/tests/dashboard_replay.test.js` | Dashboard replay coverage. |
| `requirements.lock.txt` | Verified Python dependency baseline. |
| `scripts/audit_dependencies.py` | Dependency audit command used by quality gate. |
| `scripts/check_artifact_hygiene.py` | Runtime/release artifact hygiene check. |
| `scripts/check_legacy_events.py` | Event contract guard. |
| `scripts/check_production_config.py` | Production preflight. |
| `scripts/check_vision_models.py` | Vision model/asset verification. |
| `scripts/update_vision_model.py` | Protected vision model update workflow. |
| `tests/fixtures/` | Deterministic test data. |
| `tests/unit/test_artifact_hygiene.py` | Artifact hygiene coverage. |
| `tests/unit/test_coordinate_conversions.py` | Coordinate conversion coverage. |
| `tests/unit/test_diagnostics_contract.py` | Diagnostics contract coverage. |
| `tests/unit/test_error_reporter.py` | Error reporting coverage. |
| `tests/unit/test_error_response.py` | API error response coverage. |
| `tests/unit/test_excel_report_service.py` | Excel report service coverage. |
| `tests/unit/test_legacy_event_guard.py` | Legacy event guard coverage. |
| `tests/unit/test_production_preflight.py` | Production config coverage. |
| `tests/unit/test_queue_manager.py` | Queue manager coverage. |
| `tests/unit/test_runtime_control.py` | Runtime control coverage. |
| `tests/unit/test_telemetry_service.py` | Telemetry service coverage. |
| `tests/unit/test_update_vision_model.py` | Vision model update coverage. |
| `tests/unit/test_vision_calibration.py` | Homography and calibration coverage. |
| `tests/unit/test_vision_model_assets.py` | Vision protected asset coverage. |
| `tests/unit/test_vision_pipeline.py` | Queue vision pipeline coverage. |
| `tests/unit/test_vision_regression.py` | Synthetic vision regression coverage. |
| `tests/unit/test_worker_lifecycle.py` | Worker lifecycle coverage. |

## Ignored Runtime Artifacts

These are intentionally excluded and should not be committed:

- `.env`
- `.venv/`
- `node_modules/`
- `logs/`
- `reports/`
- `data/`
- `backend/data/`
- `analysis_artifacts/`
- `*.db`
- `*.log`
- `*.xlsx`
- `__pycache__/`

## Verification Commands

Run these before freezing the baseline:

```powershell
git diff --check
.\.venv\Scripts\python.exe scripts\quality_gate.py
npm.cmd test
npm.cmd run check:system
```

Use strict mode only when the working tree is intentionally clean:

```powershell
npm.cmd run check:system:strict
```

## Next Decisions

1. Confirm the deleted detector and old docs removals.
2. Decide whether protected vision binaries belong in Git, Git LFS, or a release
   asset bundle.
3. Group the remaining modified files by feature area before commit/release.
4. Keep runtime artifacts cleaned after every system check.
