# S.M.A.R.T. Chess Robot 專案指南

更新日期：2026-05-15

本文件是專案的主要長篇文件，整合原本分散在架構、流程圖、模組權責、測試策略、清理稽核、歷史報告與 Markdown 盤點中的長期有效資訊。若 README 是快速入口，這份文件就是維護者用來理解整套系統如何串起來的主文件。

## 1. 文件定位

本指南回答四個問題：

1. 系統從啟動到前端畫面更新，中間經過哪些檔案與模組。
2. 後端事件、狀態、worker、API、WebSocket 與前端 renderer 如何分工。
3. 哪些資料是正式契約（contract），哪些只是執行期產物（runtime artifact）或歷史報告。
4. 測試、打包、清理、資安與後續重構時要注意什麼。

目前專案只保留三份主要 Markdown：

| 文件 | 用途 |
| --- | --- |
| `README.md` | 快速啟動、主要能力、常用端點與 release 指令。 |
| `docs/PROJECT_GUIDE.md` | 架構、資料流、測試、維護政策與待辦風險。 |
| `backend/infrastructure/protected_assets/ASSET_MANIFEST.md` | 受保護執行期資產的規則、檔案大小與 SHA256。 |

一次性掃描報告、舊版規劃、亂碼文件與歷史 archive 已移除或摘要到本指南，避免後續維護時誤把舊資料當作目前規格。

## 2. 系統總覽

S.M.A.R.T. Chess Robot 是一套本機執行的象棋機器人系統，主要由以下部分組成：

目前第一方程式碼未導入 OpenAI API、Agents SDK 或 ChatGPT Apps SDK。本階段重構只穩定既有 Flask/Socket.IO/Robot/Engine/Vision 架構；未來若新增 AI agent，需另開 credentials gate、官方文件確認與 threat model。

| 區塊 | 功能 |
| --- | --- |
| Web UI | 使用 Flask templates 輸出頁面，前端以 ES modules 管理狀態與渲染。 |
| REST API | 提供 health、state、control、vision、engine、export、replay 等端點。 |
| Socket.IO | 即時同步後端狀態到前端，主要契約是 `SYSTEM_STATE_UPDATE`。 |
| EventBus | 後端事件交換中心，讓 API、worker、service、state、WebSocket 不直接強耦合。 |
| StateManager | 系統狀態權威來源，透過 reducer 套用事件並產生新 state。 |
| Vision | OpenCV camera、YOLO/SAHI 或 fallback stream、棋盤偵測與 FEN 生成。 |
| Engine | Pikafish/UCI 分析，輸出 best move、score、depth、PV 等資料。 |
| Robot | 真實或 mock 機械手臂控制；v1 active authority 是 `RobotFacade.execute_move()`。 |
| Persistence | SQLite event store、replay、diagnostics、Excel export。 |

最短概念圖：

```text
使用者 / 攝影機 / 引擎 / 機械手臂
-> API、WebSocket 或 Worker
-> BaseEvent
-> EventBus
-> StateManager / Services / Workers / Persistence / Socket forwarder
-> SYSTEM_STATE_UPDATE
-> Frontend state
-> DOM Renderers
```

核心原則：

1. `EventBus` 是後端事件交換中心。
2. `StateManager` 是狀態轉換的主要權威來源。
3. `BaseEvent` 是後端內部事件封包格式。
4. `SYSTEM_STATE_UPDATE` 是後端推給前端的穩定 WebSocket envelope。
5. 前端接收到 payload 後，先經 `normalizer.js` 正規化，再交給前端 state manager 與 renderer。
6. Vision、Engine、Robot、Monitoring、Persistence 應以 service 或 worker 運作，避免阻塞 Flask request thread。

## 3. 啟動流程

系統啟動時，檔案連接順序如下：

```text
main.py
-> backend/main.py:create_app()
-> backend/application/bootstrap.py:bootstrap_system()
-> backend/application/container.py
-> backend/runtime/async_runtime.py
-> backend/runtime/workers/worker_manager.py
-> backend/interfaces/api/api_routes.py
-> backend/interfaces/websocket/socket_handler.py
-> frontend/index.html
-> frontend/templates/layouts/main_layout.html
-> frontend/static/js/app.js
-> frontend/static/js/modules/core/app.js
```

