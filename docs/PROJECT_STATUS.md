# Project Status

最後整理日期：2026-08-29

## 目前結論

本專題目前已整理成「Python 主控、網站操作、TMvision/OpenCV 供影像、Pikafish 算棋、TMflow 執行動作」的架構。下一步應先測 TMvision/EIH 是否能把影像穩定送進 Python，再測 TMflow 1.82.51 Modbus Set-only 握手，不要同時測手臂自動下棋。

## 已完成

- 後端已用 Flask + Socket.IO 提供網站、API、狀態同步。
- 玩家流程已收斂到 `POST /api/player-done` 觸發視覺辨識。
- 視覺端支援 OpenCV、TMvision HTTP ingest、舊的 TMflow JSON frame source。
- `POST /api/vision/tmvision/classify` 可接 TMvision External Classification 圖片。
- `POST /api/vision/tmvision/detect` 可接 TMvision External Detection 圖片並回 annotations。
- YOLO runtime 使用 `backend/infrastructure/protected_assets/vision/best.pt`。
- AI runtime 使用受保護 Pikafish + NNUE。
- Robot 入口已集中到 `RobotFacade` / `RobotService`。
- Modbus square-command 模式已存在，Python 可作 PC Modbus server，TMflow 輪詢棋格命令。
- TMflow Network Node -> PC TCP `9001` ingest 可接 JSON telemetry；若未設定 `TMFLOW_INGEST_KEY`，也可接簡單 CSV heartbeat、pose、BUSY、DONE、ERR。
- Set-only 通過後的 TMflow 1.82.51 完整 motion 節點設計已整理到 `docs/TMFLOW_1_82_51_FULL_NODE_DESIGN.md`，包含 Move、Point、吸盤、吃子區、子流程與狀態回寫。
- 前端測試與目前保留的 Python 測試可通過。

## 目前實際設定重點

目前本機是實驗室測試性質，不是正式部署：

```text
APP_ENV=development
SYSTEM_MODE 建議使用 lab_real_robot
FAKE_ROBOT=false
FAKE_VISION=false
FAKE_AI=false
AUTO_EXECUTE_ROBOT=false
ROBOT_ADAPTER=modbus
ROBOT_MODBUS_ROLE=server
ROBOT_MODBUS_SERVER_HOST=192.168.10.50
ROBOT_MODBUS_SERVER_PORT=1502
ROBOT_MODBUS_PAYLOAD_MODE=square_command
```

`data/setup_settings.json` 會在 development 模式覆蓋部分 `.env`，所以實際執行狀態不能只看 `.env`。

## `APP_ENV` 與 `SYSTEM_MODE` 差異

`APP_ENV` 是安全等級開關：

- `development`：允許實驗室測試、localhost、較寬鬆的 debug 設定。
- `production`：啟動嚴格檢查，例如強密鑰、非公開 snapshot、禁止 fake mode、DB 絕對路徑、TMflow ingest key 等。

`SYSTEM_MODE` 是專案語意標籤：

- `simulation`：純模擬。
- `lab_real_robot`：實驗室真機測試，但仍保守。
- `production`：正式部署語意。

所以 `SYSTEM_MODE=production` 但 `APP_ENV=development` 的問題不是馬上壞掉，而是語意誤導。它會讓人以為系統已經通過正式安全檢查，但實際上仍是開發環境規則。對真機最直接的安全保護仍是 `AUTO_EXECUTE_ROBOT=false`。

## 生產設定檢查為什麼失敗

這個指令：

```powershell
.\.venv\Scripts\python.exe scripts\check_production_config.py --current --require-production
```

意思是「目前環境必須是正式 production，否則直接失敗」。目前 `APP_ENV=development`，所以它失敗是正常結果。

實驗室測試時應先跑：

```powershell
.\.venv\Scripts\python.exe scripts\check_production_config.py --current
.\.venv\Scripts\python.exe scripts\check_production_config.py --self-test
```

等要正式部署時，才把 `APP_ENV=production` 並處理所有安全條件。

## 下一步：TM Vision 測試

下一步只測影像進 Python：

```text
TMvision/EIH camera
  -> External Classification
  -> POST http://192.168.10.50:5000/api/vision/tmvision/classify?key=<VISION_TMFLOW_INGEST_KEY>
  -> Python 回 frame_received
  -> /api/vision/snapshot 看得到 EIH 畫面
```

Classification 通過後再測 Detection：

```text
POST http://192.168.10.50:5000/api/vision/tmvision/detect?key=<VISION_TMFLOW_INGEST_KEY>
```

若 TMflow 不接受空 annotations，先用：

```text
http://192.168.10.50:5000/api/vision/tmvision/detect?probe_box=1&key=<VISION_TMFLOW_INGEST_KEY>
```

## 已知風險

- 真實硬體動作尚未在這次整理中驗證。
- 完整 TMflow motion 設計目前是節點規劃，不是現場已跑通紀錄；需要照文件分段測 HOME/READY、Z 下降、吸盤、正常走子、吃子。
- Ethernet 目前你表示可以連接，但文件只把它當作「現況前提」，不再保留舊的「網路不通」結論。
- `VISION_SOURCE=tmvision_http` 在 real/shared network 下需要 `VISION_TMFLOW_INGEST_KEY`，否則設定會拒絕啟動。
- `TMFLOW_INGEST_KEY` 若有值，`9001` 的純 CSV 狀態訊息會被拒收；要嘛送 JSON 並帶 key，要嘛在實驗室暫時不設 telemetry key。
- `AUTO_EXECUTE_ROBOT` 必須保持 `false`，直到影像、Modbus、TMflow、點位、吸盤、安全高度都通過。
- TMflow 節點欄位名稱以實機 1.82.51 畫面為準；文件只保留目前專題採用的設定方向。
- 舊的大型測試樹已被移除，只保留目前能直接驗證主線的測試。若要回復完整覆蓋率，應另行建立新的分層測試基準。

## 完成條件

目前不能稱為整套真機完成。可稱為：

```text
軟體主線整理完成
文件收斂完成
目前保留測試通過
真實 TMvision / TMflow / robot commissioning 待現場驗證
```
