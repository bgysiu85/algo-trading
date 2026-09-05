# Poll the TradingView screen and keep watchlist.txt current.
#
# Run this in its OWN terminal, started before .\run_paper.ps1, and leave it
# up for the session. It writes the file; the trader reads it.
#
# ONE WRITER ONLY: brokers/ibkr/scanner.py writes the same file from IB's
# scanner. Run one or the other, never both, or they overwrite each other
# every few seconds.
#
#   .\run_tv_feed.ps1                 # 10s poll, 04:00-09:30 ET, writes the file
#   .\run_tv_feed.ps1 -DryRun         # prints what it would write, writes nothing
#   .\run_tv_feed.ps1 -Once -DryRun   # one call -- use this first, to check
#                                     #   the endpoint is reachable from here
#   .\run_tv_feed.ps1 -Interval 30

param(
    [double]$Interval = 10,
    [switch]$DryRun,
    [switch]$Once,
    [switch]$AllHours
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "No .venv found. Run .\run_dry.ps1 once first to create it." -ForegroundColor Red
    exit 1
}

$args = @("-m", "common.tv_feed", "--interval", $Interval)
if ($DryRun)   { $args += "--dry-run" }
if ($Once)     { $args += "--once" }
if ($AllHours) { $args += "--all-hours" }

Write-Host "tv_feed: $($args -join ' ')" -ForegroundColor Cyan
& $py @args
exit $LASTEXITCODE