啟動後會完成幾件事：

| 階段 | 主要輸入 | 主要輸出 |
| --- | --- | --- |
| App factory | Flask config、environment variables | Flask app、Socket.IO instance、blueprints。 |
| Bootstrap | Service container、EventBus、StateManager | services、reducers、workers、shutdown hooks。 |
| Runtime loop | `AsyncRuntime` | 背景 coroutine loop。 |
| Worker manager | worker 註冊表 | camera、vision、engine、robot、monitoring、persistence 的生命週期管理。 |
| API registration | blueprints、auth guard | `/api/*` HTTP 端點。 |
| WebSocket registration | Socket.IO handlers | socket command handler 與 event forwarder。 |
| Frontend boot | HTML、CSS、JS modules | UI state、Socket client、API client、renderers。 |

設定來源：

| 來源 | 說明 |
| --- | --- |
| `.env` | 本機開發設定與 secret。不可進入交付壓縮檔。 |
| `.env.example` | 可提交的設定樣板。 |
| `backend/utils/config.py` | runtime config 讀取與預設值。 |
| `requirements.runtime.txt` | 基本 web/runtime 依賴。 |
| `requirements.vision.txt` | 真實 vision pipeline 需要的重型依賴。 |
| `backend/infrastructure/protected_assets/` | Pikafish、NNUE、YOLO model 的受保護標準副本。 |

## 4. 分層與權責

| 層級 | 負責內容 | 代表路徑 |
| --- | --- | --- |
| Interfaces | HTTP、WebSocket、dashboard、browser 邊界 | `backend/interfaces/api`、`backend/interfaces/websocket`、`frontend` |
| Application | use cases、service orchestration、recovery、replay facade | `backend/application/services`、`backend/application/use_cases` |
| Domain/Core/State | 規則、狀態模型、reducers、事件模型 | `backend/core`、`backend/domain`、`backend/state`、`backend/events` |
| Runtime | worker lifecycle、queues、watchdog、async loop | `backend/runtime` |
| Infrastructure | DB、engine process、vision、robot hardware、protected assets | `backend/infrastructure` |
| Observability | health、metrics、diagnostics、tracing、timeline、replay records | `backend/observability` |

架構規範：

- 每種責任只保留一個權威模組。若仍有 legacy module，只能作為 adapter 或 compatibility shim。
- 狀態變更應透過 event 和 reducer，不直接改全域 state 物件。
- Service 和 Application 層不要直接呼叫 `socket.emit`；UI 推播由 Interfaces 層處理。
- 背景任務應由 `WorkerManager` 管理，確保啟動、停止、錯誤回報一致。
- 新功能應接到穩定契約，不要讓前端依賴內部 event name。
- Robot command 不應新增第二條 active consumer；自動流程必須經過 `RobotFacade.execute_move()`。

## 5. 後端重要檔案

| 路徑 | 職責 |
| --- | --- |
| `backend/main.py` | Flask app factory、blueprint 註冊、Socket.IO 初始化。 |
| `backend/application/bootstrap.py` | wires services、EventBus、StateManager、workers、reducers、shutdown hooks。 |
| `backend/application/container.py` | runtime dependencies 的 service container。 |
| `backend/interfaces/api/api_routes.py` | state、health、runtime、vision、engine、control、export、replay 等 REST routes。 |
| `backend/interfaces/api/auth_guard.py` | JWT 驗證、控制端 endpoint 保護與 rate limit。 |
| `backend/interfaces/websocket/socket_handler.py` | Socket.IO connect、command handling、event forwarding。 |
| `backend/interfaces/websocket/serializers.py` | 將後端 state/event 轉成穩定前端 payload。 |
| `backend/events/bus/event_bus.py` | publish/subscribe event transport。 |
| `backend/state/store/manager/state_manager.py` | canonical state transition manager。 |
| `backend/state/reducers/*` | board、move、engine、robot、system reducers。 |
| `backend/runtime/contract.py` | 穩定前端 event names 與 envelope helper。 |
| `backend/runtime/contract_schema.py` | payload normalization 與 schema helper。 |
| `backend/runtime/workers/*` | camera、vision、engine、robot、monitoring、persistence workers。 |
| `backend/infrastructure/vision/*` | camera、preprocess、detection、board mapping、FEN、MJPEG stream。 |
| `backend/infrastructure/robot/*` | robot queue、planner、safety、executor、hardware adapters。 |
| `backend/infrastructure/database/*` | SQLite、event store、snapshot store、export support。 |
| `backend/utils/serialization/excel_exporter.py` | Excel export 與 event reporting helpers。 |

