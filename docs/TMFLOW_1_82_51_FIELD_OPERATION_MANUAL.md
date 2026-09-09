# TMflow 1.82.51 現場操作手冊：2026-09-02 修正版

最後修正：2026-09-02

> 現場第一線請以本文件為準；節點展開圖與完整設計文件只作工程支援。

這份手冊以目前現場已做出的節點為準。目標是先跑通「安全高度假流程」，不要同時測 Network、Listen、If 防呆、下降 Z、吸盤。

## 1. 最重要規則

只能用左側可拖曳節點：

```text
Set
Point
Move
If
Goto
Wait for
Network
Listen
Stop
```

右側工具不要當流程節點：

```text
ModbusDev
Set IO while Project Error
Set IO while Project Stop
Operation Space
Serial Port
Stop Watch
```

節點名稱能改時只輸入：

```text
A2
B11
C5
F2
```

不要輸入空格、中文、底線、括號、斜線。若 TMflow 自動顯示 `A2SET`，或 `Listen1` 暫時不能改名，以畫面位置對照即可。

變數建立時不要輸入 `var_`，例如只輸入 `status`。畫面顯示 `var_status` 是正常的。

## 2. 目前問題在哪

今天卡關主要有三個來源：

| 問題 | 現象 | 解法 |
| --- | --- | --- |
| Network | A5、B3、B5 會跳「停止專案」，但 F3 可通過 | 測 Move 時先跳過；之後照 F3 設定複製 |
| If | `active_to=1` 但 B7 不通過 | 先跳過 B6/B7/B8；主線通過後刪掉 B7 重建 |
| 測試混太多 | 通訊、防呆、Move 同時測，無法知道誰錯 | 一次只測一種：Move -> If -> Network -> 吸盤 |

目前不要再追 B7 原地打轉。因為 `active_to=1` 時 B7 本來應該通過，繼續硬改同一顆節點只會浪費時間。

## 3. 目前先用的座標

安全等待座標：

```text
X  = 363.30
Y  = 13.18
Z  = 532.27
Rx = -176.41
Ry = 0.69
Rz = 83.93
```

死棋盒 X/Y：

```text
cap_x = 124.04
cap_y = -202.49
```

死棋盒低點先記錄，暫時不要用：

```text
drop_z  = 384.54
drop_rx = 179.97
drop_ry = 1.56
drop_rz = -6.10
```

安全假流程只讓機器人在安全高度移動：

```text
Z  一律用 safe_z
Rx 一律用 safe_rx
Ry 一律用 safe_ry
Rz 一律用 safe_rz
```

## 4. 先建變數

到上方點：

```text
變數 -> 新增變數
```

新增 int：

```text
status = 0
error_code = 0
completed_cmd_id = 0
heartbeat = 0
robot_state = 0
last_cmd_id = 0
active_from = 0
active_to = 1
active_action = 0
active_cmd_id = 1
dead_slot_index = 0
```

新增 bool：

```text
flow_ok = true
has_piece = false
```

新增 double：

```text
src_x = 363.30
src_y = 13.18
dst_x = 363.30
dst_y = 13.18
cap_x = 124.04
cap_y = -202.49
safe_z = 532.27
safe_rx = -176.41
safe_ry = 0.69
safe_rz = 83.93
move_x = 363.30
move_y = 13.18
move_z = 532.27
move_rx = -176.41
move_ry = 0.69
move_rz = 83.93
```

## 5. 立即測試用接線

先把主測試線接成：

```text
Start -> A2 -> A3 -> A4 -> B1 -> B2 -> B4 -> B9 -> B10
```

也就是先不要經過：

```text
A5
Listen1
B3
B5
B6
B7
B8
F3
```

原因：

```text
A5/B3/B5/F3 是 Network，會把 Python 是否開啟混進來
Listen1 會等外部資料
B6/B7/B8 是防呆，不是測安全 Move 的必要節點
```

## 6. A 區設定

### A1 Start

保持 Start 即可。上方速度維持 `3%` 到 `5%`。

### A2 Set

點 A2 工具圖示，進入：

```text
變數
```

設定：

```text
status = 0
error_code = 0
completed_cmd_id = 0
heartbeat = 0
robot_state = 0
flow_ok = true
has_piece = false
```

### A3 Set

A3 目的：開始時關吸盤、清掉夾取狀態。

進入：

```text
變數
```

設定：

```text
has_piece = false
flow_ok = true
error_code = 0
```

