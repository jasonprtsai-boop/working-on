# 疑難排解

## PowerShell 阻擋了 .ps1 腳本的執行

部分 Windows 實驗室電腦會停用直接執行 `.ps1` 檔案的功能。請使用專案提供的包裝指令代替直接執行腳本：

```powershell
.\check_system.cmd
.\check_system_strict.cmd
```

進行設定時：

```powershell
powershell.exe -ExecutionPolicy Bypass -File setup_env.ps1
```

## Python 版本錯誤

請盡量使用 Python 3.11.9。目前尚未支援 Python 3.13。

```powershell
Remove-Item -Recurse -Force .venv
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.runtime.txt -r requirements.vision.txt
```

## 遺失 Flask 或其他 Python 套件

目前終端機可能沒有啟動 `.venv` 虛擬環境。

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe main.py
```

## 找不到 Jest

從 lockfile 重新建立 `node_modules`：

```powershell
Remove-Item -Recurse -Force node_modules
.\scripts\npm24.cmd ci
.\scripts\npm24.cmd test
```

如果仍然失敗，請檢查：

```powershell
.\scripts\node24.cmd --version
.\scripts\npm24.cmd --version
```

預期主要版本為：

- Node.js 24
- npm 11 或更新版本

## 相機畫面閃爍或凍結

請依下列順序檢查：

1. 使用供電穩定的 USB 埠或有獨立供電的 USB Hub。
2. 在 Windows 電源設定中停用 USB 選擇性暫停功能（selective suspend）。
3. 調低 `VISION_MJPEG_FPS`。
4. 調低 `VISION_MJPEG_QUALITY`。
5. 嘗試不同的 `CAMERA_INDEX`。
6. 更換相機硬體後請重啟應用程式。

## 機械手臂無法連線

請檢查：

```powershell
Test-NetConnection 192.168.10.10 -Port 5890
```

接著確認以下設定：

- `FAKE_ROBOT=false`
- `ROBOT_ADAPTER=tmflow_json`
- `ROBOT_IP=192.168.10.10`
- `ROBOT_PORT=5890`
- 電腦的 Ethernet 網路處於相同區域網路，例如 `192.168.10.50` / `255.255.0.0`，且不可與手臂 IP 重複
- TMflow TCP JSON socket server 正在執行中
- TMflow 回傳以換行符號分隔的 UTF-8 JSON 回應，且指令的 `id` 相符
- 除非 TMflow 專案要求 `flat_json`，否則應設定 `ROBOT_TMFLOW_WIRE_FORMAT=envelope`

直接探測 HELLO：

```powershell
.\.venv\Scripts\python.exe -c "import json,socket`ns=socket.create_connection(('192.168.10.10',5890),3)`nmsg={'version':'1.0','type':'COMMAND','id':'CMD_MANUAL_001','timestamp':'2026-07-24T00:00:00+08:00','command':'HELLO','payload':{'client':'manual_probe'}}`ns.sendall((json.dumps(msg)+'\n').encode())`nprint(s.recv(4096).decode())`ns.close()"
```

預期結果為一行具有 `status` 為 `DONE` 的 JSON 字串。

如果連線成功開啟但手臂無法移動，請檢查 TMflow TCP JSON 流程：

- 確認 `MOVE_L` 回傳 `ACK`，接著 `STARTED`，最後是 `DONE` 或 `ERROR`。
- 確認回應的 `id` 與請求的 `id` 一致。
- 確認請求的座標點位於 TMflow 安全限制與軟體限制的範圍內。
- 在進行實機夾取/放置測試前，請先確認 `GRIPPER` 回傳 `ACK` 接著 `DONE`。

為了相容性，保留的舊路徑包含：使用 `ROBOT_ADAPTER=techmanpy` 作為 TechmanPy External Script 用戶端，或使用 `ROBOT_ADAPTER=modbus` 以舊的暫存器橋接。使用 Modbus 時，其 `502` 埠、暫存器基底值（register base values）、指令 ACK、狀態及夾爪回饋必須與 TMflow 專案完全一致。

## 程式碼品質檢查回報 trailing_whitespace（行尾多餘空白）

執行：

```powershell
rg -n "[ \t]+$" .
```

移除行尾多餘空白後，重新執行：

```powershell
.\.venv\Scripts\python.exe scripts\quality_gate.py
git diff --check
.\check_system.cmd
```

## 真實機械手臂移動過快

保持軟體預設在較低數值：

```env
ROBOT_MAX_SPEED=80
ROBOT_TRAVEL_SPEED=30
ROBOT_LIFT_SPEED=30
ROBOT_APPROACH_SPEED=15
ROBOT_DEFAULT_ACCELERATION=60
```

並同時調低 TMflow/控制器端的 TCP 速度限制、力道限制以及安全空間設定。僅靠軟體的限制不足以確保在有操作人員環境中的安全性。