## 6. 前端重要檔案

前端資料流：

```text
Socket.IO SYSTEM_STATE_UPDATE
-> modules/websocket/event_adapter.js
-> modules/state/normalizer.js
-> modules/state/state_manager.js
-> modules/state/subscriptions.js
-> board / engine / robot / vision / diagnostics renderers
-> DOM
```

| 路徑 | 職責 |
| --- | --- |
| `frontend/index.html` | Flask render entry。 |
| `frontend/templates/layouts/main_layout.html` | 主 layout、CSS、JS includes。 |
| `frontend/templates/components/*` | Landing、Player、Console、Sidebar、Safety bar、Overlays。 |
| `frontend/static/js/app.js` | browser entry point。 |
| `frontend/static/js/modules/core/app.js` | UI orchestration、view switching、video reconnect、export binding。 |
| `frontend/static/js/modules/core/api_client.js` | REST API client、JWT token handling。 |
| `frontend/static/js/modules/websocket/*` | Socket client、connection status、event adapter。 |
| `frontend/static/js/modules/state/*` | frontend state model、normalizer、subscriptions。 |
| `frontend/static/js/modules/board/*` | board、engine、vision、robot、diagnostics renderers。 |
| `frontend/static/js/modules/ui/*` | UI registry、telemetry renderer。 |
| `frontend/tests/*` | Jest tests。 |

前端維護原則：

- 前端只依賴 `SYSTEM_STATE_UPDATE` 契約，不依賴後端內部 event name。
- `normalizer.js` 是 payload 差異的收斂點；renderer 不應到處處理後端欄位別名。
- 需要權限的操作應由 `api_client.js` 統一帶 token。
- 棋盤動畫優先使用後端提供的 move 資訊；沒有 move 時才用 FEN snapshot 校正。

## 7. 穩定 WebSocket 契約

前端應只消費 `SYSTEM_STATE_UPDATE` envelope：

```json
{
  "type": "STATE_UPDATE",
  "payload": {}
}
```

目前穩定 event type：

| 契約事件 | 用途 |
| --- | --- |
| `STATE_UPDATE` | board、engine、robot、vision、sync、ui 的主要 snapshot。 |
| `ENGINE.INFO_UPDATED` | engine score、depth、nodes、best move、principal variation。 |
| `DIAGNOSTICS.UPDATED` | runtime health、queue depth、latency、worker state、fallback state。 |
| `VISION.FRAME_PROCESSED` | detections、latency、detections count、overlay data。 |
| `ROBOT.STATUS_UPDATED` | robot connection、busy state、queue size、position、error。 |
| `UI_TOAST` | 前端通知。 |

舊版 `state_update`、`heartbeat`、port `5050` 等內容已移除。若要確認目前契約，以以下檔案為準：

- `backend/runtime/contract.py`
- `backend/runtime/contract_schema.py`
- `backend/interfaces/websocket/socket_handler.py`
- `backend/interfaces/websocket/serializers.py`
- `frontend/static/js/modules/websocket/event_adapter.js`
- `frontend/static/js/modules/state/normalizer.js`

## 8. 主要資料流

### 8.1 玩家走棋

```text
Browser player action
-> socket_handler.py or api_routes.py
-> BaseEvent(GAME_PLAYER_MOVE)
-> EventBus
-> StateManager / GameService
-> STATE_UPDATED
-> WebSocket forwarder
-> frontend STATE_UPDATE
-> board_renderer.js
```

關鍵資料：

