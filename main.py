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
from contextlib import contextmanager

from common import session_lock

# Modes that hold an IB session for an extended period and therefore take the
# lock. `scan` deliberately does NOT: the scanner is designed to run alongside
# the trader on its own client id.
SESSION_MODES = {"paper", "dry"}

# Strategies the LIVE trader can drive. MC5 joined 2026-09-09 once it had an
# evaluate_last_bar that only ever reads a CLOSED 5-minute bucket
# (strategy/mc5/mc5.last_closed_bucket) and a StrategyAdapter to carry its own
# band, trail and session. VW9 is still backtest-only: it exits on 2R targets,
# a structure stop and vwap_lost, none of which manage_position implements.
#
# More than one may be given. They run in ONE process sharing ONE position
# book, because they share one IB account -- two processes would each see half
# of it and both spend the same buying power.
LIVE_STRATEGIES = {"mcl", "mc5"}

# Strategies the backtest engine can dispatch to. All four expose
# backtest_session(df, session_date, tz) over the same 1-minute frame;
# vw9_5m/vw9_15m additionally accept an optional exit_mode kwarg (forward it
# with --exit-mode, see common/backtest.py).
BACKTEST_STRATEGIES = {"mcl", "mc5", "vw9_5m", "vw9_15m"}


def _fail(msg: str) -> int:
    print(f"main.py: {msg}", file=sys.stderr)
    return 2


def _flag_value(argv: list[str], name: str, default: str) -> str:
    """Read a forwarded flag's value for DISPLAY only.

    Deliberately not a second argparse pass: the trader's parser is the one
    that decides what these mean, and a copy here would be a second source of
    truth that could disagree with the run it is describing. If a value cannot
    be found the banner says so rather than guessing.
    """
    try:
        return argv[argv.index(name) + 1]
    except (ValueError, IndexError):
        return default


@contextmanager
def _feed_beside(mode: str, want_feed: bool, forwarded: list[str]):
    """Run common.tv_feed in a thread for the life of the trader.

    WHY A THREAD AND NOT THE EVENT LOOP. tv_feed is a synchronous urllib loop
    with time.sleep in it. Dropping that into the trader's asyncio loop would
    stall order management for the length of every HTTP call -- and the feed
    backs off to 60s on an error, which is 60 seconds of a trailing stop not
    being checked. A thread keeps them genuinely independent; they already
    communicate only through var/watchlist.txt, which the trader re-reads every
    five seconds.

    WHY IT CANNOT TAKE THE TRADER DOWN. Every exception is caught here. A feed
    that dies costs a stale watchlist, which is visible and survivable. A feed
    that kills the process leaves an OPEN POSITION WITH NO TRAILING STOP,
    because the stop lives in this process and not at IBKR. Those two outcomes
    are not close enough to trade one risk for the other, so the feed is
    strictly subordinate: it may fail, it may not take anything with it.

    daemon=True so Ctrl-C ends the process rather than waiting on a thread
    sleeping 10 seconds. The feed writes a file and holds no broker state;
    there is nothing it must finish.
    """
    if mode != "paper" or not want_feed:
        if mode == "paper":
            print("main.py: --no-feed, watchlist will not be updated by this "
                  "process. Start run_tv_feed.ps1 separately or the trader "
                  "watches a stale list.")
        yield
        return

    import threading
    from common import tv_feed

    # Pass through only what the feed shares with the trader. Its parser knows
    # nothing about --port or --strategy, and forwarding those would kill the
    # thread on an unrecognized argument the moment it started.
    feed_argv = []
    batch = _flag_value(forwarded, "--telegram-batch-min", "")
    if batch:
        feed_argv += ["--telegram-batch-min", batch]
    if "--no-telegram" in forwarded:
        feed_argv.append("--no-telegram")

    def _run():
        try:
            rc = tv_feed.main(feed_argv)
            print(f"main.py: watchlist feed exited rc={rc}. The trader "
                  f"continues; the watchlist is now STALE.", file=sys.stderr)
        except BaseException as e:                              # noqa: BLE001
            # BaseException, not Exception: a KeyboardInterrupt delivered to
            # this thread must not escape into the trader's shutdown either.
            print(f"main.py: watchlist feed died ({type(e).__name__}: {e}). "
                  f"The trader continues; the watchlist is now STALE.",
                  file=sys.stderr)

    t = threading.Thread(target=_run, name="tv_feed", daemon=True)
    t.start()
    print("main.py: watchlist feed started in this process "
          "(--no-feed to disable).")
    try:
        yield
    finally:
        # Nothing to join: daemon, holds no broker state, and the writer lock
        # it took is released by its own context manager or reaped as stale.
        pass


