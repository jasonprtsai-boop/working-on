# S.M.A.R.T. Chess Robot

2026-10-05 已依 0929、1001、1002 實測文件更新基準，詳見 [現場紀錄與整合界線](docs/FIELD_RECORD_BASELINE.md)。最新現場紀錄為 PC `192.168.1.99` → Robot `192.168.1.200:5890`、TMflow `Start → Listen`；DO3 與直接 TMSCT 相對移動已有 10/02 測試紀錄。AOI 存檔問題已於 10/01 以搜尋範圍修正。以下舊的 Listen → Vision → Listen 屬整合目標，尚未由 10/02 文件驗證；目前工作樹的 Modbus 設定亦尚未切換。

本專題是本機執行的象棋機械手臂系統。PC 上的 Python 後端是唯一流程與動作主控，負責座標移動、吸盤、棋局、辨識與 AI；TMflow 只保留 Listen → Vision → Listen 拍照循環，控制器本身的安全設定與實體急停仍是最終安全邊界。

2026-09-20 使用者確認的現行基準：

- 機械手臂控制與連結使用 **TMflow 1.82.51**；後續研究、設定與實作以此版本為準。
- 流程以 **單張影像** 為主；雙張 A/B 文件屬舊設計。
- 2026-09-29 確認採用 Python 控制全部座標移動與 DO3；動作完成後由 Python 發送 `ScriptExit()`，TMflow 執行一次 Vision 後回到 Listen。
- 這條路徑已完成軟體實作與單元測試，但尚未以 TM5-700 實機驗證；`AUTO_EXECUTE_ROBOT` 在分段測試完成前保持 `false`。

程式庫包含 `tmflow_json`、`techmanpy` 與 `modbus` adapter，這是程式盤點結果，不代表現場同時使用這些通道。現有節點 JSON 及舊設計文件也不能代替使用者確認的實際流程。詳細紀錄見 [系統理解及 TMflow 知識紀錄](docs/SYSTEM_TMFLOW_KNOWLEDGE.txt)。

`POST /api/stop` 只暫停軟體流程，不是實體急停。真機旁仍必須使用 TM 控制器安全設定與實體急停。

## 目前文件

清理後保留以下操作與驗證必要文件；DOCX、原廠 PDF、第三方套件與授權文件未刪除。

| 文件 | 保留原因 |
| --- | --- |
| `README.md` | 安裝、設定及現況入口。 |
| `backend/infrastructure/protected_assets/ASSET_MANIFEST.md` | 程式實際讀取的模型／引擎驗證清單。 |
| `docs/TMFLOW_1_82_51_NODE_SETUP_GUIDE.md` | 產圖檢查會讀取的節點表；目前與模型版本不一致。 |
| `docs/TMFLOW_1_82_51_FULL_NODE_DESIGN.md` | 節點表引用的點位、協定與控制責任定義。 |
| `docs/TMFLOW_1_82_51_FIELD_OPERATION_MANUAL.md` | 現場校正與分段測試表。 |
| `docs/TMFLOW_V2_TO_V3_MIGRATION.md` | 上述文件引用的舊版遷移對照，避免錯刪控制器節點。 |

最新檔案整理紀錄見 [專案檔案盤點](docs/PROJECT_FILE_INVENTORY.md)。舊 `reports/document_cleanup_20260920/` 已不存在，不能再依該路徑還原。2026-10-05 的歷史 Excel 與拍攝資料封存在 `data/archive/20261005/`。

## 架構與設定摘要

- `backend/application/bootstrap.py` 組裝服務、事件、狀態及背景工作；核心狀態經 EventBus、StateManager 與 reducers 更新。
- `VisionSystem` 是預設視覺入口；可選 queue pipeline 由 `VISION_WORKER_PIPELINE_ENABLED` 控制。FrameBuffer 會丟棄舊影格，不能直接當雙圖批次儲存。
- `.env`、選用的 `backend/config.yaml` 及啟用時的 `data/setup_settings.json` 共同決定設定。應同時核對 `SETUP_SETTINGS_ENABLED`。
- `APP_ENV` 決定部署安全等級；`SYSTEM_MODE` 描述使用模式。`SYSTEM_MODE=production` 不等於已啟用正式安全檢查。
- `ROBOT_ADAPTER=listen` 不是現有選項；自訂 JSON、Modbus 與 Listen/TMSCT 是不同協定。
- DO3 是實體輸出，不能直接推論為 `ROBOT_GRIPPER_REGISTER=3`；端子、極性、Base/TCP 與安全高度依實測。

