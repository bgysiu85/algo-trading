# Poll the TradingView screen and keep watchlist.txt current.
#
# SINCE 2026-09-10 YOU USUALLY DO NOT NEED THIS. main.py --mode paper starts the
# feed in its own process, so one command runs everything. This script remains
# for running the feed ALONE -- to watch the screen without trading, or with
# --mode paper --no-feed. Starting both is refused by the writer lock rather
# than silently producing two writers.
#
# Run this in its OWN terminal, started before .\run_paper.ps1, and leave it
# up for the session. It writes the file; the trader reads it.
#
# ONE WRITER ONLY: brokers/ibkr/scanner.py writes the same file from IB's
# scanner. Run one or the other, never both, or they overwrite each other
# every few seconds.
#
#   .\run_tv_feed.ps1                 # 10s poll, 04:00-09:30 ET, writes the file
#   .\run_tv_feed.ps1 -TelegramBatchMin 15   # hold notifications, send every 15 min
#   .\run_tv_feed.ps1 -DryRun         # prints what it would write, writes nothing
#   .\run_tv_feed.ps1 -Once -DryRun   # one call -- use this first, to check
#                                     #   the endpoint is reachable from here
#   .\run_tv_feed.ps1 -Interval 30
#   .\run_tv_feed.ps1 -NoTelegram    # no notifications even if configured
#
# Telegram: set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID (literal values or
# op:// references) and check with  python -m common.notify --test
# A heartbeat every hour proves the feed is alive on a quiet morning, when a
# crashed feed and a calm market look identical from the phone.

param(
    [double]$Interval = 10,
    [double]$Heartbeat = 3600,
    [switch]$DryRun,
    [switch]$Once,
    [switch]$AllHours,
    [switch]$NoTelegram,
    [int]$TelegramBatchMin = 0       # 0 = send immediately
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "No .venv found. Run .\run_dry.ps1 once first to create it." -ForegroundColor Red
    exit 1
}

$args = @("-m", "common.tv_feed", "--interval", $Interval,
          "--heartbeat", $Heartbeat)
if ($DryRun)     { $args += "--dry-run" }
if ($Once)       { $args += "--once" }
if ($AllHours)   { $args += "--all-hours" }
if ($NoTelegram) { $args += "--no-telegram" }
if ($TelegramBatchMin -gt 0) { $args += @("--telegram-batch-min", "$TelegramBatchMin") }

Write-Host "tv_feed: $($args -join ' ')" -ForegroundColor Cyan
& $py @args
exit $LASTEXITCODE
