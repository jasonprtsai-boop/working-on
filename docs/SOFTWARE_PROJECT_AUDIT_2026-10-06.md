# S.M.A.R.T. Chess Robot 全專案稽核報告

- 稽核日期：2026-10-06
- 稽核對象：目前本機工作樹（包含尚未提交的修改與新檔案）
- 基準分支：`main`
- 基準提交：`0d8189ca4974cfa51a2abe92ee39e167e2919315`
- 最終判定：**NOT READY**
- 發現統計：2 Critical、8 High、5 Medium、2 Low

## 1. 結論

目前專案具備可延續的架構基礎：後端已分成 application/domain/infrastructure/interface，狀態、事件、機械手臂、視覺、引擎與匯出功能皆有明確模組；安全限制、前置檢查、事件持久化、資產雜湊與單元測試也不是空白。

但目前不能宣稱可安全操作真實機械手臂、可完成整局、可正式部署或可對外發佈。最嚴重的兩項阻斷如下：

1. `lab_real_robot` 目前綁定所有網路介面，卻接受範例 JWT 金鑰與預設管理密碼。這可繞過原本設計的角色保護，觸發 setup／robot 控制端點。
2. 機械手臂標定採 fail-open：缺檔或解析錯誤時會使用預設座標；preflight 只檢查座標是否落在軟限制內，不確認標定是否經過實測、誤差是否合格或 Base/TCP 是否吻合。現在的 `robot/calibration.json` 仍是規則格點資料，`calibration_error` 為空且 vision-to-robot 未標定。

在修正 P0/P1 項目並完成一次受監督的實機整局驗收前，應維持 `AUTO_EXECUTE_ROBOT=false`，且不要把目前網站的「停止」按鈕當成手臂停止或急停。

## 2. 稽核範圍與限制

已檢查：

- README、設定檔、環境範例、啟動入口、API、WebSocket、狀態與事件流程。
- 象棋規則、Pikafish 服務、YOLO/TMvision 流程、三種 robot adapter、標定、preflight、資料庫、匯出與診斷包。
- 前端 JavaScript/CSS/templates、測試、CI、發佈與分享腳本、LFS 資產、第三方依賴與授權風險。
- 目前工作樹相對 `HEAD` 的 85 個 tracked 變更，以及 untracked 新檔案。

未能驗證：

- TM5-700 真機、TMflow 1.82.51 現場節點、DO3 極性、真空回授、Base/TCP、棋盤與棄子區實測誤差。
- 相機、YOLO 模型推論、完整 Flask runtime、前端 Jest/Playwright 與完整 HTTP smoke。
- 原因是目前本機 Python 缺少 runtime/vision 套件，Node 24 工具目錄缺少 `node.exe`，root `node_modules` 也不存在。

因此本報告會區分：已由程式碼或 runtime 證實、很可能、以及尚未知。未執行的實機路徑不會被寫成成功。

## 3. 系統架構圖

```text
Browser / Operator / TMvision / TMflow
                 |
                 v
Flask REST + Socket.IO + ingest servers
                 |
                 v
Application services / workflow coordinator
                 |
        +--------+--------+
        |                 |
        v                 v
Domain rules/state     Vision + Pikafish
        |                 |
        +--------+--------+
                 |
                 v
RobotFacade -> RobotService -> adapter
                 |
       modbus / techmanpy / tmflow_json
                 |
                 v
TM5-700 / TMflow / gripper

Events -> SQLite event store -> replay/export/diagnostics
```

主要 Single Source of Truth 大致成立：`state_manager` 是狀態核心，`container` 是服務註冊中心，`RobotFacade` 包住實作。不過 runtime 設定同時來自 `.env`、YAML、`data/setup_settings.json` 與 calibration JSON，優先順序不直觀，已實際造成現場設定漂移。

## 4. 重大發現

### AUD-001 — P0 / CRITICAL：真實機械手臂模式接受已知憑證與範例 JWT 金鑰

