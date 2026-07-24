# 執行真實 TM5-700 機械手臂模式

真實機械手臂模式必須被視為試車/驗收（commissioning）程序，而非一般的軟體啟動。

## 必要的 TMflow 安全設定

在設定 `FAKE_ROBOT=false` 之前，請在 TMflow 或機械手臂控制器中確認以下項目：

- TCP 速度限制低於軟體設定的 `ROBOT_MAX_SPEED`。
- 力道/碰撞偵測已啟用並通過測試。
- G-Sensor/碰撞安全功能已啟用。
- 安全區域或虛擬牆設定完成，以防止機械手臂碰到人。
- 關節與工具的移動不會夾到靠近棋盤邊緣的手。
- 緊急停止按鈕（E-Stop）放置在伸手可及之處並已測試。
- 夾爪開/合的力道對於棋子與手指是安全的。
- 在進行自動移動前，已通過手動降速點動（jog）測試。

軟體座標限制只是第二層防護，並不能取代機械手臂控制器的安全功能。

## 保守的軟體預設值

專案預設值刻意為首次真實硬體測試設定了較慢的速度：

```env
ROBOT_MAX_SPEED=80
ROBOT_TRAVEL_SPEED=30
ROBOT_LIFT_SPEED=30
ROBOT_APPROACH_SPEED=15
ROBOT_DEFAULT_ACCELERATION=60
AUTO_EXECUTE_ROBOT=false
```

只有在 TMflow 安全檢查、單步移動驗證以及操作人員同意後，才能調高這些數值。

## 環境設定

設定 `.env`：

```env
SYSTEM_MODE=real_robot
FAKE_ROBOT=false
FAKE_VISION=false
FAKE_AI=false
AUTO_EXECUTE_ROBOT=false
ROBOT_ADAPTER=tmflow_json
ROBOT_IP=192.168.10.10
ROBOT_PORT=5890
ROBOT_PC_IP=192.168.10.50
ROBOT_SUBNET_MASK=255.255.0.0
ROBOT_CONNECT_TIMEOUT_SEC=3.0
TMFLOW_VERSION=1.82
TM_CONTROLLER_VERSION=1.82.51
ROBOT_TMFLOW_PROTOCOL_VERSION=1.0
ROBOT_TMFLOW_WIRE_FORMAT=envelope
ROBOT_TMFLOW_REQUIRE_HELLO=true
ROBOT_TMFLOW_ACK_TIMEOUT_SEC=2.0
ROBOT_TMFLOW_DONE_TIMEOUT_SEC=30.0
ROBOT_TMFLOW_LONG_TASK_TIMEOUT_SEC=90.0
ROBOT_TMFLOW_BASE=ChessBoard_Base
ROBOT_TMFLOW_TCP=ChessGripper_TCP
```

## TMflow TCP JSON 合約

主要的真實機械手臂通訊路徑為第二部分（Part 2）的 TMflow TCP JSON 協定。Python 作為 TCP client；TMflow 則為 socket server。每則訊息皆為以 `\n` 結尾的 UTF-8 JSON 物件。

實驗室確認後的基準設定為：

```text
PC TMflow:       1.82
Controller:      1.82.51
Robot IP:        192.168.10.10
Robot subnet:    255.255.0.0
Suggested PC IP: 192.168.10.50
Robot port:      5890
```

在進行任何實體移動前，請確認 TMflow 專案已在執行 TCP socket server 並且可以接收：

```text
HELLO
PING / PONG
GET_STATE
MOVE_L 接著 ACK -> STARTED -> DONE 或 ERROR
GRIPPER 接著 ACK -> DONE 或 ERROR
STOP
```

使用 Python 進行快速協定探測：

