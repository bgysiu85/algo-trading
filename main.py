#!/usr/bin/env python3
"""Single entry point for every mode.

    python main.py --mode dry      --strategy mcl
    python main.py --mode paper    --strategy mcl
    python main.py --mode backtest --strategy mcl --retry-failed
    python main.py --mode backtest --strategy mc5
    python main.py --mode scan
    python main.py --mode report

Anything after this script's own flags is passed through untouched to the
underlying program, so every existing option still works:

    python main.py --mode paper --strategy mcl --port 4002 --no-archive

WHY ONE ENTRY POINT
-------------------
It is the shape Ben specified: one script that selects a strategy and
forwards parameters to it. It also removes the last filename dependency in
the repo. Live-session detection used to grep process command lines for
"mcl_paper_trader", so the trader could never be renamed without silently
disabling the guard that stops a backtest throttling a live session against
IB's account-wide request cap. That guard is now a lock file -- see
common/session_lock.py -- and mcl_paper_trader.py is gone.

RUNNING MODULES DIRECTLY
------------------------
Everything is a package, so `python common\\backtest.py` puts common/ on
sys.path rather than the repo root and fails to resolve `strategy.mcl`. Use
this script, or `python -m common.backtest`. Running the trader directly
also bypasses the lock, which is a good reason not to.
"""

from __future__ import annotations

import argparse
import sys

from common import session_lock

# Modes that hold an IB session for an extended period and therefore take the
# lock. `scan` deliberately does NOT: the scanner is designed to run alongside
# the trader on its own client id.
SESSION_MODES = {"paper", "dry"}

# Strategies the LIVE trader can drive. Only MCL implements the streaming
# interface trader.py needs (evaluate_last_bar, MIN_BARS_REQUIRED, Signals);
# MC5 and VW9 are backtest/measurement only for now.
LIVE_STRATEGIES = {"mcl"}

# Strategies the backtest engine can dispatch to. Both expose
# backtest_session(df, session_date, tz) over the same 1-minute frame.
BACKTEST_STRATEGIES = {"mcl", "mc5"}


def _fail(msg: str) -> int:
    print(f"main.py: {msg}", file=sys.stderr)
    return 2


def run(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Entry point for the trading, backtest and scanner modes",
        epilog="Unrecognised arguments are forwarded to the selected mode.")
    p.add_argument("--mode", required=True,
                   choices=["paper", "dry", "backtest", "scan", "report"])
    p.add_argument("--strategy", default="mcl",
                   help="strategy to run (default: mcl)")
    args, passthrough = p.parse_known_args(argv)

    if args.mode in SESSION_MODES:
        if args.strategy not in LIVE_STRATEGIES:
            return _fail(f"--strategy {args.strategy} cannot be traded live; "
                         f"the live trader supports {sorted(LIVE_STRATEGIES)}. "
                         f"Use --mode backtest for it instead.")
        held = session_lock.active()
        if held:
            return _fail("a live session is already running -- "
                         + session_lock.describe(held)
                         + ".\n  Two sessions would compete for IB's "
                           "account-wide request budget.")
        from brokers.ibkr import trader
        forwarded = list(passthrough)
        if args.mode == "dry" and "--dry-run" not in forwarded:
            forwarded.append("--dry-run")
        with session_lock.held(args.mode, args.strategy):
            return trader.main(forwarded) or 0

    if args.mode == "backtest":
        if args.strategy not in BACKTEST_STRATEGIES:
            return _fail(f"--strategy {args.strategy} has no backtest engine; "
                         f"available: {sorted(BACKTEST_STRATEGIES)}.")
        from common import backtest
        return backtest.main(["--strategy", args.strategy] + passthrough) or 0

    if args.mode == "scan":
        from brokers.ibkr import scanner
        return scanner.main(passthrough) or 0

    if args.mode == "report":
        from common import report_trades
        return report_trades.main(passthrough) or 0

    return _fail(f"unhandled mode {args.mode}")


if __name__ == "__main__":
    sys.exit(run())
