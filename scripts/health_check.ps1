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

  return "888888"
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

Write-Host "GET $base/api/ready"
try { Invoke-WithRetry "$base/api/ready" 20 } catch { Write-Host "READY check failed: $($_)" -ForegroundColor Red; exit 1 }

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
try { Invoke-WithRetry "$base/api/health" 20 $headers } catch { Write-Host "HEALTH check failed: $($_)" -ForegroundColor Red; exit 1 }