| 欄位 | 用途 |
| --- | --- |
| `move` | 玩家輸入或系統推導出的走法。 |
| `fen` | 棋盤最終狀態。 |
| `history` | 步驟紀錄，應維持一致格式。 |
| `current_move` | 前端棋子動畫與最後一步顯示。 |
| `state` / `game_status` | 流程階段與安全狀態。 |

### 8.2 Vision 自動辨識

```text
Camera frame
-> VisionSystem
-> detector
-> board_mapper.py
-> temporal_validator.py
-> fen_generator.py
-> VisionService
-> VISION_MOVE_DETECTED / VISION.FRAME_PROCESSED
-> EventBus
-> StateManager / WebSocket / frontend overlay
```

中間資料：

| 階段 | 資料 |
| --- | --- |
| Camera | BGR frame 或 fallback frame。 |
| Preprocess | corrected/processed frame。 |
| Detector | `Detection(class_id, class_name, confidence, bbox)`。 |
| BoardMapper | 格子位置到棋子代碼的 mapping。 |
| TemporalValidator | 多幀穩定後的 board state。 |
| FENGenerator | Xiangqi FEN string。 |
| VisionService | vision event、frontend detections、latency。 |

注意事項：

- `.pt` 模型走 YOLO/SAHI path。
- ONNX 只在明確設定 `YOLO_MODEL_PATH` 並使用 ONNX detector path 時使用。
- camera 或 ML dependency 缺失時，系統應維持 fallback stream，避免 UI 卡死。
- 未知 label 應跳過並記錄 warning，避免污染 FEN。

### 8.3 Engine 分析

```text
FEN
-> engine_worker.py
-> engine_service.py
-> protected_assets/engine/pikafish-avx2.exe
-> core/engine_parser.py
-> ENGINE.INFO_UPDATED / ENGINE_ANALYSIS_COMPLETED
-> StateManager / WebSocket
-> engine_renderer.js
```

輸入與輸出：

| 資料 | 說明 |
| --- | --- |
| `fen` | 目前棋局。 |
| `depth` | 搜尋深度。 |
| `multipv` | 候選線數量。 |
| `best_move` | 引擎最佳走法。 |
| `score` | 優勢評估。 |
| `nodes` / `nps` | 搜尋量與效率。 |
| `pv` | principal variation。 |

維護重點：

- UCI `info ... pv ...` 應視為即時分析資訊。
- 只有最終 `bestmove` 才應觸發自動 robot workflow。
- Engine busy/idle 狀態應透過 diagnostics 回到前端。

### 8.4 Robot 執行

```text
Move request
-> coordinate_workflow.py
-> RobotFacade.execute_move()
-> RobotService.move_piece() or FakeRobot implementation
-> safety.py / Modbus adapter
-> ROBOT.STATUS_UPDATED / ROBOT_MOVE_COMPLETED
-> StateManager / WebSocket / robot_renderer.js
```

Robot 指令必須經過：

1. `RobotFacade.execute_move()` active authority
2. E-Stop gate
3. safety check
4. real/mock adapter
5. status event

E-Stop 啟動後，robot action 應被阻止，前端也應顯示安全 overlay。

`RobotController`、`RobotWorker` 與舊 `robot_queue` 目前是 deprecated compatibility path，不應在 runtime 中新增 active consumer。

### 8.5 Persistence、Replay 與 Export

```text
EventBus global subscriber
-> persistence_worker.py
-> infrastructure/database/event_store.py
-> SQLite
-> replay / export / audit
```

| 功能 | 資料來源 | 輸出 |
| --- | --- | --- |
| Event persistence | EventBus events | SQLite rows。 |
| Replay | state/replay manager | `/api/replay/steps`、`/api/replay/step/<index>`。 |
| Excel export | DB、event history、runtime metrics | `.xlsx` workbook。 |
| Diagnostics | monitoring worker、services | `DIAGNOSTICS.UPDATED`。 |

Excel 欄位寫入必須經過 `sanitize_excel_cell()`，處理 `=`, `+`, `-`, `@` 開頭字串，避免 spreadsheet formula injection。

