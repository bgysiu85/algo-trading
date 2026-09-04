# Generic launcher: any mode, any strategy, through main.py.
#
#   .\run.ps1 -Mode dry      -Strategy mcl
#   .\run.ps1 -Mode backtest -Strategy mc5
#   .\run.ps1 -Mode backtest -Strategy mcl -Extra "--retry-failed"
#
# The named scripts (run_dry, run_paper, run_backtest_after_session,
# show_trades) remain the everyday entry points -- they carry the pre-flight
# checks each mode needs. This is the escape hatch for combinations they do
# not express, such as backtesting MC5.

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("paper","dry","backtest","scan","report")]
    [string]$Mode,
    [string]$Strategy = "mcl",
    [string]$Extra = ""
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "No .venv found. Run .\run_dry.ps1 once first to create it." -ForegroundColor Red
    exit 1
}

$argsList = @("main.py", "--mode", $Mode, "--strategy", $Strategy)
if ($Extra) { $argsList += $Extra.Split(" ") }

Write-Host ("main.py --mode {0} --strategy {1} {2}" -f $Mode, $Strategy, $Extra) -ForegroundColor Cyan
& $py @argsList
exit $LASTEXITCODE
