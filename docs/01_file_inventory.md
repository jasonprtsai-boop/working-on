# 第一份：專案檔案清單與用途說明

更新日期：2026-05-17

本清單依資料夾排序，逐檔說明目前工作區中的專案本體檔案用途。為了讓文件可讀，以下不逐檔展開可重建或第三方依賴資料夾：`.venv/`、`node_modules/`、`__pycache__/`、`.git/`。這些資料夾目前存在於工作區，但屬於依賴、快取或版本控制資料，不是專案原始碼交付重點。

本次列出的專案檔案數：414，資料夾群組數：90。

## 可重建或外部依賴資料夾

| 路徑 | 說明 |
| --- | --- |
| `.venv/` | Python 虛擬環境，依 `requirements*.txt` 可重建，不逐檔列入。 |
| `node_modules/` | npm 安裝的第三方套件，依 `package-lock.json` 可重建，不逐檔列入。 |
| `__pycache__/` | Python bytecode 快取，可自動再產生，不逐檔列入。 |
| `.git/` | Git 版本控制內部資料，不屬於專案功能檔案。 |

## 逐檔清單

### 專案根目錄

根目錄放啟動入口、套件設定、依賴清單、README 與環境範本。

| 檔案 | 用途 |
| --- | --- |
| `.env` | 本機環境變數與密碼/路徑設定，屬於機密設定檔，不應提交或公開內容。 |
| `.env.example` | 環境變數範本，示範啟動系統所需的 key、資料庫、engine、vision 設定。 |
| `.gitattributes` | Git 檔案屬性設定，用於換行、二進位檔或差異比對規則。 |
| `.gitignore` | Git 忽略規則，排除依賴、快取、log、runtime data 與機密檔。 |
| `jest.config.cjs` | Jest 前端測試設定，指定 jsdom/ES module 測試環境。 |
| `main.py` | 本機啟動入口，呼叫 backend app factory 並用 Flask-SocketIO 啟動服務。 |
| `package-lock.json` | Node 依賴鎖定檔，固定 npm 套件版本。 |
| `package.json` | Node/Jest/Playwright 指令與前端測試依賴設定。 |
| `README.md` | 專案快速開始、主要功能、端點與品質檢查摘要。 |
| `requirements.runtime.txt` | 最小 runtime Python 依賴，支援 Flask、Socket.IO、JWT、設定載入。 |
| `requirements.txt` | 完整研究/開發 Python 依賴，含資料分析、OpenCV、TensorFlow 等。 |
| `requirements.vision.txt` | 真實攝影機與 ML vision pipeline 的重量級選配依賴。 |
| `setup_env.ps1` | Windows PowerShell 環境建置腳本，用於建立/安裝本機 Python 環境。 |

### backend

後端 Flask/Socket.IO、應用服務、runtime、狀態、事件與硬體整合。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `main.py` | Flask app factory，建立 Flask、CORS、安全標頭、API blueprint、Dashboard 與 Socket.IO gateway。 |

### docs

長期文件與本次整理出的三份說明文件。

| 檔案 | 用途 |
| --- | --- |
| `01_file_inventory.md` | 本文件；依資料夾排序列出專案檔案與用途說明。 |
| `02_data_flow.md` | 第二份文件；說明資料流程、傳遞方向、接收對象與系統圖。 |
| `03_architecture_and_runtime.md` | 第三份文件；說明專案架構、運作原理、功能與流程圖。 |
| `PROJECT_GUIDE.md` | 原有專案指南；提供架構、流程、測試、維護與風險筆記。 |

### engine

Python 象棋 engine/reference implementation 與 UCI 路徑。

| 檔案 | 用途 |
| --- | --- |
| `board.py` | Python engine 棋盤資料結構。 |
| `evaluate.py` | Python engine 評估函式。 |
| `main.py` | Python 模組，負責 main 相關邏輯。 |
| `movegen.py` | Python engine 合法走法產生。 |
| `rules.py` | 象棋規則或核心規則輔助。 |
| `search.py` | Python engine 搜尋邏輯。 |
| `uci.py` | Python engine UCI 協定入口。 |

### frontend

Flask templates、CSS、JS modules、圖片與前端測試。

| 檔案 | 用途 |
| --- | --- |
| `index.html` | Flask/Jinja 頁面入口，組合 landing、player、console 三個主要 view。 |

### reports

檢查、smoke test、瀏覽器截圖與 audit report 產物。