- Confidence：**CONFIRMED**
- Issue：目前有效設定為 `SYSTEM_MODE=lab_real_robot`、`BIND_HOST=0.0.0.0`、`CONTROL_AUTH_REQUIRED=true`，但管理員與 setup 密碼仍是預設值，JWT 金鑰仍是文件中的可預測範例值，且 `ALLOW_INSECURE_DEFAULTS=true`。
- Evidence：直接匯入目前設定成功，沒有 fail-fast；runtime 顯示範例金鑰與兩組預設密碼都被接受。`_weak_secret` 只檢查少數字串、長度與 `change-me`，沒有把 `replace-with-*` 視為弱值；弱密碼只在 `APP_ENV=production` 強制拒絕。
- Location：`backend/utils/config.py:199-209`、`backend/utils/config.py:227-296`、`.env:22-30`、`backend/utils/auth.py:69-92`、`backend/interfaces/api/auth_guard.py:24-59`。
- Impact：知道範例密碼的人可取得 setup 權限；知道公開範例 JWT 金鑰的人可自行簽發角色 token。setup 權限可呼叫 hardware test、robot play 與手動執行 AI move。這是網路控制真實硬體的授權繞過，不只是一般網站弱密碼。
- Recommendation：
  1. 立即更換 JWT 金鑰、admin/setup 密碼並使既有 token 失效。
  2. `lab_real_robot`、`FAKE_ROBOT=false` 或 bind-all 任一成立時，都必須套用 production 等級的安全檢查。
  3. 拒絕 `replace-with-*`、`example`、`login` 等範例值；以隨機熵而非只看長度判斷金鑰。
  4. 在修正前只綁 `127.0.0.1`，並停用公開 Socket snapshot。
- Verification：新增測試，證明目前這組設定會在 import/startup 階段失敗；以新金鑰登入後驗證舊 token 全部失效。

### AUD-002 — P0 / CRITICAL：機械手臂標定與 preflight 採 fail-open

- Confidence：**CONFIRMED**
- Issue：標定檔不存在或損壞時會直接建立預設 affine；vision-to-robot 標定錯誤也只記 warning。preflight 的棋盤檢查只驗證 90 格與死棋區座標落在軟限制內，不檢查標定來源、量測點、誤差、日期、手臂序號、Base/TCP、工具姿態或 commissioning 簽核。
- Evidence：`Kinematics._load_calibration()` 在例外時呼叫 `_refresh_affine()`；`_board_and_dead_zone_safe()` 只呼叫 `RobotSafety.validate_move()`。目前 calibration 檔的格距是整齊的 40 mm、`calibration_error=null`、`vision_to_robot.calibrated=false`。手動 robot execution 使用 `require_auto_execute=False` 的同一份 preflight，因此 `AUTO_EXECUTE_ROBOT=false` 不能完全阻擋操作員端點。
- Location：`backend/utils/kinematics.py:58-104`、`backend/application/services/system_preflight.py:70-89`、`backend/application/services/system_preflight.py:386-397`、`backend/interfaces/api/robot_routes.py:302-358`、`robot/calibration.json`。
- Impact：一組「數值在軟限制內、但與真實棋盤無關」的座標仍可被判定 ready，導致碰撞、抓錯位置或越過實際安全空間。
- Recommendation：
  1. 標定載入改為 fail-closed；真實 robot 模式下缺檔、解析錯誤或未驗收不得建立預設座標。
  2. 標定資料加入 `verified`、robot serial、Base、TCP、工具、量測點數、RMS/max error、操作者、時間與設定雜湊。
  3. preflight 強制檢查上述欄位與誤差門檻，並確認所有棋格、所有死棋 slot、Z 與姿態。
  4. `save_calibration()` 使用同磁碟暫存檔後 atomic replace，避免半寫入。
- Verification：用現在的 calibration 檔跑 preflight 必須失敗；只有完成實測並寫入驗收 metadata 後才可通過。再以低速驗證四角、中心、抓取 Z 與全部死棋位置。

### AUD-003 — P1 / HIGH：吃子永遠使用同一個死棋位置，多 slot 設定未被使用

- Confidence：**CONFIRMED**（實作）；物理碰撞結果仍需現場驗證
- Issue：`_plan_move()` 對每次吃子都呼叫 `get_dead_zone_coords(1)`。雖然 calibration 與 setup UI 支援 `slot_count`/`slot_spacing`，robot workflow 沒有配置、遞增、持久化或 overflow 策略。
- Evidence：`backend/application/services/robot_service.py:283-285` 固定 slot 1；`backend/utils/kinematics.py:219-227` 已實作多 slot；目前設定為 4 slots。遷移文件也只把單一收棋盒列為尚待驗證的可能方案。
- Location：`backend/application/services/robot_service.py:269-295`、`backend/utils/kinematics.py:219-227`、`docs/TMFLOW_V2_TO_V3_MIGRATION.md:55`。
- Impact：如果現場是平面死棋區，第二顆起會堆疊或碰撞；即使是容器，整局容量、落下高度與滿載行為仍未定義。這會使整局無人值守目標無法成立。
- Recommendation：先決定並記錄實體策略：多 slot、分類盒或單一容器。多 slot 需以 game/session 狀態分配、復原與 overflow fail-stop；單一容器則需驗證容量、Z 與落子碰撞，並把 `slot_count` 從介面移除或改成容器參數。
- Verification：連續多次吃子測試、重啟後 slot 復原、滿載拒絕、人工清空後 reset，以及整局最大預期容量測試。

