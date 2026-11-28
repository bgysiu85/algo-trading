"""WICK-REV trade-shaped dollars (W15-0063 sec 4). Flat bars: ATR = 2, entry 100, short stop 102 / target 98."""
from __future__ import annotations

import numpy as np

from strategy.wick_rev import signals as G
from strategy.wick_rev import spec as S
from strategy.wick_rev import trades as TR
from tests.strategy.wick_rev.synth import flat, minute_fine, series

T = 30


def _run(mod=None, side=1, market="MNQ", idx=(T,), fine_for=None):
    o, h, l, c = flat(60)
    if mod:
        mod(o, h, l, c)
    s = series(o, h, l, c, market=market)
    if fine_for:
        s.fine_t, s.fine_h, s.fine_l = minute_fine(s, *fine_for)
    f = G.features(s)
    return TR.simulate(s, f, np.array(idx), side), s


def test_time_exit_at_close_of_t_plus_3_costs_two_sides():
    r, _ = _run()
    assert r["reason"].tolist() == ["time"] and r["gross"][0] == 0.0
    assert abs(r["cost"]["mid"] - 2 * (0.62 + 0.5)) < 1e-9          # MNQ: fee 0.62 + 1 tick $0.50, two sides
    assert abs(r["cost"]["low"] - 2 * 0.62) < 1e-9 and abs(r["cost"]["high"] - 2 * (0.62 + 1.0)) < 1e-9
    assert abs(r["net"]["mid"][0] + 2.24) < 1e-9


def test_target_stop_and_dollar_values_short_and_long():
    def tgt(o, h, l, c):
        l[T + 2] = 97.5                                             # target 98 touched on t+2
    r, _ = _run(tgt)
    assert r["reason"].tolist() == ["target"] and r["exit"][0] == 98.0 and r["gross"][0] == 4.0   # 2 pts x $2

    def stp(o, h, l, c):
        h[T + 1] = 102.5                                            # stop 102 touched on the entry bar
    r, _ = _run(stp)
    assert r["reason"].tolist() == ["stop"] and r["gross"][0] == -4.0
    r, _ = _run(stp, side=-1)                                       # long: stop 98 / target 102 -> target at 102
    assert r["reason"].tolist() == ["target"] and r["gross"][0] == 4.0
    r, _ = _run(tgt, side=-1, market="MCL")
    assert r["gross"][0] == 0.0 or r["reason"].tolist() == ["stop"]
    r, _ = _run(tgt, side=1, market="MCL")
    assert r["gross"][0] == 200.0                                   # 2.00 x $100 per $1


def test_gap_through_stop_fills_at_the_open():
    def gap(o, h, l, c):
        o[T + 2], h[T + 2], l[T + 2], c[T + 2] = 103.0, 103.5, 102.5, 103.0
    r, _ = _run(gap)
    assert r["reason"].tolist() == ["stop-gap"] and r["exit"][0] == 103.0 and r["gross"][0] == -6.0


def test_double_touch_is_stop_first_unless_finer_bars_say_otherwise():
    def both(o, h, l, c):
        h[T + 1], l[T + 1] = 102.5, 97.5
    r, _ = _run(both)
    assert r["reason"].tolist() == ["stop"]
    hs = [100.5] * 5 + [102.5] * 5 + [100.5] * 50
    ls = [99.5] * 2 + [97.5] + [99.5] * 57                          # target comes first
    r, _ = _run(both, fine_for=(T + 1, hs, ls))
    assert r["reason"].tolist() == ["target"]


def test_one_position_at_a_time_and_skips_are_counted():
    r, _ = _run(idx=(T, T + 1, T + 2, T + 3))
    # time exit at close of t+3 = bar 33: signals at 31 and 32 are blocked, the one at 33 is allowed
    assert r["signal_bar"].tolist() == [30, 33] and r["skipped"] == 2


def test_costs_come_from_the_ibkr_table_for_each_market():
    assert S.side_cost("MCL", "mid") == 0.77 + 1.0 and S.side_cost("MNQ", "high") == 0.62 + 1.0
