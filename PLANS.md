# S.M.A.R.T. Chess Robot - Development Plan

本文件整理目前專案的近期與中長期開發方向。詳細 release/changeset 分類請看 `docs/CHANGESET_TRIAGE.md`，階段性路線圖請看 `docs/ROADMAP.md`。

## Current Status

| Area | Current state |
| --- | --- |
| Dashboard contract | 前端狀態 schema、runtime contract 與 diagnostics payload 已集中管理。 |
| Socket access | `.env.example` 已提供 `SOCKET_PUBLIC_SNAPSHOT_ENABLED` 與 socket action allowlist。 |
| Queue policy | `QueuePolicy` enum、managed queue stats 與 persistence drop diagnostics 已存在。 |
| Production preflight | `scripts/check_production_config.py` 已提供 production profile 檢查。 |
| Protected assets | engine、NNUE、YOLO model、dataset mapping 與 training args 已列入 protected asset manifest。 |
| Vision pipeline | 目前以 YOLO full-frame inference、homography 校正、board mapping 與 FEN generation 為主。 |

## Phase 1 - Baseline Stabilization

目標：把目前可運作的研究平台整理成可以 review、測試、交付與回復的穩定 baseline。

Priority work:

- 完成 `docs/CHANGESET_TRIAGE.md` 中 modified、deleted、untracked 檔案分類。
- 保留必要 source、tests、scripts、protected assets，排除 runtime artifacts。
- 讓 README、install guide、runbook、queue policy 與 roadmap 對齊目前實作。
- 維持一組可重複執行的檢查指令：`.\check_system.cmd`、`.\check_system_strict.cmd`、`scripts\quality_gate.py`。
- 確認舊版 detector 與舊 docs 的刪除是有意的。

Exit criteria:

- Git working tree 中每一類變更都有明確保留或移除理由。
- 所有文件中的 setup、test、vision、robot 指令都與目前 script 名稱一致。
- `.\check_system.cmd` 可作為非 clean-tree 開發檢查。
- `.\check_system_strict.cmd` 可作為 release/handoff 前檢查。

## Phase 2 - Core Runtime Refinement

目標：降低 legacy path 與事件/worker 邊界的模糊度，讓 runtime 行為更容易驗證。

Priority work:

- 收斂 `EventBus.publish` 的 legacy dict 使用方式，讓舊資料透過 adapter 進入事件系統。
- 明確化 `WorkerProtocol` 與 worker lifecycle，包含 start、stop、status、failure/backoff。
- 持續擴充 `DIAGNOSTICS.UPDATED` nested schema，讓 dashboard 與 tests 能檢查 health、queue、workers、pipeline、topology。
- 決定長期 owner：即時 `VisionSystem` 與 queue-based `VisionPipeline` 的責任分界。
- 補強 vision coordinate metadata，保留 `camera_frame`、`rectified_board`、raw inverse-mapped bbox/anchor。

Exit criteria:

- Legacy event path 有測試保護，且 production profile 能關閉不安全相容模式。
- Worker status snapshot 能清楚指出 running、stopped、failed、blocked。
- Vision regression tests 涵蓋 calibration、mapping、FEN、DTO payload 與 overlay metadata。

## Phase 3 - Robot Safety And Hardware Readiness

目標：讓 TM5-700 實機驗證保持 fail-closed，並讓每一步操作可追蹤。

Priority work:

- 持續維護 TMflow TCP JSON ACK/STARTED/DONE/ERROR contract。
- 將 soft limits、dead zone、gripper feedback、timeouts 與 one-move validation 納入 runbook。
- 保持 `AUTO_EXECUTE_ROBOT=false` 作為安全預設。
- 在 dashboard 中清楚呈現 robot queue blocked、E-Stop、socket state 與 last command。
- 讓 robot command、vision FEN、engine move、state update 與 persistence event 使用同一 trace/session context。

Exit criteria:

- Fake robot 與 real robot mode 都能在錯誤時停止自動流程。
- 實機前必須通過 setup preflight、connect/status、safe Z、gripper 與 one-move test。
- Replay/export 能回溯每次機械手臂動作的來源與結果。

## Phase 4 - Observability And Reproducibility

目標：讓實驗資料可重播、可比較、可匯出，支援專題報告與後續研究。

Priority work:

- 建立 Vision -> Engine -> Robot -> State -> Persistence 的 trace waterfall。
- 匯出 calibration quality、detection confidence、mapping distance、YOLO latency、engine time、robot execution status。
- 建立 session replay 與 historical comparison 的穩定資料格式。
- 將 runtime logs、database、reports、temporary screenshots 與 release source 明確分離。

Exit criteria:

- 單次實驗可由 persisted events 重建主要流程。
- Excel/CSV export 足以比較 vision、engine、robot 的 latency 與錯誤率。
- 報告用資料與 runtime artifact 有明確保存位置與排除規則。

## Suggested Next Actions

1. 完成 changeset triage，確認刪除舊 detector 與舊文件。
2. 執行 `.\check_system.cmd`，保存最新可通過的檢查結果。
3. 擴充 vision regression fixtures，加入更多校正與棋子映射案例。
4. 檢查 real robot runbook 與實驗室 TMflow 專案是否完全一致。
5. 在 release 前執行 `.\check_system_strict.cmd` 與 sanitized share zip 檢查。
