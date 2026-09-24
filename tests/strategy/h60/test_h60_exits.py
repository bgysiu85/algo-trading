"""strategy.h60.exits -- the one exit implementation (REGISTERED_h60_v0.md §2.3).

Every case is a hand-built price path whose right answer can be read off it.
"""
from __future__ import annotations

import numpy as np
import pytest

from strategy.h60 import exits as X
from tests.strategy.h60 import _synth as S


def sym(closes, *, opens=None, highs=None, lows=None, n_days=None):
    n_days = n_days or len(closes) // 7
    days = S.sessions(n_days)
    df = S.bars_from_closes("AAA", days, closes, opens=opens, highs=highs, lows=lows,
                            spread=0.0)
    return S.panel([df]).arrays("AAA")


def flat(n_days=8, px=100.0):
    return np.full(n_days * 7, px)


def test_time_cap_is_the_close_of_the_fifth_session_after_entry():
    a = sym(flat())
    res = X.simulate(a, [1], X.ExitSpec(trail_pct=5.0))     # fill at session 0, 10:30
    assert res.reason[0] == X.R_TIME
    assert a.s[res.exit_idx[0]] == 5 and a.bar[res.exit_idx[0]] == 6
    assert res.phase[0] == X.PH_CLOSE


def test_a_1530_fill_bar_counts_its_own_session():
    a = sym(flat(n_days=9))
    res = X.simulate(a, [7], X.ExitSpec())                  # fill = session 1 09:30
    assert a.s[res.exit_idx[0]] == 6 and a.bar[res.exit_idx[0]] == 6


def test_trail_is_from_the_previous_bars_peak_and_seeded_at_the_fill():
    c = flat()
    h = c.copy()
    l = c.copy()
    # fill bar (idx 1) makes a high of 110 but closes at 100; the next bar's
    # low is 99. Seeded at the FILL (100) the trail is 95 on the fill bar and
    # 104.5 on bar 2 -- so bar 2 exits at min(104.5, open=100) = 100.
    h[1] = 110.0
    l[2] = 99.0
    res = X.simulate(sym(c, highs=h, lows=l), [1], X.ExitSpec(trail_pct=5.0))
    assert res.exit_idx[0] == 2 and res.reason[0] == X.R_TRAIL
    assert res.exit_px[0] == 100.0 and res.phase[0] == X.PH_OPEN   # gapped through


def test_the_fill_bars_own_high_does_not_arm_its_own_trail():
    c = flat()
    h, l = c.copy(), c.copy()
    h[1], l[1] = 110.0, 96.0      # a 95 trail from the peak 110 would be 104.5
    res = X.simulate(sym(c, highs=h, lows=l), [1], X.ExitSpec(trail_pct=5.0))
    # 96 > 95: the fill bar survives; its high arms the trail for bar 2 only
    assert res.exit_idx[0] == 2 and res.reason[0] == X.R_TRAIL


def test_intrabar_stop_fills_at_the_level():
    c = flat()
    l = c.copy()
    l[3] = 94.0
    res = X.simulate(sym(c, lows=l), [1], X.ExitSpec(trail_pct=5.0))
    assert res.exit_idx[0] == 3 and res.exit_px[0] == pytest.approx(95.0)
    assert res.phase[0] == X.PH_INTRA and res.stop_fill[0]


def test_gap_through_a_stop_fills_at_the_open_never_the_level():
    c = flat()
    o, l = c.copy(), c.copy()
    o[3], l[3] = 90.0, 89.0
    res = X.simulate(sym(c, opens=o, lows=l), [1], X.ExitSpec(trail_pct=5.0))
    assert res.exit_px[0] == 90.0 and res.phase[0] == X.PH_OPEN


def test_stop_wins_when_one_bar_reaches_stop_and_target():
    c = flat()
    h, l = c.copy(), c.copy()
    h[3], l[3] = 130.0, 80.0
    res = X.simulate(sym(c, highs=h, lows=l), [1],
                     X.ExitSpec(fixed_stop=True, target_r=2.0), fixed_stop=[90.0])
    assert res.reason[0] == X.R_STOP and res.exit_px[0] == 90.0


def test_target_fills_at_the_level_even_on_a_gap_open():
    c = flat()
    h = c.copy()
    h[3] = 125.0
    res = X.simulate(sym(c, highs=h), [1], X.ExitSpec(fixed_stop=True, target_r=2.0),
                     fixed_stop=[90.0])                       # R = 10, target 120
    assert res.reason[0] == X.R_TARGET and res.exit_px[0] == 120.0
    o = c.copy()
    o[3] = h[3] = 123.0
    res = X.simulate(sym(c, opens=o, highs=h), [1],
                     X.ExitSpec(fixed_stop=True, target_r=2.0), fixed_stop=[90.0])
    assert res.exit_px[0] == 120.0 and res.phase[0] == X.PH_OPEN   # never the better open


