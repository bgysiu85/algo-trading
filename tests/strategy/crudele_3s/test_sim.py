"""CRUDELE-3S walk (sim.py) on crafted signals: every fill, exit and skip rule, one per test."""
from __future__ import annotations

import numpy as np
import pytest

from strategy.crudele_3s import spec as S
from strategy.crudele_3s import states as ST
from strategy.crudele_3s.sim import simulate
from strategy.futbt import core as K
from tests.strategy.futbt.synth import frame_from_close

N = 40


def mk_frame(close=None, **kw):
    close = np.full(N, 100.0) if close is None else np.asarray(close, float)
    return frame_from_close(close, spread=0.5, mult=1.0, tick_usd=0.01, **kw)


def mk_sig(fr, arms=S.ARMS, ma=None, mid=None, **kw):
    n = fr.n
    sg = ST.Signals(n, S.PRIMARY.with_(arms=tuple(arms)), np.zeros(n, np.int8), np.zeros(n, np.int8),
                    np.zeros(n, np.int8), np.full(n, np.nan), np.full(n, np.nan), np.full(n, np.nan),
                    np.full(n, -1, np.int64), np.zeros(n, bool), np.full(n, -1, np.int64),
                    np.full(n, 100.0) if mid is None else mid, np.full(n, np.nan) if ma is None else ma,
                    np.full(n, 1.0), np.full(n, 0.1))
    for k, v in kw.items():
        getattr(sg, k)[...] = v if not isinstance(v, dict) else getattr(sg, k)
        if isinstance(v, dict):
            for j, val in v.items():
                getattr(sg, k)[j] = val
    return sg


def sig_at(sg, j, arm, d, stop, tgt=np.nan, l30=np.nan, ep=0):
    sg.sig_arm[j], sg.sig_dir[j], sg.sig_stop[j], sg.sig_tgt[j], sg.sig_line30[j], sg.sig_ep[j] = \
        arm, d, stop, tgt, l30, ep


def run(fr, sg, integer=False, equity=100.0):
    return simulate(fr, sg, equity=equity, integer=integer)


# --- T ---------------------------------------------------------------------------------------------
def test_t_long_enters_next_open_sized_from_the_fill_and_exits_at_the_stop():
    close = np.full(N, 100.0)
    close[6:] = 100.0
    fr = mk_frame(close)
    fr.o[6] = 101.0                                        # entry open
    fr.l[9] = 95.0                                         # stop hit on bar 9
    sg = mk_sig(fr)
    sig_at(sg, 5, 1, 1, stop=99.0)
    tr, k = run(fr, sg)
    assert len(tr) == 1
    t = tr[0]
    assert (t.entry_j, t.entry_px, t.direction, t.arm) == (6, 101.0, 1, "T")
    assert t.qty == pytest.approx(0.01 * 100.0 / 2.0)                 # 1% of $100 over a 2.0 stop, mult 1
    assert (t.exit_j, t.exit_px, t.reason, t.stop_fill) == (9, 99.0, "stop", True)


def test_risk_is_a_fraction_of_equity_by_arm():
    fr = mk_frame()
    sg = mk_sig(fr)
    sig_at(sg, 5, 1, 1, stop=98.0)
    q_t = run(fr, sg, equity=10_000.0)[0][0].qty
    sg2 = mk_sig(fr)
    sig_at(sg2, 5, 2, 1, stop=98.0, tgt=110.0, l30=97.0)
    q_mr = run(fr, sg2, equity=10_000.0)[0][0].qty
    assert q_t == pytest.approx(0.01 * 10_000 / 2.0) and q_mr == pytest.approx(0.005 * 10_000 / 2.0)


def test_t_stop_gap_fills_at_the_open_and_pays_slippage_flag():
    fr = mk_frame()
    fr.o[9] = 90.0
    fr.l[9] = 89.0
    sg = mk_sig(fr)
    sig_at(sg, 5, 1, 1, stop=98.0)
    t = run(fr, sg)[0][0]
    assert (t.exit_j, t.exit_px, t.reason, t.stop_fill) == (9, 90.0, "stop_gap", True)


def test_void_when_the_entry_open_is_already_beyond_the_stop():
    fr = mk_frame()
    fr.o[6] = 97.0
    sg = mk_sig(fr)
    sig_at(sg, 5, 1, 1, stop=98.0)
    tr, k = run(fr, sg)
    assert tr == [] and k["voided"] == 1


def test_t_exits_at_the_next_open_after_a_close_below_the_ma_and_when_bands_come_in():
    close = np.full(N, 100.0)
    close[10] = 98.0
    fr = mk_frame(close)
    ma = np.full(N, 99.0)
    sg = mk_sig(fr, ma=ma)
    sig_at(sg, 5, 1, 1, stop=90.0)
    t = run(fr, sg)[0][0]
    assert (t.reason, t.exit_j) == ("ma", 11) and t.exit_px == fr.o[11] and not t.stop_fill
    sg2 = mk_sig(fr)
    sig_at(sg2, 5, 1, 1, stop=90.0, ep=3)
    sg2.bands_in_ep[12] = 3
    t2 = run(fr, sg2)[0][0]
    assert (t2.reason, t2.exit_j) == ("bands_in", 13)
    sg3 = mk_sig(fr)
    sig_at(sg3, 5, 1, 1, stop=90.0, ep=3)
    sg3.bands_in_ep[12] = 4                                      # another episode's bands: ignored
    assert run(fr, sg3)[0][0].reason == "data_end"


