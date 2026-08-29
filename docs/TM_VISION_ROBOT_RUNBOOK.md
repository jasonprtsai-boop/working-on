# TM Vision And Robot Runbook

本文件是後續現場測 TMvision/EIH 與 TMflow/TM5-700 的主線。不要同時測影像、Modbus、pose、手臂動作；每次只驗證一條資料有沒有到下一層。

## 0. 現場前提

目前你表示 Ethernet 可以連接到，文件因此不再保留「網路不通」作為現況結論。仍需在每次測試前確認：

```text
PC Ethernet IP = 192.168.10.50
Robot IP       = 192.168.10.10
Subnet mask    = 255.255.0.0
Flask          = 0.0.0.0:5000
TMflow ingest  = 0.0.0.0:9001
Modbus server  = 192.168.10.50:1502
```

Windows 防火牆需允許：

```text
5000  HTTP from TMvision/TMflow to Python
9001  TMflow Network Node telemetry/status to Python
1502  TMflow Modbus client/master to Python Modbus server
```

## 1. 啟動 Python

實驗室真機測試建議從 `.env.tmflow-real.example` 複製必要值，但先保持：

```env
APP_ENV=development
SYSTEM_MODE=lab_real_robot
AUTO_EXECUTE_ROBOT=false
```

啟動：

```powershell
.\.venv\Scripts\python.exe main.py
```

確認：

```text
http://192.168.10.50:5000/api/ready
```

若 TMflow 要從 robot 網段 POST 影像，Flask 不能只綁 `127.0.0.1`，必須使用：

```env
SMART_CHESS_BIND_ALL=1
SMART_CHESS_HOST=0.0.0.0
```

## 2. 只測 TMvision Classification

先不要接 YOLO，不要接手臂動作。目標只是證明 EIH 影像到 Python。

TMvision / TMflow Vision node：

```text
Function: External Classification
Method: POST
URL: http://192.168.10.50:5000/api/vision/tmvision/classify
Image source: EIH / built-in camera
Image format: jpg
Form field: file first, if needed try image
Timeout: 3000-5000 ms
```

成功回應：

```json
{
  "message": "success",
  "result": "frame_received",
  "score": 1.0
}
```

接著在 PC 看 snapshot：

```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:5000/api/vision/snapshot" -OutFile "C:\tmp\tmvision_snapshot.jpg"
```

成功條件：

```text
C:\tmp\tmvision_snapshot.jpg 存在
檔案大小大於 0
影像內容是 EIH 相機畫面
```

若 HTTP 413 或 `image_too_large`，調高：

```env
MAX_REQUEST_BYTES=4194304
VISION_TMFLOW_IMAGE_MAX_MESSAGE_BYTES=4194304
```

## 3. 只測 TMvision Detection Parser

Classification 成功後，再測：

```text
Function: External Detection
URL: http://192.168.10.50:5000/api/vision/tmvision/detect
```

成功回應會有：

```json
{
  "message": "success",
  "annotations": []
}
```

若 TMflow 不接受空 annotations，用：

```text
http://192.168.10.50:5000/api/vision/tmvision/detect?probe_box=1
```

這會回一個測試框，用來證明 TMflow 的 detection JSON parser 正常。這一步通過後才開始看 YOLO 結果。

## 4. 只測 TMflow Network Node

目標：TMflow 能把 heartbeat、pose、BUSY、DONE、ERR 送進 Python `9001`。

Network Device：

```text
Device IP: 192.168.10.50
Device port: 9001
Mode: Send
```

建議測試訊息：

```text
"HB," + GetString(heartbeat) + Ctrl("\r\n")
"BUSY," + GetString(cmd_id) + Ctrl("\r\n")
"DONE," + GetString(cmd_id) + Ctrl("\r\n")
"ERR," + GetString(cmd_id) + "," + GetString(error_code) + Ctrl("\r\n")
"CoordBase," + GetString(Robot[0].CoordBase, ",") + Ctrl("\r\n")
```

