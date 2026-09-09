#!/usr/bin/env python3
"""Checks the two changes made for IB pacing and trailing-stop latency.

1. bars() must not re-request history on every loop — IB refuses beyond
   60 requests / 10 min, and identical requests inside 15s.
2. The trailing stop must fire from the fast loop off a live quote, with no
   bar data at all.
"""
import asyncio, sys, types
from datetime import datetime
from pathlib import Path

from brokers.ibkr import trader as M
from tests.brokers.ibkr.test_dryrun_roundtrip import find_firing_series
from tests.brokers.ibkr.test_live_paths import build, FakeTrade


class MovingTicker:
    def __init__(self, bid, ask): self.bid, self.ask = bid, ask


async def main():
    ok = True

    # ---- 1. history is fetched at most once per minute per symbol ---------
    tr, st, ib, log, out = build("pacing", [])
    calls = {"n": 0}
    full, _, _ = find_firing_series(140)

    async def counting_fetch(_st):
        calls["n"] += 1
        return full

    tr._fetch_bars = counting_fetch

    for _ in range(60):                      # 60 fast-loop iterations
        await tr.bars(st)
    log.close()

    if calls["n"] == 1:
        print(f"PASS  60 loop passes -> {calls['n']} history request")
    else:
        print(f"FAIL  60 loop passes -> {calls['n']} history requests "
              f"(IB caps at 60 per 10 minutes across all contracts)")
        ok = False

    # cache must still return usable data, not None
    df = await tr.bars(st)
    if df is not None and not df.empty:
        print("PASS  cached bars still returned to the strategy")
    else:
        print("FAIL  cache returned nothing — strategy would go blind")
        ok = False

    # a new minute must refresh
    st.bars_minute = (0, 0)
    st.bars_fetched_at -= 999
    await tr.bars(st)
    if calls["n"] == 2:
        print("PASS  a new minute triggers exactly one refresh")
    else:
        print(f"FAIL  refresh on new minute: {calls['n']} total requests")
        ok = False

    # ---- 2. trailing stop fires from a live quote, no bars ---------------
    tr, st, ib, log, out = build("fasttrail", [
        FakeTrade(100, 24.00, "Filled"),     # the exit fill
    ])
    st.ticker = MovingTicker(23.90, 24.00)
    st.position = M.Position(symbol="TEST", qty=100, entry_price=21.14,
                             entry_time=datetime(2026, 9, 2, 4, 1, tzinfo=M.ET),
                             peak=26.69)
    # trail level = 26.69 * 0.95 = 25.3555; ask 24.00 is below it -> must exit
    now = datetime(2026, 9, 2, 4, 2, tzinfo=M.ET)

    await tr.manage_position(st, now, bar_close=24.00, detail={})
    log.close()

    if st.position is None:
        print("PASS  trail fired from the live quote with no bar data")
    else:
        print("FAIL  trail did not fire — position still open")
        ok = False
    # Commission is the real per-leg IBKR schedule now, not a flat $2.00 --
    # 100 shares at these prices is $0.70 the round trip on Tiered, not $2.00.
    from common.commissions import order_cost
    _comm = (order_cost(100, 21.14, False, M.COMMISSION_PLAN)
             + order_cost(100, 24.00, True, M.COMMISSION_PLAN))
    if tr.session_trades == 1 and abs(tr.session_pnl - ((24.00 - 21.14) * 100 - _comm)) < 0.01:
        print(f"PASS  exit P/L correct ({tr.session_pnl:+.2f})")
    else:
        print(f"FAIL  exit P/L {tr.session_pnl} / trades {tr.session_trades}")
        ok = False

    # ---- 3. no exit while price is above the trail -----------------------
    tr, st, ib, log, out = build("notrail", [])
    st.ticker = MovingTicker(25.90, 26.00)
    st.position = M.Position(symbol="TEST", qty=100, entry_price=21.14,
                             entry_time=datetime(2026, 9, 2, 4, 1, tzinfo=M.ET),
                             peak=26.69)
    await tr.manage_position(st, now, bar_close=26.00, detail={})
    log.close()
    if st.position is not None and not ib.placed:
        print("PASS  no exit while price is above the trail level")
    else:
        print("FAIL  spurious exit above the trail level")
        ok = False

    print("\n" + ("ALL PACING/TRAIL CHECKS PASSED" if ok else "FAILURES ABOVE"))
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


def test_pacing_and_trail_checks_all_pass():
    assert asyncio.run(main()) == 0, (
        "see the FAIL lines in captured stdout above")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