如果已確認吸盤 DO 腳位，再進：

```text
數位輸出入
```

把吸盤對應 DO 設 OFF。若 DO 腳位還沒確認，不要按輸出測試。

### A4 Point

A4 設定：

```text
點位：P_READY_SAFE
速度：3% 到 5%
軌跡混合：無
```

測試版接線：

```text
A4 -> B1
```

正式版才接：

```text
A4 -> A5 -> Listen1
Listen1 Pass -> B1
```

## 7. B 區主線設定

### B1 Set

進入：

```text
變數
```

設定：

```text
heartbeat = heartbeat + 1
```

### B2 Set

設定：

```text
robot_state = 1
```

測試版接線：

```text
B2 -> B4
```

正式版中間才加回 B3 Network。

### B4 Set

B4 是目前的測試命令來源。不要同時放兩個 `active_action`。

一般搬移測試：

```text
active_from = 0
active_to = 1
active_action = 0
active_cmd_id = 1
robot_state = 2
error_code = 0
```

吃子測試時，只改同一行：

```text
active_action = 1
```

測試版接線：

```text
B4 -> B9
```

### B9 Set

B9 是座標準備，不是讀取目前座標。

設定：

```text
src_x = 363.30
src_y = 13.18
dst_x = 363.30
dst_y = 13.18
cap_x = 124.04
cap_y = -202.49
```

### B10 If

設定：

```text
var_active_action == 1
```

規則：

```text
單一
```

接線：

```text
B10 Yes/Pass -> C1
B10 No/Fail  -> B11
```

## 8. 一般搬移安全假流程

### B11 Set

先設定完整版本：

```text
move_x = src_x
move_y = src_y
move_z = safe_z
move_rx = safe_rx
move_ry = safe_ry
move_rz = safe_rz
```

如果 B11 卡住，先改成最小版本：

```text
move_x = src_x
move_y = src_y
```

因為 `move_z/move_rx/move_ry/move_rz` 已經在變數初始值設成安全姿態。

### B12 Move

Move 設定畫面：

```text
選擇座標系：工具
軌跡混合：無
```

移動設定右側選變數：

```text
X  = var_move_x
Y  = var_move_y
Z  = var_move_z
RX = var_move_rx
RY = var_move_ry
RZ = var_move_rz
```

進階設定：

```text
精準到位：打勾
```

### B13 Set

設定：

```text
move_x = dst_x
move_y = dst_y
move_z = safe_z
move_rx = safe_rx
move_ry = safe_ry
move_rz = safe_rz
```

### B14 Move

設定同 B12。

接線：

```text
B14 -> F1
```

## 9. 吃子安全假流程

### C1 Set

設定：

```text
move_x = dst_x
move_y = dst_y
move_z = safe_z
move_rx = safe_rx
move_ry = safe_ry
move_rz = safe_rz
```

### C2 Move

設定同 B12。

### C3 Set

設定：

```text
move_x = cap_x
move_y = cap_y
move_z = safe_z
move_rx = safe_rx
move_ry = safe_ry
move_rz = safe_rz
```

### C4 Move

設定同 B12。

### C5 Set

設定：

```text
dead_slot_index = dead_slot_index + 1
```

C5 後面：

```text
Goto B11
```

如果可以直接拉線到 B11，也可以直接接；如果畫面太遠或接線混亂，就放 Goto，目標選 B11。

## 10. 完成流程

### F1 Point

設定：

```text
點位：P_READY_SAFE
```

### F2 Set

設定：

```text
status = 2
error_code = 0
completed_cmd_id = active_cmd_id
robot_state = 1
```

測試版接線：

```text
F2 -> F4
```

正式版才接：

```text
F2 -> F3 -> F4
```

### F4 Wait for

設定：

```text
100 ms
```

### F5 Set

設定：

```text
status = 0
robot_state = 0
active_from = 0
active_to = 0
active_action = 0
```

F5 後面：

```text
測試版：接 Stop
正式版：Goto Listen1
```

如果接回 Listen1，停在 Listen1 等外部資料是正常的。

## 11. B7 卡關解法

目前 B7 不通過，但 B4 已設定：

```text
active_to = 1
```

所以 B7 理論上一定應通過。處理順序：

1. 先跳過 B6/B7/B8，確認假 Move 流程可以跑到 F5。
2. 假流程成功後，刪掉舊 B7。
3. 重新拖一顆 `If`。
4. 先只設定：
   ```text
   var_active_to == 1
   ```
