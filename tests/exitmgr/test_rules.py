"""Rule behaviour on hand-made bars (long; entry bar 0 at 100.00, A0 = 1, S = 99.00, tick 0.01) through the simulated broker."""
from types import SimpleNamespace

import numpy as np
import pytest

from exitmgr import rules as R
from strategy.chartmark import spec as V1
from strategy.exit_cmp.walk import walk

ENTRY, A0, S0, TICK = 100.0, 1.0, 99.0, 0.01


def mk(rows, hist=-1.0, atr=1.0):
    o, h, l, c = (np.array(x, float) for x in zip(*rows))
    n = len(o)
    return SimpleNamespace(o=o, h=h, l=l, c=c, atr=np.full(n, atr), e9=np.full(n, np.nan), e21=np.full(n, np.nan),
                           hist=np.full(n, hist) if np.isscalar(hist) else np.array(hist, float))


def run(rows, rule, scen="HOLD", p=R.BASE, proj=None, sess=None, cap=None, hist=-1.0, a0=A0, s0=S0):
    b = mk(rows, hist)
    comps = R.build(rule, b, 0, ENTRY, a0, s0, TICK, p, proj)
    se = np.zeros(len(rows), bool) if sess is None else np.array(sess, bool)
    return walk(b, 0, ENTRY, a0, s0, comps, scenario=scen, sess_end=se, cap=cap, n=len(rows))


def flat_bar(px=100.5):
    return (px, px + 0.05, px - 0.05, px)


def test_v1_constants_mirrored():
    assert R.V1_P2_ARM == V1.P2_ARM and R.V1_P1_ARM == V1.BASE.p1_arm
    assert (R.V1_R_WICK, R.V1_R_MIN_RANGE, R.V1_R_LIFE) == (V1.R_WICK, V1.R_MIN_RANGE, V1.R_LIFE)


def test_b_stop_fills_at_level_or_at_a_gap_open():
    x = run([(100, 100.2, 99.9, 100.1), (100.0, 100.1, 98.5, 98.7)], "B-STOP")
    assert (x.exit_j, x.exit_px, x.reason) == (1, 99.0, "S")
    x = run([(100, 100.2, 99.9, 100.1), (98.0, 98.4, 97.5, 98.1)], "B-STOP")
    assert (x.exit_px, x.reason) == (98.0, "S")           # gap through the stop fills at the open


def test_data_end_and_flat_and_time_cap():
    rows = [(100, 100.1, 99.9, 100.0)] + [flat_bar(100.0)] * 5
    assert run(rows, "B-STOP").reason == "data_end"
    x = run(rows, "B-STOP", scen="FLAT", sess=[0, 0, 0, 1, 0, 0])
    assert (x.exit_j, x.reason, x.exit_px) == (3, "flat", 100.0)
    x = run(rows, "B-STOP", scen="HOLD", cap=2)
    assert (x.exit_j, x.reason) == (2, "time_cap")
    # HOLD ignores the session end
    assert run(rows, "B-STOP", scen="HOLD", sess=[0, 0, 0, 1, 0, 0]).reason == "data_end"


def test_ratchet_arms_at_020_and_is_effective_from_the_next_bar():
    # entry-bar high 100.5 >= 100.20 -> stop 100.25 from bar 1 on
    x = run([(100, 100.5, 99.95, 100.3), (100.3, 100.4, 100.1, 100.2)], "R-BEN")
    assert (x.exit_j, x.exit_px, x.reason) == (1, 100.25, "RATCHET")
    # high only 100.15: not armed, falls through to S
    x = run([(100, 100.15, 99.95, 100.1), (100.1, 100.19, 100.0, 100.1), (100.0, 100.1, 98.0, 98.5)], "R-BEN")
    assert x.reason == "S"
    # bar 1 can both hit the stop and make a new high: the stop is counted first (G5)
    x = run([(100, 100.5, 99.95, 100.3), (100.3, 102.0, 100.1, 101.9)], "R-BEN")
    assert (x.exit_px, x.reason, x.stop_and_raise_same_bar) == (100.25, "RATCHET", 1)


