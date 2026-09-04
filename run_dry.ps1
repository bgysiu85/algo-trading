# MCL - dry run (places NO orders; logs signals + live bid/ask only)
#
#   .\run_dry.ps1              normal run, needs tickers in watchlist.txt
#   .\run_dry.ps1 -AllowEmpty  start with an empty watchlist (connection test)
#   .\run_dry.ps1 -Live        PLACE PAPER ORDERS (still paper-only guarded)
#
# Prerequisites: IB Gateway open, logged into the PAPER account, API on port 4002.

param(
    [switch]$AllowEmpty,
    [switch]$Live,
    [int]$Port = 4002
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

# ---- one-time environment setup -----------------------------------------
if (-not (Test-Path $py)) {
    Write-Host "No virtual environment found. Creating one..." -ForegroundColor Cyan

    $bootstrap = $null
    foreach ($cand in @("python", "py")) {
        if (Get-Command $cand -ErrorAction SilentlyContinue) { $bootstrap = $cand; break }
    }
    if (-not $bootstrap) {
        Write-Host "Python not found on PATH. Install Python 3.10+ and reopen the terminal." -ForegroundColor Red
        exit 1
    }

    if ($bootstrap -eq "py") { & py -3 -m venv .venv } else { & python -m venv .venv }
    if (-not (Test-Path $py)) {
        Write-Host "Failed to create .venv" -ForegroundColor Red
        exit 1
    }

    Write-Host "Installing ib_async and pandas..." -ForegroundColor Cyan
    & $py -m pip install --quiet --upgrade pip
    & $py -m pip install --quiet ib_async pandas
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Package install failed." -ForegroundColor Red
        exit 1
    }
    Write-Host "Environment ready." -ForegroundColor Green
}

# ---- watchlist ------------------------------------------------------------
if (-not (Test-Path ".\watchlist.txt")) {
    Write-Host "watchlist.txt not found in $PSScriptRoot" -ForegroundColor Red
    exit 1
}

# Strip trailing comments too - the scanner annotates picks as "UPC  # rank 1".
$tickers = Get-Content .\watchlist.txt |
    ForEach-Object { ($_ -split "#")[0].Trim() } |
    Where-Object { $_ -ne "" }

# Empty is normal: the watchlist is archived and cleared after every session.
if ($tickers.Count -eq 0) {
    Write-Host "watchlist.txt is empty - starting with nothing to watch." -ForegroundColor Yellow
    Write-Host "Add tickers at any time; they are picked up within 5 seconds." -ForegroundColor Yellow
} else {
    Write-Host ("Watchlist: " + ($tickers -join ", ")) -ForegroundColor Cyan
}

# ---- build args and go ----------------------------------------------------
$argsList = @(".\mcl_paper_trader.py", "--watchlist", ".\watchlist.txt", "--port", "$Port")
if (-not $Live)    { $argsList += "--dry-run" }
if ($AllowEmpty)   { $argsList += "--allow-empty" }

if ($Live) {
    Write-Host "LIVE PAPER ORDERS enabled (paper-account guard still applies)." -ForegroundColor Magenta
} else {
    Write-Host "DRY RUN - no orders will be placed." -ForegroundColor Green
}
Write-Host ""

& $py @argsList
