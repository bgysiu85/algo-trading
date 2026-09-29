"""BREIT-CAP walk (sim.py) on crafted orders: entry fills, same-bar stop, trail, targets, sizing, skips
(G5 order-of-events tests)."""
from __future__ import annotations

import numpy as np
import pytest

from strategy.breit_cap import spec as S
from strategy.breit_cap import signals as SG
from strategy.breit_cap.sim import simulate
from strategy.futbt import core as K
from tests.strategy.futbt.synth import frame_from_close

N = 40


def mk_frame(**kw):
    return frame_from_close(np.full(N, 100.0), spread=0.5, mult=1.0, tick_usd=0.01, **kw)


def mk_sig(fr, params=S.PRIMARY, mid=None):
    n = fr.n
    return SG.Signals(n, params, np.zeros((2, n), bool), np.full((2, n), np.nan), np.full((2, n), np.nan),
                      np.full((2, n), -1, np.int64), np.zeros((2, n), np.int64), np.full((2, n), np.nan),
                      np.full((2, n), -1, np.int64), np.full((2, n), np.nan),
                      np.full(n, 100.0) if mid is None else mid, np.full(n, 1.0))


def order(sg, j, side=1, entry=101.0, stop=97.0, grade=2, k=5, tgt50=np.nan, dat=4.0):
    s = 0 if side == 1 else 1
    sg.ok[s, j], sg.entry[s, j], sg.stop[s, j], sg.grade[s, j] = True, entry, stop, grade
    sg.k[s, j], sg.d_atr[s, j], sg.run_id[s, j], sg.tgt50[s, j] = k, dat, j - 4, tgt50


def run(fr, sg, integer=False, equity=1000.0):
    return simulate(fr, sg, equity=equity, integer=integer)


def test_buy_stop_fills_at_the_level_when_the_bar_trades_through_it():
    fr = mk_frame()
    fr.h[6] = 101.6                                    # trades above E = 101
    sg = mk_sig(fr)
    order(sg, 5)
    t = run(fr, sg)[0][0]
    assert (t.entry_j, t.entry_px, t.direction) == (6, 101.0, 1)
    assert t.qty == pytest.approx(0.01 * 1000 / (101.0 - 97.0))     # grade 2 -> 1%
    assert (t.grade, t.k, t.arm) == (2, 5, "B")


def test_a_gap_above_the_stop_fills_at_the_open():
    fr = mk_frame()
    fr.o[6], fr.h[6] = 103.0, 103.5
    sg = mk_sig(fr)
    order(sg, 5)
    assert run(fr, sg)[0][0].entry_px == 103.0


def test_an_order_that_does_not_trade_is_dropped_and_counted():
    fr = mk_frame()                                    # highs 100.5 < 101
    sg = mk_sig(fr)
    order(sg, 5)
    tr, k = run(fr, sg)
    assert tr == [] and k["unfilled"] == 1


def test_an_entry_bar_that_trades_to_the_initial_stop_is_stopped_that_bar():
    fr = mk_frame()
    fr.h[6], fr.l[6] = 101.5, 96.5
    sg = mk_sig(fr)
    order(sg, 5)
    t = run(fr, sg)[0][0]
    assert (t.exit_j, t.reason, t.exit_px, t.stop_fill) == (6, "same_bar_stop", 97.0, True)


def test_the_trail_starts_from_the_bar_after_entry_and_uses_the_prior_bar_low():
    fr = mk_frame()
    fr.h[6] = 101.6
    fr.l[6] = 99.0                                     # entry bar low
    fr.l[7] = 99.5                                     # bar 7 does not reach the trail (99.0 - tick)
    fr.h[7], fr.l[8], fr.h[8] = 103.0, 98.0, 103.0     # bar 8 trades below the trail 99.5-0.01
    sg = mk_sig(fr)
    order(sg, 5)
    tr, _ = run(fr, sg)
    t = tr[0]
    assert t.exit_j == 8 and t.reason == "trailed_stop" and t.stop_fill
    assert t.exit_px == pytest.approx(99.5 - fr.tick)  # stop = prior bar (7) low - 1 tick; ratcheted from 99.0-tick


def test_the_trail_never_loosens():
    fr = mk_frame()
    fr.h[6] = 101.6
    fr.l[6] = 99.5
    fr.l[7] = 99.0                                     # a LOWER prior low: stop must stay at 99.5 - tick
    fr.l[8] = 99.2                                     # trades below 99.49
    sg = mk_sig(fr)
    order(sg, 5)
    t = run(fr, sg)[0][0]
    assert t.exit_j == 7 and t.exit_px == pytest.approx(99.5 - fr.tick) and t.reason == "trailed_stop"


