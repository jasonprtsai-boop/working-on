@echo off
setlocal
set "ROOT=%~dp0.."
set "NODE_HOME=%ROOT%\.tools\node-v24.18.0-win-x64"

if not exist "%NODE_HOME%\node.exe" (
  echo Missing project-local Node.js 24 at "%NODE_HOME%".
  echo Expected Node.js v24.18.0 portable zip extracted under .tools.
  exit /b 1
)

"%NODE_HOME%\node.exe" %*
exit /b %ERRORLEVEL%