```powershell
.\.venv\Scripts\python.exe -c "import json,socket`ns=socket.create_connection(('192.168.10.10',5890),3)`nmsg={'version':'1.0','type':'COMMAND','id':'CMD_MANUAL_001','timestamp':'2026-07-24T00:00:00+08:00','command':'HELLO','payload':{'client':'manual_probe'}}`ns.sendall((json.dumps(msg)+'\n').encode())`nprint(s.recv(4096).decode())`ns.close()"
```

預期結果為一行具有相同 `id` 且狀態為 `DONE` 的 JSON 字串。

若要使用完整的 Part 2 JSON 封包，請設定 `ROBOT_TMFLOW_WIRE_FORMAT=envelope`。如果 TMflow 1.82 的解析無法處理巢狀 payload，請切換至 `ROBOT_TMFLOW_WIRE_FORMAT=flat_json`，並保持 RobotService / Vision / AI 的程式碼不變。

舊有的 `techmanpy` 仍可透過設定 `ROBOT_ADAPTER=techmanpy` 使用。而較舊的 Modbus 暫存器橋接則只能透過設定 `ROBOT_ADAPTER=modbus` 使用；請不要將 `502` 埠視為此實驗室設定的預設真實機械手臂連線路徑。

## 試車順序 (Commissioning Order)

1. 啟動伺服器。
2. 開啟設定頁面，並使用設定好的 `SETUP_PASSWORD` 登入。
3. 驗證相機與棋盤校正。
4. 驗證原點高度、安全高度、抓取高度與放置偏移。
5. 驗證軟體 X/Y/Z 軸限制及死區範圍。
6. 執行設定前檢查（setup preflight）。
7. 執行機械手臂連線/狀態測試。
8. 確認 TMflow TCP JSON 在 `5890` 埠回報 HELLO/PING/GET_STATE。
9. 在手臂遠離棋盤的情況下執行夾爪開/合測試。
10. 執行安全高度與原點測試。
11. 執行死區測試。
12. 淨空棋盤並安排一位操作人員在 E-Stop 旁，執行單步移動測試。
13. 只有在上述測試皆通過後，才可設定 `AUTO_EXECUTE_ROBOT=true`。

## 正式機械手臂校正點

在進行第一場真實對局前，請測量並儲存至少以下機械手臂空間座標點：

```text
a0
i0
a9
i9
e4 或 e5
dead zone slot 1 (死區插槽 1)
```

驗收標準（Acceptance criteria）：

- 棋盤上的 90 個交叉點都在 X/Y/Z 軟體限制範圍內。
- 整個死區範圍都在 X/Y 軟體限制範圍內。
- `Z_SAFE` 高度能越過最高的棋子與夾爪本體。
- `Z_GRAB` 高度能觸及棋子，且不會壓迫到棋盤。
- 重啟後能重新載入已儲存的機械手臂校正檔案與設定數值。

## 真實硬體空跑測試流程 (Dry Run Sequence)

在進行任何自動化對局之前，請執行此流程。直到最後一步通過前，請保持 `AUTO_EXECUTE_ROBOT=false`。

1. 從 Windows 端 Ping TM5-700 控制器的 IP。
2. 執行 `Test-NetConnection 192.168.10.10 -Port 5890`。
3. 使用硬體設定測試 `connect` 與 `status` 來驗證 TMflow TCP JSON 節點與狀態。
4. 只能在空跑測試時使用硬體設定測試 `write_pose`；實際未觸發點位的姿勢寫入（no-trigger pose writes）是專為 Modbus 保留的舊版測試。
5. 在 `Z_SAFE` 高度移動至棋盤上方的 a0。
6. 在 `Z_SAFE` 高度移動至 `corner_a0`、`corner_i0`、`corner_a9` 以及 `corner_i9`。
7. 在 `Z_SAFE` 高度移動至 `center_e4`。
8. 測試 e4 位置的 `grab_z`。
9. 測試 `gripper_open`（夾爪打開）與 `gripper_close`（夾爪關閉）。
10. 測試單步移動 `a0a1`。
11. 測試吃子動作，並確認棋子成功放置於死區插槽 1（dead zone slot 1）。
12. 在需要自動執行的情況下執行設定 preflight。
13. 啟用 `AUTO_EXECUTE_ROBOT=true`。

## 停止條件

若出現以下情況，請立即停止：

- 相機畫面凍結或偵測時間過舊。
- Python 無法連上 `5890` 埠，或是 TMflow 沒有回傳 ACK/DONE/ERROR JSON 格式回應。
- 手臂移動至超出校正過之棋盤/死區限制外的區域。
- 任何動作需要人工介入處理。
- 操作人員無法預測手臂的下一步動作。