def test_t_target_is_used_only_if_beyond_the_fill():
    fr = mk_frame()
    fr.h[9] = 106.0
    sg = mk_sig(fr)
    sig_at(sg, 5, 1, 1, stop=90.0, tgt=105.0)
    t = run(fr, sg)[0][0]
    assert (t.reason, t.exit_px, t.exit_j, t.stop_fill) == ("target", 105.0, 9, False)
    sg2 = mk_sig(fr)
    sig_at(sg2, 5, 1, 1, stop=90.0, tgt=99.5)                    # below the fill (open 100): no target
    assert run(fr, sg2)[0][0].reason == "data_end"


def test_stop_and_target_in_one_bar_is_the_stop():
    fr = mk_frame()
    fr.h[9], fr.l[9] = 106.0, 95.0
    sg = mk_sig(fr)
    sig_at(sg, 5, 1, 1, stop=96.0, tgt=105.0)
    assert run(fr, sg)[0][0].reason == "stop"


def test_t_short_mirrors():
    fr = mk_frame()
    fr.l[9] = 94.0
    sg = mk_sig(fr)
    sig_at(sg, 5, 1, -1, stop=102.0, tgt=95.0)
    t = run(fr, sg)[0][0]
    assert (t.direction, t.reason, t.exit_px) == (-1, "target", 95.0)


# --- MR --------------------------------------------------------------------------------------------
def test_mr_short_target_line50_close_back_beyond_line30_and_time_stop():
    fr = mk_frame()
    fr.l[9] = 90.0
    sg = mk_sig(fr)
    sig_at(sg, 5, 2, -1, stop=105.0, tgt=95.0, l30=101.0)
    t = run(fr, sg)[0][0]
    assert (t.arm, t.reason, t.exit_px) == ("MR", "target", 95.0)
    close = np.full(N, 100.0)
    close[8] = 102.0                                             # a close back above line30 (short)
    fr2 = mk_frame(close)
    sg2 = mk_sig(fr2)
    sig_at(sg2, 5, 2, -1, stop=110.0, tgt=80.0, l30=101.0)
    t2 = run(fr2, sg2)[0][0]
    assert (t2.reason, t2.exit_j) == ("back30", 9)
    fr3 = mk_frame()
    sg3 = mk_sig(fr3)
    sig_at(sg3, 5, 2, -1, stop=110.0, tgt=80.0, l30=101.0)
    t3 = run(fr3, sg3)[0][0]
    assert (t3.reason, t3.entry_j, t3.exit_j) == ("time", 6, 6 + 10)   # bar 6 is bar 1; close of bar 15 -> open 16


def test_mr_void_when_the_open_is_already_through_the_target():
    fr = mk_frame()
    sg = mk_sig(fr)
    sig_at(sg, 5, 2, -1, stop=110.0, tgt=100.5, l30=101.0)      # short, open 100 <= target 100.5
    tr, k = run(fr, sg)
    assert tr == [] and k["void_target"] == 1


# --- C ---------------------------------------------------------------------------------------------
def test_c_target_is_the_prior_close_middle_band_refreshed_each_bar():
    fr = mk_frame()
    mid = np.full(N, 110.0)
    mid[7] = 103.0
    fr.h[8] = 103.4
    fr.o[6], fr.h[6] = 99.0, 99.5
    sg = mk_sig(fr, mid=mid)
    sig_at(sg, 5, 3, 1, stop=95.0)
    t = run(fr, sg)[0][0]
    assert (t.arm, t.exit_j, t.exit_px, t.reason) == ("C", 8, 103.0, "target")   # mid[7] on bar 8


def test_c_void_when_the_open_is_already_through_the_middle_band():
    fr = mk_frame()
    sg = mk_sig(fr, mid=np.full(N, 99.0))                        # long, open 100 >= mid 99
    sig_at(sg, 5, 3, 1, stop=95.0)
    tr, k = run(fr, sg)
    assert tr == [] and k["void_target"] == 1


def test_c_exits_when_t_fires_and_on_the_5_bar_time_stop():
    fr = mk_frame()
    fr.o[6], fr.h[6] = 99.0, 99.5
    mid = np.full(N, 110.0)
    sg = mk_sig(fr, mid=mid)
    sig_at(sg, 5, 3, 1, stop=95.0)
    sg.t_fire[9] = True
    t = run(fr, sg)[0][0]
    assert (t.reason, t.exit_j) == ("T_fired", 10)
    sg2 = mk_sig(fr, mid=mid)
    sig_at(sg2, 5, 3, 1, stop=95.0)
    t2 = run(fr, sg2)[0][0]
    assert (t2.reason, t2.entry_j, t2.exit_j) == ("time", 6, 11)


