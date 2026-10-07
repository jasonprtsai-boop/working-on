# TM5-700 整局驗收：初步就緒檢查

日期：2026-10-05。驗收目標：實機完成一整局，包含正常走子、吃子、回合辨識、終局及異常停止。此文件是初步阻礙盤點，不是完整產品稽核結果。

更新：收到 0929、1001、1002 文件後確認，下面 192.168.10.10 的逾時檢查使用了舊地址，不能判定目前 192.168.1.200 的連線狀態。10/02 有 Listen、DO3 與相對移動成功紀錄；最新基準及未驗證界線見 FIELD_RECORD_BASELINE.md。整局仍未驗收。

## 結論

Status: NOT READY。尚無本次實機整局證據。不評分，因主要硬體流程未連通。

## 已確認問題

| 嚴重度／信心 | 證據與位置 | 影響與下一步 |
| --- | --- | --- |
| HIGH / CONFIRMED | .tools/python-3.10.11 執行 EngineService import 時缺 yaml；模組檢查亦缺 flask、numpy、cv2、ultralytics、techmanpy、pyModbusTCP | 該 Python 不能啟動後端。建立專案環境並安装 requirements.runtime.txt 與 requirements.vision.txt，再跑後端測試。 |
| HIGH / CONFIRMED | 不受沙箱限制的 TCP 檢查：127.0.0.1:5000、192.168.10.10:5890、192.168.10.10:502 均在 2 秒內逾時 | 本次無法連通網站或上述手臂服務；原因仍未知，不能據此推論手臂故障。核對 PC IP、實體網路、控制器狀態與服務。 |
| HIGH / CONFIRMED（差異）；UNKNOWN（現場正確設定） | README 指定 Python 全座標／DO3、Listen→Vision→Listen；.env 與 setup_settings.json 選 modbus/server/square_command | 不得僅依文件改切 adapter。讀取現場 TMflow 匯出與 operator 確認後統一通道。 |
| HIGH / CONFIRMED | data/commissioning_report.json 頂層 ok=true，但其 preflight.ok=false；settings_saved 快照為 fake_robot=true | 歷史報告不是本次真機整局通過證據；需重新取得即時 preflight 與分段測試紀錄。 |

## 已驗證與保留

- Pikafish 與 NNUE 經 UCI 實測，成功載入模型，深度 2 回傳 bestmove c3c4。
- 模型大小與 SHA256 符合受保護清單；原壓縮包及 Pikafish 副本保留。
- AUTO_EXECUTE_ROBOT=false 保持原值。本次未送出移動、吸放、ScriptExit 或控制器流程啟動指令。

## 未知與分段驗收

未知：現場是否有人值守、實體急停是否可用、TMflow 實際節點、Base/TCP、DO3 極性、棋盤／棄子區校正、目前姿態及障礙物。

依序完成：環境及軟體測試 → 通道與新鮮影像 → operator 確認安全條件 → 空載低速點位 → 單顆吸放 → 正常走子 → 吃子 → 人機連續回合 → 終局 → 一整局驗收。每階段保存實際命令、結果、影像與錯誤紀錄；前段失敗不能跳到整局。

整局成功條件：每一回合使用新鮮影像；合法走法與手臂結果一致；吃子後棋盤與棄子區一致；終局停止發送命令；沒有已知重大安全或狀態回歸。模擬／單元測試通過不能代替實機證據。
