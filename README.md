# S.M.A.R.T. Chess Robot

這是專為象棋機器人研究所開發的本機 Flask + Socket.IO 控制系統。

目前的執行環境包含：
- 透過 Flask 渲染網頁介面以及靜態的前端模組。
- 使用 Socket.IO 進行狀態同步，並具備穩定的前端事件合約 (event contract)。
- 透過受保護的引擎及 NNUE 資源進行 Pikafish 引擎分析。
- 具備 OpenCV / YOLO 視覺管線，並支援 MJPEG 串流。
- 提供假訊號 (fake)、TMflow TCP JSON、TechmanPy 以及 Modbus 相容模式的機器人整合介面，並受到緊急停止 (E-Stop) 安全機制的保護。
- 使用 SQLite 支援事件持久化、重播、遙測資料，以及 Excel/CSV 匯出功能。

## Clone 與 Git LFS 注意事項

本專案的 Pikafish 引擎與 YOLO 模型使用 Git LFS 管理。別台電腦第一次取得專案前，請先安裝 Git LFS，然後執行：

```powershell
git lfs install
git clone https://github.com/jasonprtsai-boop/working-on.git
cd working-on
git lfs pull
```

如果沒有安裝 Git LFS，或 clone 後沒有執行 `git lfs pull`，`backend/infrastructure/protected_assets/` 內的模型與引擎檔可能只會是 LFS 指標檔，程式會找不到真正的二進位內容。

## 快速開始

Windows / PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.runtime.txt -r requirements.vision.txt
.\scripts\npm24.cmd ci
Copy-Item .env.example .env
.\.venv\Scripts\python.exe main.py
```

或者使用安裝輔助腳本：

```powershell
powershell.exe -ExecutionPolicy Bypass -File setup_env.ps1
```

開啟網頁：
- 控制台 UI: `http://127.0.0.1:5000/`
- 任務控制 / 遙測儀表板: `http://127.0.0.1:5000/dashboard`

儀表板需要從 `POST /api/login` 取得且帶有設定之 `ADMIN_PASSWORD` 的 bearer token 才能存取。

建議的 Windows 系統檢查：

```powershell
.\check_system.cmd
```

在發佈打包或交接前，請使用 `.\check_system_strict.cmd`。`.cmd` 包裝腳本會特別為了本專案略過本機 PowerShell 腳本執行原則，並接著呼叫 `scripts\check_system.ps1`。

## 常用指令

請在專案根目錄的 PowerShell 執行這些指令。在本專案中建議使用 `.\scripts\npm24.cmd` 來執行 Node/npm 指令；這會使用專案本地的 Node 24 執行環境，並避免意外執行尚未支援的 Node 25+ 版本。