# --- position rules --------------------------------------------------------------------------------
def test_one_position_a_signal_while_in_position_is_counted_and_dropped():
    fr = mk_frame()
    sg = mk_sig(fr)
    sig_at(sg, 5, 1, 1, stop=90.0)
    sig_at(sg, 10, 1, 1, stop=90.0, ep=1)
    tr, k = run(fr, sg)
    assert len(tr) == 1 and k["skipped_in_position"] == 1


def test_a_signal_on_the_bar_the_position_is_leaving_enters_at_the_same_open():
    close = np.full(N, 100.0)
    close[10] = 98.0
    fr = mk_frame(close)
    sg = mk_sig(fr, ma=np.full(N, 99.0))
    sig_at(sg, 5, 1, 1, stop=90.0)
    sig_at(sg, 10, 1, -1, stop=110.0, ep=1)                      # close 98 < ma: leaves at open 11
    tr, k = run(fr, sg)
    assert [(t.direction, t.entry_j, t.exit_j) for t in tr][0] == (1, 6, 11)
    assert tr[1].entry_j == 11 and tr[1].direction == -1 and k["skipped_in_position"] == 0


def test_integer_zero_contracts_is_a_counted_skip_and_the_walk_stays_flat():
    fr = mk_frame()
    sg = mk_sig(fr)
    sig_at(sg, 5, 1, 1, stop=50.0)                               # risk $1 / (50 * 1) = 0.02 contracts
    tr, k = run(fr, sg, integer=True)
    assert tr == [] and k["skipped_size"] == 1


def test_arms_filter_switches_an_arm_off_but_still_counts_its_signal():
    fr = mk_frame()
    sg = mk_sig(fr, arms=("MR",))
    sig_at(sg, 5, 1, 1, stop=90.0)
    tr, k = run(fr, sg)
    assert tr == [] and k["signals_T"] == 1 and k["entries_T"] == 0


def test_last_bar_closes_at_the_close_as_data_end():
    fr = mk_frame()
    sg = mk_sig(fr)
    sig_at(sg, 5, 1, 1, stop=90.0)
    t = run(fr, sg)[0][0]
    assert (t.reason, t.exit_j, t.exit_px) == ("data_end", N - 1, fr.c[-1])


# --- booking ----------------------------------------------------------------------------------------
def test_booking_costs_and_daily_marks_equal_the_trade_list_across_a_roll():
    close = 100 + np.arange(N) * 0.5
    fr = mk_frame(close, roll_at=(8,))
    sg = mk_sig(fr)
    sig_at(sg, 5, 1, 1, stop=90.0)
    tr, _ = run(fr, sg, equity=1000.0)
    t = tr[0]
    b = K.book_trade(t, fr)
    assert b["n_rolls"] == 1 and b["sides"] == 4
    assert b["net_mid"] == pytest.approx(b["gross"] - 1.25 * t.qty * 4)
    dm = K.daily_marks(tr, fr)
    for i, lv in enumerate(("low", "mid", "high")):
        assert dm[:, i].sum() == pytest.approx(b["net_" + lv])


def test_stop_fill_charges_one_tick_of_slippage():
    fr = mk_frame()
    fr.l[9] = 90.0
    sg = mk_sig(fr)
    sig_at(sg, 5, 1, 1, stop=98.0)
    t = run(fr, sg)[0][0]
    b = K.book_trade(t, fr)
    assert b["slip"] == pytest.approx(fr.tick_usd * t.qty)


def test_booking_matches_the_tl_v0_booker_on_an_open_fill_across_a_roll():
    from strategy.tl_v0 import bars as B
    from strategy.tl_v0 import pnl
    from strategy.tl_v0.sim import Trade
    from strategy.tl_v0.spec import Market
    from tests.strategy.tl_v0.synth import ROOT, contracts_and_rows
    rows, con, _ = contracts_and_rows()
    mb = B.build_bars(rows, con, ROOT, "XX")
    m = Market("XX", "XX", "MXX", 10.0, 1.0, ROOT)
    fr = K.frame_from_daily(mb, m)
    rolls = np.nonzero(fr.roll_after)[0]
    e = int(rolls[1]) - 3
    x = int(rolls[1]) + 4
    f = mb.frame
    t = Trade(1, e, x, float(f["open"].iat[e]), float(f["close"].iat[x]), 0.0, 2.0, "data_end", False)
    ref = pnl.book(t, f, m)
    mine = K.book_trade(t, fr)
    for lv in ("low", "mid", "high"):
        assert mine["net_" + lv] == pytest.approx(ref.net(lv, t.qty))
    assert mine["gross"] == pytest.approx(ref.gross)
    dm_ref = pnl.daily([t], [ref], f, m)
    assert np.allclose(K.daily_marks([t], fr), dm_ref)
