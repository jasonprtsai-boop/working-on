# S.M.A.R.T Chess Robot - Environment Setup Script (Windows PowerShell)
# Run this script from the repo root.

$ErrorActionPreference = "Stop"

Write-Host "[setup] Starting environment setup..." -ForegroundColor Cyan

function Test-IncompatiblePythonVersion([string]$versionText) {
  return ($versionText -notmatch "Python 3\.(10|11|12)\.")
}

# 1) Create or reuse venv
$needsRecreate = $false
if (Test-Path ".venv\Scripts\python.exe") {
  $venvVersion = & ".\.venv\Scripts\python.exe" --version
  if (Test-IncompatiblePythonVersion $venvVersion) {
    Write-Host "[setup] Existing .venv uses $venvVersion (incompatible with common ML wheels). Recreating..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force ".venv"
    $needsRecreate = $true
  }
} else {
  $needsRecreate = $true
}

if ($needsRecreate) {
  Write-Host "[setup] Creating .venv..." -ForegroundColor Cyan
  $created = $false

  if (Get-Command "py" -ErrorAction SilentlyContinue) {
    foreach ($ver in @("3.12", "3.11", "3.10")) {
      try {
        py -$ver -m venv .venv
        $created = $true
        break
      } catch { }
    }
  }

  if (-not $created) {
    if (-not (Get-Command "python" -ErrorAction SilentlyContinue)) {
      Write-Error "[setup] No python found. Install Python 3.10, 3.11, or 3.12 (64-bit) and retry."
      exit 1
    }
    $sysVer = & python --version
    if (Test-IncompatiblePythonVersion $sysVer) {
      Write-Error "[setup] System python is $sysVer (incompatible). Install Python 3.10, 3.11, or 3.12 (64-bit) and retry."
      exit 1
    }
    python -m venv .venv
  }

  $finalVersion = & ".\.venv\Scripts\python.exe" --version
  if (Test-IncompatiblePythonVersion $finalVersion) {
    Write-Error "[setup] Created venv uses $finalVersion (incompatible). Install Python 3.10, 3.11, or 3.12 and retry."
    exit 1
  }
}

# 2) Install deps
Write-Host "[setup] Installing python deps..." -ForegroundColor Cyan
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.runtime.txt
if (Test-Path "requirements.vision.txt") {
  Write-Host "[setup] Optional: installing vision deps..." -ForegroundColor Cyan
  & ".\.venv\Scripts\python.exe" -m pip install -r requirements.vision.txt
}

Write-Host "[setup] Installing node deps (optional)..." -ForegroundColor Cyan
if (Get-Command "npm" -ErrorAction SilentlyContinue) {
  npm install
} else {
  Write-Host "[setup] npm not found; skipping." -ForegroundColor Yellow
}

# 3) Ensure folders
Write-Host "[setup] Ensuring folders..." -ForegroundColor Cyan
$folders = @("logs", "snapshots", "reports", "backend\infrastructure\database", "backend\infrastructure\database\archive")
foreach ($folder in $folders) {
  if (-not (Test-Path $folder)) {
    New-Item -ItemType Directory -Path $folder | Out-Null
    Write-Host "  + $folder"
  }
}

# 4) Init DB
Write-Host "[setup] Initializing DB schema..." -ForegroundColor Cyan
& ".\.venv\Scripts\python.exe" -m backend.infrastructure.database.init_db

# 5) Engine check
if (-not (Test-Path "backend\infrastructure\bin\pikafish-avx2.exe")) {
  Write-Host "[setup] WARNING: pikafish-avx2.exe not found at backend/infrastructure/bin/." -ForegroundColor Yellow
} else {
  Write-Host "[setup] Engine binary detected." -ForegroundColor Green
}

Write-Host "[setup] Complete. Run: .\.venv\Scripts\python.exe .\main.py" -ForegroundColor Green
