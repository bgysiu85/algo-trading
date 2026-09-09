#!/usr/bin/env python3
"""Offline checks for MAX_CONCURRENT_POSITIONS -- the portfolio-level entry gate.

Until 2026-09-05 no such gate existed. MAX_SYMBOLS_SAFE only warns about
watchlist size for IB request pacing; the entry path never counted positions
across symbols, and size_for() bills each one against the FULL account equity
(which is read once at startup and never decremented). So N concurrent entries
committed N x MAX_EQUITY_PCT of equity rather than sharing it.

What is checked here:

  1. a second symbol CAN enter while one position is open, at cap 2
  2. a third is DECLINED, and the decline is logged rather than silent
  3. the cap counts POSITIONS, not symbols watched -- freeing one lets the
     next entry through, so this is a live gate and not a one-shot latch
  4. cap 1 blocks the second symbol, proving the constant is actually read

Temp paths come from tempfile.gettempdir(), NOT a hardcoded "/tmp": on Windows
Path("/tmp/x") resolves to a "tmp" folder at the root of the current DRIVE,
which does not exist.
"""
import asyncio
import csv
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from brokers.ibkr import trader as M
from tests.brokers.ibkr.test_dryrun_roundtrip import FakeTicker, find_firing_series
from tests.brokers.ibkr.test_live_paths import FakeIB, FakeTrade


def build(tag, symbols, outcomes, cap=None):
    """A trader watching several symbols, each with its own firing series."""
    out = Path(tempfile.gettempdir()) / f"conc_{tag}.csv"
    if out.exists():
        out.unlink()
    log = M.FillLog(out)
    ib = FakeIB(outcomes)
    tr = M.MCLPaperTrader(ib, Path(tempfile.gettempdir()) / "wl.txt",
                          log, dry_run=False)
    tr.equity = 22290.96
    states = {}
    for s in symbols:
        st = M.SymbolState(symbol=s)
        st.contract = object()
        st.ticker = FakeTicker()
        tr.states[s] = st
        states[s] = st
    return tr, states, ib, log, out


async def feed_one(tr, st, seq, start_min=0, stop_on_entry=True):
    """Walk one symbol through its bar series, as run() would.

    stop_on_entry matters: the shared firing series also produces an EXIT a few
    bars after the entry, so feeding it to the end leaves the symbol flat and
    the concurrency state empty. Here the point is to HOLD positions open, so
    by default we stop the moment one opens -- which is also what the real loop
    effectively does, since it moves on to the next symbol after each bar.
    """
    now = datetime(2026, 9, 2, 8, 0, tzinfo=M.ET)
    for i, df in enumerate(seq):
        tr.bars = lambda _s, _d=df: asyncio.sleep(0, result=_d)
        await tr.step_symbol(st, now + timedelta(minutes=start_min + i))
        if stop_on_entry and st.position is not None:
            return True
    return st.position is not None


def opened(rows, symbol):
    return [r for r in rows
            if r["symbol"] == symbol and r["action"] == "BUY"
            and r["status"] in ("FILLED", "PARTIAL_FILL")]


def declined(rows, symbol):
    return [r for r in rows
            if r["symbol"] == symbol and r["status"] == "SKIPPED_CONCURRENCY_CAP"]


async def main():
    n = 140
    full, _seed, _spike = find_firing_series(n)
    seq = [full.iloc[: k + 1] for k in range(M.MIN_BARS_REQUIRED, n)]
    ok = True
    original = M.MAX_CONCURRENT_POSITIONS

    # ---- 1/2/3. cap 2: A and B enter, C is declined, then C gets in -------
    try:
        M.MAX_CONCURRENT_POSITIONS = 2
        # Buys fill; no sells are scripted, so positions stay open.
        tr, sts, ib, log, out = build("cap2", ["AAA", "BBB", "CCC"],
                                      [FakeTrade(100, 10.00, "Filled")] * 40)
        for sym in ("AAA", "BBB", "CCC"):
            await feed_one(tr, sts[sym], seq)

        held = sorted(s for s, st in sts.items() if st.position is not None)
        if held == ["AAA", "BBB"]:
            print("PASS  two positions open at cap 2 (AAA, BBB)")
        else:
            print(f"FAIL  expected AAA+BBB open, got {held}")
            ok = False

        log.close()
        rows = list(csv.DictReader(out.open()))

        if declined(rows, "CCC"):
            r = declined(rows, "CCC")[0]
            print(f"PASS  third entry declined and logged "
                  f"(reason: {r['reject_reason']})")
        else:
            print("FAIL  third entry not logged as SKIPPED_CONCURRENCY_CAP")
            ok = False

        if not opened(rows, "CCC"):
            print("PASS  no order was placed for the declined symbol")
        else:
            print("FAIL  an order was placed for CCC despite the cap")
            ok = False

        # The cap must be a live gate, not a latch: free a slot and the next
        # signal should be taken.
        buys_before = len(ib.placed)
        sts["AAA"].position = None
        sts["CCC"].last_bar_ts = None          # let CCC evaluate a bar again
        log2 = M.FillLog(out.with_name("conc_cap2b.csv"))
        tr.log = log2
        await feed_one(tr, sts["CCC"], seq)
        log2.close()
        if sts["CCC"].position is not None and len(ib.placed) > buys_before:
            print("PASS  freeing a slot lets the next entry through")
        else:
            print("FAIL  cap behaved as a one-shot latch, not a live gate")
            ok = False

        # ---- 4. cap 1 blocks the second symbol ---------------------------
        M.MAX_CONCURRENT_POSITIONS = 1
        tr, sts, ib, log, out = build("cap1", ["AAA", "BBB"],
                                      [FakeTrade(100, 10.00, "Filled")] * 40)
        for sym in ("AAA", "BBB"):
            await feed_one(tr, sts[sym], seq)
        log.close()
        rows = list(csv.DictReader(out.open()))
        held = sorted(s for s, st in sts.items() if st.position is not None)
        if held == ["AAA"] and declined(rows, "BBB"):
            print("PASS  cap 1 admits one position and declines the second")
        else:
            print(f"FAIL  cap 1 not honoured: held={held}, "
                  f"declined={len(declined(rows, 'BBB'))}")
            ok = False
    finally:
        M.MAX_CONCURRENT_POSITIONS = original

    print()
    print("ALL CONCURRENCY-CAP CHECKS PASSED" if ok
          else "SOME CONCURRENCY-CAP CHECKS FAILED")
    return 0 if ok else 1


# --- pytest entry point -----------------------------------------------------
#
# ADDED 2026-09-09, AND THE REASON IS THE POINT. This file is a print-style
# script: it defines main() and reports each check with PASS/FAIL, but it
# declares no test_* function, so `pytest` collected ZERO tests from it and
# ran none of these checks. Seven files in this suite were in that state,
# every one of them covering the live trader or an engine, while the suite
# reported hundreds of passes.
#
# Two of the seven were FAILING and said nothing: this pattern does not just
# fail to catch a regression, it hides one that has already happened.
#
# The wrapper below is deliberately thin -- it runs the existing checks and
# fails the suite if any of them failed. Splitting each check into its own
# test would report better, and is worth doing; rewriting seven files of
# control logic in the same pass that relies on them as a control is not.


def test_concurrency_cap_checks_all_pass():
    assert asyncio.run(main()) == 0, (
        "see the FAIL lines in captured stdout above")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
