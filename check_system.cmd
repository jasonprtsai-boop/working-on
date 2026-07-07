@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\check_system.ps1" -SkipGitCleanCheck %*
exit /b %ERRORLEVEL%