## 安裝

Windows / PowerShell：

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.runtime.txt -r requirements.vision.txt
.\scripts\npm24.cmd ci
Copy-Item .env.example .env
```

若使用專案安裝腳本：

```powershell
powershell.exe -ExecutionPolicy Bypass -File setup_env.ps1
```

建議版本：

| 項目 | 版本 |
| --- | --- |
| Python | 3.10.x，實驗室建議 3.10.13 |
| Node.js | 24.x |
| npm | 11.x |
| Ultralytics | 8.4.55 或相容版本 |

Pikafish、NNUE、YOLO 模型使用 Git LFS。第一次 clone 後請確認：

```powershell
git lfs install
git lfs pull
```

## 啟動

安全模擬模式：

```powershell
Copy-Item .env.example .env
.\.venv\Scripts\python.exe main.py
```

開啟：

```text
http://127.0.0.1:5000/
```

實驗室目前的 IP/Listen 設定保留，不為了套範例覆蓋已通的 `.env`。先統一 v3.0/v3.1 規格，再依 `docs/TMFLOW_1_82_51_FIELD_OPERATION_MANUAL.md` 修訂現場測試。以下為保留的雙張設計測試順序，尚未代表 v3.1：

1. 記錄 DO3 的端子、極性及停止時行為；示教 7 個固定點與 5 個動態點模板。
2. 填入棋盤基準點、Base/TCP、取放高度與兩視角校正。
3. 接入 Listen 點位命令與 A/B 批次配對，先測不退出 Listen 的點位寫入/讀回。
4. 依序測雙張拍攝、空載座標、單顆吸放及吃子，最後測完整回合。
5. 全部通過前保持 `AUTO_EXECUTE_ROBOT=false`。測試工具中的 ScriptExit 可能接續動作節點，名稱含 fake 不代表不會移動。

## 常用檢查

```powershell
.\scripts\npm24.cmd test
.\scripts\npm24.cmd run check:system
.\scripts\npm24.cmd run check:system:hardware
.\.venv\Scripts\python.exe -m unittest discover tests -v
.\.venv\Scripts\python.exe scripts\check_production_config.py --self-test
.\.venv\Scripts\python.exe scripts\check_production_config.py --current
```

`check:system` 代表軟體 smoke、HTML、測試與基本 runtime 檢查通過；`check:system:hardware` 會要求 `/api/ready` 回報真機 readiness，robot 未連線時會失敗。

`--require-production` 只應在真正 `APP_ENV=production` 時使用。若目前是實驗室測試，`APP_ENV=development` 失敗是正常保護，不代表程式壞掉。

## 關鍵安全開關

| 設定 | 意義 |
| --- | --- |
| `APP_ENV` | 決定是否啟動正式部署等級的安全檢查。 |
| `SYSTEM_MODE` | 專案語意模式，例如 `simulation`、`lab_real_robot`、`production`。 |
| `SETUP_SETTINGS_ENABLED` | 是否讓 `data/setup_settings.json` 覆蓋 robot/vision runtime 值；模擬模式保持 `false`，實機測試用 `true`。 |
| `FAKE_ROBOT` | 是否使用假機械手臂。 |
| `FAKE_VISION` | 是否使用假視覺。 |
| `FAKE_AI` | 是否使用假 AI。 |
| `AUTO_EXECUTE_ROBOT` | 是否讓 AI 走法自動送到真機。真機測試前保持 `false`。 |

`SYSTEM_MODE=production` 但 `APP_ENV=development` 會讓人誤會：系統看起來像正式模式，但安全檢查仍是開發模式。實驗室真機測試建議用 `SYSTEM_MODE=lab_real_robot`，正式部署才用 `APP_ENV=production`。

## 受保護資產

請不要在一般整理中刪除或重新命名：

```text
backend/infrastructure/protected_assets/engine/pikafish-avx2.exe
backend/infrastructure/protected_assets/engine/pikafish.nnue
backend/infrastructure/protected_assets/vision/best.pt
backend/infrastructure/protected_assets/vision/dataset_mapping.yaml
backend/infrastructure/protected_assets/vision/args.yaml
```

詳細 hash 與大小在 `backend/infrastructure/protected_assets/ASSET_MANIFEST.md`。
