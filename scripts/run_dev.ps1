$ErrorActionPreference = "Stop"

function Test-SupportedPythonVersion([string]$versionText) {
  return ($versionText -match "Python 3\.(10|11|12)\.")
}

if (Test-Path ".\\.venv\\Scripts\\python.exe") {
  $venvVersion = & .\\.venv\\Scripts\\python.exe --version
  if (-not (Test-SupportedPythonVersion $venvVersion)) {
    throw "Existing .venv uses $venvVersion. Recreate it with Python 3.10, 3.11, or 3.12."
  }
} else {
  Write-Host "Missing .venv. Creating venv with Python 3.10+..." -ForegroundColor Yellow
  $created = $false
  foreach ($ver in @("3.12", "3.11", "3.10")) {
    try {
      py -$ver -m venv .venv
      $created = $true
      break
    } catch { }
  }
  if (-not $created) {
    throw "Python 3.10+ was not found. Install Python 3.10, 3.11, or 3.12 and retry."
  }
}

Write-Host "Installing minimal runtime deps..." -ForegroundColor Cyan
& .\\.venv\\Scripts\\python.exe -m pip install -r requirements.runtime.txt

Write-Host "Starting server on http://127.0.0.1:5000 ..." -ForegroundColor Green
& .\\.venv\\Scripts\\python.exe main.py
