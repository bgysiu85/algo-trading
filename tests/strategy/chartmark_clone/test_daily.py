"""Trading-day bars (18:00 NY roll) and F1: bars <= t only."""
import numpy as np
import pandas as pd

from strategy.chartmark.data import make_frame
from strategy.chartmark_clone import daily as DL
from tests.strategy.chartmark.synth import walk


def week_frame():
    """Hourly bars, Sun 2015-03-01 18:00 NY .. Fri 2015-03-06 17:00 NY, no gaps other than the weekend."""
    ny = pd.date_range("2015-03-01 18:00", "2015-03-06 17:00", freq="h", tz="America/New_York")
    n = len(ny)
    c = np.linspace(50, 52, n)
    return make_frame(ny.tz_convert("UTC"), c, c + 0.1, c - 0.1, c, np.ones(n) * 100)


def test_the_18_00_ny_roll_assigns_bars_to_the_next_trading_day():
    fr = week_frame()
    dn, wd = DL.day_numbers(fr)
    ny = fr.ny
    assert wd[0] == 0 and dn[0] == 0                                            # Sunday 18:00 opens Monday's day
    i17 = int(np.where((ny.weekday == 0) & (ny.hour == 17))[0][0])              # Monday 17:00 is still Monday's day
    assert dn[i17] == 0 and dn[i17 + 1] == 1 and wd[i17 + 1] == 1               # Monday 18:00 opens Tuesday
    assert wd[-1] == 4                                                          # Friday 17:00 closes Friday
    d = DL.build_daily(fr)
    assert d.n == 5 and list(d.weekday) == [0, 1, 2, 3, 4]
    assert d.first[0] == 0 and d.last[0] == i17


def test_daily_bars_and_partial_today_use_bars_up_to_t_only():
    fr = week_frame()
    d = DL.build_daily(fr)
    t = int(d.first[2]) + 3                                                     # four bars into Wednesday's day
    o, h, l, c = DL.partial_today(fr, d, t)
    assert o == fr.o[d.first[2]] and c == fr.c[t]
    assert h == fr.h[d.first[2]: t + 1].max() and l == fr.l[d.first[2]: t + 1].min()


def test_f1_ignores_everything_after_t_and_sees_the_previous_day():
    fr = walk(4000, 5, drift=0.0, vol=0.4)
    d = DL.build_daily(fr)
    ts = [int(d.first[k]) + 5 for k in range(25, d.n - 2, 7)]
    base = {t: DL.f1_daily_trend(d, t) for t in ts}
    assert set(base.values()) == {-1, 1}
    for t in ts:
        mut = make_frame(fr.t, fr.o.copy(), fr.h.copy(), fr.l.copy(), fr.c.copy(), fr.v.copy())
        rng = np.random.default_rng(t)
        for arr in (mut.o, mut.h, mut.l, mut.c):
            arr[t + 1:] = rng.uniform(1, 500, len(arr) - t - 1)
        dm = DL.build_daily(mut)
        assert DL.f1_daily_trend(dm, t) == base[t]
        assert np.array_equal(dm.e21[: int(d.day_of_bar[t])], d.e21[: int(d.day_of_bar[t])], equal_nan=True)


def test_f1_warm_up_counts_as_down_and_is_flagged():
    fr = walk(4000, 5, drift=0.0, vol=0.4)
    d = DL.build_daily(fr)
    assert DL.f1_daily_trend(d, 3) == -1 and DL.f1_is_warmup(d, 3)
    late = int(d.first[40])
    assert not DL.f1_is_warmup(d, late)


def test_f1_flips_when_the_last_completed_close_changes_side():
    fr = walk(4000, 5, drift=0.0, vol=0.4)
    d = DL.build_daily(fr)
    k = 60
    t = int(d.first[k]) + 2
    s0 = DL.f1_daily_trend(d, t)
    mut = make_frame(fr.t, fr.o.copy(), fr.h.copy(), fr.l.copy(), fr.c.copy(), fr.v.copy())
    last_prev = int(d.last[k - 1])
    mut.c[last_prev] = 1e4 if s0 == -1 else 1.0                                 # one bar of the previous day moves
    assert DL.f1_daily_trend(DL.build_daily(mut), t) == -s0
