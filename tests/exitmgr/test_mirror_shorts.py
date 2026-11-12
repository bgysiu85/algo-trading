"""Shorts mirror (left to sub 4 by the sub 2 handover): a short on real bars, run through the long-only rules on the reflected
bars (exitmgr.mirror), must give the exit a hand calculation of the short rule gives. Entry 100.00 short, A0 = 1,
S = 101.00 (above), tick 0.01. Each case is the mirror of a long case in test_rules.py, written out in real short prices."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from exitmgr import rules as R
from exitmgr.mirror import mirror_bars, reflect, short_inputs, to_short_level
from strategy.exit_cmp.walk import walk

ENTRY, A0, S0, TICK = 100.0, 1.0, 101.0, 0.01


def mk(rows, hist=-1.0, atr=1.0):
    o, h, l, c = (np.array(x, float) for x in zip(*rows))
    n = len(o)
    return SimpleNamespace(o=o, h=h, l=l, c=c, atr=np.full(n, atr), e9=np.full(n, np.nan), e21=np.full(n, np.nan),
                           hist=np.full(n, hist) if np.isscalar(hist) else np.array(hist, float))


def run_short(rows, rule, hist=-1.0, s0=S0):
    b = mk(rows, hist)
    mb = mirror_bars(b, ENTRY)
    e, s0m = short_inputs(ENTRY, s0)
    comps = R.build(rule, mb, 0, e, A0, s0m, TICK)
    x = walk(mb, 0, e, A0, s0m, comps, scenario="HOLD", sess_end=np.zeros(len(rows), bool), cap=None, n=len(rows))
    return x.exit_j, round(to_short_level(x.exit_px, ENTRY), 6), x.reason


def test_reflection_properties():
    rng = np.random.default_rng(7)
    c = 100 + np.cumsum(rng.normal(0, 0.2, 60))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) + 0.1
    l = np.minimum(o, c) - 0.1
    b = SimpleNamespace(o=o, h=h, l=l, c=c, atr=np.full(60, 0.5), e9=c, e21=c, hist=c - 100)
    m = mirror_bars(b, ENTRY)
    mm = mirror_bars(m, ENTRY)
    for k in ("o", "h", "l", "c", "hist"):
        assert np.allclose(getattr(mm, k), getattr(b, k))
    assert (m.h >= m.l).all() and np.allclose(m.h - m.l, h - l)            # ranges (so true range / ATR) unchanged

    def ema(x, n):
        out, a = np.empty_like(x), 2 / (n + 1)
        out[0] = x[0]
        for i in range(1, len(x)):
            out[i] = a * x[i] + (1 - a) * out[i - 1]
        return out
    macd = lambda x: ema(x, 12) - ema(x, 26) - ema(ema(x, 12) - ema(x, 26), 9)
    assert np.allclose(macd(reflect(c, ENTRY)), -macd(c))                    # MACD histogram changes sign
    assert np.allclose(ema(reflect(c, ENTRY), 9), reflect(ema(c, 9), ENTRY))  # EMAs reflect


def test_b_stop_short_stop_above_at_level_or_gap_open():
    assert run_short([(100, 100.1, 99.8, 99.9), (100.0, 101.5, 99.9, 101.3)], "B-STOP") == (1, 101.0, "S")
    assert run_short([(100, 100.1, 99.8, 99.9), (102.0, 102.5, 101.6, 101.9)], "B-STOP") == (1, 102.0, "S")


def test_r_ben_short_ratchet_arms_at_020_below_and_halves_profit():
    # lowest low 99.50 <= 99.80 -> buy-stop 100 - 0.5 x 0.50 = 99.75 from bar 1
    assert run_short([(100, 100.05, 99.5, 99.7), (99.7, 99.9, 99.6, 99.8)], "R-BEN") == (1, 99.75, "RATCHET")
    # low only 99.85: not armed; falls to S
    assert run_short([(100, 100.05, 99.85, 99.9), (99.9, 100.0, 99.81, 99.9), (100.0, 102.0, 99.9, 101.5)],
                     "R-BEN")[2] == "S"


def test_r_mom_m1_short_three_green_bars_and_macd_positive_buys_next_open():
    green = lambda o: (o, o + 0.3, o - 0.1, o + 0.2)
    rows = [(100, 100.05, 99.9, 100.0), green(100.0), green(100.2), green(100.4), (100.5, 100.7, 100.4, 100.6),
            (100.6, 100.65, 100.55, 100.6)]
    assert run_short(rows, "R-MOM", hist=+1.0, s0=102.0) == (4, 100.5, "M1")
    assert run_short(rows, "R-MOM", hist=-0.5, s0=102.0)[2] == "data_end"


def test_r_mom_m2_short_hammer_buy_stop_at_body_high_plus_tick():
    # bar 1: range 1.05, lower wick 0.95 >= 50 %, range >= 0.3 A0 -> buy-stop at body high max(o, c) 99.95 + 0.01 = 99.96
    rows = [(100, 100.05, 99.9, 99.95), (99.95, 100.0, 98.95, 99.9), (99.9, 100.2, 99.85, 100.1)]
    assert run_short(rows, "R-MOM", hist=-1.0) == (2, pytest.approx(99.96), "M2")


def test_x_jump_short_arms_at_1r_and_jumps_above_a_confirmed_swing_high():
    rows = [(100, 100.1, 99.9, 99.95),          # 0 entry
            (99.9, 99.95, 98.9, 98.95),          # 1 low 98.90 <= 100 - 1 R0 (R0 = 1.00): armed
            (98.6, 98.7, 98.3, 98.4),
            (98.4, 98.5, 98.0, 98.1),
            (98.1, 98.9, 98.0, 98.8),            # 4 swing high 98.90 (bars 2, 3, 5, 6 lower)
            (98.8, 98.85, 98.2, 98.3),
            (98.3, 98.4, 97.9, 98.0),            # 6 confirms bar 4 -> buy-stop 98.91 from bar 7
            (98.0, 99.0, 97.9, 98.95)]
    assert run_short(rows, "X-JUMP") == (7, pytest.approx(98.91), "JUMP")


def test_short_level_mapping_round_trip():
    for lv in (98.91, 100.0, 101.37):
        assert to_short_level(to_short_level(lv, ENTRY), ENTRY) == pytest.approx(lv)
    assert short_inputs(100.0, 101.0) == (100.0, 99.0)
