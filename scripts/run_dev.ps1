$ErrorActionPreference = "Stop"

function Test-SupportedPythonVersion([string]$versionText) {
  return ($versionText -match "Python 3\.(9|10|11|12)\.")
}

if (Test-Path ".\\.venv\\Scripts\\python.exe") {
  try {
    $venvVersion = (& ".\.venv\Scripts\python.exe" --version 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or (-not (Test-SupportedPythonVersion $venvVersion))) {
      throw "Existing .venv uses unsupported or broken Python ($venvVersion). Recreate it with setup_env.ps1."
    }
  } catch {
    Write-Host "[run_dev] Warning: .venv python is not functioning properly: $_" -ForegroundColor Yellow
  }
} else {
  Write-Host "Missing .venv. Creating venv with Python 3.11 preferred..." -ForegroundColor Yellow
  $created = $false
  foreach ($ver in @("3.11", "3.12", "3.10", "3.9")) {
    try {
      py -$ver -m venv .venv
      $created = $true
      break
    } catch { }
  }
  if (-not $created) {
    throw "Python 3.11 recommended, or Python 3.9, 3.10, or 3.12, was not found."
  }
}

Write-Host "Installing minimal runtime deps..." -ForegroundColor Cyan
& .\\.venv\\Scripts\\python.exe -m pip install -r requirements.runtime.txt

Write-Host "Starting server on http://127.0.0.1:5000 ..." -ForegroundColor Green
& .\\.venv\\Scripts\\python.exe main.py