TMflow 1.82 若不接受 `Ctrl("\r\n")`，改用畫面內建 newline。不要輸入普通字串 `var_tcp_x` 期待它變成座標；那只會送出文字。

成功條件：

```text
/api/robot/status 看得到 telemetry/status/pose
heartbeat 有變化
pose 不是 stale
```

## 5. 只測 Modbus Square Command

主方案：

```text
Python PC = Modbus TCP server
TMflow    = Modbus client/master
```

PC 端設定：

```env
ROBOT_ADAPTER=modbus
ROBOT_MODBUS_ROLE=server
ROBOT_MODBUS_SERVER_HOST=192.168.10.50
ROBOT_MODBUS_SERVER_PORT=1502
ROBOT_MODBUS_PAYLOAD_MODE=square_command
ROBOT_MODBUS_REGISTER_ADDRESSING=holding_40001
```

Register map：

| Register | 變數 | 說明 |
| ---: | --- | --- |
| 40001 | `from_square` | 來源格 0..89 |
| 40002 | `to_square` | 目標格 0..89 |
| 40003 | `action_type` | `0=move`, `1=capture`, `3=special` |
| 40004 | `cmd_id` | 命令編號 |
| 40005 | `trigger` | `1=執行`, `0=清除` |
| 40006 | `status` | `0=Idle`, `1=Busy`, `2=Done`, `3=Error`, `4=Fault` |
| 40007 | `error_code` | 錯誤碼 |
| 40008 | `completed_cmd_id` | 完成命令 |
| 40009 | `heartbeat` | 心跳 |
| 40010 | `robot_state` | 手臂狀態摘要 |

先用獨立測試 server：

```powershell
.\.venv\Scripts\python.exe scripts\start_modbus_square_server.py --host 192.168.10.50 --port 1502 --watch
```

成功條件：

```text
TMflow 讀到 trigger=1
TMflow 寫回 status=1 Busy
TMflow 寫回 status=2 Done
completed_cmd_id 等於 cmd_id
Python 清 trigger=0
下一筆 cmd_id 可以再次觸發
```

## 6. TMflow 最小主流程

主 PollLoop 只做命令輪詢、動作、狀態回報：

```text
Init
  -> Write heartbeat/status
  -> Read from/to/action/cmd_id/trigger
  -> if trigger and new cmd_id: Busy
  -> validate from_square/to_square/action_type
  -> capture target if action_type=1
  -> move source to target
  -> Done
  -> wait trigger clear
  -> Idle
```

不要放進主 PollLoop：

```text
Vision node
Python /api/ready
port 探針
棋規 / FEN / AI
Listen Node 5890
高頻影像串流
軟體 pause flow
```

## 7. 真機動作前安全檢查

在任何自動移動前，必須完成：

- TM 控制器速度限制。
- 力道/碰撞偵測。
- 安全區域或虛擬牆。
- 實體急停可用且有人在旁。
- `Z_SAFE` 高於棋子與夾具。
- `Z_GRAB` 不會壓壞棋盤。
- 棋盤四角、中心、dead zone 都教點完成。
- 吸盤 DO 腳位已確認。

第一輪只測：

```text
P_square_0_SAFE
P_square_8_SAFE
P_square_40_SAFE
P_square_81_SAFE
P_square_89_SAFE
P_dead_1_SAFE
```

安全點通過後才測吸盤與單顆棋子的 pick/place。

## 8. 啟用自動執行前完成條件

全部通過後，才考慮 `AUTO_EXECUTE_ROBOT=true`：

```text
TMvision Classification -> Python snapshot 成功
TMvision Detection parser 成功
YOLO annotations 能對應棋盤
TMflow Network heartbeat/status/pose 成功
Modbus square-command trigger/status/completed_cmd_id 成功
安全點 motion 成功
吸盤 ON/OFF 成功
單步 pick/place 成功
吃子 dead-zone 成功
```

任何一項失敗，不要開自動下棋。
