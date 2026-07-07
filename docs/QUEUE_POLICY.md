# S.M.A.R.T. Chess Robot - Queue Policy (佇列管理原則)

本系統作為兼具視覺處理與實體硬體控制的 Robotics 系統，其背景非同步佇列必須有明確的丟棄 (Drop) 與背壓 (Backpressure) 處理原則，以避免 OOM 或控制延遲累積。

## 1. 佇列屬性與 Policy 定義

系統中共維護四種主要背景佇列，透過 `AsyncQueueManager` 與 `PersistenceWorker` 管理。

| 佇列名稱 | 管理者 | 大小上限 | Policy | 說明與預期行為 |
| --- | --- | --- | --- | --- |
| **Vision Frame Queue** | `AsyncQueueManager` | `maxsize=1` | `latest-only` | 推送新影像時若佇列已滿，丟棄舊有影像，確保視覺分析始終拿到最新的一幀。 |
| **AI Detect Queue** | `AsyncQueueManager` | `maxsize=1` | `latest-only` | 推送新辨識需求時丟棄舊需求，確保 Engine 始終對應最新狀態。 |
| **Robot Command Queue** | `AsyncQueueManager` | `maxsize=10` | `bounded` | 命令有連續性，不應被靜默丟棄。若佇列滿則觸發 `blocked` 狀態。 |
| **Persistence Queue** | `PersistenceWorker` | `2000` | `bounded-with-warning` | 非同步寫入 SQLite。允許有限的 Drop，但觸發警報，以保護系統記憶體不被突發高頻事件佔滿。 |

## 2. Metrics 與診斷機制 (Diagnostics)

### 2.1 Queue Stats (`AsyncQueueManager`)
`AsyncQueueManager` 負責蒐集 frame, detect, robot 的資料，並透過 `MonitoringWorker` 每 2 秒封裝進 `DIAGNOSTICS.UPDATED.queue` 中。

- **`dropped_oldest`**: 記錄因為佇列已滿而被丟棄的次數。
- **`status`**: 包含 `idle`, `processing`, `warning` (有 dropped 發生), `blocked` (佇列滿且無法丟棄，或存在 stale item 超過 5 秒未消費)。
- **`blocked_reason`**: `full` 或是 `stale_item`。

### 2.2 Persistence Stats (`PersistenceWorker`)
Persistence Queue 使用 Python 原生的 `queue.Queue` 搭配背景執行緒收集，寫入 SQLite。

- 當 Queue Full 時，會觸發 `dropped_events` 累加。
- **Warning 機制**: Drop 次數若超過 `PERSISTENCE_DROP_WARNING_THRESHOLD` (預設 1)，且距離上次發送警告超過 5 秒，則主動推送一筆 source 為 `persistence_worker` 的 `DIAGNOSTICS_UPDATED` 事件，內含 `dropped_event_type` 與當下 stats。

## 3. UI 對應 (Dashboard)

- **Vision FPS 與 Drop Rate**: 讀取 `frame.dropped_oldest` 計算攝影機處理效能。
- **Robot Topology 警告**: 若 `robot` 佇列呈現 `blocked` 狀態，控制面板將呈現警告燈號，代表無法消化更多物理移動指令。
- **Error Panel**: 當收到由 `PersistenceWorker` 觸發的 Drop Diagnostics，代表本地儲存 I/O 發生瓶頸，此警告應出現在 Dashboard 錯誤面板。
