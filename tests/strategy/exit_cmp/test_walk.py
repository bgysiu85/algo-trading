import numpy as np
import pandas as pd
import pytest

from strategy.chartmark.data import indicators, make_frame
from strategy.exit_cmp import spec as S
from strategy.exit_cmp.walk import session_end
from tests.strategy.exit_cmp.helpers import world


def test_session_end_is_the_16h_ny_bar_and_early_closes():
    # NY wall clock 2015-01-07 10:00..15:00 hourly, then a gap to the next evening: the 15:00 bar closes the session early;
    # the next session runs 18:00 -> 16:00 and ends on its 16:00 bar
    t1 = pd.date_range("2015-01-07 10:00", "2015-01-07 15:00", freq="h", tz="America/New_York")
    t2 = pd.date_range("2015-01-07 18:00", "2015-01-08 16:00", freq="h", tz="America/New_York")
    t = (t1.append(t2)).tz_convert("UTC")
    n = len(t)
    px = np.linspace(60, 61, n)
    fr = make_frame(t, px, px + .1, px - .1, px, np.full(n, 1000.0))
    ind = indicators(fr)
    end, early = session_end(fr, ind)
    ny = fr.ny
    assert early == 1
    assert [str(ny[i].hour) for i in np.where(end)[0]] == ["15", "16"]


def test_flat_trades_never_cross_the_close_and_hold_trades_can():
    fr, ind, trades, entries, st = world(seed=5, n=6000)
    flat = st.run("B-STOP", "FLAT")
    assert len(flat) > 15
    for x, en in zip(flat, entries):
        nxt = en.e + 1 + int(np.argmax(st.sess_end[en.e + 1:]))
        assert x.exit_j <= nxt
        assert x.reason in ("S", "flat")
    hold = st.run("B-STOP", "HOLD")
    assert any(x.exit_j - en.e > 24 for x, en in zip(hold, entries))
    assert all(x.exit_j - en.e <= S.HOLD_CAP for x, en in zip(hold, entries))


def test_every_rule_set_keeps_the_initial_stop_as_a_floor():
    fr, ind, trades, entries, st = world(seed=6, n=6000)
    for rid in ("R-BEN", "R-MOM", "X-ALERT-touch", "X-ALERT-close", "X-JUMP", "R-BEN-EMA", "R-MOM+BEN", "X-JUMP-1R-half"):
        for sc in S.SCENARIOS:
            for x, en in zip(st.run(rid, sc), entries):
                if x.reason == "S":
                    assert x.exit_px <= en.s0 + 1e-9 or x.exit_px == pytest.approx(fr.o[x.exit_j])
                assert x.reason != "data_end" or x.exit_j == fr.n - 1


def test_a_ratchet_or_jump_never_fills_above_the_highest_high_or_the_open():
    """Stops sit under the best price reached, so a stop exit cannot be priced above it."""
    fr, ind, trades, entries, st = world(seed=8, n=6000)
    for rid in ("R-BEN", "X-JUMP", "R-MOM+BEN", "X-JUMP-1R-half"):
        for x, en in zip(st.run(rid, "FLAT"), entries):
            if x.reason in ("RATCHET", "JUMP"):
                assert x.exit_px <= x.mfe_px + 1e-9 and x.exit_px <= max(fr.o[x.exit_j], x.mfe_px)


def test_x_alert_without_any_line_is_b_stop():
    fr, ind, trades, entries, st = world(seed=2, n=6000)
    a = st.run("X-ALERT-touch", "FLAT")
    b = st.run("B-STOP", "FLAT")
    for x, y in zip(a, b):
        if "line_active" not in x.fired:
            assert (x.exit_j, x.exit_px, x.reason) == (y.exit_j, y.exit_px, y.reason)
