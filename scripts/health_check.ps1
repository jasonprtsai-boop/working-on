param(
  [switch]$RequireHardwareReady,
  [switch]$StartServer,
  [string]$BaseUrl = "http://127.0.0.1:5000"
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$base = $BaseUrl.TrimEnd("/")

function Get-LocalAdminPassword {
  if ($env:SMART_CHESS_ADMIN_PASSWORD) { return $env:SMART_CHESS_ADMIN_PASSWORD }
  if ($env:ADMIN_PASSWORD) { return $env:ADMIN_PASSWORD }

  $envPath = Join-Path $root ".env"
  if (Test-Path $envPath) {
    $line = Get-Content $envPath | Where-Object { $_ -match "^\s*ADMIN_PASSWORD\s*=" } | Select-Object -First 1
    if ($line) {
      return (($line -split "=", 2)[1]).Trim().Trim('"').Trim("'")
    }
  }

  return "login"
}

function Test-CommandPathExists($command) {
  if ([System.IO.Path]::IsPathRooted($command) -or $command.Contains("\") -or $command.Contains("/")) {
    return Test-Path -LiteralPath $command
  }
  return $true
}

function New-PythonCandidate($label, $command, [string[]]$prefixArgs = @()) {
  return [pscustomobject]@{
    Label = $label
    Command = $command
    PrefixArgs = $prefixArgs
  }
}

function Test-PythonCandidate($candidate) {
  if (-not (Test-CommandPathExists $candidate.Command)) {
    return [pscustomobject]@{ Ok = $false; Detail = "not found" }
  }
  $versionArgs = @($candidate.PrefixArgs) + @("--version")
  try {
    $output = (& $candidate.Command @versionArgs 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -eq 0) {
      return [pscustomobject]@{
        Label = $candidate.Label
        Command = $candidate.Command
        PrefixArgs = $candidate.PrefixArgs
        Ok = $true
        Detail = $output
      }
    }
  } catch { }
  return [pscustomobject]@{ Ok = $false; Detail = "not executable" }
}

function Resolve-ProjectPython {
  $candidates = @()
  if ($env:SMART_CHESS_PYTHON) { $candidates += New-PythonCandidate "env override" $env:SMART_CHESS_PYTHON }
  $candidates += New-PythonCandidate "project virtualenv" (Join-Path $root ".venv\Scripts\python.exe")
  foreach ($ver in @("3.11", "3.12", "3.10", "3.9")) {
    $candidates += New-PythonCandidate "Python launcher $ver" "py.exe" @("-$ver")
  }
  $candidates += New-PythonCandidate "python on PATH" "python.exe"

  foreach ($cand in $candidates) {
    $tested = Test-PythonCandidate $cand
    if ($tested.Ok) { return $tested }
  }
  throw "No usable Python runtime was found. Run setup_env.ps1 first."
}

function Test-ServerReachable {
  try {
    $response = Invoke-WebRequest -UseBasicParsing "$base/api/ready" -TimeoutSec 2
    return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300)
  } catch {
    return $false
  }
}

function Invoke-WithRetry($url, $secondsTotal = 20, $headers = $null) {
  $deadline = (Get-Date).AddSeconds($secondsTotal)
  while ((Get-Date) -lt $deadline) {
    try {
      if ($headers) {
        return (Invoke-WebRequest -UseBasicParsing $url -TimeoutSec 3 -Headers $headers).Content
      }
      return (Invoke-WebRequest -UseBasicParsing $url -TimeoutSec 3).Content
    } catch {
      Start-Sleep -Milliseconds 500
    }
  }
  throw "Timeout waiting for $url"
}

function Read-JsonPayload($content) {
  try {
    return $content | ConvertFrom-Json
  } catch {
    return $null
  }
}

function Write-ReadinessSummary($content) {
  $payload = Read-JsonPayload $content
  if ($null -eq $payload) {
    Write-Host "Hardware readiness: UNKNOWN (ready response was not JSON)" -ForegroundColor Yellow
    if ($RequireHardwareReady) { exit 1 }
    return
  }

  $ready = [bool]$payload.ready
  $robotConnected = [bool]$payload.robot_connected
  $bootstrapReady = [bool]$payload.bootstrap.ready
  if ($ready) {
    Write-Host "Hardware readiness: READY" -ForegroundColor Green
    return
  }

  Write-Host "Hardware readiness: NOT READY (ready=$ready, bootstrap=$bootstrapReady, robot_connected=$robotConnected)" -ForegroundColor Yellow
  if ($payload.bootstrap.errors) {
    $payload.bootstrap.errors | ForEach-Object {
      Write-Host "  - $($_.component): $($_.error)" -ForegroundColor Yellow
    }
  }

  if ($RequireHardwareReady) {
    Write-Host "RequireHardwareReady is enabled; failing health check." -ForegroundColor Red
    exit 1
  }
}

function Write-HealthSummary($content) {
  $payload = Read-JsonPayload $content
  if ($null -eq $payload) { return }
  if ($payload.ok -eq $false) {
    Write-Host "Health payload reports ok=false; software endpoints are reachable but readiness is degraded." -ForegroundColor Yellow
  }
}

$backendProcess = $null
try {
  $isReachable = Test-ServerReachable
  if (-not $isReachable) {
    if ($StartServer) {
      $py = Resolve-ProjectPython
      Write-Host "[health_check] Starting backend server with $($py.Label)..." -ForegroundColor Cyan
      $info = [System.Diagnostics.ProcessStartInfo]::new()
      $info.FileName = $py.Command
      $info.WorkingDirectory = $root.Path
      $info.UseShellExecute = $false
      $info.CreateNoWindow = $true
      $info.Arguments = (@($py.PrefixArgs) + @("main.py")) -join " "
      $backendProcess = [System.Diagnostics.Process]::Start($info)
      Start-Sleep -Milliseconds 1500
    } else {
      Write-Host "READY check failed: Backend server is not running on $base." -ForegroundColor Red
      Write-Host "Tip: Start the server with 'python main.py' or run with -StartServer: .\scripts\health_check.ps1 -StartServer" -ForegroundColor Yellow
      exit 1
    }
  }

  Write-Host "GET $base/api/ready"
  try {
    $readyContent = Invoke-WithRetry "$base/api/ready" 20
    Write-ReadinessSummary $readyContent
  } catch {
    Write-Host "READY check failed: $($_)" -ForegroundColor Red
    exit 1
  }

  Write-Host "POST $base/api/login"
  try {
    $loginBody = @{
      username = "admin"
      password = Get-LocalAdminPassword
    } | ConvertTo-Json
    $login = Invoke-RestMethod "$base/api/login" -Method Post -ContentType "application/json" -Body $loginBody -TimeoutSec 10
    $headers = @{ Authorization = "Bearer $($login.token)" }
  } catch {
    Write-Host "LOGIN failed: $($_)" -ForegroundColor Red
    exit 1
  }

  Write-Host "GET $base/api/health"
  try {
    $healthContent = Invoke-WithRetry "$base/api/health" 20 $headers
    Write-HealthSummary $healthContent
  } catch {
    Write-Host "HEALTH check failed: $($_)" -ForegroundColor Red
    exit 1
  }

  Write-Host "Health check completed successfully." -ForegroundColor Green
} finally {
  if ($backendProcess -and (-not $backendProcess.HasExited)) {
    Write-Host "[health_check] Stopping auto-started backend server..." -ForegroundColor Cyan
    try {
      $backendProcess.Kill($true)
      $backendProcess.WaitForExit(3000)
    } catch { }
    $backendProcess.Dispose()
  }
}

