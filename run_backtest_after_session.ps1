# Waits until the pre-market session is over, then runs the historical backtest.
#
#   .\run_backtest_after_session.ps1                    # waits, runs, leaves PC awake
#   .\run_backtest_after_session.ps1 -SleepWhenDone     # sleeps the PC afterwards
#   .\run_backtest_after_session.ps1 -StartAtET "10:00" # different start time
#
# Start this ANY TIME (before or during the session) and walk away. It sleeps
# until the target Eastern time, confirms the trader has exited, then runs.
#
# WHY THE WAIT MATTERS
# The backtest issues ~48 historical requests per 10 minutes. The live trader
# issues up to 60. IBKR's cap is ~60 PER ACCOUNT, and past it IB returns empty
# responses with no error - the trader would silently stop seeing new bars.
# So these two must never overlap.
#
# IMPORTANT: do NOT also pass -SleepWhenDone to run_paper.ps1 today. The trader
# would put the PC to sleep ~20 minutes after 09:30 and kill this run. Let this
# script own the sleep instead.

param(
    [string]$StartAtET = "09:35",
    [switch]$SleepWhenDone,
    [int]$SleepDelayMin = 10,
    [switch]$NoWait                  # run immediately, skip the clock check
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "No .venv found. Run .\run_dry.ps1 once first." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path (Join-Path $PSScriptRoot "traded_pairs.json"))) {
    Write-Host "traded_pairs.json not found - nothing to backtest." -ForegroundColor Red
    exit 1
}

function Get-ETNow {
    $tz = [TimeZoneInfo]::FindSystemTimeZoneById("Eastern Standard Time")
    [TimeZoneInfo]::ConvertTimeFromUtc([DateTime]::UtcNow, $tz)
}

function Test-TraderRunning {
    # Any python process whose command line mentions the live trader.
    $procs = Get-CimInstance Win32_Process -Filter "Name like '%python%'" -ErrorAction SilentlyContinue
    foreach ($p in $procs) {
        if ($p.CommandLine -and $p.CommandLine -match "mcl_paper_trader") { return $true }
    }
    return $false
}

$log = Join-Path $PSScriptRoot ("backtest_run_{0:yyyyMMdd}.log" -f (Get-ETNow))

Write-Host ""
Write-Host "MCL historical backtest - unattended runner" -ForegroundColor Green
Write-Host ("  now          {0:HH:mm:ss} ET" -f (Get-ETNow))
Write-Host ("  starts at    {0} ET (and only once the trader has exited)" -f $(if ($NoWait) { "immediately" } else { $StartAtET }))
Write-Host ("  sleeps PC    {0}" -f $(if ($SleepWhenDone) { "yes, $SleepDelayMin min after it finishes" } else { "no" }))
Write-Host "  log          $log"
Write-Host "You can leave this window alone. Ctrl-C is safe at any point." -ForegroundColor Green
Write-Host ""

if (-not $NoWait) {
    $target = [DateTime]::ParseExact($StartAtET, "HH:mm", $null)
    while ($true) {
        $et = Get-ETNow
        $todayTarget = $et.Date.Add($target.TimeOfDay)
        if ($et -ge $todayTarget) { break }
        $mins = [math]::Ceiling(($todayTarget - $et).TotalMinutes)
        Write-Host ("{0:HH:mm:ss} ET - waiting {1} min until {2} ET" -f $et, $mins, $StartAtET) -ForegroundColor Cyan
        Start-Sleep -Seconds ([Math]::Min(300, [Math]::Max(20, ($todayTarget - $et).TotalSeconds)))
    }
}

# Never start while the trader still holds the pacing budget.
$waited = 0
while (Test-TraderRunning) {
    if ($waited -eq 0) {
        Write-Host "Trader still running - waiting for it to exit before starting." -ForegroundColor Yellow
        Write-Host "(it may be holding a position past 09:30)" -ForegroundColor Yellow
    }
    Start-Sleep -Seconds 60
    $waited += 1
    if ($waited -ge 90) {
        Write-Host "Trader still running after 90 min. Not starting - would throttle it." -ForegroundColor Red
        exit 1
    }
}

$et = Get-ETNow
Write-Host ""
Write-Host ("{0:HH:mm:ss} ET - starting backtest over 407 symbol/date pairs" -f $et) -ForegroundColor Green
Write-Host "~85 minutes. Checkpointed, so it can be interrupted and resumed." -ForegroundColor Green
Write-Host "Logging to $log" -ForegroundColor Green
Write-Host ""

# Python's logging writes to stderr. With ErrorActionPreference=Stop, redirecting
# a native command's stderr into the pipeline turns every log line into a
# terminating error, so drop back to Continue for the duration of the run.
$ErrorActionPreference = "Continue"
& $py -m common.backtest --retry-failed 2>&1 | Tee-Object -FilePath $log
$code = $LASTEXITCODE
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host ("{0:HH:mm:ss} ET - backtest finished (exit {1})" -f (Get-ETNow), $code) -ForegroundColor Green

if ($SleepWhenDone) {
    Write-Host "Sleeping this PC in $SleepDelayMin minutes. Ctrl-C to cancel." -ForegroundColor Yellow
    for ($i = $SleepDelayMin; $i -gt 0; $i--) {
        Write-Host "  sleep in $i min..."
        Start-Sleep -Seconds 60
    }
    rundll32.exe powrprof.dll,SetSuspendState 0,1,0
}
