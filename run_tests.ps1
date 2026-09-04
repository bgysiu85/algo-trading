# Run every test suite in the repo.
#
# Two conventions are in play, which is why this script exists rather than a
# bare `pytest`:
#   * MCL/MC5 suites are standalone scripts with their own main() and PASS/FAIL
#     output. They run as modules so the repo root is on sys.path.
#   * common/ and VW9 suites are pytest.
#
# Run from the repo root:  .\run_tests.ps1

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "No .venv found. Run .\run_dry.ps1 once first to create it." -ForegroundColor Red
    exit 1
}

$scriptSuites = @(
    "tests.strategy.mcl.test_backtest_engine",
    "tests.strategy.mc5.test_mc5_strategy",
    "tests.brokers.ibkr.test_dryrun_roundtrip",
    "tests.brokers.ibkr.test_live_paths",
    "tests.brokers.ibkr.test_pacing_and_trail"
)

$failed = @()

foreach ($m in $scriptSuites) {
    Write-Host ""
    Write-Host "=== $m ===" -ForegroundColor Cyan
    & $py -m $m
    if ($LASTEXITCODE -ne 0) { $failed += $m }
}

Write-Host ""
Write-Host "=== pytest (common, strategy/vw9) ===" -ForegroundColor Cyan
& $py -m pytest tests/common tests/strategy/vw9 -q
if ($LASTEXITCODE -ne 0) { $failed += "pytest" }

Write-Host ""
if ($failed.Count -eq 0) {
    Write-Host "ALL SUITES PASSED" -ForegroundColor Green
    exit 0
} else {
    Write-Host ("FAILED: " + ($failed -join ", ")) -ForegroundColor Red
    exit 1
}
