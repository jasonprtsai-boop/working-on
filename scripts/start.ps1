param(
  [int]$Port = 5000
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root

$pythonExe = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
  if (Get-Command "python" -ErrorAction SilentlyContinue) {
    $pythonExe = "python"
  } else {
    Write-Host "[start] Virtualenv not found at .venv. Please run setup_env.ps1 first." -ForegroundColor Red
    exit 1
  }
}

$url = "http://127.0.0.1:$Port/"
$env:PORT = "$Port"

Write-Host "[start] Opening $url"
Start-Process $url | Out-Null

Write-Host "[start] Starting backend on port $Port using $pythonExe"
& $pythonExe .\main.py