| 檔案 | 用途 |
| --- | --- |
| `browser-smoke-20260515-162116-console.png` | 前端或報告使用的影像資產。 |
| `browser-smoke-20260515-162116.err.log` | 執行或 smoke test log 檔。 |
| `browser-smoke-20260515-162116.out.log` | 執行或 smoke test log 檔。 |
| `file_consistency_audit.md` | 檢查/audit 產生的 Markdown report。 |
| `html-check-20260515-154111-console.png` | HTML/browser smoke test 截圖產物。 |
| `html-check-20260515-161650-console.png` | HTML/browser smoke test 截圖產物。 |
| `html-check-20260515-161650-player.png` | HTML/browser smoke test 截圖產物。 |
| `html-function-check-20260515-153955.md` | 檢查/audit 產生的 Markdown report。 |
| `html-function-check-20260515-154111.md` | 檢查/audit 產生的 Markdown report。 |
| `html-function-check-20260515-161650.md` | 檢查/audit 產生的 Markdown report。 |
| `smart-chess-browser-smoke-20260515-162116.db` | HTML/browser smoke 或 audit 的 SQLite 結果資料庫。 |
| `smart-chess-html-check-20260515-153955.db` | HTML/browser smoke 或 audit 的 SQLite 結果資料庫。 |
| `smart-chess-html-check-20260515-154111.db` | HTML/browser smoke 或 audit 的 SQLite 結果資料庫。 |
| `smart-chess-html-check-20260515-161650.db` | HTML/browser smoke 或 audit 的 SQLite 結果資料庫。 |
| `system-review-20260515.md` | 檢查/audit 產生的 Markdown report。 |

### scripts

維護、檢查、啟動、模擬、benchmark、release scripts。

| 檔案 | 用途 |
| --- | --- |
| `audit_project.py` | 掃描專案一致性/清理候選的 audit script。 |
| `build_release_zip.py` | 建立 release zip，排除機密、依賴、runtime artifacts。 |
| `check_assets.py` | 驗證 protected assets 與 manifest。 |
| `check_contract.py` | 檢查前後端事件合約。 |
| `check_db.py` | 檢查 SQLite database 狀態。 |
| `consistency_audit.py` | 專案檔案/引用一致性 audit。 |
| `health_check.ps1` | PowerShell health check。 |
| `html_function_check.mjs` | 前端 HTML 功能檢查腳本。 |
| `migrate_db.py` | 資料庫 migration helper。 |
| `playwright_smoke.mjs` | Playwright 瀏覽器 smoke test。 |
| `quality_gate.py` | 綜合品質閘門，跑 compile、contract、asset、tests 等檢查。 |
| `repair_excel_workbook.py` | 修復/整理 Excel workbook 的維護腳本。 |
| `run_demo.py` | demo 執行腳本。 |
| `run_dev.ps1` | 開發啟動 PowerShell script。 |
| `run_web_simulation.py` | 啟動 web simulation。 |
| `simulation_driver.py` | 模擬流程 driver。 |
| `start.ps1` | Windows 啟動腳本。 |
| `system_diagnostic.py` | 系統診斷輸出腳本。 |
| `test_camera.py` | 攝影機測試腳本。 |
| `test_export.py` | 匯出流程測試腳本。 |
| `test_import_v2.py` | 匯入/模組相容性測試腳本。 |
| `test_vision_pipeline.py` | vision pipeline 測試腳本。 |
| `vision_benchmark.py` | vision benchmark 執行入口。 |

### tests

Python 測試總目錄。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `helpers.py` | Python 模組，負責 helpers 相關邏輯。 |
| `smoke_test_engine.py` | Python 模組，負責 smoke test engine 相關邏輯。 |
| `test_simulation.py` | Python 測試檔，驗證 simulation 相關行為。 |
| `test_vision_model.py` | Python 測試檔，驗證 vision model 相關行為。 |
| `verify_flow.py` | Python 模組，負責 verify flow 相關邏輯。 |

### .github/workflows

GitHub Actions CI workflow 設定。

| 檔案 | 用途 |
| --- | --- |
| `ci.yml` | 專案檔案。 |

### backend/app

後端輔助 app 元件，例如任務佇列。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `task_queue.py` | Python 模組，負責 task queue 相關邏輯。 |

### backend/application

應用層，放系統啟動、依賴容器、服務與 use cases。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `bootstrap.py` | 系統啟動總線，依序啟動 AsyncRuntime、服務、reducers、workers、workflow、timeline 與 persistence。 |
| `container.py` | 全域 service container，集中註冊與解析 bus/state/engine/vision/robot/runtime 等依賴。 |

### backend/core

象棋核心工具、座標、記譜、engine parser 與通用例外。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `coordinate_system.py` | 棋盤/像素/機械座標系轉換或座標工具。 |
| `engine_parser.py` | 解析 UCI engine info/score/PV 輸出為內部事件資料。 |
| `exceptions.py` | Python 模組，負責 exceptions 相關邏輯。 |
| `notation.py` | 象棋走法轉中文記譜。 |
| `rules.py` | 象棋規則或核心規則輔助。 |

### backend/events

事件模型、事件型別、middleware、factory、envelope 與 handler。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `envelope.py` | 事件 envelope 結構。 |
| `event_domains.py` | 事件領域分類定義。 |
| `event_factory.py` | 事件建立輔助工廠。 |
| `event_model.py` | 事件模型或相容資料結構。 |
| `event_types.py` | 系統事件列舉，定義 state、vision、engine、robot、diagnostics、UI 等事件名稱。 |
| `event_validator.py` | 事件 payload 驗證器。 |
| `middleware.py` | 事件 middleware，處理 logging/validation。 |

### backend/interfaces