## 9. HTTP API 端點總覽

| 端點 | 用途 | 權限重點 |
| --- | --- | --- |
| `GET /api/health` | App health 與高階 runtime 狀態。 | 對外展示前需確認是否降敏。 |
| `GET /api/ready` | readiness check。 | 通常可公開。 |
| `POST /api/login` | 取得 admin/operator JWT。 | 不可使用預設密碼上線。 |
| `GET /api/state` | state snapshot。 | 若公開給 viewer，應只回傳降敏狀態。 |
| `GET /api/runtime/status` | workers、queues、EventBus diagnostics。 | 應保護。 |
| `GET /api/vision/status` | vision mode、camera、detector、model、fallback。 | 對外展示前需降敏或保護。 |
| `GET /api/vision/cameras` | camera enumeration。 | 建議保護。 |
| `POST /api/vision/camera` | 切換 camera。 | 應保護。 |
| `GET /api/vision/stream` | MJPEG stream。 | 視場景保護。 |
| `GET /api/video_feed` | MJPEG stream alias。 | 視場景保護。 |
| `GET /api/engine/status` | engine readiness 與 probe。 | 建議保護或降敏。 |
| `GET /api/assets/status` | protected assets validation。 | 應保護。 |
| `POST /api/control` | 控制端操作。 | 應保護。 |
| `POST /api/move` | player move request。 | 依模式決定。 |
| `POST /api/reset` | reset。 | 應保護。 |
| `GET /api/export/excel` | Excel export。 | 應保護。 |
| `GET /api/replay/steps` | replay list。 | 應保護或降敏。 |
| `GET /api/replay/step/<index>` | replay snapshot。 | 應保護或降敏。 |

若系統會被其他裝置連線，請先檢查 `backend/interfaces/api/auth_guard.py`、`.env` 與 CORS 設定。

## 10. 執行期輸出資料

| 輸出 | 產生來源 | 消費者 |
| --- | --- | --- |
| HTML page | Flask templates | Browser。 |
| Static JS/CSS | `frontend/static` | Browser。 |
| JSON API responses | `api_routes.py` | frontend API client / manual checks。 |
| `SYSTEM_STATE_UPDATE` | `socket_handler.py` | frontend socket adapter。 |
| MJPEG frames | vision stream route | Console video panel。 |
| Detections | Vision service | vision overlay。 |
| FEN | Vision/FEN generator 或 move reducer | StateManager / EngineWorker。 |
| Engine best move | Engine service/worker | engine renderer / workflow coordinator。 |
| Robot status | Robot service/status worker | StateManager / robot renderer。 |
| Diagnostics | Monitoring worker/services | diagnostics renderer / sidebar。 |
| SQLite events | Persistence worker | replay / export / audit。 |
| Replay JSON | Replay manager | replay API。 |
| Excel workbook | Excel exporter | user download。 |
| Logs | logger helpers | `logs/` 與 terminal。 |

## 11. 測試與品質檢查

建議本機檢查：

```powershell
npm test
npm run quality
npm run smoke:frontend
```

常用直接命令：

```powershell
.\.venv\Scripts\python.exe -m compileall -q backend scripts tests
.\.venv\Scripts\python.exe scripts\check_contract.py
.\.venv\Scripts\python.exe scripts\check_assets.py
.\.venv\Scripts\python.exe scripts\quality_gate.py
node scripts\playwright_smoke.mjs
```

測試分層：

| 層級 | 目的 | 例子 |
| --- | --- | --- |
| Unit tests | 測單一模組，不依賴硬體。 | EventBus、StateManager、reducers、request models、board mapper。 |
| Integration tests | 測 API、WebSocket、runtime contract。 | `/api/state`、WS initial state、MJPEG smoke、protected assets。 |
| Simulation tests | 測 fake vision/robot/engine 的無硬體流程。 | `tests/simulation/*`。 |
| Frontend tests | 測 browser module 行為。 | API client、event adapter、board renderer、vision overlay。 |
| Performance tests | 壓力與效能檢查。 | stress/performance tests。 |

無硬體測試建議：

