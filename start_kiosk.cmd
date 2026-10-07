@echo off
setlocal enabledelayedexpansion
title Smart Chess Robot - Kiosk Launcher
chcp 65001 >nul
cd /d "%~dp0"

echo ===================================================
echo   智慧西洋/象棋機械手臂系統 - 展演全螢幕啟動器
echo ===================================================
echo.

:: 1. 偵測 Python 執行環境
set "PYTHON_CMD="
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_CMD=%~dp0.venv\Scripts\python.exe"
) else (
    where py.exe >nul 2>nul
    if !ERRORLEVEL! EQU 0 (
        py.exe -3.10 --version >nul 2>nul
        if !ERRORLEVEL! EQU 0 (
            set "PYTHON_CMD=py.exe -3.10"
        ) else (
            set "PYTHON_CMD=py.exe"
        )
    ) else (
        set "PYTHON_CMD=python.exe"
    )
)

echo [*] Python 執行環境: !PYTHON_CMD!

:: 2. 檢查伺服器是否已在運行
powershell -NoProfile -Command "try { $res = Invoke-WebRequest -Uri 'http://127.0.0.1:5000/api/ready' -UseBasicParsing -TimeoutSec 2; if ($res.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>nul
if !ERRORLEVEL! EQU 0 (
    echo [*] 後端伺服器已在運行中 (http://127.0.0.1:5000)
    goto LAUNCH_BROWSER
)

:: 3. 啟動後端主程序
echo [*] 正在背景啟動主系統 (main.py)...
start "Smart Chess Robot Backend" /min !PYTHON_CMD! main.py

echo [*] 等待後端服務就緒 (最多等待 25 秒)...
set "READY=0"
for /L %%i in (1,1,25) do (
    powershell -NoProfile -Command "try { $res = Invoke-WebRequest -Uri 'http://127.0.0.1:5000/api/ready' -UseBasicParsing -TimeoutSec 2; if ($res.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>nul
    if !ERRORLEVEL! EQU 0 (
        set "READY=1"
        goto SERVER_ONLINE
    )
    timeout /t 1 /nobreak >nul
)

:SERVER_ONLINE
if "!READY!"=="0" (
    echo [!] 伺服器啟動逾時，請檢查 main.py 或記錄檔。
) else (
    echo [v] 後端伺服器已就緒！
)

:LAUNCH_BROWSER
:: 4. 偵測 Chrome 或 Edge 瀏覽器
set "BROWSER_BIN="

if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" (
    set "BROWSER_BIN=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
) else if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" (
    set "BROWSER_BIN=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
) else if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" (
    set "BROWSER_BIN=%LocalAppData%\Google\Chrome\Application\chrome.exe"
) else if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" (
    set "BROWSER_BIN=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
) else if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" (
    set "BROWSER_BIN=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
)

if defined BROWSER_BIN (
    echo [*] 使用應用程式模式啟動: !BROWSER_BIN!
    start "" "!BROWSER_BIN!" --app=http://127.0.0.1:5000/ --start-maximized
) else (
    echo [*] 未找到 Chrome 或 Edge，使用系統預設瀏覽器開啟...
    start http://127.0.0.1:5000/
)

echo.
echo ===================================================
echo   展演介面已開啟完成。按任意鍵關閉此啟動視窗...
echo ===================================================
timeout /t 5 >nul
exit /b 0
