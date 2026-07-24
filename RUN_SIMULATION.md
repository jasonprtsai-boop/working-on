# 執行模擬模式

將專案轉移到新電腦後，必須先進行模擬模式（Simulation mode）測試。

## 環境設定

在 `.env` 中設定以下數值：

```env
SYSTEM_MODE=simulation
FAKE_ROBOT=true
FAKE_VISION=true
FAKE_AI=true
AUTO_EXECUTE_ROBOT=false
ENGINE_AUTO_ANALYZE=false
```

## 啟動

```powershell
.\.venv\Scripts\python.exe main.py
```

開啟：

- 控制台（Console）: `http://127.0.0.1:5000/`
- 儀表板（Dashboard）: `http://127.0.0.1:5000/dashboard`

## 冒煙測試 (Smoke Test)

```powershell
.\check_system.cmd
```

預期結果：

- 介面能載入，且不需要真實相機與機械手臂。
- 玩家模式會等待按下 Start（開始）按鈕。
- 機械手臂指令不會發送至硬體。
- Preflight 檢查應清楚顯示為模擬/虛擬（simulation/fake）狀態。