- Vision 使用 fake 或 fallback mode。
- Robot 使用 fake adapter。
- Engine 可使用 mock 或降低依賴外部執行檔的 smoke path。
- 這類測試只能證明軟體流程，不等同硬體驗收。

硬體驗收需另外確認：

- 攝影機清晰度、角度、光線與辨識準確率。
- 機械手臂座標轉換、路徑規劃、吸附/夾取成功率。
- Modbus/serial 連線穩定性。
- E-Stop 與安全邊界的實機反應。

## 12. 交付包與清理規則

建立乾淨交付包：

```powershell
npm run release:zip
```

交付產物應排除：

- `.env`
- `.venv/`
- `node_modules/`
- `logs/`
- `data/` 與 runtime SQLite files
- `backend/data/`
- `reports/`
- `snapshots/`
- `__pycache__/` 與 `*.pyc`
- generated Excel files
- temporary repair / corrupt workbook files

保留：

- source code
- templates / frontend assets
- tests and scripts
- 受保護執行期資產
- `ASSET_MANIFEST.md`

根目錄不應長期保留 Excel、logs、runtime database、cache 或一次性報告。

## 13. 受保護資產

受保護資產位於 `backend/infrastructure/protected_assets/`：

| 資產 | 用途 |
| --- | --- |
| `engine/pikafish-avx2.exe` | Pikafish engine executable。 |
| `engine/pikafish.nnue` | NNUE evaluation file。 |
| `vision/best.pt` | YOLO vision model。 |

規則：

- 正常重構或清理時不要改名、刪除、搬移或覆蓋。
- 更新資產時，必須同步更新 `ASSET_MANIFEST.md` 的 size 與 SHA256。
- 更新後執行 `scripts/check_assets.py` 或 `npm run quality`。
- 交付壓縮檔必須保留受保護資產，但仍要排除 secret、logs、DB、cache、dependency folders 與 runtime reports。

## 14. 已知待確認項目

以下項目來自已移除的一次性報告與掃描摘要。它們不是全部都代表目前可被外部利用的問題，但在 demo、部署或下一輪重構前應逐項確認。

| 區域 | 待確認事項 |
| --- | --- |
| Secrets | `.env` 不可交付；`CHESS_SECRET_KEY` 要換成非預設值；正式展示不應使用預設 admin password。 |
| 公開診斷資料 | 若開放給同網段裝置，應把 public viewer state 與 admin diagnostics 分開。 |
| Auth / CORS | 非本機展示前，確認 CORS、JWT、protected endpoint matrix。 |
| HTTP rate limit | 除非 immediate peer 是 trusted proxy，否則不要信任 `X-Forwarded-For`。 |
| Socket rate limit | rate limit key 不應只依賴 SID，應考慮 user identity 或 token id。 |
| Engine workflow | UCI intermediate `info ... pv ...` 只應更新 telemetry；最終 `bestmove` 才能觸發 robot workflow。 |
| Excel export | 寫入 workbook 前要走 `sanitize_excel_cell()`，避免 formula injection。 |
| 執行期資產 | production-like mode 載入 engine/model 前應驗證 protected asset hash。 |
| 事件契約 | legacy dict event 應逐步收斂，只在 adapter 層轉換；EventBus stats 會記錄 deprecation counters。 |
| Robot worker | `RobotFacade.execute_move()` 是唯一 active authority；legacy worker/controller/queue 僅保留相容。 |
| Database | 動態 SQL table name 必須使用 export allowlist 與 identifier quoting。 |
| Performance | 大量 Excel export 不宜長時間阻塞 request thread。 |
| Vision labels | 若 logs 出現 unknown class label，需同步模型 label 與 mapper 設定。 |

## 15. 後續文件維護規則

新增文件前先判斷它是哪一類：

| 類型 | 放置方式 |
| --- | --- |
| 使用者快速啟動資訊 | 更新 `README.md`。 |
| 長期架構、流程、測試與維護資訊 | 更新本文件。 |
| 受保護資產 hash 或資產規則 | 更新 `ASSET_MANIFEST.md`。 |
| 一次性掃描結果 | 不放進主要文件；必要時摘要到本文件的待辦。 |
| 歷史報告或舊規劃 | 不再新增 Markdown archive，除非它仍是目前規格。 |

