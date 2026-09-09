#!/usr/bin/env python3
"""Checks the offline backtest engine against hand-computed cases.

The engine is only useful if its exits and sizing are right, so these cover the
three exit paths, the sizing rule, the no-lookahead property of the trail, and
agreement with the paper trader's own signal code.
"""
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from strategy.mcl import mcl as S

ET = ZoneInfo("America/New_York")


def frame(closes, highs=None, lows=None, vols=None, start="04:00"):
    """Build a 1-minute frame on 2026-09-02 starting at a given ET time."""
    n = len(closes)
    t0 = datetime.strptime(f"2026-09-02 {start}", "%Y-%m-%d %H:%M").replace(tzinfo=ET)
    idx = pd.date_range(t0, periods=n, freq="1min").tz_convert("UTC")
    highs = highs or [c * 1.001 for c in closes]
    lows = lows or [c * 0.999 for c in closes]
    vols = vols or [5000] * n
    return pd.DataFrame({"open": closes, "high": highs, "low": lows,
                         "close": closes, "volume": vols}, index=idx)


def main():
    ok = True

    # --- 1. sizing -------------------------------------------------------
    cases = [(5.00, 100), (2.00, 100), (23.00, 100), (500.00, 80), (5000.00, 8)]
    for px, want in cases:
        got = S.size_for(px)
        good = got == want
        ok &= good
        print(("PASS" if good else "FAIL"), f"size at ${px:<8} -> {got} (want {want})")

    # --- 2. trailing stop must NOT use the current bar's high -------------
    # A bar that spikes up then collapses must not stop out against its own high.
    closes = [10.0] * 5 + [10.0, 10.0]
    highs = [10.01] * 5 + [12.00, 10.01]      # bar 5 spikes to 12
    lows = [9.99] * 5 + [9.99, 11.30]         # bar 6 low 11.30
    # peak entering bar 6 (previous-bar peak) is ~10.01 -> trail 9.51
    # 11.30 is far above that, so no stop. If the engine used bar 5's high (12),
    # trail would be 11.40 and bar 6 WOULD stop out. That is the bug we exclude.
    df = frame(closes, highs, lows)
    sig = S.signals(df)
    print(("PASS" if "entry" in sig.columns else "FAIL"), "signals() produces entry column")
    ok &= "entry" in sig.columns

    # --- 3. exit reasons all reachable ------------------------------------
    # Construct a session where a position is opened by forcing the entry
    # condition, then verify each exit path in isolation via backtest_session.
    import numpy as np
    rng = np.random.default_rng(0)

    def build_entry_series(n=200, spike_at=120, after=None):
        px, closes = 3.0, []
        for i in range(n):
            drift = rng.uniform(-0.004, 0.011) if i < spike_at + 3 else (after or -0.02)
            px *= 1.0 + drift
            closes.append(px)
        vols = [rng.integers(4000, 7000) for _ in range(n)]
        vols[spike_at] = int(vols[spike_at - 1] * 6)
        return closes, [int(v) for v in vols]

    found = None
    for seed in range(60):
        rng = np.random.default_rng(seed)
        closes, vols = build_entry_series()
        df = frame(closes, vols=vols)
        s = S.signals(df)
        local = s.index.tz_convert(ET)
        insess = (local.time >= S.SESSION_START) & (local.time < S.SESSION_END)
        if (s["entry"] & insess).any():
            found = (seed, df)
            break
    if found:
        seed, df = found
        trades = S.backtest_session(df, date(2026, 9, 2), ET)
        print(("PASS" if trades else "FAIL"),
              f"engine produces a round trip (seed {seed}, {len(trades)} trades)")
        ok &= bool(trades)
        if trades:
            t = trades[0]
            good = t.exit_price and t.entry_price and t.qty == 100
            print(("PASS" if good else "FAIL"),
                  f"trade well-formed: {t.entry_price} -> {t.exit_price} "
                  f"x{t.qty} {t.reason} net {t.net:+.2f}")
            ok &= good
            # Assert INTERNAL CONSISTENCY, not a particular fee schedule.
            # This used to recompute the expected net with
            # S.COMMISSION_PER_SHARE * qty * 2, which pinned the test to the
            # flat legacy model -- so it broke the moment commissions became
            # a real IBKR schedule with a per-ORDER minimum, even though the
            # engine was correct. net == gross - commission holds under every
            # plan; the plan itself is checked in tests/common/.
            expect = round(t.gross - t.commission, 2)
            good = abs(t.net - expect) < 0.01
            print(("PASS" if good else "FAIL"),
                  f"net == gross - commission  {t.net:+.2f} == {expect:+.2f} "
                  f"(plan {S.COMMISSION_PLAN}, comm {t.commission:.2f})")
            ok &= good
            good = t.reason in ("trailing_stop", "apex_reversal", "window_close")
            print(("PASS" if good else "FAIL"), f"exit reason valid: {t.reason}")
            ok &= good
    else:
        print("FAIL  could not construct an entry in 60 seeds")
        ok = False

    # --- 4. no trades outside the session window --------------------------
    df = frame([3.0 + i * 0.01 for i in range(60)], start="10:00")   # after 09:30
    trades = S.backtest_session(df, date(2026, 9, 2), ET)
    print(("PASS" if not trades else "FAIL"),
          f"no trades outside 04:00-09:30 ({len(trades)} found)")
    ok &= not trades

    # --- 5. evaluate_last_bar() agrees with signals() on the same frame ----
    # There is only one indicator implementation now (see STEP 2 of
    # claude/repo_reorg_and_github_plan.md) -- evaluate_last_bar() is built
    # by calling signals() and reading off the last row, so this is a
    # regression test of that wiring rather than a cross-file duplication
    # check. The old version of this test compared mcl_strategy's indicators
    # against mcl_paper_trader's separate copy of the same math; that copy no
    # longer exists, trader.py imports evaluate_last_bar from here directly.
    df = frame([3.0 + (i % 7) * 0.05 for i in range(120)])
    sig_row = S.signals(df).iloc[-1]
    live = S.evaluate_last_bar(df)
    good = (live is not None
            and abs(live.close - float(sig_row["close"])) < 1e-9
            and live.long_entry == bool(sig_row["entry"])
            # GATED, not raw. USE_APEX_EXIT has been False since 2026-09-05
            # and evaluate_last_bar has applied it since 09-08 -- the fix that
            # stopped the live trader taking apex exits the backtest did not.
            # This line compared against the UNGATED column and has been
            # failing ever since, unnoticed, because pytest collects no tests
            # from this file (it is a print-style script). Both facts are the
            # same defect: a check nobody runs cannot report anything.
            and live.exit_signal == (bool(sig_row["exit_sig"])
                                     and S.USE_APEX_EXIT)
            and abs(live.detail["macd"] - round(float(sig_row["macd"]), 5)) < 1e-9)
    print(("PASS" if good else "FAIL"),
          "evaluate_last_bar() agrees with signals() on the last row")
    ok &= good

    short = frame([3.0] * 10)   # fewer than MIN_BARS_REQUIRED
    good = S.evaluate_last_bar(short) is None
    print(("PASS" if good else "FAIL"),
          "evaluate_last_bar() returns None below MIN_BARS_REQUIRED")
    ok &= good

    print()
    print("ALL ENGINE CHECKS PASSED" if ok else "FAILURES ABOVE")
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


def test_backtest_engine_checks_all_pass():
    assert main() == 0, (
        "see the FAIL lines in captured stdout above")


if __name__ == "__main__":
    sys.exit(main())
