# TMflow 1.82.51 逐節點設定表：2026-09-02 現場修正版

> 現場操作請先看 `TMFLOW_1_82_51_FIELD_OPERATION_MANUAL.md`。本表只在需要查欄位、變數或節點內容時搭配使用。

本表只列目前中文介面左側可拖曳的流程節點。右側 `ModbusDev`、`Set IO while Project Error`、`Set IO while Project Stop` 只作設定，不列為流程節點。

## 1. 先建參數

點位：

| 名稱 | 用途 |
| --- | --- |
| `P_READY_SAFE` | 必填。安全等待點、回家點、假流程測試高度。 |

狀態與命令：

| 名稱 | 型態 | 初始值 |
| --- | --- | --- |
| `status` | int | `0` |
| `error_code` | int | `0` |
| `completed_cmd_id` | int | `0` |
| `heartbeat` | int | `0` |
| `robot_state` | int | `0` |
| `last_cmd_id` | int | `0` |
| `active_from` | int | `0` |
| `active_to` | int | `1` |
| `active_action` | int | `0` |
| `active_cmd_id` | int | `1` |
| `dead_slot_index` | int | `0` |

旗標：

| 名稱 | 型態 | 初始值 |
| --- | --- | --- |
| `flow_ok` | bool | `true` |
| `has_piece` | bool | `false` |

座標：

| 名稱 | 型態 | 初始值 |
| --- | --- | --- |
| `src_x` | double | `363.30` |
| `src_y` | double | `13.18` |
| `dst_x` | double | `363.30` |
| `dst_y` | double | `13.18` |
| `cap_x` | double | `124.04` |
| `cap_y` | double | `-202.49` |
| `safe_z` | double | `532.27` |
| `safe_rx` | double | `-176.41` |
| `safe_ry` | double | `0.69` |
| `safe_rz` | double | `83.93` |
| `move_x` | double | `363.30` |
| `move_y` | double | `13.18` |
| `move_z` | double | `532.27` |
| `move_rx` | double | `-176.41` |
| `move_ry` | double | `0.69` |
| `move_rz` | double | `83.93` |

## 2. 安全假流程主線

測試時先用這條，先不要接 Network、Listen、防呆 If：

```text
Start -> A2 -> A3 -> A4 -> B1 -> B2 -> B4 -> B9 -> B10
```

| 代號 | 節點 | 主要設定 | 下一步 |
| --- | --- | --- | --- |
| A1 | Start | 專案入口；速度 3%～5%；不要開運動不間斷 | A2 |
| A2 | Set | `status=0,error_code=0,completed_cmd_id=0,heartbeat=0,robot_state=0,flow_ok=true,has_piece=false` | A3 |
| A3 | Set | `has_piece=false`；若 DO 腳位已確認，數位輸出吸盤 OFF | A4 |
| A4 | Point | `P_READY_SAFE`；低速；軌跡混合選無 | B1 |
| B1 | Set | `heartbeat=heartbeat+1` | B2 |
| B2 | Set | `robot_state=1` | B4 |
| B4 | Set | `active_from=0,active_to=1,active_action=0,active_cmd_id=1,robot_state=2,error_code=0` | B9 |
| B9 | Set | `src_x=363.30,src_y=13.18,dst_x=363.30,dst_y=13.18,cap_x=124.04,cap_y=-202.49` | B10 |
| B10 | If | `var_active_action == 1` | Yes 到 C1；No 到 B11 |

## 3. 一般搬移安全假流程

這段只移動到安全高度，不下降 Z，不開吸盤。

| 代號 | 節點 | 主要設定 | 下一步 |
| --- | --- | --- | --- |
| B11 | Set | `move_x=src_x,move_y=src_y,move_z=safe_z,move_rx=safe_rx,move_ry=safe_ry,move_rz=safe_rz` | B12 |
| B12 | Move | 座標系選工具；X/Y/Z/RX/RY/RZ 都選 `var_move_*`；軌跡混合無；精準到位 | B13 |
| B13 | Set | `move_x=dst_x,move_y=dst_y,move_z=safe_z,move_rx=safe_rx,move_ry=safe_ry,move_rz=safe_rz` | B14 |
| B14 | Move | 同 B12 設定 | F1 |

若 B11 仍卡住，先改成只留：

```text
move_x = src_x
move_y = src_y
```

其餘 `move_z/move_rx/move_ry/move_rz` 靠變數初始值。

## 4. 吃子安全假流程

這段只驗證路線：到目標格安全高度，再到死棋盒安全高度，最後回一般搬移流程。