對外介面層，包含 HTTP API、WebSocket、dashboard、硬體/engine interface。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `engine_interface.py` | engine interface 協定。 |
| `hardware_interfaces.py` | vision/robot 硬體 interface 協定。 |

### backend/observability

健康檢查、logger、replay、timeline、tracing。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `logger.py` | 統一 logging 設定與 logger helper。 |

### backend/runtime

背景 runtime、worker lifecycle、queues、watchdog 與前後端合約。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `async_runtime.py` | 背景 asyncio event loop 管理器，讓 workers 與非同步任務可從 Flask thread 安全提交。 |
| `contract.py` | 前後端穩定事件合約，建立 SYSTEM_STATE_UPDATE 使用的事件名稱與 envelope。 |
| `contract_schema.py` | Socket 合約 payload schema 與 diagnostics 正規化，避免前端收到不穩定資料。 |

### backend/utils

設定、auth、rate limit、logger、座標/運動學、FEN、序列化與錯誤工具。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `auth.py` | JWT/token 產生與驗證工具。 |
| `config.py` | Python 模組，負責 config 相關邏輯。 |
| `error_response.py` | 統一 JSON 錯誤格式。 |
| `idempotency.py` | API idempotency 快取，避免重複控制命令。 |
| `kinematics.py` | 棋盤格到 robot 座標與 dead-zone 的運動學換算。 |
| `logger.py` | 統一 logging 設定與 logger helper。 |
| `rate_limit.py` | 通用 rate limiter。 |

### data/runtime

本機 runtime database。

| 檔案 | 用途 |
| --- | --- |
| `app.db` | 本機 SQLite runtime database，保存事件、replay/export 所需資料。 |

### frontend/tests

Jest/jsdom 前端測試。

| 檔案 | 用途 |
| --- | --- |
| `api.test.js` | Jest 前端測試，驗證 api 模組行為。 |
| `board.move.test.js` | Jest 前端測試，驗證 board move 模組行為。 |
| `board.test.js` | Jest 前端測試，驗證 board 模組行為。 |
| `core.app.smoke.test.js` | Jest 前端測試，驗證 core app smoke 模組行為。 |
| `dashboard_renderer.test.js` | Jest 前端測試，驗證 dashboard renderer 模組行為。 |
| `event_adapter.test.js` | Jest 前端測試，驗證 event adapter 模組行為。 |
| `render_scheduler.test.js` | Jest 前端測試，驗證 render scheduler 模組行為。 |
| `socket_client.test.js` | Jest 前端測試，驗證 socket client 模組行為。 |
| `state.engine.test.js` | Jest 前端測試，驗證 state engine 模組行為。 |
| `test_dom.js` | 前端 JavaScript 模組或測試輔助檔。 |
| `ui.test.js` | Jest 前端測試，驗證 ui 模組行為。 |
| `vision_renderer.test.js` | Jest 前端測試，驗證 vision renderer 模組行為。 |

### scripts/maintenance

清理/維護腳本。

| 檔案 | 用途 |
| --- | --- |
| `cleanup.py` | 清理可重建 artifact 的維護腳本。 |

### scripts/test

script 層級 smoke tests。

| 檔案 | 用途 |
| --- | --- |
| `smoke_test.py` | Python 模組，負責 smoke test 相關邏輯。 |

### tests/integration

後端 API/WebSocket/runtime integration tests。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `smoke_test.py` | Python 模組，負責 smoke test 相關邏輯。 |
| `test_api.py` | Python 測試檔，驗證 api 相關行為。 |
| `test_contract_guard_blocks_invalid.py` | Python 測試檔，驗證 contract guard blocks invalid 相關行為。 |
| `test_contract_payload_schemas.py` | Python 測試檔，驗證 contract payload schemas 相關行為。 |
| `test_diagnostics_contract_keys.py` | Python 測試檔，驗證 diagnostics contract keys 相關行為。 |
| `test_http_smoke.py` | Python 測試檔，驗證 http smoke 相關行為。 |
| `test_mjpeg_smoke.py` | Python 測試檔，驗證 mjpeg smoke 相關行為。 |
| `test_protected_assets.py` | Python 測試檔，驗證 protected assets 相關行為。 |
| `test_robot_status_contract.py` | Python 測試檔，驗證 robot status contract 相關行為。 |
| `test_runtime_smoke.py` | Python 測試檔，驗證 runtime smoke 相關行為。 |
| `test_socket_auth.py` | Python 測試檔，驗證 socket auth 相關行為。 |
| `test_system.py` | Python 測試檔，驗證 system 相關行為。 |
| `test_ws_contract_smoke.py` | Python 測試檔，驗證 ws contract smoke 相關行為。 |

### tests/performance

壓力與效能測試。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `stress_test.py` | Python 模組，負責 stress test 相關邏輯。 |

### tests/simulation

模擬對局測試。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `run_10_games.py` | Python 模組，負責 run 10 games 相關邏輯。 |
| `simulate_full_game.py` | Python 模組，負責 simulate full game 相關邏輯。 |

### tests/unit