def test_a_stop_gap_exits_at_the_open():
    fr = mk_frame()
    fr.h[6] = 101.6
    fr.o[9], fr.l[9] = 90.0, 89.0
    sg = mk_sig(fr)
    order(sg, 5)
    t = run(fr, sg)[0][0]
    assert (t.exit_j, t.exit_px, t.reason, t.stop_fill) == (9, 90.0, "trailed_stop", True)


def test_short_side_mirrors_with_a_sell_stop_and_half_size():
    fr = mk_frame()
    fr.l[6] = 98.9
    sg = mk_sig(fr)
    order(sg, 5, side=-1, entry=99.0, stop=103.0, grade=2)
    t = run(fr, sg)[0][0]
    assert (t.direction, t.entry_px) == (-1, 99.0)
    assert t.qty == pytest.approx(0.5 * 0.01 * 1000 / 4.0) and t.risk_frac == pytest.approx(0.005)


def test_graded_risk_by_band_and_the_flat_variant():
    fr = mk_frame()
    fr.h[6] = 101.6
    for g, r in ((0, 0.005), (1, 0.005), (2, 0.01), (3, 0.01), (4, 0.02), (5, 0.02)):
        sg = mk_sig(fr)
        order(sg, 5, grade=g)
        assert run(fr, sg)[0][0].risk_frac == pytest.approx(r)
    sg = mk_sig(fr, S.VARIANTS["flat-1pct"])
    order(sg, 5, grade=5)
    assert run(fr, sg)[0][0].risk_frac == pytest.approx(0.01)


def test_min_grade_and_sides_filters():
    fr = mk_frame()
    fr.h[6] = 101.6
    sg = mk_sig(fr, S.VARIANTS["grade>=2"])
    order(sg, 5, grade=1)
    tr, k = run(fr, sg)
    assert tr == [] and k["grade_skipped"] == 1
    sg2 = mk_sig(fr, S.VARIANTS["short-only"])
    order(sg2, 5, side=1)
    tr, k = run(fr, sg2)
    assert tr == [] and k["side_off"] == 1


def test_a_setup_while_a_position_is_open_is_counted_not_taken():
    fr = mk_frame()
    fr.h[6], fr.h[10] = 101.6, 101.6
    sg = mk_sig(fr)
    order(sg, 5)
    order(sg, 9)
    tr, k = run(fr, sg)
    assert len(tr) == 1 and k["skipped_in_position"] == 1


def test_integer_zero_contracts_is_a_counted_skip():
    fr = mk_frame()
    fr.h[6] = 101.6
    sg = mk_sig(fr)
    order(sg, 5, stop=1.0)
    tr, k = run(fr, sg, integer=True, equity=1000.0)
    assert tr == [] and k["skipped_size"] == 1


def test_50pct_target_used_only_beyond_the_fill_and_stop_first_in_one_bar():
    fr = mk_frame()
    fr.h[6] = 101.6
    fr.h[9] = 106.0
    sg = mk_sig(fr, S.VARIANTS["+50pct-target"])
    order(sg, 5, tgt50=105.0)
    t = run(fr, sg)[0][0]
    assert (t.reason, t.exit_px, t.exit_j, t.stop_fill) == ("target", 105.0, 9, False)
    fr.l[9] = 90.0                                     # target and stop both in bar 9: the stop
    assert run(fr, sg)[0][0].reason in ("initial_stop", "trailed_stop")
    sg2 = mk_sig(fr, S.VARIANTS["+50pct-target"])
    order(sg2, 5, tgt50=100.5)                         # below the fill (101): no target
    assert run(fr, sg2)[0][0].reason != "target"


def test_ma_target_is_the_prior_close_sma20_refreshed_each_bar():
    fr = mk_frame()
    fr.h[6] = 101.6
    mid = np.full(N, 120.0)
    mid[7] = 102.0
    fr.h[8] = 102.3
    sg = mk_sig(fr, S.VARIANTS["+MA-target"], mid=mid)
    order(sg, 5)
    t = run(fr, sg)[0][0]
    assert (t.reason, t.exit_j, t.exit_px) == ("target", 8, 102.0)


def test_the_last_bar_closes_at_the_close():
    fr = mk_frame()
    fr.h[6] = 101.6
    sg = mk_sig(fr)
    order(sg, 5, stop=50.0)
    t = run(fr, sg)[0][0]
    assert (t.reason, t.exit_j, t.exit_px) == ("data_end", N - 1, fr.c[-1])


def test_booking_and_marks_agree_on_a_buy_stop_fill_inside_the_bar():
    fr = mk_frame()
    fr.h[6] = 101.6
    fr.l[9] = 90.0
    sg = mk_sig(fr)
    order(sg, 5)
    tr, _ = run(fr, sg)
    b = K.book_trade(tr[0], fr)
    dm = K.daily_marks(tr, fr)
    for i, lv in enumerate(("low", "mid", "high")):
        assert dm[:, i].sum() == pytest.approx(b["net_" + lv])