def test_ratchet_moves_up_with_new_highs_and_never_down():
    rows = [(100, 100.5, 99.95, 100.4), (100.4, 101.0, 100.4, 100.9), (100.9, 100.95, 100.3, 100.4), (100.4, 100.45, 100.2, 100.3)]
    x = run(rows, "R-BEN")
    # after bar 1 the highest high is 101.0 -> stop 100.50; bar 2 low 100.3 <= 100.50 -> exit at 100.50 (bar 2 open 100.9 is above it)
    assert (x.exit_j, x.exit_px) == (2, pytest.approx(100.5))


def test_m1_three_red_bars_and_macd_negative_sells_at_the_next_open():
    red = lambda o: (o, o + 0.1, o - 0.3, o - 0.2)
    rows = [(100, 100.1, 99.95, 100.0), red(100.0), red(99.8), red(99.6), (99.5, 99.6, 99.3, 99.4), flat_bar(99.4)]
    x = run(rows, "R-MOM", s0=98.0)
    assert (x.exit_j, x.exit_px, x.reason) == (4, 99.5, "M1")
    # MACD histogram not negative: no M1
    assert run(rows, "R-MOM", hist=0.5, s0=98.0).reason == "data_end"
    # the entry bar does not count as one of the three (I2): only two post-entry red bars before bar 3 closes -> fires at bar 3, not 2
    assert run(rows[:3], "R-MOM", s0=98.0).reason == "data_end"


def test_m2_shooting_star_body_stop_lives_three_bars():
    star = (100.5, 102.0, 100.4, 100.6)          # wick 1.4 of range 1.6; body low 100.5
    rows = [(100, 100.1, 99.95, 100.0), star, flat_bar(100.6), flat_bar(100.7), (100.7, 100.8, 100.45, 100.5), flat_bar(100.5)]
    x = run(rows, "R-MOM", s0=98.0)
    # level 100.49; live for bars 2..4; bar 4 low 100.45 <= 100.49
    assert (x.exit_j, x.reason) == (4, "M2") and x.exit_px == pytest.approx(100.49)
    late = [(100, 100.1, 99.95, 100.0), star, flat_bar(100.6), flat_bar(100.7), flat_bar(100.7), (100.7, 100.8, 100.45, 100.5)]
    assert run(late, "R-MOM", s0=98.0).reason == "data_end"        # order expired after 3 bars


def test_x_jump_moves_straight_into_profit_under_a_confirmed_swing_low():
    # R0 = 1.0 -> arms when the high >= 101.0 (bar 1). Swing low at bar 3 (low 100.40) is confirmed at the close of bar 5.
    rows = [(100, 100.5, 99.95, 100.4), (100.4, 101.2, 100.9, 101.1), (101.1, 101.3, 100.7, 100.9), (100.9, 101.0, 100.4, 100.8),
            (100.8, 101.1, 100.8, 101.0), (101.0, 101.4, 100.9, 101.3), (101.3, 101.4, 100.3, 100.5), flat_bar(100.5)]
    x = run(rows, "X-JUMP")
    assert x.reason == "JUMP" and x.exit_j == 6 and x.exit_px == pytest.approx(100.39)
    assert "jump_armed" in x.fired and "swing_used" in x.fired


def test_x_jump_skips_a_swing_low_at_or_below_entry():
    rows = [(100, 100.5, 99.95, 100.4), (100.4, 101.2, 100.9, 101.1), (101.1, 101.3, 100.0, 100.9), (100.9, 101.0, 99.8, 100.8),
            (100.8, 101.1, 100.8, 101.0), (101.0, 101.4, 100.9, 101.3), flat_bar(101.3)]
    x = run(rows, "X-JUMP")
    assert "jump_armed" in x.fired and "swing_used" not in x.fired and x.reason == "data_end"