def test_close_decided_exit_fills_at_the_next_open():
    c = flat()
    o = c.copy()
    o[5] = 101.0
    x = np.zeros(len(c), bool)
    x[4] = True
    res = X.simulate(sym(c, opens=o), [1], X.ExitSpec(close_exit=True), xsig=x)
    assert res.exit_idx[0] == 5 and res.exit_px[0] == 101.0
    assert res.reason[0] == X.R_SIGNAL and res.phase[0] == X.PH_OPEN


def test_a_signal_before_the_fill_is_not_an_exit():
    c = flat()
    x = np.zeros(len(c), bool)
    x[0] = True                                  # the signal bar itself
    res = X.simulate(sym(c), [1], X.ExitSpec(close_exit=True), xsig=x)
    assert res.reason[0] == X.R_TIME


def test_a_close_signal_on_the_cap_bar_is_the_time_cap():
    c = flat()
    x = np.zeros(len(c), bool)
    cap_bar = 5 * 7 + 6
    x[cap_bar] = True
    res = X.simulate(sym(c), [1], X.ExitSpec(close_exit=True), xsig=x)
    assert res.exit_idx[0] == cap_bar and res.reason[0] == X.R_TIME


def test_last_bar_of_the_series_is_the_exit():
    a = sym(flat(n_days=3))
    res = X.simulate(a, [1], X.ExitSpec(trail_pct=5.0))
    assert res.exit_idx[0] == a.n - 1 and res.reason[0] == X.R_DATA_END


def test_a_gap_in_the_symbols_sessions_across_the_cap_exits_before_it():
    days = S.sessions(12)
    import pandas as pd
    df = S.bars_from_closes("AAA", days, flat(12), spread=0.0)
    df = df[~df["session"].isin(days[3:8])]        # sessions 3-7 missing for AAA
    other = S.bars_from_closes("BBB", days, flat(12), spread=0.0)
    a = S.panel([df, other]).arrays("AAA")
    res = X.simulate(a, [1], X.ExitSpec())
    assert a.s[res.exit_idx[0]] == 2 and res.reason[0] == X.R_DATA_GAP


def test_ratchet_never_loosens_and_applies_from_the_next_bar():
    c = flat()
    l = c.copy()
    rat = np.full(len(c), np.nan)
    rat[2] = 97.0
    rat[3] = 93.0                  # lower: ignored
    l[3] = 97.5                    # above 97: survives
    l[4] = 96.5                    # below the 97 carried from bar 2
    res = X.simulate(sym(c, lows=l), [1], X.ExitSpec(fixed_stop=True, ratchet=True),
                     fixed_stop=[90.0], ratchet=rat)
    assert res.exit_idx[0] == 4 and res.exit_px[0] == 97.0
    assert res.reason[0] == X.R_SAFETY


def test_ratchet_value_on_a_bar_does_not_stop_that_same_bar():
    c = flat()
    l = c.copy()
    rat = np.full(len(c), np.nan)
    rat[2] = 99.0
    l[2] = 98.0                    # the level set at bar 2's close is not live on bar 2
    res = X.simulate(sym(c, lows=l), [1], X.ExitSpec(fixed_stop=True, ratchet=True),
                     fixed_stop=[90.0], ratchet=rat)
    assert res.reason[0] == X.R_TIME


def test_fill_at_or_below_its_own_stop_is_void():
    res = X.simulate(sym(flat()), [1, 2], X.ExitSpec(fixed_stop=True),
                     fixed_stop=[100.0, 99.0])
    assert list(res.void) == [True, False]


def test_atr_trail_reads_the_previous_bars_atr():
    c = flat()
    l = c.copy()
    l[3] = 93.0
    atr_prev = np.full(len(c), 2.0)
    atr_prev[3] = 50.0        # if the bar's OWN width leaked in, no exit
    res = X.simulate(sym(c, lows=l), [1], X.ExitSpec(trail_atr=2.0),
                     atr_prev=np.where(np.arange(len(c)) == 3, 3.0, 2.0))
    assert res.exit_idx[0] == 3 and res.exit_px[0] == pytest.approx(94.0)


def test_many_entries_at_once_match_one_at_a_time():
    a = S.panel([S.random_walk("AAA", S.sessions(20))]).arrays("AAA")
    fills = np.arange(1, a.n - 1, 3)
    spec = X.ExitSpec(trail_pct=5.0)
    together = X.simulate(a, fills, spec)
    for k, f in enumerate(fills):
        alone = X.simulate(a, [f], spec)
        assert alone.exit_idx[0] == together.exit_idx[k]
        assert alone.exit_px[0] == together.exit_px[k]


def test_marks():
    a = sym(flat())
    res = X.simulate(a, [1], X.ExitSpec())
    assert X.entry_mark(a, res)[0] == 2 * 1
    assert X.exit_mark(a, res)[0] == 2 * (5 * 7 + 6) + 1
