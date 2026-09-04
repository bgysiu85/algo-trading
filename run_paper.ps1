# MCL - PLACE REAL ORDERS against the IBKR PAPER account.
#
#   .\run_paper.ps1                  normal run
#   .\run_paper.ps1 -SleepWhenDone   sleep the PC ~20 min after the 09:30 close
#   .\run_paper.ps1 -NoArchive       keep the watchlist instead of clearing it
#
# Starting with an empty watchlist is normal - it is archived and cleared at the
# end of every session. Add names while it runs; they are picked up within 5s.
#
# Guards that still apply and cannot be bypassed from here:
#   * port must be 4002 or 7497 (Gateway/TWS PAPER). 4001/7496 are LIVE and refused.
#   * every account id must start with 'DU'. Anything else aborts before trading.
#
# Prerequisites: IB Gateway logged into PAPER, API enabled on 4002,
# and **Read-Only API UNTICKED** - otherwise every order is rejected.

param(
    [switch]$AllowEmpty,             # accepted and ignored; empty is now the default
    [switch]$SleepWhenDone,          # put the PC to sleep after the session ends
    [switch]$NoArchive,              # keep the watchlist instead of clearing it
    [int]$SleepDelayMin = 20,
    [int]$Port = 4002
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "No .venv found. Run .\run_dry.ps1 once first to create it." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path ".\var\watchlist.txt")) {
    Write-Host "var\watchlist.txt not found under $PSScriptRoot" -ForegroundColor Red
    exit 1
}

# Strip trailing comments too - the scanner annotates picks as "UPC  # rank 1".
$tickers = Get-Content .\var\watchlist.txt |
    ForEach-Object { ($_ -split "#")[0].Trim() } |
    Where-Object { $_ -ne "" }

# Starting empty is NORMAL: the watchlist is archived and cleared at the end of
# every session. So this warns rather than refusing - the trader keeps repeating
# the warning while nothing is being watched.
if ($tickers.Count -eq 0) {
    Write-Host "watchlist.txt is empty - starting with nothing to watch." -ForegroundColor Yellow
    Write-Host "Add tickers (picked up within 5s) or run mcl_scanner.py alongside." -ForegroundColor Yellow
    Write-Host ""
}

Write-Host ""
Write-Host "  ORDERS WILL BE PLACED  " -ForegroundColor Black -BackgroundColor Yellow
Write-Host ""
Write-Host "  Port      : $Port  (paper only - live ports are refused)" -ForegroundColor Yellow
Write-Host "  Watchlist : $(if ($tickers.Count) { $tickers -join ', ' } else { '(empty)' })" -ForegroundColor Yellow
Write-Host "  Size      : up to 100 shares per name, 5% trailing stop" -ForegroundColor Yellow
Write-Host ""
Write-Host "  The trailing stop lives in this script, not at IBKR." -ForegroundColor Yellow
Write-Host "  If this window closes with a position open, that position is unprotected." -ForegroundColor Yellow
Write-Host ""

$confirm = Read-Host "Type PAPER to continue"
if ($confirm -ne "PAPER") {
    Write-Host "Cancelled." -ForegroundColor Cyan
    exit 0
}

$argsList = @("main.py", "--mode", "paper", "--strategy", "mcl",
              "--watchlist", ".\var\watchlist.txt", "--port", "$Port")
if ($NoArchive)      { $argsList += "--no-archive" }
if ($SleepWhenDone)  {
    $argsList += @("--sleep-on-exit", "--sleep-delay-min", "$SleepDelayMin")
    Write-Host "  This PC will sleep $SleepDelayMin min after the session ends." -ForegroundColor Yellow
    Write-Host "  (Skipped if a position is still open. Ctrl-C cancels the countdown.)" -ForegroundColor Yellow
    Write-Host ""
}

Write-Host ""
& $py @argsList
