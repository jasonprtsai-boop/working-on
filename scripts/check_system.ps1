param(
  [switch]$SkipGitCleanCheck,
  [switch]$SkipRuntimeSmoke
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$python = Join-Path $root ".venv\Scripts\python.exe"
$baseUrl = "http://127.0.0.1:5000"
$gitSafeDirectory = ($root.Path -replace "\\", "/")

Set-Location $root

function Invoke-Step($name, $scriptBlock) {
  Write-Host ""
  Write-Host "== $name =="
  & $scriptBlock
}

function Invoke-Git {
  & git -c "safe.directory=$gitSafeDirectory" @args
}

function Assert-CommandSucceeded($exitCode, $name) {
  if ($exitCode -ne 0) {
    throw "$name failed with exit code $exitCode"
  }
}

function Test-ServerReachable {
  try {
    $response = Invoke-WebRequest -UseBasicParsing "$baseUrl/api/ready" -TimeoutSec 2
    return $response.StatusCode -eq 200
  } catch {
    return $false
  }
}

function Wait-ServerReady($secondsTotal = 40) {
  $deadline = (Get-Date).AddSeconds($secondsTotal)
  while ((Get-Date) -lt $deadline) {
    if (Test-ServerReachable) {
      Write-Host "Server ready at $baseUrl"
      return
    }
    Start-Sleep -Milliseconds 500
  }
  throw "Timeout waiting for $baseUrl/api/ready"
}

function Start-BackendProcess {
  $info = [System.Diagnostics.ProcessStartInfo]::new()
  $info.FileName = $python
  $info.WorkingDirectory = $root.Path
  $info.UseShellExecute = $false
  $info.CreateNoWindow = $true
  $info.Arguments = "main.py"

  $keys = @($info.Environment.Keys)
  if (($keys -contains "Path") -and ($keys -contains "PATH")) {
    [void]$info.Environment.Remove("PATH")
  }

  $process = [System.Diagnostics.Process]::new()
  $process.StartInfo = $info
  [void]$process.Start()
  return $process
}

function Stop-BackendProcess($process) {
  if ($null -eq $process) {
    return
  }
  if (-not $process.HasExited) {
    $process.Kill()
    $process.WaitForExit(8000)
  }
  $process.Dispose()
}

if (-not (Test-Path $python)) {
  throw "Missing Python virtualenv at $python"
}

if (-not $SkipGitCleanCheck) {
  Invoke-Step "Git status" {
    $status = Invoke-Git status --short --branch
    $status | ForEach-Object { Write-Host $_ }
    $dirty = $status | Where-Object { $_ -notmatch "^## " }
    if ($dirty) {
      throw "Git working tree is not clean. Review git status before running full system check."
    }
  }
}

Invoke-Step "Git diff hygiene" {
  Invoke-Git diff --check
  Assert-CommandSucceeded $LASTEXITCODE "git diff --check"
}

Invoke-Step "Git tracked-file safety" {
  $blockedPattern = '(^|/)(\.env|\.venv|node_modules|logs|data|reports|analysis_artifacts)(/|$)|\.db$|\.log$|\.xlsx$|\.nnue$|\.pt$|\.exe$|backend/infrastructure/vision/models/'
  $blocked = Invoke-Git ls-files | Where-Object { $_ -match $blockedPattern }
  if ($blocked) {
    $blocked | ForEach-Object { Write-Host "Blocked tracked file: $_" -ForegroundColor Red }
    throw "Tracked-file safety check failed."
  }
  Write-Host "Tracked-file safety check passed."
}

Invoke-Step "Quality gate" {
  & npm.cmd run quality
  Assert-CommandSucceeded $LASTEXITCODE "npm.cmd run quality"
}

Invoke-Step "System diagnostic" {
  & $python scripts\system_diagnostic.py
  Assert-CommandSucceeded $LASTEXITCODE "system diagnostic"
}

if (-not $SkipRuntimeSmoke) {
  Invoke-Step "Runtime smoke" {
    $startedHere = $false
    $backendProcess = $null
    try {
      if (-not (Test-ServerReachable)) {
        $backendProcess = Start-BackendProcess
        $startedHere = $true
      }
      Wait-ServerReady 40

      & powershell.exe -ExecutionPolicy Bypass -File scripts\health_check.ps1
      Assert-CommandSucceeded $LASTEXITCODE "health check"

      & $python scripts\test\smoke_test.py
      Assert-CommandSucceeded $LASTEXITCODE "HTTP smoke"

      & npm.cmd run smoke:frontend
      Assert-CommandSucceeded $LASTEXITCODE "frontend smoke"
    } finally {
      if ($startedHere) {
        Stop-BackendProcess $backendProcess
      }
    }
  }
}

Write-Host ""
Write-Host "System check completed successfully."
