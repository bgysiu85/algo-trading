# MCL - read-only account view (positions, orders, fills, balances)
#
#   .\show_trades.ps1           print once
#   .\show_trades.ps1 -Watch    refresh every 30s until Ctrl-C
#
# Safe to run at the same time as run_dry.ps1 - it connects on its own
# client id and places nothing.

param(
    [switch]$Watch,
    [int]$Port = 4002
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "No .venv found. Run .\run_dry.ps1 once first to create it." -ForegroundColor Red
    exit 1
}

$argsList = @(".\report_trades.py", "--port", "$Port")
if ($Watch) { $argsList += "--watch" }

& $py @argsList