| 代號 | 節點 | 主要設定 | 下一步 |
| --- | --- | --- | --- |
| C1 | Set | `move_x=dst_x,move_y=dst_y,move_z=safe_z,move_rx=safe_rx,move_ry=safe_ry,move_rz=safe_rz` | C2 |
| C2 | Move | 同 B12 設定 | C3 |
| C3 | Set | `move_x=cap_x,move_y=cap_y,move_z=safe_z,move_rx=safe_rx,move_ry=safe_ry,move_rz=safe_rz` | C4 |
| C4 | Move | 同 B12 設定 | C5 |
| C5 | Set | `dead_slot_index=dead_slot_index+1` | Goto B11 |

如果 C5 不能直接拉線回 B11，就放一顆 `Goto`，目標選 B11。畫面可能會顯示目標名稱 `B11`。

## 5. 完成流程

| 代號 | 節點 | 主要設定 | 測試版下一步 |
| --- | --- | --- | --- |
| F1 | Point | 回 `P_READY_SAFE` | F2 |
| F2 | Set | `status=2,error_code=0,completed_cmd_id=active_cmd_id,robot_state=1` | F4 |
| F3 | Network | 正式送 `DONE`；測試版先跳過 | F4 |
| F4 | Wait for | `100 ms` | F5 |
| F5 | Set | `status=0,robot_state=0,active_from=0,active_to=0,active_action=0` | Goto Listen1 或 Stop |

安全假流程測試時，若不想回到 Listen1 等資料，F5 後面可以先接一顆 `Stop`。正式版再改成回 Listen1。

## 6. 先跳過的節點

| 代號 | 節點 | 先跳過原因 | 加回條件 |
| --- | --- | --- | --- |
| A5 | Network | 沒開 Python 或設定不同時會停止專案 | Python 9001 開啟後 |
| Listen1 | Listen | 沒外部資料會等待 | Python 能送命令後 |
| B3 | Network | 目前可能會停止專案 | 照 F3 設定複製後 |
| B5 | Network | 目前可能會停止專案 | 照 F3 設定複製後 |
| B6 | If | 防呆檢查，非假流程必要 | 主線跑通後 |
| B7 | If | 今日卡關點 | 刪掉重建後 |
| B8 | If | action 防呆，非假流程必要 | B6/B7 通過後 |
| F3 | Network | 測試 Move 時不測通訊 | A5/B3/B5 都通過後 |

## 7. B6/B7/B8 加回設定

B6：

```text
var_active_from >= 0
var_active_from <= 89
規則：全部
Yes -> B7
No -> Stop 或 G1
```

B7 先重建成最小測試版：

```text
var_active_to == 1
規則：單一
Yes -> B8
No -> Stop 或 G1
```

B7 通過後再改正式版：

```text
var_active_to >= 0
var_active_to <= 89
規則：全部
```

B8 測試版：

```text
var_active_action >= 0
var_active_action <= 1
規則：全部
Yes -> B9
No -> Stop 或 G1
```

B8 正式版可改：

```text
var_active_action == 0
var_active_action == 1
var_active_action == 3
規則：單一
```

## 8. Network 加回設定

全部 Network 先使用純文字，不串變數：

| 代號 | 送出內容 |
| --- | --- |
| A5 | `READY` |
| B3 | `HB` |
| B5 | `BUSY` |
| F3 | `DONE` |
| G3 | `ERR` |

共同設定：

```text
選擇裝置：ntd_PY9001
模式：發送
綠色圓點：發送內容
發送狀態：var_flow_ok
額外閒置時間：0
```

## 9. 正式取放後續節點

安全假流程通過後，才新增以下真動作：

| 區段 | 後續新增內容 |
| --- | --- |
| 吃子 | 下降到死棋 pickup 高度、吸盤 ON、上升、到死棋盒、下降到 drop_z、吸盤 OFF |
| 一般搬移 | 下降到來源 pickup 高度、吸盤 ON、上升、到目標、下降到 place_z、吸盤 OFF |
| 錯誤流程 | G1 Set 錯誤狀態、G2 關吸盤、G3 送 ERR、G4 判斷 fault、G5 回安全點、G6 Stop/Goto |

正式取放前必須先確認：

```text
pick_z
place_z
drop_z
吸盤 DO 腳位
吹氣 DO 腳位
```

## 10. 驗收標準

安全假流程：

```text
active_action=0 可跑到 F5
active_action=1 可跑 C1-C5，再回 B11，最後跑到 F5
全程不下降 Z
全程不開吸盤
不出現停止專案
```

通訊：

```text
Python 9001 已開啟
A5 READY 可通過
B3 HB 可通過
B5 BUSY 可通過
F3 DONE 可通過
```

正式取放：

```text
來源格上方安全點正確
目標格上方安全點正確
下降高度正確
吸盤 ON/OFF 正確
死棋可落入盒子
完成後回 P_READY_SAFE
```