### AUD-004 — P1 / HIGH：目前有效 robot profile 與最新現場基準不一致

- Confidence：**CONFIRMED**
- Issue：最新現場紀錄為 PC `192.168.1.99`、Robot `192.168.1.200:5890`、Start→Listen/TMSCT；目前有效 runtime 卻是舊的 `192.168.10.x`、Modbus、port 502、server/square-command。
- Evidence：直接載入 config 顯示 `ROBOT_ADAPTER=modbus` 與舊 endpoint。`SYSTEM_MODE=lab_real_robot` 會預設啟用 setup settings，而 development 模式的 setup JSON 優先於 `.env`。README 也明確說目前工作樹尚未切換。
- Location：`backend/utils/config.py:62-97`、`data/setup_settings.json:9-64`、`config/system_parameters.json:189-191`、`README.md:3`、`docs/FIELD_RECORD_BASELINE.md:8-23`。
- Impact：程式可能等待錯誤端口、連到舊設備或使用沒有經過現場驗證的協定。即使單一 TMSCT/DO3 測試成功，也不能證明現有 `techmanpy` 或 Modbus 整合等價。
- Recommendation：建立具名、不可混合的 profile（例如 `field-2026-10-02-listen`、`legacy-modbus-lab`）；每個 profile 綁定 adapter、IP、port、Base/TCP、firmware、節點版本與 commissioning hash。啟動時顯示每個有效值的來源並要求 profile 與 commissioning report 相符。
- Verification：在現場對選定 profile 逐段驗證 connect、status、DO3、單一步移動、Vision 往返、吃子與整局；保留封包與結果證據。

### AUD-005 — P1 / HIGH：網站「停止」只暫停軟體，現有 halt wrapper 又會假回報成功

- Confidence：**CONFIRMED**
- Issue：`POST /api/stop` 只發佈 `GAME_PAUSE`，不呼叫 robot halt。`RobotService.stop_all()` 即使 `adapter.halt()` 失敗也會清除 moving 狀態並回傳 `True`；目前也沒有控制 route 使用它。前端文字卻顯示「系統已停止」。
- Evidence：route docstring 已承認只暫停 software flow；`stop_all()` 捕捉例外後無條件成功。
- Location：`backend/interfaces/api/control_routes.py:238-251`、`backend/application/services/robot_service.py:508-514`、`frontend/templates/components/overlays.html:2-8`。
- Impact：操作員可能把 UI 狀態誤認為手臂已停止；控制通道故障時系統會回報假成功。這不能取代實體 E-stop，但仍應有可靠的受控停止。
- Recommendation：把語意拆開為「暫停遊戲流程」與「受控停止手臂」。前者在 UI 明示不會停止手臂；後者需要高權限、回傳真實 adapter 結果、失敗時保持 fault 狀態並要求實體 E-stop。不要把軟體按鈕標成 emergency stop。
- Verification：模擬 halt 成功、回傳 false、timeout、例外與斷線；每種狀態都要正確反映在 API、WebSocket、UI 與 audit log。

### AUD-006 — P1 / HIGH：目前工作區無法執行標準啟動與完整品質門檻

- Confidence：**CONFIRMED**
- Issue：bundled Python 3.10.11 缺少 Flask、PyYAML、requests、numpy、OpenCV、openpyxl 等；Node 24 目錄沒有 `node.exe`；系統 Node 為 25.9.0，會被專案版本檢查拒絕；`node_modules` 不存在。
- Evidence：Python unittest discovery 找到 47 個 tests，但 24 個在 import 階段失敗，只有 23 個完成；前端 Jest/Playwright 無法啟動；vision warm-up 在 import `yaml` 即失敗。完整 quality gate 更早因 `robot/calibration.json` 缺 final newline 結束。
- Location：`.python-version`、`.node-version`、`package.json:5-9`、`scripts/quality_gate.py:120-147`、`reports/file_consistency_audit.md`。
- Impact：目前無法證明新修改沒有破壞網站、視覺、匯出、設定或硬體流程；「程式碼存在」不能等於可執行。
- Recommendation：建立可重建的 Python 3.10.13 venv 與 Node 24，安裝受控依賴，讓 `npm run check:system` 從乾淨環境一次通過。不要把個人 `.tools` 當成可攜式完整 runtime。
- Verification：fresh clone + documented bootstrap 後，完整 quality gate、HTTP smoke、Jest、Playwright 與 vision model warm-up 全綠。