單元測試。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `test_ai_engine.py` | Python 測試檔，驗證 ai engine 相關行為。 |
| `test_base_event.py` | Python 測試檔，驗證 base event 相關行為。 |
| `test_board_mapper.py` | Python 測試檔，驗證 board mapper 相關行為。 |
| `test_build_release_zip.py` | Python 測試檔，驗證 build release zip 相關行為。 |
| `test_config_security.py` | Python 測試檔，驗證 config security 相關行為。 |
| `test_estop.py` | Python 測試檔，驗證 estop 相關行為。 |
| `test_event_bus.py` | Python 測試檔，驗證 event bus 相關行為。 |
| `test_event_store_adapter.py` | Python 測試檔，驗證 event store adapter 相關行為。 |
| `test_excel_exporter.py` | Python 測試檔，驗證 excel exporter 相關行為。 |
| `test_export_engine.py` | Python 測試檔，驗證 export engine 相關行為。 |
| `test_logic_rules.py` | Python 測試檔，驗證 logic rules 相關行為。 |
| `test_rate_limit.py` | Python 測試檔，驗證 rate limit 相關行為。 |
| `test_request_models.py` | Python 測試檔，驗證 request models 相關行為。 |
| `test_robot_authority.py` | Python 測試檔，驗證 robot authority 相關行為。 |
| `test_state_manager.py` | Python 測試檔，驗證 state manager 相關行為。 |
| `test_task_queue.py` | Python 測試檔，驗證 task queue 相關行為。 |
| `test_vision_benchmark.py` | Python 測試檔，驗證 vision benchmark 相關行為。 |
| `test_vision_service.py` | Python 測試檔，驗證 vision service 相關行為。 |

### backend/application/dto

應用層資料傳輸物件。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `vision_dto.py` | Python 模組，負責 vision dto 相關邏輯。 |

### backend/application/services

應用服務，協調 engine、vision、robot、game、runtime control、E-Stop。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `ai_service.py` | AI/engine 應用服務封裝。 |
| `engine_service.py` | Pikafish/UCI engine 控制服務，負責啟動、NNUE probe、送指令、解析輸出與分析 FEN。 |
| `estop.py` | E-Stop 聯鎖控制，清空任務、停止 robot、將狀態設為 ERROR 並鎖住 UI。 |
| `game_service.py` | Python 模組，負責 game service 相關邏輯。 |
| `robot_facade.py` | robot facade，統一真實 Modbus robot 與 FakeRobot，並檢查 E-Stop 後執行走子。 |
| `robot_service.py` | 真實 robot 動作服務，做座標換算、安全檢查、pick-and-place 與 robot status event。 |
| `runtime_control.py` | runtime session、安全模式、engine depth 與前端 UI 狀態控制服務。 |
| `vision_service.py` | vision 應用服務，接收 detection event，做棋盤映射、穩定化、FEN 產生與前端 heartbeat。 |

### backend/application/use_cases

高階工作流程與 use case orchestration。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `analyze_strategy.py` | Python 模組，負責 analyze strategy 相關邏輯。 |
| `apply_move.py` | Python 模組，負責 apply move 相關邏輯。 |
| `coordinate_workflow.py` | Python 模組，負責 coordinate workflow 相關邏輯。 |

### backend/core/errors

後端錯誤碼常數。

| 檔案 | 用途 |
| --- | --- |
| `codes.py` | Python 模組，負責 codes 相關邏輯。 |

### backend/data/replays

此資料夾中的專案檔案。

| 檔案 | 用途 |
| --- | --- |
| `session_1778858605.json` | runtime replay session JSON，保存一次執行/對局事件序列。 |
| `session_1778858612.json` | runtime replay session JSON，保存一次執行/對局事件序列。 |
| `session_1778858636.json` | runtime replay session JSON，保存一次執行/對局事件序列。 |
| `session_1778858641.json` | runtime replay session JSON，保存一次執行/對局事件序列。 |
| `session_1778859188.json` | runtime replay session JSON，保存一次執行/對局事件序列。 |
| `session_1778859240.json` | runtime replay session JSON，保存一次執行/對局事件序列。 |
| `session_1778859306.json` | runtime replay session JSON，保存一次執行/對局事件序列。 |
| `session_1778859402.json` | runtime replay session JSON，保存一次執行/對局事件序列。 |
| `session_1778859520.json` | runtime replay session JSON，保存一次執行/對局事件序列。 |
| `session_1778859596.json` | runtime replay session JSON，保存一次執行/對局事件序列。 |
| `session_1778859672.json` | runtime replay session JSON，保存一次執行/對局事件序列。 |
| `session_1778859720.json` | runtime replay session JSON，保存一次執行/對局事件序列。 |
| `session_1778859725.json` | runtime replay session JSON，保存一次執行/對局事件序列。 |
| `session_1778861811.json` | runtime replay session JSON，保存一次執行/對局事件序列。 |
| `session_1778861845.json` | runtime replay session JSON，保存一次執行/對局事件序列。 |
| `session_1778861852.json` | runtime replay session JSON，保存一次執行/對局事件序列。 |
| `session_1778861878.json` | runtime replay session JSON，保存一次執行/對局事件序列。 |
| `session_1778861883.json` | runtime replay session JSON，保存一次執行/對局事件序列。 |
| `session_1778862077.json` | runtime replay session JSON，保存一次執行/對局事件序列。 |
| `session_1778865283.json` | runtime replay session JSON，保存一次執行/對局事件序列。 |