def _confirmed(wanted: list[str], forwarded: list[str]) -> bool:
    """Show what is about to happen and require the word PAPER.

    Non-interactive callers (a scheduled run, a pipe, CI) have no stdin, and a
    prompt there would either hang forever or read EOF and be taken as a
    refusal. `--yes` is the explicit opt-out; an absent tty without it is
    refused rather than assumed either way, because guessing in the permissive
    direction is how an unattended process starts placing orders nobody asked
    for.
    """
    if "--yes" in forwarded:
        forwarded.remove("--yes")
        print("main.py: --yes given, skipping the confirmation prompt.")
        return True

    port = _flag_value(forwarded, "--port", "4002 (default)")
    cap = _flag_value(forwarded, "--max-positions", "trader default")
    print()
    print("  ORDERS WILL BE PLACED")
    print()
    print(f"  Strategies : {', '.join(wanted)}")
    print(f"  Port       : {port}   (paper only -- live ports are refused)")
    print(f"  Position cap: {cap} across ALL strategies")
    print()
    print("  The trailing stop lives in this process, not at IBKR.")
    print("  If this window closes with a position open, that position is")
    print("  unprotected.")
    print()
    if not sys.stdin or not sys.stdin.isatty():
        print("  no terminal to prompt on -- pass --yes to run non-interactively.")
        return False
    try:
        return input("Type PAPER to continue: ").strip() == "PAPER"
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def run(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Entry point for the trading, backtest and scanner modes",
        epilog="Unrecognised arguments are forwarded to the selected mode.")
    p.add_argument("--mode", required=True,
                   choices=["paper", "dry", "backtest", "scan", "report",
                            "probe-window"])
    p.add_argument("--no-feed", dest="feed", action="store_false",
                   help="do NOT run the TradingView watchlist feed in this "
                        "process. --mode paper runs it by default so one "
                        "command starts everything; use this when "
                        "run_tv_feed.ps1 or the IB scanner is already "
                        "writing the watchlist from elsewhere.")
    p.add_argument("--strategy", default="mcl",
                   help="strategy to run, COMMA-separated for more than one "
                        "(default: mcl; e.g. --strategy mcl,mc5). A space "
                        "between names does NOT work -- see the guard below.")
    args, passthrough = p.parse_known_args(argv)

    # `--strategy mcl mc5` (space, not comma) is the shape everyone types,
    # because the TRADER's own --strategy takes nargs="+" and the help text for
    # this one does not say otherwise. This parser takes a single value, so
    # "mcl" is the strategy and "mc5" falls into passthrough as a bare
    # positional.
    #
    # WHY THIS IS A GUARD AND NOT A NOTE. Tonight it failed loudly, because the
    # trader's parser had no positional to absorb "mc5" and said
    # "unrecognized arguments". That was luck. Add one positional anywhere
    # downstream -- or forward to a mode whose parser ignores extras -- and the
    # session runs ONE strategy while the operator believes it is running two,
    # and every fill log and review afterwards is describing the wrong thing.
    # A silent half-configured live session is the exact failure this project
    # keeps finding, so the shape is refused rather than documented.
    strays = [a for a in passthrough
              if not a.startswith("-")
              and (a in LIVE_STRATEGIES or a in BACKTEST_STRATEGIES)]
    if strays:
        return _fail(
            f"strategy name(s) {', '.join(strays)} passed as bare arguments. "
            f"--strategy takes ONE comma-separated value, not a list:\n"
            f"  correct:   --strategy {args.strategy},{','.join(strays)}\n"
            f"  incorrect: --strategy {args.strategy} {' '.join(strays)}\n"
            f"Refusing rather than running only {args.strategy}.")

    if args.mode in SESSION_MODES:
        wanted = args.strategy.split(",") if "," in args.strategy \
            else [args.strategy]
        bad = [w for w in wanted if w not in LIVE_STRATEGIES]
        if bad:
            return _fail(f"--strategy {','.join(bad)} cannot be traded live; "
                         f"the live trader supports {sorted(LIVE_STRATEGIES)}. "
                         f"Use --mode backtest for it instead.")
        held = session_lock.active()
        if held:
            return _fail("a live session is already running -- "
                         + session_lock.describe(held)
                         + ".\n  Two sessions would compete for IB's "
                           "account-wide request budget.")
        from brokers.ibkr import trader
        forwarded = list(passthrough) + ["--strategy", *wanted]
        if args.mode == "dry" and "--dry-run" not in forwarded:
            forwarded.append("--dry-run")
        # THE CONFIRMATION, MOVED HERE 2026-09-10.
        #
        # It used to live only in run_paper.ps1. Ben ran `python main.py` for
        # the first time tonight and noticed it was gone -- nothing had removed
        # it; the wrapper was simply not in the path any more. A safety prompt
        # that exists in ONE of four entry points (run.ps1, run_dry.ps1,
        # run_paper.ps1, main.py) is not a guard, it is a habit, and the way it
        # fails is by being absent exactly when someone takes a new route.
        #
        # It is NOT the real protection and must never be mistaken for it. The
        # port allowlist and the DU-prefix account check live in
        # trader.main_async and cannot be bypassed from any entry point. This
        # only makes a person look at what is about to happen.
        if args.mode == "paper" and not _confirmed(wanted, forwarded):
            return _fail("cancelled at the confirmation prompt.")
        with session_lock.held(args.mode, args.strategy):
            with _feed_beside(args.mode, args.feed, forwarded):
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

    if args.mode == "probe-window":
        from common import probe_window
        return probe_window.main(passthrough) or 0

    if args.mode == "report":
        from common import report_trades
        return report_trades.main(passthrough) or 0

    return _fail(f"unhandled mode {args.mode}")


if __name__ == "__main__":
    sys.exit(run())