### AUD-007 — P1 / HIGH：CI 的 LFS 與版本設定使品質檢查不可信或直接失敗

- Confidence：**CONFIRMED**
- Issue：protected `.exe/.nnue/.pt` 是 Git LFS 檔案；CI 使用 `actions/checkout@v4` 但沒有 `lfs: true`，接著 quality gate 又強制檢查實體檔案大小與 SHA256。GitHub checkout 官方設定的 LFS 預設值是 false，因此 fresh runner 只會拿到 pointer。CI 另用 Python 3.11，而實機基準明確是 3.10.x。
- Evidence：Git blob 是 LFS pointer；local `check_assets.py` 需要實際 1.6 MB/53 MB/5.4 MB 檔案；CI 沒有 LFS 拉取步驟。
- Location：`.github/workflows/ci.yml:12-35`、`.gitattributes`、`scripts/quality_gate.py:125-146`、`backend/infrastructure/protected_assets/ASSET_MANIFEST.md`。
- Impact：CI 不能代表可交付狀態；修完第一個格式錯誤後，很可能在 protected asset 檢查失敗。即使通過 Python 3.11，也不代表硬體用 Python 3.10 相容。
- Recommendation：checkout 加 `lfs: true` 並明確驗證 `git lfs pull`；主矩陣至少跑 3.10.13，3.11 只能當額外相容性。另加入 server smoke 與 Playwright，或把大型資產檢查拆成明確的 LFS job。
- Source：[actions/checkout 官方 action.yml：`lfs` 預設 false](https://github.com/actions/checkout/blob/main/action.yml)
- Verification：在沒有 cache 的 GitHub-hosted runner 執行，先列出資產大小/雜湊，再完成全部測試。

### AUD-008 — P1 / HIGH：依賴基準有已知漏洞，且所謂 lock 沒有被安裝

- Confidence：**CONFIRMED**（漏洞版本）；實際可利用性需逐項判定
- Issue：Python lock 的 `pip-audit` 結果有 14 個套件、141 筆 advisory records（去重後 85 個 package/advisory pairs），包含 PyJWT、python-engineio/socketio、requests、urllib3、Pillow、Torch、ONNX 與 Keras。npm production tree 有 4 項（3 high、1 moderate），都在 `socket.io` 的 transitive tree。
- Evidence：`requirements.lock.txt` 固定了受影響版本，但 README 與 CI 安裝的是寬鬆的 `requirements.runtime.txt` + `requirements.vision.txt`，不是 lock。`audit_dependencies.py` 只檢查套件名稱有沒有出現在 lock，不驗證版本、hash、安裝結果或 CVE。npm 的 direct `socket.io` server dependency 在專案程式碼中沒有 import，前端實際使用 vendored client。
- Location：`requirements.lock.txt`、`requirements.runtime.txt`、`requirements.vision.txt`、`scripts/audit_dependencies.py:26-70`、`package.json:20-25`。
- Impact：認證、網路、影像解析與 ML 檔案載入都有已知安全債；CI 每次可能取得不同版本。另一方面，直接大幅升級 Torch/Ultralytics 也可能破壞模型與硬體相容性。
- Recommendation：先移除未使用的 npm `socket.io` server dependency；為 Python 建立真正可安裝的 lock（含 hashes），CI/deployment 都從它安裝。依 code path 與 advisory 前置條件逐項分流，優先更新 PyJWT、Socket.IO stack、requests/urllib3、Pillow，再在獨立環境驗證 ML stack。
- Verification：`pip-audit`/`npm audit --omit=dev` 無未接受的 high issue；每一個暫不修的 advisory 有 owner、理由、期限與補償控制。

### AUD-009 — P1 / HIGH：對外發佈缺少專案與第三方授權、資產來源證據

- Confidence：**CONFIRMED**（缺檔）；特定模型權利狀態為 UNKNOWN
- Issue：Git 追蹤內容中沒有 `LICENSE`、`COPYING`、`NOTICE` 或 AUTHORS，資產 manifest 只有大小與 hash，沒有原始版本、下載來源、原始碼對應點或模型資料集授權。release ZIP 預設會包含 protected assets。
- Evidence：Pikafish 官方要求發佈 binary 時附 GPLv3 授權與產生該 binary 的完整 source 或精確來源指標；官方 NNUE 條款另限制未經許可的商業用途。Ultralytics 官方提供 AGPL-3.0 或 enterprise license。現在的 `best.pt` 只被描述成 configured model，無訓練資料與權利來源。
- Location：`backend/infrastructure/protected_assets/ASSET_MANIFEST.md`、`scripts/build_release_zip.py:35-177`、repository root。
- Impact：公開 repo／release ZIP 可能不符合 GPL、NNUE 或 Ultralytics 條款；也無法證明 `best.pt` 與 dataset 可合法散布。這是發佈阻斷，而不是可延後的排版問題。
- Recommendation：
  1. 決定本專案自身授權並加入 `LICENSE`。
  2. 建立 `THIRD_PARTY_NOTICES.md`，附 Pikafish exact build/tag/commit/source、GPL 文本、AUTHORS 與 NNUE 條款。
  3. 記錄 `best.pt` 的訓練者、base model、Ultralytics 版本、dataset 來源/授權、可否再散布。
  4. 發佈腳本在缺少所需授權檔或 provenance 時 fail。
- Sources：[Pikafish 官方 GPL 與 binary 發佈要求](https://github.com/official-pikafish/Pikafish)、[Pikafish NNUE 官方授權條款](https://www.pikafish.com/zh-hant/list.html?lang=zh-Hant)、[Ultralytics 官方授權說明](https://github.com/ultralytics/ultralytics/blob/main/README.md?plain=1)
- Verification：由專案負責人/法律顧問確認使用情境；release ZIP 內含全部必要 notices，且能追溯每個 binary/model 的來源。

### AUD-010 — P1 / HIGH：`APP_ENV=production` 沒有可用的正式啟動路徑

- Confidence：**CONFIRMED**
- Issue：主程式固定使用 Flask-SocketIO `async_mode="threading"`，再呼叫 `socketio.run()`。production 時把 `allow_unsafe_werkzeug` 設為 false，官方行為會拒絕 production 使用 Werkzeug；專案卻沒有另一個正式 server、process supervisor、reverse proxy/TLS 或部署 runbook。
- Evidence：development 能用目前入口啟動；切到 production 取得完整安全檢查後，同一路徑反而不能作為正式 server。
- Location：`backend/main.py:76-103`、`requirements.runtime.txt`、README。
- Impact：安全設定與可啟動性形成衝突；操作人員可能長期留在 development/lab 設定以求能跑，連帶避開 production hardening。
- Recommendation：先明確決定產品只支援單機 lab，還是要支援正式網路部署。若要部署，依 Flask-SocketIO 官方支援方式選定 server，加入 TLS/reverse proxy、服務管理、log rotation、backup/restore 與更新回滾 runbook。
- Sources：[Flask-SocketIO `allow_unsafe_werkzeug` 官方說明](https://flask-socketio.readthedocs.io/en/latest/api.html?highlight=start_background_task)、[Flask-SocketIO 官方部署文件](https://flask-socketio.readthedocs.io/en/stable/deployment.html)
- Verification：在與現場相同 Windows/網路環境，以 production 設定啟動、重啟、斷線恢復並通過 WebSocket/HTTP smoke。

### AUD-011 — P2 / MEDIUM：測試數量不少，但最危險的行為沒有回歸門檻

- Confidence：**CONFIRMED**
- Issue：已有 23 個 Python test files 與 15 個 frontend test files，但沒有 coverage 報告/門檻；CI 不跑 HTTP smoke、Playwright 或 hardware-simulation 系統路徑。也沒有測試要求「未驗收標定必須失敗」、「halt 失敗不得成功」、「多次吃子不得重用 slot」或「lab-real 不得接受預設憑證」。
- Impact：現有測試可驗證局部資料結構與協定，卻不阻止最嚴重的安全與整合回歸。
- Recommendation：先補上述四個 regression tests，再加一條 simulation end-to-end：玩家 move → vision/state → engine → robot plan → verification → next turn；CI 中實際啟動 server 並跑 browser smoke。
- Verification：測試在修正前會紅、修正後會綠；coverage 只作輔助，關鍵是覆蓋 failure path。

### AUD-012 — P2 / MEDIUM：現場與設計文件缺乏單一有效版本

- Confidence：**CONFIRMED**
- Issue：README 已承認 node setup guide 與模型版本不一致，最新 field record 又與目前 runtime profile 不同。工作樹同時刪除了原有 Architecture、Configuration、Project Status 與 runbook，新增文件尚未形成一份可直接照做的 canonical procedure。
- Location：`README.md:20-29`、`docs/FIELD_RECORD_BASELINE.md`、`docs/REAL_ROBOT_READINESS.md`、目前 git status。
- Impact：現場人員可能使用錯誤 IP、協定、節點或圖；文件存在不代表內容已被實機證實。
- Recommendation：把文件分成 `CURRENT/VALIDATED`、`DRAFT`、`HISTORICAL`；只保留一份現行架構、設定優先序、API、TMflow runbook、commissioning checklist 與 recovery guide。每份文件標示 firmware、hardware、adapter、日期、證據與 confidence。
- Verification：由另一位未參與開發者依 canonical runbook 從乾淨機器完成 simulation 啟動；現場操作員依 runbook 完成受監督的分段測試。

### AUD-013 — P2 / MEDIUM：宣稱 redacted 的診斷包會原樣複製 logs

- Confidence：**CONFIRMED**
- Issue：config/JSON 會按 key redaction，但 `_write_recent_logs()` 直接把原始 bytes 放進 ZIP，沒有套用同樣的 redaction。
- Location：`backend/observability/diagnostic_bundle.py:16-30`、`backend/observability/diagnostic_bundle.py:114-130`。
- Impact：支援包外傳時可能包含 IP、棋局資料、路徑、錯誤 payload 或未來新增的敏感 log。函式說明與實際保證不一致。
- Recommendation：對 text logs 做結構化欄位 redaction與 token pattern 遮罩；二進位或無法安全解析的 log 不自動包含。UI 應列出將匯出的檔案與警告。
- Verification：以含 password/token/header/IP 的合成 log 建立 bundle，解壓後不得出現原值。

### AUD-014 — P2 / MEDIUM：設定優先序與錯誤處理會隱藏使用者真正使用的值

- Confidence：**CONFIRMED**
- Issue：lab-real 預設開啟 setup settings；在 development 中 setup JSON 優先於 `.env`。setup JSON 解析錯誤會靜默回傳空 dict，YAML 解析錯誤只寫 debug，calibration 解析錯誤則使用預設值。
- Location：`backend/utils/config.py:27-33`、`backend/utils/config.py:62-97`、`backend/utils/setup_settings.py:15-22`、`backend/utils/kinematics.py:102-104`。
- Impact：使用者改了 `.env` 但 runtime 沒有採用；檔案損壞後系統可能悄悄切換來源。對硬體控制而言，這會增加 debug 成本並可能使用錯誤座標/網路。
- Recommendation：建立單一 typed runtime profile；啟動時輸出 sanitized effective config 與每個值的來源。真實硬體模式中，任何設定檔解析錯誤都要 fail closed。
- Verification：加入 precedence matrix tests、corrupt JSON/YAML tests 與 `/api/ready` 的 sanitized provenance。

### AUD-015 — P3 / MEDIUM：高風險邏輯集中在超大檔案，變更成本與回歸面過大

- Confidence：**CONFIRMED**
- Issue：`excel_exporter.py` 2685 行、前端 `app.js` 2418 行、`config.py` 1321 行、`modbus_adapter.py` 962 行、`kinematics.py` 861 行、`coordinate_workflow.py` 722 行。
- Impact：設定、硬體、UI 與匯出規則難以局部推理；review 與測試定位成本高，容易在修一個流程時破壞另一個流程。
- Recommendation：先以 characterization tests 固定行為，再按責任拆分：typed config schemas/profile loader、capture-slot allocator、robot command/feedback state machine、Excel sheet builders、前端 setup/player controllers。不要在 P0 尚未修完前做大重構。
- Verification：拆分後公開 interface 不變，單元測試更集中，且關鍵檔案不再同時承擔 parsing、I/O、domain 與 presentation。

### AUD-016 — P4 / LOW：內建 `audit_project.py` 掃描 bundled Python，結果不可用

- Confidence：**CONFIRMED**
- Issue：skip list 沒有 `.tools`，實際報告掃到 Python 標準函式庫，產生 2153 files、766 TODO、2123 bare pass、401 NotImplementedError，與本專案品質無關。
- Location：`scripts/audit_project.py:13-24`、`reports/system_audit.md`。
- Recommendation：排除 `.tools`、vendor、generated/minified files，並只掃 `git ls-files`；CI 使用明確 lint/static-analysis 規則。

### AUD-017 — P4 / LOW：一個換行問題會讓完整 quality gate 提前中止

- Confidence：**CONFIRMED**
- Issue：`robot/calibration.json` 缺 final newline，`consistency_audit.py` 回傳 1，導致後續 contract/assets/tests 都不執行。
- Location：`reports/file_consistency_audit.md`、`robot/calibration.json`。
- Recommendation：修正換行，並讓 quality gate 收集可並行的全部失敗後再總結，避免第一個格式錯誤遮蔽更重要問題。

## 5. 功能與交付狀態

| 領域 | 狀態 | 證據與缺口 |
| --- | --- | --- |
| 象棋規則與狀態 | PARTIAL | 純邏輯測試有通過項目；完整 runtime/state workflow 未跑完。 |
| Pikafish | VERIFIED / LIMITED | protected hash 通過；直接 UCI `uci`/`isready` 回覆成功。未重跑完整局面分析服務。 |
| Vision 資產 | VERIFIED / LIMITED | `best.pt`、mapping、args hash/size 正確；Ultralytics/OpenCV runtime 未安裝，無 warm-up/相機實測。 |
| TMvision HTTP ingest | PARTIAL | 有 size、decode、key 與 freshness 邏輯；server integration 未跑。 |
| Robot adapters | NOT READY | 三種 adapter 存在，但目前 profile 與現場基準漂移，真機整合未驗證。 |
| Calibration/preflight | NOT READY | 有軟限制與 UI，但可接受未驗收的預設標定。 |
| 吃子流程 | NOT READY | 固定 dead-zone slot 1；實體策略與容量未驗證。 |
| Stop/Recovery | NOT READY | public stop 只 pause；controlled halt 無可靠 API 結果。 |
| Web UI | PARTIAL | 55 個 JS syntax check 與 24 個 CSS integrity check 通過；Jest/Playwright/視覺可用性未跑。 |
| Auth/Security | CRITICAL | 架構上有 role/JWT/rate limit/CSP，但 current lab-real 憑證可預測。 |
| Persistence/Replay | PARTIAL | SQLite WAL/indexes/event store 存在；完整 tests 被缺依賴阻擋。 |
| Excel/CSV/diagnostics | PARTIAL | 實作完整度高；openpyxl tests 未跑，diagnostic logs 未 redaction。 |
| CI/Release | BROKEN | LFS 未 checkout、Python baseline 不同、E2E 未包含。 |
| Documentation | PARTIAL | 有誠實的 NOT READY 與 field evidence，但現行操作文件仍互相不一致。 |
| License/Provenance | NOT READY | 無 project license/notices；binary/model 來源與散布條件不完整。 |

## 6. 已執行驗證

| 檢查 | 結果 |
| --- | --- |
| Python compileall | PASS |
| JavaScript syntax | PASS，55 files |
| CSS integrity | PASS，24 files |
| Event contract / legacy publisher | PASS |
| Protected asset size/SHA256 | PASS |
| Artifact hygiene | PASS |
| Release ZIP / share ZIP dry-run | PASS |
| Git diff whitespace check | PASS；只有 CRLF 提示 |
| Pikafish UCI handshake | PASS，回覆 `uciok`、`readyok` |
| Python unittest discovery | FAIL：47 tests，24 import errors，23 completed |
| Full quality gate | FAIL：先被 calibration missing final newline 中止 |
| Vision model warm-up | BLOCKED：缺 PyYAML，且完整 vision stack 未安裝 |
| Frontend Jest/Playwright | BLOCKED：Node 24 runtime/node_modules 缺失 |
| Production config self-test | BLOCKED：標準 Python 環境缺 PyYAML |
| Current config import（暫存依賴） | PASS，但證實不安全 current profile 被接受 |
| npm production audit | FAIL：3 high、1 moderate |
| pip-audit lock scan | FAIL：14 packages，85 unique package/advisory pairs |
| 真機/相機/整局 | NOT RUN |

注意：`scripts/audit_dependencies.py` 的 PASS 只表示 declared package 名稱存在於 lock，不代表安裝使用 lock、版本相符、hash 完整或無漏洞。

## 7. 品質評分表

| 面向 | 評估 | 說明 |
| --- | --- | --- |
| Product completeness | LOW | simulation/單段功能已有，但整局實機目標未驗收。 |
| Correctness | MEDIUM-LOW | domain 與協定有測試；實體座標、吃子、stop 還有核心缺口。 |
| Architecture | MEDIUM | 分層與 facade/container 清楚；設定與大型模組仍集中。 |
| Code quality | MEDIUM | 有 validation、timeout、logging；也有 fail-open 與吞錯誤。 |
| Testing | LOW | 測試檔不少，但目前環境跑不起完整 gate，CI 也有結構性問題。 |
| Security | CRITICAL | current real-robot network profile 使用預設憑證/範例 signing key。 |
| Performance | UNKNOWN | 有 queue/throttle/fps limit，沒有有效 runtime benchmark 或負載結果。 |
| UX/accessibility | UNKNOWN-PARTIAL | 靜態結構可讀；runtime/Playwright 未跑，停止語意會誤導。 |
| Deployment/operations | LOW | production server、recovery、backup、profile control 未完成閉環。 |
| Documentation | MEDIUM-LOW | field evidence 有價值，但尚無單一可信 runbook。 |
| Legal/compliance | LOW | 缺 project license、third-party notices 與 asset provenance。 |

## 8. 建議執行順序

### Phase 0 — 立即阻斷風險

1. 維持 `AUTO_EXECUTE_ROBOT=false`，暫時只綁 localhost。
2. 更換 JWT/admin/setup credentials，停用 public snapshot，讓 lab-real 套用 production hardening。
3. 讓未驗收 calibration 必定 preflight fail；禁止 manual execute/hardware motion 繞過。
4. 修正 UI stop 文案；建立可驗證的 controlled halt，但仍以實體 E-stop 為安全邊界。

### Phase 1 — 恢復可驗證性

1. 修正 final newline，重建 Python 3.10.13 + Node 24 環境。
2. 讓 lock 成為唯一安裝基準並更新高風險依賴。
3. 修正 CI LFS、Python baseline、HTTP smoke 與 Playwright。
4. 新增四個 P0/P1 regression tests：credential、calibration、halt、capture slots。

### Phase 2 — 實機整合

1. 選定唯一 field profile，不混用 old Modbus 與 Listen/TMSCT。
2. 現場量測 Base/TCP、棋盤、Z、DO3 與死棋區，寫入具 provenance 的 commissioning report。
3. 分段驗證：連線 → status → DO3 → 單點 → 四角/中心 → 單步 → 吃子 → Vision 往返。
4. 完成一局受監督整局，保留每回合影像、命令、回覆、狀態與人工簽核。

### Phase 3 — 發佈與維護

1. 補授權、third-party notices、binary/model provenance。
2. 決定並實作正式部署拓撲，或明確宣告只支援單機 lab。
3. 合併現行文件，標記歷史稿；補 backup/restore、rollback 與 incident runbook。
4. 在 characterization tests 後拆分超大檔案。

## 9. 可驗收的完成條件

只有同時符合以下條件，才能把「真實機械手臂整局」標成 READY：

- Current lab-real profile 沒有預設/範例 secrets，且 bind-all 安全檢查會 fail closed。
- 未驗收、缺失或損壞的 calibration 無法通過任何會移動手臂的 route。
- 所有棋格、Z、工具姿態、死棋策略與容量經現場驗證。
- controlled halt 的成功/失敗可被實際觀察，UI 不把 pause 說成手臂已停止。
- Fresh clone 的 CI 包含 LFS、Python 3.10、Jest、HTTP smoke、Playwright 並全綠。
- 依賴漏洞已修復或有書面風險接受；release 內含合法所需的 license/notices/source pointers。
- 至少完成一次受監督整局：新鮮影像、合法走法、手臂結果、吃子區與最終狀態全部一致。
- 沒有已知 Critical/High 未處理問題。

## 10. 正面證據

以下內容應保留並強化，而不是推倒重做：

- `AUTO_EXECUTE_ROBOT=false` 的預設方向正確。
- move lock、workflow single-worker、fresh vision gate、motion timeout 與軟限制已存在。
- protected asset manifest 的大小/SHA256 檢查有效，三個主要 binary/model 在目前工作樹通過。
- event contract、legacy publisher check、SQLite WAL/index、JWT revocation、rate limit、CSP 與 ingest key compare-digest 都是可用基礎。
- README 與 readiness 文件有主動標示「尚未驗證」，沒有把 10/02 的單段成功誤寫成整局成功。

## 11. 決策紀錄

```text
Decision: 專案目前判定 NOT READY。
Reason: 存在真實硬體安全與授權控制兩個 Critical，且完整測試/CI/實機整局均未通過。
Alternatives: 只修局部格式或把 AUTO_EXECUTE 保持 false。
Trade-off: 局部措施可降低當下風險，但 manual robot route、弱憑證與 fail-open calibration 仍存在，因此不足以改變判定。
Date / Version: 2026-10-06 / current working tree @ 0d8189c + uncommitted changes
```
