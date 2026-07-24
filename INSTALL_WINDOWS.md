# Windows 安裝指南

這是針對一般 Windows 測試電腦的建議設定。

## 支援版本

- Windows 10/11 64位元
- 實驗室電腦建議使用 Python 3.11.9
- 支援 Python 3.9、3.10、3.11 與 3.12
- 本專案目前尚未支援 Python 3.13
- 建議使用 Node.js 24 LTS
- npm 11 或更新版本

## 全新安裝

請在專案根目錄的 PowerShell 中執行以下指令：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.runtime.txt -r requirements.vision.txt
.\scripts\npm24.cmd ci
Copy-Item .env.example .env
.\.venv\Scripts\python.exe main.py
```

開啟 `http://127.0.0.1:5000/`。

## 安裝輔助腳本

此輔助腳本會建立 `.venv`、安裝 Python 依賴套件，若系統中有 npm 則會一併安裝 Node 依賴套件、初始化資料夾，並檢查受保護資產（protected assets）：

```powershell
powershell.exe -ExecutionPolicy Bypass -File setup_env.ps1
```

## Node 重設

當將資料夾複製到其他電腦，導致 Jest 或 `node_modules` 變得不一致時，請使用此方式：

```powershell
Remove-Item -Recurse -Force node_modules
.\scripts\npm24.cmd ci
.\scripts\npm24.cmd test
```

請保留 `package-lock.json`。它是可重製依賴套件的基準（baseline）。

## Python 重設

當虛擬環境（venv）由錯誤的 Python 版本建立時，請使用此方式：

```powershell
Remove-Item -Recurse -Force .venv
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.runtime.txt -r requirements.vision.txt
```

## 驗證

```powershell
.\check_system.cmd
```

在打包發佈版或是將專案作為穩定版本複製前，請使用 `.\check_system_strict.cmd`。這些包裝腳本會使用 `-ExecutionPolicy Bypass` 來呼叫 PowerShell，這可以避免實驗室電腦因為本機腳本執行被停用而發生錯誤。
