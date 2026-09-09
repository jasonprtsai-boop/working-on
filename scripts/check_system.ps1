param(
  [switch]$SkipGitCleanCheck,
  [switch]$SkipRuntimeSmoke,
  [switch]$SkipHtmlFunctionCheck,
  [switch]$RequireHardwareReady
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$nodeHome = Join-Path $root ".tools\node-v24.18.0-win-x64"
$baseUrl = "http://127.0.0.1:5000"
$gitSafeDirectory = ($root.Path -replace "\\", "/")

Set-Location $root

if (Test-Path (Join-Path $nodeHome "node.exe")) {
  $env:Path = "$nodeHome;$env:Path"
}

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
    return [pscustomobject]@{
      Label = $candidate.Label
      Command = $candidate.Command
      PrefixArgs = $candidate.PrefixArgs
      Ok = $false
      Detail = "not found"
    }
  }

  $versionArgs = @($candidate.PrefixArgs) + @("--version")
  $output = ""
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
  } catch {
    $output = $_.Exception.Message
  }

  return [pscustomobject]@{
    Label = $candidate.Label
    Command = $candidate.Command
    PrefixArgs = $candidate.PrefixArgs
    Ok = $false
    Detail = $(if ($output) { $output } else { "not executable" })
  }
}

function Resolve-ProjectPython {
  $candidates = @()
  $envPython = $env:SMART_CHESS_PYTHON
  if (-not $envPython) {
    $envPython = $env:PYTHON_EXE
  }
  if ($envPython) {
    $candidates += New-PythonCandidate "environment override" $envPython
  }
  $candidates += New-PythonCandidate "project virtualenv" (Join-Path $root ".venv\Scripts\python.exe")
  foreach ($version in @("3.11", "3.12", "3.10", "3.9")) {
    $candidates += New-PythonCandidate "Python launcher $version" "py.exe" @("-$version")
  }
  $candidates += New-PythonCandidate "python on PATH" "python.exe"

  $attempts = @()
  foreach ($candidate in $candidates) {
    $attempt = Test-PythonCandidate $candidate
    $attempts += $attempt
    if ($attempt.Ok) {
      return $attempt
    }
  }

  Write-Host "No usable Python runtime was found for this project." -ForegroundColor Red
  Write-Host ""
  Write-Host "Checked:"
  foreach ($attempt in $attempts) {
    Write-Host "- $($attempt.Label): $($attempt.Detail)"
  }
  Write-Host "Fix: run setup_env.ps1 after installing Python 3.11, or set SMART_CHESS_PYTHON to a working python.exe." -ForegroundColor Yellow
  exit 1
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
  $info.FileName = $script:python.Command
  $info.WorkingDirectory = $root.Path
  $info.UseShellExecute = $false
  $info.CreateNoWindow = $true
  $info.Arguments = (@($script:python.PrefixArgs) + @("main.py")) -join " "

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

$script:python = Resolve-ProjectPython
Write-Host "Python runtime: $($script:python.Label) $($script:python.Detail)"

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
  $blockedPattern = '(^|/)(\.env|\.venv|node_modules|logs|data|reports|analysis_artifacts|docx_work)(/|$)|\.db$|\.log$|\.xlsx$|\.nnue$|\.pt$|\.onnx$|\.exe$|backend/infrastructure/vision/models/'
  $protectedAssetPattern = '^backend/infrastructure/protected_assets/'
  $blocked = Invoke-Git ls-files | Where-Object {
    ($_ -match $blockedPattern) -and ($_ -notmatch $protectedAssetPattern)
  }
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

Invoke-Step "CSS integrity check" {
  & npm.cmd run check:css
  Assert-CommandSucceeded $LASTEXITCODE "npm.cmd run check:css"
}

Invoke-Step "System diagnostic" {
  $pythonArgs = @($script:python.PrefixArgs) + @("scripts\system_diagnostic.py")
  & $script:python.Command @pythonArgs
  Assert-CommandSucceeded $LASTEXITCODE "system diagnostic"
}

if (-not $SkipHtmlFunctionCheck) {
  Invoke-Step "HTML function check" {
    & npm.cmd run check:html
    Assert-CommandSucceeded $LASTEXITCODE "HTML function check"
  }
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

      $healthArgs = @("-ExecutionPolicy", "Bypass", "-File", "scripts\health_check.ps1")
      if ($RequireHardwareReady) {
        $healthArgs += "-RequireHardwareReady"
      }
      & powershell.exe @healthArgs
      Assert-CommandSucceeded $LASTEXITCODE "health check"

      $previousHardwareReadyRequirement = $env:SMART_CHESS_REQUIRE_HARDWARE_READY
      try {
        if ($RequireHardwareReady) {
          $env:SMART_CHESS_REQUIRE_HARDWARE_READY = "1"
        }
        $pythonArgs = @($script:python.PrefixArgs) + @("scripts\test\smoke_test.py")
        & $script:python.Command @pythonArgs
        Assert-CommandSucceeded $LASTEXITCODE "HTTP smoke"
      } finally {
        if ($null -eq $previousHardwareReadyRequirement) {
          Remove-Item Env:\SMART_CHESS_REQUIRE_HARDWARE_READY -ErrorAction SilentlyContinue
        } else {
          $env:SMART_CHESS_REQUIRE_HARDWARE_READY = $previousHardwareReadyRequirement
        }
      }

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
if ($RequireHardwareReady) {
  Write-Host "System check completed successfully with hardware readiness."
} else {
  Write-Host "System check completed successfully for software smoke. Hardware readiness is reported separately above."
}