環境設定：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\scripts\npm24.cmd ci
Copy-Item .env.example .env
```

啟動應用程式：

```powershell
.\.venv\Scripts\python.exe main.py
.\.venv\Scripts\python.exe scripts\run_web_simulation.py
powershell.exe -ExecutionPolicy Bypass -File scripts\run_dev.ps1
```

版本與依賴套件檢查：

```powershell
.\scripts\npm24.cmd run check:versions
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe scripts\audit_dependencies.py
```

品質與測試指令：

```powershell
.\.venv\Scripts\python.exe scripts\quality_gate.py
.\check_system.cmd
.\check_system_strict.cmd
.\scripts\npm24.cmd test
.\.venv\Scripts\python.exe -m unittest discover tests -v
```

視覺與相機指令：

```powershell
.\.venv\Scripts\python.exe scripts\test_camera.py
.\.venv\Scripts\python.exe scripts\test_vision_pipeline.py
.\.venv\Scripts\python.exe scripts\check_vision_models.py --warmup
.\.venv\Scripts\python.exe scripts\vision_benchmark.py
.\.venv\Scripts\python.exe scripts\update_vision_model.py <source-folder> --warmup
```

資料庫、匯出與報告指令：

```powershell
.\.venv\Scripts\python.exe -m backend.infrastructure.database.init_db
.\.venv\Scripts\python.exe scripts\migrate_db.py
.\.venv\Scripts\python.exe scripts\check_db.py
.\.venv\Scripts\python.exe scripts\test_export.py
.\.venv\Scripts\python.exe scripts\repair_excel_workbook.py
```

清理與打包：

```powershell
.\scripts\npm24.cmd run cleanup:dry-run
.\scripts\npm24.cmd run release:zip
.\scripts\npm24.cmd run share:zip
```

疑難排解：

```powershell
.\.venv\Scripts\python.exe -m pip check
.\scripts\node24.cmd --version
.\scripts\npm24.cmd --version
rg -n "[ \t]+$" .
git diff --check
```

真實 TM5-700 機械手臂網路檢查：

```powershell
Test-NetConnection 169.254.47.64 -Port 5890
```

## 安裝與執行說明 (Installation And Runbooks)

當轉移專案到不同電腦，或是準備實驗室電腦時，請參閱以下文件：

| 檔案 | 用途 |
| --- | --- |
| `INSTALL_WINDOWS.md` | 標準 Windows 設定與依賴套件重置。 |
| `INSTALL_LAB_PC.md` | 用於相機與 TM5-700 驗證的實驗室電腦設定。 |
| `RUN_SIMULATION.md` | 無實體硬體情況下的安全首跑模式。 |
| `RUN_REAL_ROBOT.md` | TM5-700 試車順序與安全檢查清單。 |
| `TROUBLESHOOTING.md` | 常見的 Python, npm, 相機, 機械手臂, 以及程式碼品質檢查修正。 |

## 組態設定 (Configuration)

請使用 `.env.example` 作為已文件化的本機開發基準，並將其複製到 `.env`。

重要預設值：

| 設定 | 本機預設值 | 備註 |
| --- | --- | --- |
| `APP_ENV` | `development` | 只有在安全性設定皆已配置妥當後才設定為 `production`。 |
| `SYSTEM_MODE` | `simulation` | Production 模式絕不能使用 `simulation`、`test` 或 `demo`。 |
| `SMART_CHESS_HOST` / `PORT` | `127.0.0.1` / `5000` | 若要綁定所有 IP（Bind-all）需設定 `SMART_CHESS_BIND_ALL=true`，並配置安全密碼/CORS。 |
| `CHESS_SECRET_KEY` | placeholder | 在部署前必須是一組 32+ 字元的隨機字串。 |
| `ADMIN_PASSWORD` | placeholder | 除了明確不安全的測試模式外，不能使用 `888888`。 |
| `SETUP_PASSWORD` | placeholder | 在 production 模式下不可使用預設值 `login`。 |
| `FAKE_ROBOT` / `FAKE_AI` | `true` / `true` | 安全的本機預設值。Production 模式兩者皆需為 `false`。 |
| `FAKE_VISION` | `true` | 若為真實相機/模型執行環境請使用 `false`。Production 模式需為 `false`。 |
| `ROBOT_ADAPTER` | `tmflow_json` | 針對 TMflow 1.82 支援換行符分隔的 TCP JSON 協定所設定的主要真實手臂路徑。只有為了相容性才使用 `techmanpy` 或 `modbus`。 |
| `ROBOT_IP` / `ROBOT_PORT` | `169.254.47.64` / `5890` | 確認適用於實驗室的 TM5-700 控制器基準。 |
| `CONTROL_AUTH_REQUIRED` | `true` | 核心控制 API 路徑需要 JWT 驗證。 |
| `RATE_LIMITS_ENABLED` | `true` | 應用於登入、控制以及 socket 動作。 |
| `DB_PATH` | `data/runtime/app.db` | Production 模式需要明確的絕對路徑。 |
| `YOLO_CONFIG_DIR` | `logs/ultralytics` | 將 Ultralytics 的設定檔保持在被忽略的 runtime logs 內。 |

上線前檢查 (Production preflight):

```powershell
.\.venv\Scripts\python.exe scripts\check_production_config.py --self-test
.\.venv\Scripts\python.exe scripts\check_production_config.py --current --require-production
```

## 已驗證環境 (Verified Environment)

最近一次的本機驗證：2026-07-15 透過 `.\.venv\Scripts\python.exe scripts\quality_gate.py`。

建議安裝基準：
- 實驗室電腦使用 Python 3.11.9 64位元版本。支援 Python 3.9-3.12；尚未支援 Python 3.13。
- 具備 npm 11 或更新版本的 Node.js 24 LTS。`.nvmrc` 與 `.node-version` 皆設為 Node 24。

| 項目 | 已驗證版本 |
| --- | --- |
| Python | 3.9.13 |
| Flask | 3.1.3 |
| Flask-SocketIO | 5.6.1 |
| OpenCV | 4.11.0 (`opencv-python==4.11.0.86`) |
| Ultralytics | 8.4.55 |
| YOLO 模型 | `backend/infrastructure/protected_assets/vision/best.onnx` |
| ONNX Runtime | 1.19.2 |
| Pikafish | 2026-01-31 (`pikafish-avx2.exe`) |
| Node 測試堆疊 | Node 24.18.0 (透過 `scripts\npm24.cmd`), Jest 30.4.1, Playwright 1.60.0 |

主要的依賴套件檔案：

| 檔案 | 用途 |
| --- | --- |
| `requirements.runtime.txt` | 最精簡的 web, websocket, auth, engine, TMflow TCP JSON, TechmanPy, 以及 Modbus 相容執行環境。 |
| `requirements.vision.txt` | 相機, ML 視覺, ONNX, benchmark, 以及報告工具。 |
| `requirements.txt` | 整合後的研究環境。 |
| `requirements.lock.txt` | 源自已驗證 `.venv` 可重製的 Python 基準。 |
| `package-lock.json` | 可重製的 Node/Jest/Playwright 基準。 |

## 視覺系統 (Vision)

- 使用中的模型插槽: `backend/infrastructure/protected_assets/vision/best.onnx`
- 選用的來源權重檔: `backend/infrastructure/protected_assets/vision/best.pt`
- 資料集 metadata: `backend/infrastructure/protected_assets/vision/dataset_mapping.yaml`
- 訓練 metadata: `backend/infrastructure/protected_assets/vision/args.yaml`
- 校正檔案: `data/vision_calibration.json`

目前的辨識流程：

1. `CameraManager` 讀取 OpenCV 的畫面，並將最新的一幀儲存至 `frame_buffer`。
2. 棋盤校正採用手動標定角落點或是自動化 ArUco/輪廓偵測。
3. 透過單應性矩陣（homography matrix）將 `camera_frame` 校正至預設為 `1000x1000` 的 `rectified_board` 座標。
4. OpenCV 前處理應用 CLAHE 色彩增強、可選的去噪/模糊以及銳利化處理。
5. `YOLODetector` 使用受保護的 ONNX 模型進行全畫面 YOLO 推論。
6. `BoardMapper` 將偵測到的定錨點（anchors）對應至最接近的象棋棋盤交點。
7. 分類標籤轉換為象棋 FEN 棋子編碼，接著由 `TemporalValidator` 確保能穩定重複相同狀態。
8. `FENGenerator` 產生象棋 FEN，最後由系統發布 `position fen ...` 供引擎使用。

實用指令：

```powershell
.\.venv\Scripts\python.exe scripts\check_vision_models.py --warmup
.\.venv\Scripts\python.exe scripts\update_vision_model.py <source-folder> --warmup
.\.venv\Scripts\python.exe scripts\vision_benchmark.py
```

視覺相關 endpoints：
- `GET /api/vision/status`
- `GET /api/vision/cameras`
- `POST /api/vision/camera` 含 payload `{"index": 0}`
- `GET /api/vision/calibration`
- `POST /api/vision/calibration`
- `GET /api/vision/stream`
- `GET /api/video_feed`
- `GET /api/vision/snapshot`

如果相機或 YOLO 模型無法開啟，系統會直接回報錯誤，而不是靜默地切換偵測模式。

## 引擎與機械手臂 (Engine And Robot)

受保護的引擎資源：
- `backend/infrastructure/protected_assets/engine/pikafish-avx2.exe`
- `backend/infrastructure/protected_assets/engine/pikafish.nnue`

關鍵引擎參數：
- `ENGINE_PROBE_ON_BOOT=false`
- `ENGINE_AUTO_ANALYZE=false` (玩家模式只會在按下 Start 按鈕後才開始分析)
- `ENGINE_OUTPUT_QUEUE_SIZE=2000`

對開發安全的機械手臂預設值：
- `FAKE_ROBOT=true`
- `AUTO_EXECUTE_ROBOT=false`
- `ROBOT_ADAPTER=tmflow_json`
- `ROBOT_IP=169.254.47.64`
- `ROBOT_PORT=5890`
- `ROBOT_COMMAND_QUEUE_SIZE=200`
- 保守的首跑速度預設值: `ROBOT_MAX_SPEED=80`, `ROBOT_TRAVEL_SPEED=30`, `ROBOT_LIFT_SPEED=30`, `ROBOT_APPROACH_SPEED=15`

真實手臂模式需要 `FAKE_ROBOT=false`，`ROBOT_ADAPTER=tmflow_json`，TCP 埠 `5890` 上有一個可連線的 TMflow TCP JSON socket server，並回傳遵循 Part 2 協定的 ACK/DONE/ERROR。
在啟用 `AUTO_EXECUTE_ROBOT=true` 之前，請遵循 `RUN_REAL_ROBOT.md`；與人面對面運作前，必須設定 TMflow/controller TCP 速度限制、力道/碰撞偵測、G-Sensor、安全區域、虛擬牆，並有一個經過測試的實體緊急停止按鈕 (E-Stop)。

## API 總覽 (API Summary)

身分驗證：
- `POST /api/login`
- `POST /api/logout`

健康狀況與診斷：
- `GET /api/ready`
- `GET /api/health`
- `GET /api/runtime/status`
- `GET /api/runtime/metrics`
- `GET /api/assets/status`
- `GET /api/engine/status`

狀態與控制：
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

安全性：
- `GET /api/estop/status`
- `POST /api/estop/trigger` 包含 `{"reason": "..."}`
- `POST /api/estop/reset`

重播與匯出：
- `GET /api/replay/sessions`
- `GET /api/replay/steps`
- `GET /api/replay/step/<index>`
- `GET /api/replay/export`
- `GET /api/export/excel`
- `GET /api/export/csv`
- `GET /api/export_json`
- `GET /api/export_kpi`

機械手臂校正：
- `GET /api/robot/calibration`
- `POST /api/robot/calibration`

## 系統合約 (Runtime Contract)

前端程式應依賴這些穩定由後端發送至前端的事件名稱：
- `STATE_UPDATE`
- `ENGINE.INFO_UPDATED`
- `DIAGNOSTICS.UPDATED`
- `VISION.FRAME_PROCESSED`
- `ROBOT.STATUS_UPDATED`

合約程式碼：
- `backend/runtime/contract.py`
- `backend/runtime/contract_schema.py`
- `scripts/check_contract.py`

## 品質檢查 (Quality Checks)

快速的指定檢查：

```powershell
.\.venv\Scripts\python.exe scripts\check_artifact_hygiene.py
.\.venv\Scripts\python.exe scripts\check_legacy_events.py
.\.venv\Scripts\python.exe scripts\audit_dependencies.py
.\.venv\Scripts\python.exe scripts\quality_gate.py
.\scripts\npm24.cmd test
```

如果 Node 包裝腳本找不到專案本機的 Node 24，請安裝 Node.js 24 LTS，或將 Node 24 免安裝版解壓縮至 `.tools\node-v24.18.0-win-x64`。如果將資料夾複製到另一台電腦後，測試指令找不到 Jest，請刪除 `node_modules` 並在專案根目錄執行 `.\scripts\npm24.cmd ci`。請保留 `package-lock.json`。

完整本機系統檢查：

```powershell
.\check_system.cmd
```

嚴格的乾淨檔案樹（clean-tree）系統檢查：

```powershell
.\check_system_strict.cmd
```

非嚴格檢查刻意跳過了乾淨 Git 檔案樹的要求，這在工作目錄包含活躍開發中的變更時非常實用。

## 開發規劃 (Development Planning)

目前的規劃與 changeset 分類：
- `docs/ROADMAP.md`
- `docs/CHANGESET_TRIAGE.md`

請使用 roadmap 了解分階段的開發優先事項。使用 triage 文件來決定哪些被修改、刪除以及未追蹤的檔案該列入下一次穩定的 baseline 中。

## 清理與打包 (Cleanup And Release)

乾跑測試清理 (Dry-run cleanup)：

```powershell
.\scripts\npm24.cmd run cleanup:dry-run
```

建立發佈 zip 檔：

```powershell
.\scripts\npm24.cmd run release:zip
```

建立一個經過淨化、供原始碼審查或分享的 zip 檔（不含本地執行資料或受保護的二進位/模型資產）：

```powershell
.\scripts\npm24.cmd run share:zip
```

執行時產生的工件會刻意從 Git 與發佈輸出中排除：
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
- 不屬於受保護發佈流程處理的模型/引擎執行檔