文件應維持：

- 繁體中文為主。
- 英文保留在程式識別字、路徑、event name、endpoint、command。
- 每次大改後重新檢查是否有舊路徑、舊 port、舊 event name。
- 不要把 runtime artifacts 的說明散落在 `data/`、`reports/` 或根目錄。
## 16. Folder Cleanup Notes

Cleanup pass on 2026-05-15 removed only generated or safely reproducible
artifacts:

| Removed | Reason |
| --- | --- |
| Project `__pycache__/` directories | Python bytecode cache; regenerated automatically. |
| `logs/` | Local runtime and smoke-test logs; regenerated automatically. |
| `reports/` | Generated reports and scan artifacts; durable findings are summarized in this guide. |
| `backend/data/` | Runtime replay data; regenerated by the replay recorder. |
| `data/runtime/` | Local SQLite runtime database; initialized by setup/runtime. |
| `data/archive/database/` | Old archived database files. |
| `dist/` | Generated release archives. |
| Duplicate Excel repair backups | Identical copies; one representative backup remains. |

The cleanup script is `scripts/maintenance/cleanup.py`. It intentionally skips
`.venv/`, `node_modules/`, and protected assets.

Second-pass cleanup on 2026-05-15 quarantined stale source candidates in
batches, ran compile/contract/asset checks after each batch, then ran the full
Python and frontend test suites before deleting the quarantine.

One candidate was restored and kept:

| Kept | Reason |
| --- | --- |
| `backend/core/coordinate_system.py` | Required by `engine/board.py`; removing it caused `unit.test_ai_engine` to fail with `ModuleNotFoundError`. |

Source paths removed in the second pass:

| Removed | Reason |
| --- | --- |
| `backend/frontend_sync/` | Old delta sync path with no current import/test references. |
| `backend/verification/`, `backend/observability/verification/` | Legacy verification paths with no current import/test references. |
| `backend/bootstrap/`, `backend/core/protocols/` | Compatibility scaffolding not used by current runtime imports. |
| `backend/observability/platform.py`, `backend/observability/replay/manager.py`, `backend/observability/timeline/tracker.py` | Older observability facade/tracker paths; active replay/timeline code uses the current observability modules. |
| `backend/core/replay/`, `backend/application/replay/`, `backend/events/replay/` | Replay experiments not wired into the active recorder. |
| `backend/observability/metrics/`, `backend/observability/logging/`, `backend/observability/handlers/` | Standalone observability helpers not referenced by current tests/runtime. |
| `backend/infrastructure/repositories/`, `backend/infrastructure/queue/`, `backend/infrastructure/logging/` | Generic infrastructure helpers not wired into the active container. |
| `backend/application/recovery/`, `backend/application/commands/`, `backend/application/context/`, `backend/application/exceptions/`, `backend/shared/dto/` | Architecture scaffolding not currently used. |
| `backend/core/analysis_state.py`, `backend/core/base_module.py`, `backend/core/board/`, `backend/core/exceptions.py`, `backend/core/light_validator.py`, `backend/core/move_validator.py`, `backend/core/robot.py`, `backend/core/robot_simulator.py`, `backend/core/state_diff_validator.py`, `backend/core/session/` | Legacy core helpers that remained unused after the coordinate-system dependency was restored. |
| `backend/utils/export_tools.py`, `backend/utils/serialization/report_generator.py`, `backend/utils/error_handler.py`, `backend/utils/retry.py`, `backend/utils/math/` | Older utility paths; active APIs use other modules. |
| `backend/nnue/`, `pikafish/` | Source/release backup material; runtime uses protected canonical binaries/assets. |
| `tests/simulation/fake_modules.py`, `tests/simulation/logger_report.py` | Old simulation helpers; current simulation smoke tests do not import them. |

Final validation after deleting the quarantine: `npm.cmd run quality` passed,
including Python compile checks, file consistency audit, event contract check,
protected asset manifest check, release zip dry-run, 87 Python tests, JS syntax
checks, and 33 frontend Jest tests.