### backend/domain/game

遊戲領域規則服務。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `rule_engine.py` | 遊戲規則服務，封裝合法性/流程判斷。 |

### backend/events/bus

EventBus publish/subscribe 實作。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `event_bus.py` | 事件匯流排，負責 publish/subscribe、全域訂閱、非同步派送與 dead-letter 診斷。 |

### backend/events/handlers

事件處理器，主要銜接 state handler。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `state_handler.py` | 事件到 state 的 handler glue code。 |

### backend/events/models

事件資料模型。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `base_event.py` | 標準事件資料模型，封裝 event_id、trace_id、source、timestamp、payload。 |

### backend/events/store

事件儲存 adapter，銜接 database event store。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `event_store.py` | 事件儲存實作或 adapter。 |

### backend/infrastructure/database

SQLite、snapshot、event store、export 與 DB 初始化/檢查。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `db.py` | SQLite database helper/proxy。 |
| `event_store.py` | 事件儲存實作或 adapter。 |
| `export_engine.py` | DB/事件資料轉 Excel 或完整 snapshot 的匯出 engine。 |
| `init_db.py` | SQLite schema 初始化。 |
| `inspect_db.py` | DB 檢查工具。 |
| `models.py` | 資料庫或 DTO models。 |
| `snapshot_store.py` | 狀態 snapshot SQLite 儲存。 |
| `unit_of_work.py` | 資料庫 unit-of-work 交易封裝。 |

### backend/infrastructure/protected_assets

不可任意修改的 engine/model 二進位資產。

| 檔案 | 用途 |
| --- | --- |
| `ASSET_MANIFEST.md` | 受保護二進位資產清單與 hash，記錄 Pikafish、NNUE、YOLO model 的大小與 SHA256。 |
| `manifest.py` | Python 模組，負責 manifest 相關邏輯。 |

### backend/infrastructure/robot

robot controller、adapter、planner、executor、safety 與 queue。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `command_queue.py` | robot command queue。 |
| `controller.py` | robot controller，高階協調 state machine、queue、planner、executor。 |
| `executor.py` | robot 執行器，對 adapter 發送動作。 |
| `modbus_adapter.py` | Modbus/TCP robot adapter。 |
| `motion_queue.py` | robot motion queue。 |
| `planner.py` | robot motion planner。 |
| `safety.py` | robot 安全邊界檢查。 |
| `safety_monitor.py` | robot safety monitor，監控 E-Stop/安全狀態。 |
| `serial_adapter.py` | Serial robot adapter。 |
| `state_machine.py` | robot 狀態機。 |

### backend/infrastructure/simulation

FakeRobot/FakeEngine，用於沒有實體硬體時的模擬。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `fake_engine.py` | 模擬 engine 實作，供測試或 demo 使用。 |
| `fake_robot.py` | 模擬 robot 實作，無硬體時提供相同行為介面。 |

### backend/infrastructure/vision

vision system、pipeline、camera、detection、FEN、校正與 overlay。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `benchmark.py` | vision benchmark 工具。 |
| `classifier.py` | 棋子分類器。 |
| `confidence_estimator.py` | vision detection 信心分數估計。 |
| `fake_vision.py` | 模擬 vision 資料來源。 |
| `fen_builder.py` | 由 board/detection 組成 FEN 的 builder。 |
| `morphology.py` | OpenCV morphology 影像處理工具。 |
| `perspective.py` | 影像透視校正/轉換工具。 |
| `piece_predictor.py` | 棋子分類/預測 helper。 |
| `pipeline.py` | vision pipeline，串接前處理、偵測、棋盤映射與 FEN。 |
| `roi_optimizer.py` | vision ROI 最佳化。 |
| `schemas.py` | 資料 schema 定義。 |
| `vision_system.py` | vision system facade/fallback，管理 camera stream、detector、mapper、validator、FEN generator。 |

### backend/interfaces/api