def test_x_jump_does_not_arm_below_1r():
    rows = [(100, 100.5, 99.95, 100.4)] + [flat_bar(100.6)] * 5
    assert "jump_armed" not in run(rows, "X-JUMP").fired


def test_x_alert_touch_is_a_sell_stop_at_the_projected_line_while_below_the_prior_close():
    rows = [(100, 100.1, 99.95, 100.0), (100.0, 100.2, 99.9, 100.1), (100.1, 100.15, 99.7, 99.8), flat_bar(99.8)]
    proj = np.array([np.nan, 99.9, 99.9, 99.9])         # proj[j-1] is the level for bar j
    x = run(rows, "X-ALERT-touch", proj=proj)
    assert (x.exit_j, x.reason, x.exit_px) == (2, "ALERT", pytest.approx(99.9))      # no level in bar 1 (proj[0] is nan)
    # a line at or above the prior close is not eligible
    proj2 = np.array([np.nan, 100.5, 100.5, 100.5])
    assert run(rows, "X-ALERT-touch", proj=proj2).reason == "data_end"


def test_x_alert_close_fires_on_a_close_below_the_line_less_buffer_and_exits_next_open():
    rows = [(100, 100.1, 99.95, 100.0), (100.0, 100.1, 99.85, 100.0), (100.0, 100.05, 99.5, 99.6), (99.55, 99.6, 99.4, 99.5), flat_bar(99.5)]
    proj = np.array([np.nan, 99.9, 99.9, 99.9, 99.9])
    x = run(rows, "X-ALERT-close", proj=proj)
    # close of bar 2 = 99.6 < 99.9 - 0.10 -> market sell at the open of bar 3
    assert (x.exit_j, x.exit_px, x.reason) == (3, 99.55, "ALERT")
    # no line (nan): exactly B-STOP
    none = np.full(5, np.nan)
    assert run(rows, "X-ALERT-close", proj=none).reason == run(rows, "B-STOP").reason


def test_a_market_exit_decided_on_the_flat_bar_is_the_flat_close():
    red = lambda o: (o, o + 0.1, o - 0.3, o - 0.2)
    rows = [(100, 100.1, 99.95, 100.0), red(100.0), red(99.8), red(99.6), (99.5, 99.6, 99.3, 99.4)]
    x = run(rows, "R-MOM", scen="FLAT", s0=98.0, sess=[0, 0, 0, 1, 0])
    assert (x.exit_j, x.reason) == (3, "flat")


def test_variants_build_and_compose():
    # R-MOM+BEN keeps both the red-bar exit and the ratchet; R-BEN-EMA adds the EMA trail; X-JUMP-1R-half adds the half-profit ratchet
    names = lambda rid: sorted(type(c).__name__ for c in R.build(rid, mk([(100, 101, 99, 100)] * 3), 0, 100.0, 1.0, 99.0, 0.01, R.BASE, np.zeros(3)))
    assert set(names("R-MOM+BEN")) == {"Floor", "RedRun", "Ratchet", "Reversal"}
    assert {"EmaTrail", "Ratchet"} <= set(names("R-BEN-EMA"))
    assert {"Jump", "Ratchet"} <= set(names("X-JUMP-1R-half"))
    rows = [(100, 100.5, 99.95, 100.4), (100.4, 101.2, 100.9, 101.1), (101.1, 101.3, 101.0, 101.2), (101.2, 101.3, 100.9, 101.0)]
    x = run(rows, "X-JUMP-1R-half")
    # armed at bar 1 (high 101.2 >= 101.0): half-profit ratchet 100 + (101.2-100)/2 = 100.6 from bar 2, not yet hit
    assert x.reason == "data_end"
    x = run(rows + [(101.0, 101.1, 100.5, 100.6)], "X-JUMP-1R-half")
    assert (x.exit_j, x.reason, x.exit_px) == (4, "RATCHET", pytest.approx(100.65))
