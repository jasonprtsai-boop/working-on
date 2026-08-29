# S.M.A.R.T. Chess Robot

本專題是本機執行的象棋機械手臂系統。PC 上的 Python 後端是主控，網站負責玩家操作與監控，TMvision/EIH 或 OpenCV 提供影像，YOLO/SAHI 做棋子辨識，Pikafish/NNUE 產生 AI 走法，TMflow/TM5-700 負責安全動作、吸盤與狀態回報。

目前主線不是讓 TMflow 自己做棋規、AI 或完整視覺判斷，而是：

```text
玩家下棋
  -> 網站按「我已下棋」
  -> Python 擷取/接收影像
  -> YOLO/SAHI 辨識棋盤
  -> Python 驗證玩家棋步
  -> Pikafish 產生 AI 走法
  -> Python 寫入 Modbus 棋格命令
  -> TMflow 執行 pick/place/capture
  -> TMflow 回報 status / completed_cmd_id / heartbeat
```

`POST /api/stop` 只暫停軟體流程，不是實體急停。真機旁仍必須使用 TM 控制器安全設定與實體急停。

## 目前文件

專案文件已收斂成少數幾份：

| 文件 | 用途 |
| --- | --- |
| `docs/PROJECT_STATUS.md` | 目前進度、設定語意、已知風險、下一步 TM Vision 測試重點。 |
| `docs/ARCHITECTURE.md` | 系統分層、資料流、服務責任、事件/API/queue 規則。 |
| `docs/CONFIGURATION.md` | `.env`、`data/setup_settings.json`、模擬/實驗室真機/正式部署設定。 |
| `docs/TM_VISION_ROBOT_RUNBOOK.md` | TMvision/EIH、TMflow Network Node、Modbus、真機試車順序。 |
| `backend/infrastructure/protected_assets/ASSET_MANIFEST.md` | 受保護模型與引擎資產 manifest。 |

舊的日期式進度封存、重複 TMflow 研究筆記、過期安裝文件與不存在檔案引用已移除，避免現場測試時讀到舊路線。

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

實驗室真機模式請先不要直接改成自動下棋，依 `docs/TM_VISION_ROBOT_RUNBOOK.md` 逐步測：

1. PC Ethernet 能被 TMflow/TM Robot 網段連到。
2. Flask bind 到 `0.0.0.0:5000` 並設定強密鑰。
3. TMvision External Classification 先能 POST 到 Python。
4. `/api/vision/snapshot` 確認收到 EIH 影像。
5. External Detection parser 通過。
6. TMflow Network Node `9001` heartbeat/pose/status 通過。
7. Modbus square-command trigger/status/completed_cmd_id 通過。
8. 單步安全點與吸盤通過後才考慮 `AUTO_EXECUTE_ROBOT=true`。

## 常用檢查

```powershell
.\scripts\npm24.cmd test
.\.venv\Scripts\python.exe -m unittest discover tests -v
.\.venv\Scripts\python.exe scripts\check_production_config.py --self-test
.\.venv\Scripts\python.exe scripts\check_production_config.py --current
```

`--require-production` 只應在真正 `APP_ENV=production` 時使用。若目前是實驗室測試，`APP_ENV=development` 失敗是正常保護，不代表程式壞掉。

## 關鍵安全開關

| 設定 | 意義 |
| --- | --- |
| `APP_ENV` | 決定是否啟動正式部署等級的安全檢查。 |
| `SYSTEM_MODE` | 專案語意模式，例如 `simulation`、`lab_real_robot`、`production`。 |
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