5. 規則選：
   ```text
   單一
   ```
6. 接線：
   ```text
   B6 Yes -> B7
   B7 Yes -> B8
   B7 No -> Stop
   ```
7. 成功後才改回正式範圍：
   ```text
   var_active_to >= 0
   var_active_to <= 89
   ```
8. 規則改：
   ```text
   全部
   ```

不要在 B7 沒修好前繼續加新功能。

## 12. B6/B8 加回方式

B6：

```text
var_active_from >= 0
var_active_from <= 89
規則：全部
Yes -> B7
No -> Stop
```

B8 測試版：

```text
var_active_action >= 0
var_active_action <= 1
規則：全部
Yes -> B9
No -> Stop
```

B8 正式版：

```text
var_active_action == 0
var_active_action == 1
var_active_action == 3
規則：單一
Yes -> B9
No -> Stop 或 G1
```

## 13. Network 加回方式

安全假流程沒跑通前，不要接回 Network。

等 Python 9001 開啟後，再逐顆加回：

```text
A5
B3
B5
F3
```

每一顆都照 F3 可通過的設定複製，只改發送文字：

```text
A5: READY
B3: HB
B5: BUSY
F3: DONE
```

Network 設定共同規則：

```text
選擇裝置：ntd_PY9001
選：發送
綠色圓點選：發送內容
發送狀態：var_flow_ok
額外閒置時間：0
```

先不要用：

```text
由變數接收
變數發送
BUSY,<active_cmd_id>
DONE,<active_cmd_id>
```

先用純文字確認通訊能過。

## 14. Listen1 加回方式

正式通訊時才接：

```text
A5 -> Listen1
Listen1 Pass -> B1
```

Listen1 Fail：

```text
先接 Stop
之後錯誤流程完成後再接 G1
```

如果 Python 沒有送資料，Listen1 停住是正常的，不是 TMflow 壞掉。

## 15. 正式取放後續

安全假流程通過後，才加入真取放：

一般搬移：

```text
到來源安全高度
下降到 pick_z
吸盤 ON
等待
上升到 safe_z
到目標安全高度
下降到 place_z
吸盤 OFF
上升到 safe_z
```

吃子：

```text
到目標安全高度
下降到 pick_z
吸盤 ON
等待
上升到 safe_z
到死棋盒上方
下降到 drop_z
吸盤 OFF
上升到 safe_z
回 B11 搬來源棋
```

正式取放前必須先確認：

```text
pick_z
place_z
drop_z
吸盤 DO 腳位
吹氣 DO 腳位
棋盤每一格 X/Y
```

## 16. 建議測試順序

第一輪：一般搬移假流程

```text
B4: active_action = 0
期望：B10 No -> B11 -> B12 -> B13 -> B14 -> F1 -> F2 -> F4 -> F5
```

第二輪：吃子假流程

```text
B4: active_action = 1
期望：B10 Yes -> C1 -> C2 -> C3 -> C4 -> C5 -> B11 -> B12 -> B13 -> B14 -> F1 -> F2 -> F4 -> F5
```

第三輪：重建 If 防呆

```text
先 B7
再 B6
再 B8
```

第四輪：加回 Network

```text
先 F3
再 A5
再 B3
再 B5
```

第五輪：加回 Listen1。

第六輪：加下降 Z 和吸盤。

## 17. 驗收標準

安全假流程完成：

```text
active_action=0 可跑到 F5
active_action=1 可跑 C1-C5，再回 B11，最後跑到 F5
全程不下降 Z
全程不開吸盤
不出現停止專案
```

通訊完成：

```text
Python 9001 已開啟
A5 READY 可通過
B3 HB 可通過
B5 BUSY 可通過
F3 DONE 可通過
```

正式取放完成：

```text
來源格上方安全點正確
目標格上方安全點正確
下降高度正確
吸盤 ON/OFF 正確
死棋可落入盒子
完成後回 P_READY_SAFE
```

## 18. 已撤回舊說法

不要再使用：

```text
Modbus Read 節點
Modbus Write 節點
I/O Node
右側 ModbusDev 當流程節點
B2 是 Network 的舊表
B3 是 If 的舊表
```

目前現場版：

```text
B1 = Set heartbeat
B2 = Set robot_state
B3 = Network HB，測試版先跳過
B4 = Set 測試命令
B9 = Set 座標
B10 = If 是否吃子
```
