@echo off
setlocal
set "ROOT=%~dp0.."
set "NODE_HOME=%ROOT%\.tools\node-v24.18.0-win-x64"

if not exist "%NODE_HOME%\node.exe" (
  echo Missing project-local Node.js executable at "%NODE_HOME%\node.exe".
  echo Expected Node.js v24.18.0 portable zip extracted under .tools.
  exit /b 1
)

if not exist "%NODE_HOME%\npm.cmd" (
  echo Missing project-local npm launcher at "%NODE_HOME%\npm.cmd".
  echo Expected Node.js v24.18.0 portable zip extracted under .tools.
  exit /b 1
)

set "PATH=%NODE_HOME%;%PATH%"
"%NODE_HOME%\npm.cmd" %*
exit /b %ERRORLEVEL%
