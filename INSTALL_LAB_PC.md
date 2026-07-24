# 實驗室電腦安裝指南

請使用這份清單來設定將連接相機與 TM5-700 機械手臂的電腦。

## 安裝前準備

- 確認為 Windows 10/11 64位元系統。
- 安裝 Python 3.11.9 64位元版本。
- 安裝 Node.js 24 LTS。
- 停用相機所連接的 USB 埠的主動節能（省電）功能。
- 將實驗室電腦與機械手臂控制器連接至同一個獨立網域。
- 將電腦網路卡設定為符合機械手臂網域的 IP，例如 `192.168.10.50`，子網路遮罩 `255.255.0.0`。若現場網卡已有固定 IP，可使用同一個 `192.168.x.x` 網段且不要與手臂 IP 重複。
- 確認 TMflow 版本為 `1.82`，控制器版本為 `1.82.51`，機械手臂 IP 為 `192.168.10.10`，並且在 TCP 埠 `5890` 上開啟 TMflow TCP JSON Socket 伺服器。

## 安裝步驟

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.runtime.txt -r requirements.vision.txt
.\scripts\npm24.cmd ci
Copy-Item .env.example .env
```

為實驗室電腦編輯 `.env` 檔案：

```env
SMART_CHESS_HOST=127.0.0.1
FAKE_ROBOT=true
FAKE_VISION=false
FAKE_AI=true
AUTO_EXECUTE_ROBOT=false
CAMERA_INDEX=0
ROBOT_ADAPTER=tmflow_json
ROBOT_IP=192.168.10.10
ROBOT_PORT=5890
ROBOT_PC_IP=192.168.10.50
ROBOT_SUBNET_MASK=255.255.0.0
TMFLOW_VERSION=1.82
TM_CONTROLLER_VERSION=1.82.51
ROBOT_TMFLOW_PROTOCOL_VERSION=1.0
ROBOT_TMFLOW_WIRE_FORMAT=envelope
ROBOT_TMFLOW_REQUIRE_HELLO=true
```

首先以模擬安全模式啟動：

```powershell
.\.venv\Scripts\python.exe main.py
```

在連接真實機械手臂之前，請先執行完整的軟體檢查：

```powershell
.\check_system.cmd
```

## 首次設定流程

1. 使用密碼 `login` 登入設定頁面。
2. 選擇並驗證相機。
3. 進行棋盤視角校正。
4. 設定原點高度（origin height）、安全高度（safe Z）、抓取高度（grab Z）以及放置偏移（place offset）。
5. 設定軟體 X/Y/Z 軸限制及死區（dead-zone）範圍。
6. 執行 preflight（飛行前/操作前）檢查。
7. 只有在啟用 TMflow 安全限制與 TCP JSON Socket 伺服器後，才可執行硬體測試。
8. 只有在準備進行實機驗證時，才將 `FAKE_ROBOT=false` 啟用。
9. 只有在單步移動測試（one-move testing）成功後，才可將 `AUTO_EXECUTE_ROBOT=true` 啟用。

## 實驗室規範

請勿在共用或公開網域使用真實機械手臂模式。請將機械手臂、相機與控制電腦維持在受控的實驗室網域內。
