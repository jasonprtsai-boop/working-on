# S.M.A.R.T. Chess Robot - Phase 1 實作計畫

根據 `system-review-20260515.md` 的審查結果，以下是接下來優先執行的 Phase 1 Quick Wins 與建議下一步的實作計畫：

## 1. Dashboard 資料字典 (Dashboard Data Dictionary)
- **目標**: 建立 `reports/dashboard-data-dictionary.md`，列出 Dashboard 每個數據來源、更新頻率、stale (過期) 規則。
- **行動**:
  - 檢視 `backend/runtime/contract_schema.py` 與 `frontend/static/js/modules/state/schemas.js`。
  - 整理 `DIAGNOSTICS.UPDATED` (health, telemetry, queue, pipeline, topology, workers) 及 `STATE_UPDATE` 的資料欄位。
  - 撰寫 Markdown 文件儲存至 `reports/`。

## 2. Socket Viewer Policy 設定
- **目標**: 新增 `SOCKET_PUBLIC_SNAPSHOT_ENABLED` 設定，管理未授權 Socket 連線的唯讀快照存取權。
- **行動**:
  - 於 `backend/utils/config.py` 及 `.env.example` 新增 `SOCKET_PUBLIC_SNAPSHOT_ENABLED`，預設為 `true`。
  - 於 `config.py` 的 production preflight 檢查中，確保 production 模式下 `SOCKET_PUBLIC_SNAPSHOT_ENABLED = false`。
  - 修改 `backend/interfaces/websocket/socket_handler.py`，若該設定為 `false`，則拒絕未帶 token 的連線或不發送快照。
  - 更新/新增相關測試 (`tests/integration/test_socket_auth.py`)。

## 3. Queue Policy 文件化與測試
- **目標**: 明確定義並測試 robot / persistence 的 queue policy (drop / dead-letter)。
- **行動**:
  - 於技術文件中記錄各 queue 的 maxsize、drop 條件與警告機制。
  - 針對 queue 滿時的 drop 與 metrics 行為，增補 Python 單元測試，確保行為符合預期。

## 4. Production Profile Smoke Test
- **目標**: 確保在不啟動硬體的情況下，危險設定 (unsafe config) 會被正確攔截 (fail closed)。
- **行動**:
  - 於 release preflight 加入 production ready 檢查。
  - 驗證 `IS_PRODUCTION=true` 時，弱密碼、預設密鑰、`BIND_ALL=true` 且未授權等設定會導致啟動失敗。

## 5. Engine/Model Runtime Hash Verification
- **目標**: Production 啟動前強制檢查 protected asset 的 hash，避免惡意置換。
- **行動**:
  - 抽取 `scripts/check_assets.py` 中的 hash 檢查邏輯。
  - 在 `backend/application/bootstrap.py` 或相關模組啟動流程中加入 hash 驗證步驟。
  - 若 `IS_PRODUCTION=true` 且 hash 不符，則終止啟動程序。

---

# Phase 2 Core Refactoring

## 1. EventBus 與 Legacy Dict 收斂
- **目標**: `EventBus.publish` 僅接受 `BaseEvent`，legacy dict 需統一使用 ingress adapter 處理。
- **行動**:
  - 修改 `backend/events/bus/event_bus.py`，新增 `publish_from_legacy`。
  - 更新 `backend/state/store/manager/state_manager.py` 移除對 dict 的依賴。

## 2. WorkerProtocol 正式化
- **目標**: 為背景 Worker 建立統一的 `WorkerProtocol` 介面，統一啟動、停止與健康度檢測。
- **行動**: 建立 `WorkerProtocol`，並實作至 `MonitoringWorker`、`PersistenceWorker` 與 `EngineWorker`。

## 3. Queue Policy Enum 化
- **目標**: 在程式碼中正式定義 Queue Policy 的 Enum。
- **行動**: 在 `backend/runtime/messaging/queues.py` 中替換字串定義為 `Enum`。

## 4. `DIAGNOSTICS.UPDATED` Nested Schema Versioning
- **目標**: 對 Diagnostics nested keys (如 `health`, `queue`) 加入 Schema 版本管理與警告。
- **行動**: 於 `backend/runtime/contract_schema.py` 增加 Nested Models，初期採不強制 Hard Fail 的警告模式。

## 5. Dashboard 與 主控台分工定稿
- **目標**: 確認 `/` 作為純操作與簡版燈號，`/dashboard` 作為完整觀測。
- **行動**: 微調兩個頁面的 UI/JS 來區隔用途。

---

# Phase 3 Long-term Optimization

## 1. Trace Waterfall
- **目標**: 追蹤端到端事件流 (Vision -> Engine -> Robot -> State -> Storage)。
- **行動**: 實作或強化 TimelineTracer，記錄各階段的 Latency、Status 與 Error。

## 2. Historical Replay
- **目標**: 讓系統能夠從 SQLite/event store 回放歷史紀錄，供 demo 與 debug 使用。
- **行動**: 實作 Session replay 與 Trace replay 的資料讀取與推送 API。

## 3. Performance Analytics
- **目標**: 計算關鍵效能指標並呈現於 Dashboard。
- **行動**: 實作 Latency percentile、Error rate、Timeout rate 等指標計算。

## 4. CI Quality Gate
- **目標**: 在開發流程中導入自動化整合測試與發布檢查。
- **行動**: 補齊或串接 unit/integration 測試指令，確保 release dry-run 可在 CI 執行。

## 5. Hardware Fallback Strategy
- **目標**: 在實體設備遺失時，能夠優雅降級 (Graceful Degradation)。
- **行動**: 處理 Camera unavailable, Robot disconnected, Engine incompatible 等情境的 fallback 邏輯與 UI 提示。
