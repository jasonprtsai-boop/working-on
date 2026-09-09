param(
  [switch]$RequireHardwareReady
)

$ErrorActionPreference = "Stop"

$base = "http://127.0.0.1:5000"

function Get-LocalAdminPassword {
  if ($env:SMART_CHESS_ADMIN_PASSWORD) { return $env:SMART_CHESS_ADMIN_PASSWORD }
  if ($env:ADMIN_PASSWORD) { return $env:ADMIN_PASSWORD }

  $envPath = Join-Path (Get-Location) ".env"
  if (Test-Path $envPath) {
    $line = Get-Content $envPath | Where-Object { $_ -match "^\s*ADMIN_PASSWORD\s*=" } | Select-Object -First 1
    if ($line) {
      return (($line -split "=", 2)[1]).Trim().Trim('"').Trim("'")
    }
  }

  return "login"
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
