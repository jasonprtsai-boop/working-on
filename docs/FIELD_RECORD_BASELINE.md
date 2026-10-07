# 0929 至 1002 實測紀錄與專案決策

來源：使用者提供的 0929.docx、1001 進度.docx、1002.docx；本次僅讀取文字，三份皆無內嵌圖片。紀錄中的成功表示當次現場觀察，不表示 2026-10-05 已重新實測。

## 最新基準

- 0929：TMvision External Detection 用 multipart/form-data 的 file 欄位送 JPG；Python annotations 回應可顯示框。當時 AOI 存檔失敗。
- 1001：扩大 Search Range 後 AOI 存檔成功；因此不能再把 AOI 相容性當作已確認阻礙。192.168.10.x 下 Listen 失敗，Network 9001 方案當時成功。
- 1002：新網段 PC 192.168.1.99、Robot 192.168.1.200、遮罩 255.255.255.0；Listen 5890 成功，取代 1001 暫不用 Listen 的判斷。Start → Listen、DO3 開關、50 mm 正方形相對移動有現場紀錄。

## 本次修改

診斷工具預設 IP 與實機範例更新為 1002；範例保留 AUTO_EXECUTE_ROBOT=false。9001 ingest 預設停用；Start→Listen 尚未驗證退出後 Vision，因此範例停用自動 ScriptExit 拍照。RobotBase 依 1001 更新；TCP 留空待現場校正。新增離線封包測試，檢查紀錄中的回應校驗碼、UTF-8 長度及 scalar Move_Line 封包。

現行 .env 與 data/setup_settings.json 未直接套用新範例：兩者目前為 Modbus，範例的 techmanpy 不是 1002 直接 socket 實測用的程式，不能宣稱替換後等價。正式切換須完成現有 adapter 指令對照與整合測試，亦不可用範例覆蓋實機校正及認證。

## 實測界線

1002 指出 pytmrobot 的 CDP 指令失敗，直接 TMSCT 的 CPP scalar 格式成功；這不能推出現有 techmanpy 也有相同錯誤。CPP 範例描述相對移動，不能將棋盤絕對 XYZ 直接套入。DO3 可開關不代表吸附極性、真空確認或持棋停止行為已驗證。

1002 範例以 recv 一次及 sleep(2) 判斷段落結束；TCP 可能分段，OK 回覆亦不能單獨證明物理到位。整合必須保留封包完整性、命令 ID 配對、控制器完成訊號、逾時與禁止盲目重送。

1001 不使用 Homography 是當時設計決策；手動對正本身不證明鏡頭畸變與透視誤差可忽略。現有校正功能保留，應以 90 格量測誤差驗收後決定模式。Pikafish 文件稱 UCCI，但本專案已實測 uci 握手成功，因此不改為未驗證的 ucci。

## 尚未完成

直接 TMSCT 與現有 RobotService 的正式整合、绝對定位格式、完成訊號、DO3 吸放極性、拍照循環、全棋盤映射與整局驗收均未因這三份文件而自動完成。後續操作手冊以本文件日期順序判斷，歷史文件不作現行動作指引。