Flask /api/* route modules 與 request models/auth guard。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `api_routes.py` | API blueprint 聚合器，匯入各 route module 以註冊 /api/* 端點。 |
| `auth_guard.py` | API 控制面 auth/rate-limit guard，保護需要 admin 權限的端點。 |
| `auth_routes.py` | 登入/登出 API route，發放或清除控制台 JWT。 |
| `client_identity.py` | 解析 client IP，支援可信 proxy 設定與 rate limit identity。 |
| `control_routes.py` | 控制面 API，將 move/reset/control/simulation 請求轉成 EventBus 事件。 |
| `diagnostics_routes.py` | 健康、ready、runtime metrics、engine/vision/assets 狀態查詢 API。 |
| `estop_routes.py` | E-Stop 狀態、觸發與重置 API。 |
| `export_routes.py` | Excel/CSV 匯出 API。 |
| `replay_routes.py` | replay steps 與指定 step snapshot API。 |
| `request_models.py` | Pydantic request model，驗證 HTTP/Socket request payload。 |
| `runtime_control_routes.py` | runtime control API，管理 session、safe mode、engine depth 等。 |
| `shared.py` | API 共用工具，提供 blueprint、event 發布、runtime diagnostics、idempotency、錯誤回應。 |
| `state_routes.py` | 提供目前 SSOT 狀態 snapshot 的 API。 |
| `vision_routes.py` | 攝影機列表、切換、MJPEG stream、snapshot 等 vision API。 |

### backend/interfaces/dashboard

簡易 dashboard blueprint。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |

### backend/interfaces/shared

跨 interface 的 schema。

| 檔案 | 用途 |
| --- | --- |
| `schemas.py` | 資料 schema 定義。 |

### backend/interfaces/websocket

Socket.IO handler、request model 與 serializer。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `request_models.py` | Pydantic request model，驗證 HTTP/Socket request payload。 |
| `serializers.py` | 後端狀態與 engine event 序列化器，輸出前端可直接正規化的 payload。 |
| `socket_handler.py` | Socket.IO gateway，處理 connect/auth/action/player_move，並把 EventBus 事件轉成前端合約。 |

### backend/observability/health

health monitor。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `monitor.py` | health monitor。 |

### backend/observability/replay

replay manager。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `replay_manager.py` | replay 資料讀寫/管理。 |

### backend/observability/timeline

timeline tracer。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `timeline_tracer.py` | timeline event tracer。 |

### backend/observability/tracing

trace id 管理。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `trace_manager.py` | trace_id 建立與追蹤工具。 |

### backend/runtime/lifecycle

worker 抽象與 lifecycle manager。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `base_worker.py` | async worker 抽象基底。 |
| `worker_manager.py` | worker 註冊、啟動、停止與狀態快照。 |

### backend/runtime/messaging

runtime queue manager。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `queues.py` | runtime queue manager，提供 frame/detect/robot queue。 |

### backend/runtime/watchdog

robot watchdog。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `robot_watchdog.py` | robot watchdog 監控器。 |

### backend/runtime/workers

engine、camera、vision、robot status、monitoring、persistence workers。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `camera_worker.py` | Python 模組，負責 camera worker 相關邏輯。 |
| `engine_worker.py` | 背景 engine polling worker，讀取 SSOT FEN，呼叫 EngineService 分析並發布 engine event。 |
| `monitoring_worker.py` | 定期收集 CPU/記憶體/worker 等 runtime diagnostics 並發布診斷事件。 |
| `persistence_worker.py` | 全域事件持久化 worker，將 EventBus 事件批次寫入 SQLite。 |
| `robot_status_worker.py` | 定期讀取 robot 狀態並發布 ROBOT.STATUS_UPDATED 給狀態與前端。 |
| `robot_worker.py` | Python 模組，負責 robot worker 相關邏輯。 |
| `vision_inference_worker.py` | Python 模組，負責 vision inference worker 相關邏輯。 |
| `worker_manager.py` | worker 註冊、啟動、停止與狀態快照。 |

### backend/shared/protocols

共享 protocol 與 payload dataclass/typing。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `event_protocol.py` | 事件 protocol/envelope typing。 |
| `payloads.py` | 共享 protocol payload 定義。 |

### backend/state/reducers

狀態轉換 reducers。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `board_reducer.py` | 處理 board 狀態更新的 reducer。 |
| `engine_reducer.py` | 處理 engine 分析結果的狀態 reducer。 |
| `move_reducer.py` | 處理走子/FEN 類事件的狀態 reducer。 |
| `robot_reducer.py` | 處理 robot 狀態與動作事件的狀態 reducer。 |
| `system_reducer.py` | 處理 reset/error/diagnostics 等系統事件的狀態 reducer。 |

### backend/state/store

state store、diff/hash、transaction、sync 與 models。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `diff_engine.py` | state diff 計算。 |
| `hash_engine.py` | state hash/一致性計算。 |
| `legacy_models.py` | 舊版 state model 相容結構。 |
| `move_history.py` | 走子歷史管理。 |
| `state_store.py` | state manager 的 facade/store wrapper。 |
| `sync_state.py` | 同步狀態資料結構。 |
| `transaction.py` | state transaction helper。 |

### backend/utils/fen

FEN parsing utilities。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `parser.py` | Python 模組，負責 parser 相關邏輯。 |

### backend/utils/serialization

Excel/報表序列化與匯出服務。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `excel_exporter.py` | Excel 檔產生器，將事件/研究資料輸出 workbook。 |
| `excel_report_service.py` | Excel 報表服務，包裝匯出流程。 |

### data/archive/excel

研究資料 Excel 封存。

| 檔案 | 用途 |
| --- | --- |
| `chess_robot_experiment.before_excel_fix_20260515041131.xlsx` | Excel 研究資料或匯出/修復備份 workbook。 |
| `chess_robot_experiment.xlsx` | Excel 研究資料或匯出/修復備份 workbook。 |
| `README.md` | 專案檔案。 |

### frontend/static/css

前端樣式。

| 檔案 | 用途 |
| --- | --- |
| `main.css` | 前端樣式表。 |
| `research.css` | 前端樣式表。 |

### frontend/static/img

前端影像 placeholder。

| 檔案 | 用途 |
| --- | --- |
| `no-signal.png` | 前端或報告使用的影像資產。 |
| `placeholder.png` | 前端或報告使用的影像資產。 |

### frontend/static/js

前端 ES module 入口。

| 檔案 | 用途 |
| --- | --- |
| `app.js` | 瀏覽器端 JavaScript 入口，匯入核心 app orchestrator。 |
| `notifier.js` | 前端 toast/通知輔助。 |

### frontend/static/vendor

第三方前端 vendor 檔。

| 檔案 | 用途 |
| --- | --- |
| `socket.io.min.js` | 前端 JavaScript 模組或測試輔助檔。 |

### frontend/templates/components

Jinja UI component partials。

| 檔案 | 用途 |
| --- | --- |
| `console_view.html` | HTML/Jinja template 或 dashboard 靜態頁面。 |
| `landing_view.html` | HTML/Jinja template 或 dashboard 靜態頁面。 |
| `overlays.html` | HTML/Jinja template 或 dashboard 靜態頁面。 |
| `player_view.html` | HTML/Jinja template 或 dashboard 靜態頁面。 |
| `safety_bar.html` | HTML/Jinja template 或 dashboard 靜態頁面。 |
| `sidebar.html` | HTML/Jinja template 或 dashboard 靜態頁面。 |

### frontend/templates/layouts

Jinja layout。

| 檔案 | 用途 |
| --- | --- |
| `main_layout.html` | 前端主版型，載入 CSS、Socket.IO vendor 與 ES module 入口。 |

### backend/infrastructure/protected_assets/engine

Pikafish engine executable 與 NNUE 評估檔。

| 檔案 | 用途 |
| --- | --- |
| `pikafish-avx2.exe` | Windows 可執行檔，這裡作為 Pikafish engine runtime asset。 |
| `pikafish.nnue` | Pikafish NNUE 評估網路檔。 |

### backend/infrastructure/protected_assets/vision

YOLO vision 模型資產。

| 檔案 | 用途 |
| --- | --- |
| `best.pt` | PyTorch/YOLO 模型權重，用於 vision detector。 |

### backend/infrastructure/robot/queue

robot command queue model 與佇列。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `robot_command.py` | robot command 資料模型。 |
| `robot_queue.py` | robot queue 實作與清空控制。 |

### backend/infrastructure/vision/board

vision 座標系與棋盤格映射。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `board_mapper.py` | 棋盤座標/偵測結果映射工具。 |
| `coordinate_system.py` | 棋盤/像素/機械座標系轉換或座標工具。 |

### backend/infrastructure/vision/calibration

棋盤校正與透視轉換資料。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `board_calibrator.py` | 棋盤校正器。 |

### backend/infrastructure/vision/camera

攝影機管理與 frame buffer。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `camera_manager.py` | 攝影機開啟、讀取與重連管理。 |
| `frame_buffer.py` | 最新 camera frame buffer。 |

### backend/infrastructure/vision/debug

vision debug overlay 渲染。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `overlay_renderer.py` | debug overlay renderer。 |

### backend/infrastructure/vision/detection

多種 detector 與 detection result model。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `board_detector.py` | 棋盤偵測器。 |
| `detection_result.py` | detection bounding box/result 資料模型。 |
| `detector.py` | detector 抽象或通用偵測介面。 |
| `grid_detector.py` | 棋盤格線偵測器。 |
| `mode_factory.py` | 依設定建立 detector mode。 |
| `opencv_dnn_detector.py` | OpenCV DNN detector 實作。 |
| `piece_detector.py` | 棋子 detector。 |
| `sahi_detector.py` | SAHI slicing detector 實作。 |
| `yolo_detector.py` | YOLO detector 實作。 |

### backend/infrastructure/vision/fen

由棋盤狀態產生 Xiangqi FEN。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `fen_generator.py` | 由穩定棋盤狀態產生 Xiangqi FEN。 |

### backend/infrastructure/vision/overlay

vision overlay 管理。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `overlay_manager.py` | vision overlay 狀態管理。 |

### backend/infrastructure/vision/preprocess

影像前處理。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `image_preprocessor.py` | 影像前處理器。 |

### backend/infrastructure/vision/stream

MJPEG stream 輸出。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `mjpeg_stream.py` | MJPEG stream generator。 |

### backend/infrastructure/vision/tracking

棋子追蹤與時間連續性。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `piece_tracker.py` | 棋子追蹤器。 |

### backend/infrastructure/vision/validation

vision temporal validation。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `temporal_validator.py` | 時間穩定化 validator，避免單張 frame 抖動。 |

### backend/interfaces/dashboard/static

dashboard 靜態 HTML/JS。

| 檔案 | 用途 |
| --- | --- |
| `dashboard.js` | 前端 JavaScript 模組或測試輔助檔。 |
| `index.html` | HTML/Jinja template 或 dashboard 靜態頁面。 |

### backend/state/store/manager

state manager 與 reducer registry。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `reducer_registry.py` | event type 到 reducer 的註冊表，讓狀態轉換維持低耦合。 |
| `state_manager.py` | 後端 SSOT 狀態管理器，接收事件、呼叫 reducer、驗證 FEN、提交狀態並廣播 STATE_UPDATED。 |

### backend/state/store/models

game/engine/robot/vision/system state models。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `engine_state.py` | engine state dataclass/model。 |
| `game_state.py` | game state dataclass/model。 |
| `robot_state.py` | robot state dataclass/model。 |
| `system_state.py` | 系統 root state dataclass/model。 |
| `vision_state.py` | vision state dataclass/model。 |

### backend/state/store/synchronization

state sync manager。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `sync_manager.py` | state synchronization manager。 |

### backend/state/store/validators

state/FEN validators。

| 檔案 | 用途 |
| --- | --- |
| `__init__.py` | Python package initializer，讓此資料夾可被 import。 |
| `fen_validator.py` | FEN 格式驗證。 |

### backend/infrastructure/vision/models/chess_pieces

TensorFlow/SavedModel 棋子分類模型檔。

| 檔案 | 用途 |
| --- | --- |
| `labels.txt` | 文字設定/label/依賴清單檔。 |
| `saved_model.pb` | TensorFlow SavedModel graph 檔。 |

### frontend/static/js/modules/board

棋盤、engine、robot、vision、dashboard renderers。

| 檔案 | 用途 |
| --- | --- |
| `board_mapper.js` | 前端棋盤座標/DOM mapping helper。 |
| `board_renderer.js` | 前端棋盤 renderer。 |
| `dashboard_renderer.js` | 前端 dashboard renderer。 |
| `diagnostics_renderer.js` | 前端 diagnostics renderer。 |
| `engine_renderer.js` | 前端 engine 指標 renderer。 |
| `render.js` | 前端 renderer hub，訂閱 state 變化並呼叫棋盤、engine、robot、vision、dashboard renderer。 |
| `robot_renderer.js` | 前端 robot 狀態 renderer。 |
| `vision_renderer.js` | 前端 vision overlay/偵測結果 renderer。 |

### frontend/static/js/modules/core

前端 app orchestration、API client、export controller、render scheduler。

| 檔案 | 用途 |
| --- | --- |
| `api_client.js` | REST API client，負責 JWT 儲存、登入、Authorization header、timeout 與 JSON 錯誤處理。 |
| `app.js` | 前端總控，初始化 UIRegistry、Socket、EventAdapter、Renderer、API 初始狀態與控制按鈕。 |
| `errors.js` | 前端錯誤 helper。 |
| `export_controller.js` | 前端匯出按鈕 controller。 |
| `render_scheduler.js` | 前端 render 排程器，避免過度重繪。 |

### frontend/static/js/modules/state

前端 state、normalizer、schemas、subscriptions 與 event store。

| 檔案 | 用途 |
| --- | --- |
| `board_state.js` | 前端 board state 與更新函式。 |
| `engine_state.js` | 前端 engine state 與更新函式。 |
| `event_store.js` | 前端事件暫存，用於 telemetry/replay UI。 |
| `normalizer.js` | 前端資料正規化器，將 backend contract payload 統一成 renderer 使用的 shape。 |
| `schemas.js` | 前端 JavaScript 模組或測試輔助檔。 |
| `state.js` | 前端 JavaScript 模組或測試輔助檔。 |
| `state_manager.js` | 前端 SSOT，正規化 payload、更新 board/engine/robot/vision/ui/sync state 並通知 subscribers。 |
| `subscriptions.js` | 前端 state subscription/pub-sub helper。 |
| `sync_state.js` | 前端 sync state 與更新函式。 |
| `ui_state.js` | 前端 UI state 與更新函式。 |

### frontend/static/js/modules/ui

UI registry 與 telemetry renderer。

| 檔案 | 用途 |
| --- | --- |
| `telemetry_renderer.js` | 前端 telemetry/event log renderer。 |
| `ui_registry.js` | 前端 DOM element registry 與 UI helper。 |

### frontend/static/js/modules/websocket

Socket client、event adapter、connection status。

| 檔案 | 用途 |
| --- | --- |
| `event_adapter.js` | 接收 SYSTEM_STATE_UPDATE，檢查事件名稱與 payload 後送進 frontend state。 |
| `socket_client.js` | Socket.IO client wrapper，處理 token auth、emit/ack、重連事件與連線狀態。 |
| `socket_status.js` | 前端 socket 連線狀態 UI。 |

### backend/infrastructure/vision/models/chess_pieces/variables

SavedModel 變數權重。

| 檔案 | 用途 |
| --- | --- |
| `variables.data-00000-of-00001` | TensorFlow SavedModel 變數權重/索引。 |
| `variables.index` | TensorFlow SavedModel 變數權重/索引。 |
