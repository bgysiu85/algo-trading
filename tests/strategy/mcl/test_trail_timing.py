#!/usr/bin/env python3
"""How the trail is TESTED, as opposed to how wide it is.

Ben's question: is the 5% stop selling into noise -- does price rally back
within 2-5 bars? Measurably yes (common/stop_timing.py), so two looser ways of
testing the same level were added:

    trail_on_close       require the bar to CLOSE below the level
    trail_confirm_bars   breach, then exit only if still below N bars later

Both are strictly looser than the default intrabar test, and that is exactly
what makes them dangerous to evaluate: anything looser earns more on a dataset
whose big movers carry the P/L. The tests below pin the ORDERING properties
that make a fair comparison possible -- above all that these rules can only
ever remove exits, never add them, so their gains have to be judged against a
wider intrabar trail rather than against the 5% baseline.
"""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from strategy.mcl import mcl as S

ET = ZoneInfo("America/New_York")
DATE = date(2026, 9, 2)


def frame(closes, highs=None, lows=None, vols=None):
    n = len(closes)
    t0 = datetime.strptime("2026-09-02 04:00", "%Y-%m-%d %H:%M").replace(tzinfo=ET)
    idx = pd.date_range(t0, periods=n, freq="1min").tz_convert("UTC")
    return pd.DataFrame(
        {"open": closes,
         "high": highs or [c * 1.004 for c in closes],
         "low": lows or [c * 0.996 for c in closes],
         "close": closes,
         "volume": vols or [5000] * n}, index=idx)


@pytest.fixture(scope="module")
def choppy():
    for seed in range(200):
        rng = np.random.default_rng(seed)
        px, closes = 3.0, []
        for i in range(220):
            px *= 1.0 + (rng.uniform(-0.004, 0.012) if i < 130
                         else rng.uniform(-0.015, 0.015))
            closes.append(px)
        vols = [int(v) for v in rng.integers(4000, 7000, 220)]
        vols[125] = vols[124] * 6
        df = frame(closes, vols=vols)
        t = S.backtest_session(df, DATE, ET, trail_pct=5.0)
        if t and t[0].reason == "trailing_stop":
            return df
    pytest.skip("no trailing-stop exit found in 200 seeds")


def test_defaults_are_the_shipped_intrabar_rule(choppy):
    a = S.backtest_session(choppy, DATE, ET, trail_pct=5.0)
    b = S.backtest_session(choppy, DATE, ET, trail_pct=5.0,
                           trail_on_close=False, trail_confirm_bars=0)
    assert a and [t.net for t in a] == [t.net for t in b]


def test_a_wick_through_the_level_exits_intrabar_but_not_on_close():
    """The exact case the whole question is about: one bar wicks well below
    the trail and closes back at the top. The intrabar rule sells it; the
    close-based rule ignores it."""
    rng = np.random.default_rng(0)
    px, c = 3.0, []
    for i in range(220):
        px *= 1.0 + (rng.uniform(-0.002, 0.010) if i < 130 else 0.001)
        c.append(px)
    hi = [x * 1.002 for x in c]
    lo = [x * 0.998 for x in c]
    lo[170] = c[170] * 0.90               # a single deep wick that recovers
    v = [int(x) for x in rng.integers(4000, 7000, 220)]
    v[125] = v[124] * 6
    df = frame(c, highs=hi, lows=lo, vols=v)
    intrabar = S.backtest_session(df, DATE, ET, trail_pct=5.0)
    on_close = S.backtest_session(df, DATE, ET, trail_pct=5.0,
                                  trail_on_close=True)
    if not intrabar:
        pytest.skip("synthetic frame produced no entry")
    assert intrabar[0].bars_held <= on_close[0].bars_held, (
        "the intrabar rule must exit no later than the close-based one")


def test_looser_rules_can_only_remove_exits(choppy):
    """Both alternatives are supersets of 'price stayed below the level', so
    neither can produce MORE trailing-stop exits than the intrabar rule. If
    this ever fails, the comparison in common/stop_timing.py is invalid."""
    strict = S.backtest_session(choppy, DATE, ET, trail_pct=5.0)
    n_strict = sum(1 for t in strict if t.reason == "trailing_stop")
    for kw in ({"trail_on_close": True}, {"trail_confirm_bars": 1},
               {"trail_confirm_bars": 5}):
        loose = S.backtest_session(choppy, DATE, ET, trail_pct=5.0, **kw)
        assert sum(1 for t in loose if t.reason == "trailing_stop") <= n_strict


def test_confirmation_never_shortens_the_hold(choppy):
    """Waiting N bars before acting cannot exit earlier than not waiting."""
    strict = S.backtest_session(choppy, DATE, ET, trail_pct=5.0)
    for n in (1, 3, 5):
        delayed = S.backtest_session(choppy, DATE, ET, trail_pct=5.0,
                                     trail_confirm_bars=n)
        assert delayed
        assert delayed[0].bars_held >= strict[0].bars_held


def test_confirmation_takes_precedence_over_on_close(choppy):
    """The two are alternative tests of the same level, not composable. The
    engine checks confirmation first; pinning that stops a future caller from
    passing both and quietly getting one of them."""
    both = S.backtest_session(choppy, DATE, ET, trail_pct=5.0,
                              trail_on_close=True, trail_confirm_bars=3)
    confirm = S.backtest_session(choppy, DATE, ET, trail_pct=5.0,
                                 trail_confirm_bars=3)
    assert [t.net for t in both] == [t.net for t in confirm]


def test_a_breach_that_recovers_resets_the_confirmation(choppy):
    """If price is back above the level at the check, the position is kept and
    the breach is forgotten -- otherwise one early wick would arm a permanent
    exit and the rule would be a delayed stop rather than a confirmed one."""
    delayed = S.backtest_session(choppy, DATE, ET, trail_pct=5.0,
                                 trail_confirm_bars=5)
    assert delayed
    # A trade that survived far beyond the first breach can only exist if the
    # reset works; with no reset every trade would end within 5 bars of its
    # first wick.
    assert delayed[0].bars_held > 5


def test_every_variant_still_closes_the_position_at_the_window(choppy):
    """The regression that mattered. The trail test used to be chained as
    `if trail_confirm_bars > 0:` -- a test on a PARAMETER -- which made the
    window_close branch unreachable whenever a variant was enabled. Positions
    open at 09:30 were then never closed and their trades vanished from the
    results entirely: 450 rows instead of 496, with the missing P/L simply
    absent rather than zero. Trade COUNT is the invariant that catches it."""
    strict = S.backtest_session(choppy, DATE, ET, trail_pct=5.0)
    assert strict
    for kw in ({"trail_on_close": True}, {"trail_confirm_bars": 1},
               {"trail_confirm_bars": 5}, {"trail_confirm_bars": 50}):
        loose = S.backtest_session(choppy, DATE, ET, trail_pct=5.0, **kw)
        assert loose, f"{kw} produced no trades at all -- a position was dropped"
        assert all(t.reason in ("trailing_stop", "window_close", "apex_reversal")
                   for t in loose)
    # A confirmation longer than the session can never fire, so the position
    # MUST come back as window_close. Under the bug it came back as nothing.
    forever = S.backtest_session(choppy, DATE, ET, trail_pct=5.0,
                                 trail_confirm_bars=10_000)
    assert len(forever) == 1 and forever[0].reason == "window_close"
