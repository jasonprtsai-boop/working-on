# S.M.A.R.T. Chess Robot - Queue Policy

本文件說明目前 runtime 中各類佇列的容量、丟棄策略、診斷欄位與操作原則。目標是讓即時影像不累積延遲，同時避免機械手臂命令與事件紀錄被靜默覆蓋。

## Policy Summary

| Queue | Implementation | Max size | Policy | Behavior |
| --- | --- | ---: | --- | --- |
| Vision frame queue | `AsyncQueueManager.frame_queue` | `1` | `latest-only` | 新影格進來時若佇列已滿，丟棄舊影格，只保留最新影像供辨識使用。 |
| AI detect queue | `AsyncQueueManager.detect_queue` | `1` | `latest-only` | 新辨識需求進來時若佇列已滿，丟棄舊需求，避免 engine 或 vision 使用過期狀態。 |
| Robot command queue | `AsyncQueueManager.robot_queue` | `10` | `bounded` | 機械手臂命令不可自動覆蓋；滿載時應回報 blocked，由控制流程決定是否拒絕或等待。 |
| Persistence queue | `PersistenceWorker._queue` | `PERSISTENCE_QUEUE_SIZE`, default `2000` | `bounded-with-warning` | 事件紀錄佇列滿時會丟棄新事件並發布 diagnostics warning，不會覆蓋已排隊事件。 |
| Legacy camera frame buffer | `FrameBuffer.raw_frame_queue` / `detection_queue` | `3` | drop-oldest | 舊版即時串流路徑使用 drop-oldest，確保 MJPEG 與 overlay 儘量顯示最新畫面。 |

## Runtime Diagnostics

`AsyncQueueManager.stats()` 會輸出到 `DIAGNOSTICS.UPDATED.queue` 與 `DIAGNOSTICS.UPDATED.queues`。每個 managed queue 會包含：

| Field | Meaning |
| --- | --- |
| `initialized` | 該 queue 是否已被建立。 |
| `size` / `maxsize` | 目前排隊數量與容量上限。 |
| `policy` | `latest-only`, `bounded`, 或 `bounded-with-warning`。 |
| `dropped_oldest` | latest-only queue 已丟棄舊資料的次數。 |
| `put_count` / `get_count` | 累積寫入與讀取次數。 |
| `age_sec` | 最新寫入資料的年齡。 |
| `consumer_idle_sec` | consumer 距離上次讀取的時間。 |
| `utilization` | `size / maxsize`，用於 dashboard 顯示壅塞程度。 |
| `blocked` | queue 是否已滿或資料過久未被消耗。 |
| `blocked_reason` | `full`, `stale_item`, 或 `null`。 |
| `status` | `idle`, `processing`, `warning`, 或 `blocked`。 |

`PersistenceWorker.stats()` 會輸出到 `DIAGNOSTICS.UPDATED.persistence`，重點欄位包含：

- `queue_size`
- `queue_maxsize`
- `queue_full`
- `received_events`
- `persisted_events`
- `dropped_events`
- `drop_warning`
- `drop_rate`
- `last_drop_at`
- `last_persist_at`
- `last_error`

當 persistence queue 滿載且丟棄事件數達到 `PERSISTENCE_DROP_WARNING_THRESHOLD` 時，worker 會以 `persistence_worker` 為 source 發布 diagnostics。發布間隔由 `PERSISTENCE_DROP_WARNING_INTERVAL_SEC` 控制，預設 5 秒，避免 warning 本身造成事件風暴。

## Dashboard Interpretation

- Vision FPS 與 drop rate 應優先參考 `queue.frame.dropped_oldest`、vision latency 與 `VISION.FRAME_PROCESSED` 的 age。
- Robot queue 出現 `blocked=true` 時，不應再自動送出新 robot command；UI 應提示操作者等待或執行停止流程。
- Persistence `drop_warning=true` 表示事件紀錄已不完整，仍可繼續操作，但該段 replay/export 不應被視為完整實驗資料。
- `stale_item` 代表資料已排隊超過目前的 5 秒 blocked threshold，通常表示 consumer 停止、worker 異常或下游 I/O 卡住。

## Operational Rules

1. 影像與辨識需求使用 latest-only，因為舊資料會導致高延遲與錯誤棋局。
2. 機械手臂命令使用 bounded，不自動 drop，因為每一道命令都有安全語意。
3. Persistence queue 可以丟棄新事件，但必須留下 diagnostics，避免操作者誤以為紀錄完整。
4. 若 dashboard 顯示 queue 長時間 blocked，先停止自動流程，再檢查 worker 狀態、camera stream、SQLite I/O 與 robot socket。
5. 調整容量時應同步更新本文件、`.env.example` 與相關測試。

## Verification

建議修改 queue policy 或 worker lifecycle 後執行：

```powershell
.\.venv\Scripts\python.exe -m unittest tests.unit.test_queue_manager tests.unit.test_persistence_worker_queue -v
.\check_system.cmd
```
