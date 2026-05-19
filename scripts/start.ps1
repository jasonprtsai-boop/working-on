param(
  [int]$Port = 5000
)

$ErrorActionPreference = "Stop"

Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location ".."

$url = "http://127.0.0.1:$Port/"

Write-Host "[start] Opening $url"
Start-Process $url | Out-Null

Write-Host "[start] Starting backend on port $Port"
python .\main.py
