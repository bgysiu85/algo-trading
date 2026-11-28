"""strategy.w16.open_window: bars, indicators, triggers, the book and the
trailing walk. Every sec 7.2 look-ahead guard of REGISTERED_w16_open_window.md
has a test here (or in test_owa_holdout.py) that a one-bar or one-minute shift
breaks. Board W16-0040 sub 4."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.w16 import open_window as OW
from tests.strategy.w16 import owa_fixtures as F

MIN = OW.NS_MIN


@pytest.fixture(scope="module")
def walk_data():
    dates = F.weekdays(45)
    return dates, F.random_bars(dates)


@pytest.fixture(scope="module")
def walk_market(walk_data):
    return OW.prepare(walk_data[1])


# ---------------------------------------------------------------------
# indicators
# ---------------------------------------------------------------------

def test_registered_constants():
    assert (OW.BIG_MULT, OW.CROSS_K, OW.MACD_K, OW.PULLBACK_BARS) == (1.5, 3, 3, 12)
    assert (OW.SWING_BARS, OW.STOP_MIN_ATR, OW.STOP_MAX_ATR, OW.TRAIL_ATR) == (6, 0.5, 2.0, 2.5)
    assert (OW.MAX_FILLS_PER_DAY, OW.SLOT_LEN, OW.SLOT_MIN_OBS, OW.ATR_LEN) == (2, 20, 20, 14)
    assert (OW.WINDOW_FIRST_MIN, OW.WINDOW_LAST_MIN, OW.WINDOW_END_MIN) == (480, 715, 720)
    assert (OW.FLAT_MIN, OW.FLAT_MIN_EARLY, OW.SKIP_FIRST_MIN, OW.SKIP_GAP_MIN) == (955, 775, 420, 15)
    assert (OW.WARMUP_5M, OW.WARMUP_15M, OW.WARMUP_1H) == (35, 21, 21)


def test_ema_is_seeded_with_the_first_value():
    got = OW.ema(np.array([10.0, 20.0, 20.0]), 9)
    assert got[0] == 10.0
    assert got[1] == pytest.approx(12.0)
    assert got[2] == pytest.approx(13.6)


def test_wilder_atr_seeds_with_a_simple_mean():
    n = 20
    high = np.arange(n, dtype=float) + 2.0
    low = np.arange(n, dtype=float)
    high[16] += 10.0
    close = np.arange(n, dtype=float) + 1.0
    atr = OW.wilder_atr(high, low, close)
    assert np.isnan(atr[:13]).all()
    tr = np.maximum(high - low, np.abs(high - np.concatenate(([np.nan], close[:-1]))))
    tr[0] = 2.0
    assert atr[13] == pytest.approx(tr[:14].mean())
    assert atr[14] == pytest.approx((atr[13] * 13 + tr[14]) / 14)
    assert atr[16] == pytest.approx((atr[15] * 13 + tr[16]) / 14)


def test_crosses_and_within_last():
    a = np.array([1.0, 1.0, 3.0, 3.0, 1.0, 3.0])
    b = np.full(6, 1.0)
    assert OW.crossed_up(a, b).tolist() == [False, False, True, False, False, True]
    flags = np.array([False, True, False, False, False, False])
    assert OW.within_last(flags, 3).tolist() == [False, True, True, True, True, False]
    assert OW.within_last(flags, 0).tolist() == flags.tolist()


def test_slot_average_never_contains_the_bar_being_judged():
    """sec 7.2: the average used at day j contains no bar from day j."""
    n = 25
    slot = np.tile([480, 485], n)
    rng = np.where(slot == 480, 10.0, 1.0).astype(float)
    prev, count = OW.slot_average(slot, rng)
    day21 = 2 * 21
    assert prev[day21] == pytest.approx(10.0) and count[day21] == 21
    assert prev[day21 + 1] == pytest.approx(1.0)          # slots do not mix
    assert np.isnan(prev[0]) and count[0] == 0
    changed = rng.copy()
    changed[day21] = 100.0
    prev2, _ = OW.slot_average(slot, changed)
    assert prev2[day21] == prev[day21]                    # same day: unchanged
    next_day = day21 + 2
    assert prev2[next_day] == pytest.approx(10.0 + 2.0 / 21.0 * 90.0)


def test_big_bar_needs_twenty_earlier_days():
    mk, date = F.flat_market(22)
    j = F.bar_at(mk, date, "09:00")
    mk.b5.ah[j] += 5.0
    mk.slot_prev[j], mk.slot_n[j] = 1.0, 20
    assert OW.compute_signals(mk, "1H").big[j]
    mk.slot_n[j] = 19
    assert not OW.compute_signals(mk, "1H").big[j]
    mk.slot_n[j] = 20
    mk.slot_prev[j] = 5.0 / 1.5
    assert OW.compute_signals(mk, "1H").big[j]            # exactly 1.5x counts
    mk.slot_prev[j] = 5.0 / 1.5 + 1e-6
    assert not OW.compute_signals(mk, "1H").big[j]


# ---------------------------------------------------------------------
# bars and the roll adjustment
# ---------------------------------------------------------------------

def test_bars_are_clock_anchored_and_empty_periods_have_no_bar():
    date = "2015-03-09"
    clocks = ["08:03", "08:04", "08:17"]
    idx = pd.DatetimeIndex([F.stamp(date, c) for c in clocks])
    df = pd.DataFrame({"open": [1.0, 2.0, 3.0], "high": [5.0, 6.0, 7.0], "low": [0.5, 0.25, 2.0],
                       "close": [2.0, 3.0, 4.0], "held_id": 1}, index=idx)
    m = OW.build_minutes(df)
    b = OW.resample(m, 5)
    assert [OW.hhmm(int(x)) for x in b.minute] == ["08:00", "08:15"]
    assert (b.o[0], b.h[0], b.l[0], b.c[0]) == (1.0, 6.0, 0.25, 3.0)
    assert b.close_time[0] == F.stamp(date, "08:05").value
    hourly = OW.resample(m, 60)
    assert len(hourly) == 1 and hourly.minute[0] == 480


def test_adjusted_series_is_continuous_across_a_roll(walk_data):
    dates, df = walk_data
    cut = F.stamp(dates[30], "20:00")
    rolled = df.copy()
    later = rolled.index >= cut
    rolled.loc[later, ["open", "high", "low", "close"]] += 50.0
    rolled.loc[later, "held_id"] = 2
    a, b = OW.prepare(df), OW.prepare(rolled)
    # real prices differ by the gap after the roll; adjusted prices do not
    after = b.b5.start >= cut.value
    assert np.allclose(b.b5.c[after] - a.b5.c[after], 50.0)
    assert np.allclose(b.b5.ac, a.b5.ac)
    assert np.allclose(b.m1.roll_off[b.m1.t >= cut.value], 50.0)
    for name in OW.FILTERS:
        sa, sb = OW.compute_signals(a, name), OW.compute_signals(b, name)
        for field in ("a_long", "a_short", "c_long", "c_short", "b_fire_long", "b_arm_short"):
            assert np.array_equal(getattr(sa, field), getattr(sb, field)), field


def test_a_later_roll_changes_nothing_earlier(walk_data):
    """sec 7.2: back-adjustment at time tau uses only rolls at or before tau."""
    dates, df = walk_data
    cut = F.stamp(dates[40], "20:00")
    rolled = df.copy()
    later = rolled.index >= cut
    rolled.loc[later, ["open", "high", "low", "close"]] += 137.25
    rolled.loc[later, "held_id"] = 2
    a, b = OW.prepare(df), OW.prepare(rolled)
    early = a.b5.start < cut.value
    for x, y in ((a.b5.ac, b.b5.ac), (a.e9, b.e9), (a.e21, b.e21), (a.macd, b.macd)):
        assert np.array_equal(x[early], y[early])
    assert np.array_equal(a.atr[early], b.atr[early], equal_nan=True)
    for name in OW.FILTERS:
        assert np.array_equal(a.filt[name][early], b.filt[name][early])


# ---------------------------------------------------------------------
# trend filter
# ---------------------------------------------------------------------

def test_filter_reads_only_bars_closed_by_the_bar_start():
    """sec 7.2: move a 1H close one minute later and the state must change."""
    nine = F.stamp("2015-03-09", "09:00").value
    closes = np.array([nine - 60 * MIN, nine])
    state = np.array([OW.DOWN, OW.UP])
    got, done = OW.filter_state(np.array([nine - 5 * MIN, nine]), closes, state)
    assert got.tolist() == [OW.DOWN, OW.UP] and done.tolist() == [1, 2]
    late = closes.copy()
    late[1] += MIN
    got, _ = OW.filter_state(np.array([nine]), late, state)
    assert got.tolist() == [OW.DOWN]
    got, _ = OW.filter_state(np.array([closes[0] - MIN]), closes, state)
    assert got.tolist() == [OW.NONE]


@pytest.mark.parametrize("name,hour_start,seen_from", [("1H", "08:00", "09:00"),
                                                       ("15", "08:00", "08:15")])
def test_filter_in_the_market_ignores_the_bar_still_forming(walk_data, name, hour_start, seen_from):
    dates, df = walk_data
    date = dates[-1]
    moved = df.copy()
    last = pd.Timestamp(f"{date} {seen_from}") - pd.Timedelta(minutes=1)
    sel = (moved.index >= F.stamp(date, hour_start)) & (moved.index <= F.stamp(date, last.strftime("%H:%M")))
    a = OW.prepare(df)
    results = []
    for shift in (+2000.0, -2000.0):
        moved = df.copy()
        moved.loc[sel, ["open", "high", "low", "close"]] += shift
        b = OW.prepare(moved)
        before = b.b5.start < F.stamp(date, seen_from).value
        assert np.array_equal(a.filt[name][before], b.filt[name][before])
        results.append(int(b.filt[name][F.bar_at(b, date, seen_from)]))
    assert results == [OW.UP, OW.DOWN]


def test_filter_equality_is_neither_side():
    mk, date = F.flat_market(25)
    j = F.bar_at(mk, date, "09:00")
    assert mk.filt["1H"][j] == OW.NONE and mk.filt["15"][j] == OW.NONE


# ---------------------------------------------------------------------
# triggers
# ---------------------------------------------------------------------

def _flat_signal_market():
    mk, date = F.flat_market(25)
    j = F.bar_at(mk, date, "09:00")
    n = len(mk.b5)
    mk.filt = {k: np.full(n, OW.UP) for k in OW.FILTERS}
    return mk, j


def test_trigger_a_needs_cross_big_green_filter_and_order():
    mk, j = _flat_signal_market()
    mk.e9, mk.e21 = mk.e9.copy(), mk.e21.copy()
    mk.e9[j - 3:j + 1] = mk.e21[j] + 1.0                   # cross up at j-3
    mk.slot_prev[j] = 1.0
    mk.b5.ah[j] += 5.0
    mk.b5.ac[j] += 4.0
    assert OW.compute_signals(mk, "1H").a_long[j]
    mk.e9[j - 4] = mk.e21[j] + 1.0                          # now the cross is 4 back
    assert not OW.compute_signals(mk, "1H").a_long[j]
    mk.e9[j - 4] = mk.e21[j - 4]
    mk.filt["1H"][j] = OW.NONE
    assert not OW.compute_signals(mk, "1H").a_long[j]


def test_trigger_c_below_the_slow_ema_needs_a_narrowing_gap():
    mk, j = _flat_signal_market()
    n = len(mk.b5)
    mk.e21 = np.full(n, 100.0)
    mk.e9 = np.full(n, 90.0)
    mk.e9[j] = 92.0                                         # rising, still below
    mk.macd, mk.signal = np.zeros(n), np.zeros(n)
    mk.macd[j - 2:j + 1] = 1.0                              # MACD cross up at j-2
    assert OW.compute_signals(mk, "1H").c_long[j]
    mk.e21[j] = 103.0                                       # gap widened despite the rise
    assert not OW.compute_signals(mk, "1H").c_long[j]
    mk.e21[j] = 100.0
    assert not OW.compute_signals(mk, "1H", OW.Params(macd_k=1)).c_long[j]
    mk.e9[j] = 101.0                                        # crosses on this bar
    assert OW.compute_signals(mk, "1H").c_long[j]
    mk.e9[j - 1] = 100.5                                    # crossed earlier: above, no new cross
    assert not OW.compute_signals(mk, "1H").c_long[j]


def test_pullback_state_window_touch_and_rearm():
    pb = OW.PullbackState()
    assert not pb.step(10, True, True, True)               # the arming bar cannot fire
    assert not pb.step(11, False, False, True)             # armed, not touched
    assert pb.step(12, False, True, True)                  # touch on the firing bar counts
    assert pb.step(22, False, False, True)                 # j - i = 12
    assert not pb.step(23, False, True, True)              # 13: expired
    pb = OW.PullbackState()
    pb.step(10, True, False, False)
    pb.step(11, False, True, False)                        # touched
    assert not pb.step(15, True, False, True)              # re-arm: no fire, touch cleared
    assert not pb.step(16, False, False, True)
    assert pb.step(17, False, True, True)
    pb.reset()
    assert not pb.step(18, False, True, True)


def test_pullback_arms_only_on_big_bars_inside_the_window(walk_market):
    mk = walk_market
    for name in OW.FILTERS:
        sig = OW.compute_signals(mk, name)
        for armed in (sig.b_arm_long, sig.b_arm_short):
            assert armed.sum() > 0
            assert mk.b5.minute[armed].min() >= 480 and mk.b5.minute[armed].max() <= 715
        assert (sig.big & (mk.b5.minute > 715) & (mk.filt[name] == OW.UP)
                & sig.big_up).sum() > 0                    # big bars do occur outside it


def test_pullback_book_resets_on_a_b_fill_only():
    mk, date = F.flat_market(25)
    sig = F.forced_signals(mk)
    n = len(mk.b5)
    idx = [F.bar_at(mk, date, c) for c in ("09:00", "09:05", "09:20")]
    sig.b_arm_long = np.zeros(n, dtype=bool)
    sig.b_arm_long[idx[0]] = True
    sig.b_touch_long = np.ones(n, dtype=bool)
    sig.b_fire_long = np.zeros(n, dtype=bool)
    sig.b_fire_long[idx[1:]] = True
    # stop the first trade out at once so the book is free again by 09:20
    mk.m1.l = mk.m1.l.copy()
    mk.m1.l[F.minute_at(mk, date, "09:11")] = F.FLAT - 50
    book = OW.simulate_book(mk, sig, "B", [date])
    assert [t["signal_bar"] for t in book["trades"]] == ["09:05"]
    assert len(book["signals"]) == 1                        # 09:20 no longer armed
    sig.a_long = np.zeros(n, dtype=bool)
    sig.a_long[idx[1]] = True
    both = OW.simulate_book(mk, sig, "All", [date])         # A takes the bar: B stays armed
    assert [t["trigger"] for t in both["trades"]] == ["A", "B"]


def test_all_book_takes_long_before_short_and_a_first():
    mk, date = F.flat_market(25)
    j = F.bar_at(mk, date, "09:00")
    sig = F.forced_signals(mk, a_long=[j], a_short=[j])
    sig.c_long = sig.a_long.copy()
    t = OW.simulate_book(mk, sig, "All", [date])["trades"]
    assert (t[0]["direction"], t[0]["trigger"]) == ("long", "A")
    only = OW.simulate_book(mk, sig, "All", [date], sides=(OW.SHORT,))["trades"]
    assert only[0]["direction"] == "short"
    with pytest.raises(ValueError):
        OW.simulate_book(mk, sig, "D", [date])


# ---------------------------------------------------------------------
# entry
# ---------------------------------------------------------------------

def test_signal_fills_at_the_next_bar_open_never_the_signal_close():
    """sec 7.2."""
    def edits(df, date):
        F.set_minute(df, date, "09:04", c=1001.0, h=1001.0)
        F.set_minute(df, date, "09:05", o=1002.0, h=1002.0, l=1000.0)
    mk, date = F.flat_market(25, edits)
    j = F.bar_at(mk, date, "09:00")
    t = OW.simulate_book(mk, F.forced_signals(mk, a_long=[j]), "A", [date])["trades"][0]
    assert (t["fill_time"], t["fill_price"]) == (f"{date} 09:05", 1002.0)
    view = OW.simulate_book(mk, F.forced_signals(mk, a_long=[j]), "A", [date],
                            at_signal_close=True)["trades"][0]
    assert view["fill_price"] == 1001.0                    # reported variant only


def test_signal_with_no_bar_in_the_next_five_minutes_is_dropped():
    def edits(df, date):
        df.drop([F.stamp(date, f"09:0{m}") for m in range(5, 10)], inplace=True)
    mk, date = F.flat_market(25, edits)
    j = F.bar_at(mk, date, "09:00")
    book = OW.simulate_book(mk, F.forced_signals(mk, a_long=[j]), "A", [date])
    assert book["trades"] == [] and len(book["dropped"]) == 1
    assert book["signals"][0]["fillable"] is False


def test_a_late_first_minute_inside_the_five_minutes_still_fills():
    def edits(df, date):
        df.drop([F.stamp(date, "09:05"), F.stamp(date, "09:06")], inplace=True)
    mk, date = F.flat_market(25, edits)
    j = F.bar_at(mk, date, "09:00")
    t = OW.simulate_book(mk, F.forced_signals(mk, a_long=[j]), "A", [date])["trades"][0]
    assert t["fill_time"] == f"{date} 09:07"


def test_signals_outside_the_window_are_not_traded():
    mk, date = F.flat_market(25)
    idx = [F.bar_at(mk, date, c) for c in ("07:55", "12:00")]
    assert OW.simulate_book(mk, F.forced_signals(mk, a_long=idx), "A", [date])["trades"] == []
    idx = [F.bar_at(mk, date, c) for c in ("08:00", "11:55")]
    got = OW.simulate_book(mk, F.forced_signals(mk, a_long=[idx[1]]), "A", [date])["trades"]
    assert got[0]["fill_time"].endswith("12:00") and got[0]["pre_open"] is False
    got = OW.simulate_book(mk, F.forced_signals(mk, a_long=[idx[0]]), "A", [date])["trades"]
    assert got[0]["fill_time"].endswith("08:05") and got[0]["pre_open"] is True


# ---------------------------------------------------------------------
# initial stop
# ---------------------------------------------------------------------

def _stop(mk, date, side, fill, atr=F.ATR):
    j = F.bar_at(mk, date, "09:00")
    mk.atr[j] = atr
    return j, OW.initial_stop(mk, j, F.minute_at(mk, date, "09:05"), fill, side)


@pytest.mark.parametrize("low,expected", [
    (999.75, 998.0),       # swing distance 0.5 -> clamped up to 0.5 x ATR = 2
    (995.0, 994.75),       # inside the band: 1 tick under the swing
    (960.0, 992.0),        # too far -> clamped to 2 x ATR = 8
    (1003.0, 998.0),       # opens below the swing: d negative -> 0.5 x ATR
])
def test_initial_stop_long(low, expected):
    mk, date = F.flat_market(25)
    j = F.bar_at(mk, date, "09:00")
    mk.b5.al[j - 5:j + 1] = low
    assert _stop(mk, date, OW.LONG, 1000.0)[1] == expected


def test_initial_stop_short_mirrors_and_uses_six_bars():
    mk, date = F.flat_market(25)
    j = F.bar_at(mk, date, "09:00")
    mk.b5.ah[j - 5] = 1005.0                               # sixth bar back counts
    mk.b5.ah[j - 6] = 1007.0                               # seventh does not
    assert _stop(mk, date, OW.SHORT, 1000.0)[1] == 1005.25
    mk.b5.al[j - 5] = 995.0
    mk.b5.al[j - 6] = 993.0
    assert _stop(mk, date, OW.LONG, 1000.0)[1] == 994.75


def test_initial_stop_is_rounded_and_at_least_a_tick_away():
    mk, date = F.flat_market(25)
    assert _stop(mk, date, OW.LONG, 1000.0, atr=4.3)[1] == 997.75     # 0.5 x 4.3 = 2.15
    assert _stop(mk, date, OW.LONG, 1000.0, atr=0.1)[1] == 999.75
    assert _stop(mk, date, OW.SHORT, 1000.0, atr=0.1)[1] == 1000.25


def test_initial_stop_is_in_the_fill_contracts_prices():
    mk, date = F.flat_market(25)
    j = F.bar_at(mk, date, "09:00")
    mk.b5.al[j - 5:j + 1] = 995.0
    mk.m1.roll_off[:] = 100.0                              # real = adjusted + 100
    assert _stop(mk, date, OW.LONG, 1100.0)[1] == 1094.75


# ---------------------------------------------------------------------
# the trailing walk
# ---------------------------------------------------------------------

def _walk(mk, date, side="long", fill="09:05", price=1000.0, stop=998.0, trail=OW.TRAIL_ATR):
    i, p, why = OW.walk_exit(mk, F.day_of(mk, date), F.minute_at(mk, date, fill), price, side,
                             stop, trail)
    return OW.hhmm(int(mk.m1.minute[i])), p, why


def test_stop_during_a_bar_was_set_at_the_previous_close():
    """sec 7.2: bar k's own high must not move the stop bar k is tested on.
    09:10 spikes to 1030 (a new stop of 1020 at that bar's CLOSE) and then
    trades at 1001 inside the same 5-min bar: no exit until 09:15."""
    def edits(df, date):
        F.set_minute(df, date, "09:10", h=1030.0)
        F.set_minute(df, date, "09:12", l=1001.0)
        F.set_minute(df, date, "09:15", o=1025.0, h=1025.0, c=1025.0, l=1019.0)
    mk, date = F.flat_market(25, edits)
    assert _walk(mk, date) == ("09:15", 1020.0, "trail_stop")


def test_walk_starts_at_the_fill_minute():
    """sec 7.2: a low before the fill is invisible; the fill minute's is not."""
    def before(df, date):
        F.set_minute(df, date, "09:04", l=900.0)
    mk, date = F.flat_market(25, before)
    assert _walk(mk, date)[2] == "time"

    def at(df, date):
        F.set_minute(df, date, "09:05", l=997.0)
    mk, date = F.flat_market(25, at)
    assert _walk(mk, date) == ("09:05", 998.0, "initial_stop")


def test_a_gap_through_the_stop_fills_at_the_open():
    def edits(df, date):
        F.set_minute(df, date, "10:00", o=990.0, l=989.0, h=990.0, c=990.0)
    mk, date = F.flat_market(25, edits)
    assert _walk(mk, date) == ("10:00", 990.0, "initial_stop")


def test_trail_never_loosens_and_rounds_down():
    def edits(df, date):
        F.set_minute(df, date, "09:06", h=1020.1)
        F.set_from(df, date, "09:10", 1015.0)
        F.set_minute(df, date, "09:30", l=1010.0)
    mk, date = F.flat_market(25, edits)
    mk.atr[F.bar_at(mk, date, "09:20"):] = 40.0            # ATR jumps: stop stays put
    assert _walk(mk, date) == ("09:30", 1010.0, "trail_stop")     # 1020.1 - 10 = 1010.1 -> 1010.0


def test_short_walk_mirrors():
    def edits(df, date):
        F.set_minute(df, date, "09:06", l=979.9)
        F.set_from(df, date, "09:10", 985.0)
        F.set_minute(df, date, "09:30", h=990.0)
    mk, date = F.flat_market(25, edits)
    assert _walk(mk, date, side="short", stop=1002.0) == ("09:30", 990.0, "trail_stop")
    assert _walk(mk, date, side="short", stop=1002.0, trail=3.0)[2] == "time"


def test_time_exit_at_the_1555_open_even_through_the_stop():
    def edits(df, date):
        F.set_minute(df, date, "15:55", o=900.0, h=900.0, l=900.0, c=900.0)
    mk, date = F.flat_market(25, edits)
    assert _walk(mk, date) == ("15:55", 900.0, "time")


def test_early_close_day_goes_flat_at_1255():
    mk, date = F.flat_market(30, start="2015-10-19")
    early = next(d for d in mk.days if d.date == "2015-11-27")
    assert early.early
    i, _, why = OW.walk_exit(mk, early, F.minute_at(mk, "2015-11-27", "09:05"), 1000.0, "long",
                             998.0)
    assert (OW.hhmm(int(mk.m1.minute[i])), why) == ("12:55", "time")


def test_trail_updates_start_with_the_fill_bar():
    def edits(df, date):
        F.set_minute(df, date, "09:07", h=1030.0)          # inside the fill bar
        F.set_from(df, date, "09:10", 1019.0)
    mk, date = F.flat_market(25, edits)
    assert _walk(mk, date) == ("09:10", 1019.0, "trail_stop")


def test_void_when_the_contract_changes_between_entry_and_exit():
    mk, date = F.flat_market(25)
    j = F.bar_at(mk, date, "09:00")
    mk.m1.held = mk.m1.held.copy()
    mk.m1.held[F.minute_at(mk, date, "12:00"):] = 2
    t = OW.simulate_book(mk, F.forced_signals(mk, a_long=[j]), "A", [date])["trades"][0]
    assert t["voided"] is True


# ---------------------------------------------------------------------
# one at a time, re-entry, daily cap
# ---------------------------------------------------------------------

def _three_signal_day(stop_minutes, signal_bars):
    def edits(df, date):
        for clock in stop_minutes:
            F.set_minute(df, date, clock, l=990.0)
    mk, date = F.flat_market(25, edits)
    idx = [F.bar_at(mk, date, c) for c in signal_bars]
    return mk, date, F.forced_signals(mk, a_long=idx)


def test_reentry_needs_a_signal_bar_that_starts_after_the_exit():
    """sec 7.2: no entry from the bar the exit happened in."""
    mk, date, sig = _three_signal_day(["09:22"], ["09:00", "09:10", "09:20", "09:25"])
    book = OW.simulate_book(mk, sig, "A", [date])
    assert [t["signal_bar"] for t in book["trades"]] == ["09:00", "09:25"]
    # an exit in a bar's FIRST minute still rules that bar out
    mk, date, sig = _three_signal_day(["09:20"], ["09:00", "09:20"])
    assert len(OW.simulate_book(mk, sig, "A", [date])["trades"]) == 1
    # one minute earlier (the previous bar) frees the 09:20 bar
    mk, date, sig = _three_signal_day(["09:19"], ["09:00", "09:20"])
    assert len(OW.simulate_book(mk, sig, "A", [date])["trades"]) == 2


def test_two_fills_a_day():
    mk, date, sig = _three_signal_day(["09:11", "09:31", "09:51"], ["09:00", "09:20", "09:40"])
    assert len(OW.simulate_book(mk, sig, "A", [date])["trades"]) == 2
    assert len(OW.simulate_book(mk, sig, "A", [date], max_fills=None)["trades"]) == 3


def test_without_exits_only_the_first_fill_exists_and_no_walk_runs(monkeypatch):
    mk, date, sig = _three_signal_day(["09:11"], ["09:00", "09:20", "09:40"])
    monkeypatch.setattr(OW, "walk_exit", lambda *a, **k: pytest.fail("pre-flight read an exit"))
    book = OW.simulate_book(mk, sig, "A", [date], exits=False)
    assert len(book["trades"]) == 1 and len(book["signals"]) == 3
    assert book["days"] == [{"date": date, "fills": 1, "fillable_signals": 3}]
    assert "exit_price" not in book["trades"][0]


# ---------------------------------------------------------------------
# days
# ---------------------------------------------------------------------

def test_gap_rule():
    full = np.arange(0, 1020)
    assert not OW.has_gap(full, OW.FLAT_MIN)
    assert not OW.has_gap(full[(full <= 600) | (full >= 615)], OW.FLAT_MIN)     # 15 min: kept
    assert OW.has_gap(full[(full <= 600) | (full >= 616)], OW.FLAT_MIN)         # 16 min: skipped
    assert OW.has_gap(full[full >= 436], OW.FLAT_MIN)                           # starts late
    assert not OW.has_gap(full[full >= 435], OW.FLAT_MIN)
    assert OW.has_gap(full[full <= 939], OW.FLAT_MIN)                           # stops early
    assert not OW.has_gap(full[(full < 100) | (full >= 300)], OW.FLAT_MIN)      # before 07:00
    assert not OW.has_gap(full[full <= 775], OW.FLAT_MIN_EARLY)
    assert OW.has_gap(np.array([], dtype=int), OW.FLAT_MIN)


def test_warmup_then_tradable_then_skipped():
    dates = F.weekdays(26)
    df = F.flat_bars(dates)
    hole = (df.index > F.stamp(dates[-1], "10:00")) & (df.index < F.stamp(dates[-1], "10:30"))
    mk = OW.prepare(df[~hole])
    status = [d.status for d in mk.days]
    assert status[:20] == ["warmup"] * 20                  # 20 earlier days at each slot
    assert status[20:25] == ["tradable"] * 5
    assert status[25] == "skipped"


def test_only_exchange_trading_days_are_traded():
    mk = OW.prepare(F.flat_bars(["2015-12-23", "2015-12-24", "2015-12-25", "2015-12-28"]))
    assert [d.date for d in mk.days] == ["2015-12-23", "2015-12-24", "2015-12-28"]
    assert [d.early for d in mk.days] == [False, True, False]


# ---------------------------------------------------------------------
# on the random walk: invariants over many trades
# ---------------------------------------------------------------------

@pytest.mark.parametrize("trigger", ["A", "B", "C"])
def test_shorts_are_the_exact_mirror_of_longs(walk_data, walk_market, trigger):
    """sec 3: turn the prices upside down and every long becomes the short."""
    _, df = walk_data
    mirror = df.copy()
    mirror["open"], mirror["close"] = 20000.0 - df["open"], 20000.0 - df["close"]
    mirror["high"], mirror["low"] = 20000.0 - df["low"], 20000.0 - df["high"]
    other = OW.prepare(mirror)
    flip = {"long": "short", "short": "long"}
    for name in OW.FILTERS:
        a = OW.simulate_book(walk_market, OW.compute_signals(walk_market, name), trigger)["trades"]
        b = OW.simulate_book(other, OW.compute_signals(other, name), trigger)["trades"]
        assert len(a) == len(b) > 0
        for x, y in zip(a, b):
            assert (flip[x["direction"]], x["fill_time"], x["exit_time"], x["exit_reason"]) == (
                y["direction"], y["fill_time"], y["exit_time"], y["exit_reason"])
            assert y["fill_price"] == pytest.approx(20000.0 - x["fill_price"])
            assert y["stop"] == pytest.approx(20000.0 - x["stop"])
            assert y["exit_price"] == pytest.approx(20000.0 - x["exit_price"])


@pytest.mark.parametrize("trigger", ["A", "B", "C", "All"])
def test_every_trade_obeys_the_rules(walk_market, trigger):
    mk = walk_market
    for name in OW.FILTERS:
        book = OW.simulate_book(mk, OW.compute_signals(mk, name), trigger)
        per_day: dict = {}
        last_exit: dict = {}
        for t in book["trades"]:
            j = t["signal_idx"]
            per_day[t["date"]] = per_day.get(t["date"], 0) + 1
            assert "08:00" <= t["signal_bar"] <= "11:55"
            assert mk.filt[name][j] == (OW.UP if t["direction"] == "long" else OW.DOWN)
            assert mk.m1.t[t["fill_idx"]] >= mk.b5.close_time[j]
            assert t["fill_price"] == mk.m1.o[t["fill_idx"]]
            assert mk.b5.start[j] > last_exit.get(t["date"], -1)
            last_exit[t["date"]] = mk.m1.t[t["exit_idx"]]
            assert t["exit_idx"] >= t["fill_idx"] and t["exit_time"][11:] <= "15:55"
            dist = t["stop_dist"]
            assert 0.5 * t["atr_signal"] - 0.13 <= dist <= 2.0 * t["atr_signal"] + 0.13
        assert not per_day or max(per_day.values()) <= 2


def test_walk_matches_a_slow_bar_by_bar_version(walk_market):
    """The vectorised walk against a plain loop, over every trade of two books."""
    mk = walk_market
    trades = []
    for name in OW.FILTERS:
        trades += OW.simulate_book(mk, OW.compute_signals(mk, name), "All", max_fills=None)["trades"]
    assert len(trades) > 50
    by_date = {d.date: d for d in mk.days}
    reasons = set()
    for t in trades:
        day = by_date[t["date"]]
        long = t["direction"] == "long"
        stop = best = None
        stop, best = t["stop"], t["fill_price"]
        got = None
        i = t["fill_idx"]
        while got is None:
            if i >= day.exit_idx:
                got = (day.exit_idx, mk.m1.o[day.exit_idx], "time")
                break
            if (mk.m1.l[i] <= stop) if long else (mk.m1.h[i] >= stop):
                gapped = (mk.m1.o[i] <= stop) if long else (mk.m1.o[i] >= stop)
                got = (i, mk.m1.o[i] if gapped else stop,
                       "initial_stop" if stop == t["stop"] else "trail_stop")
                break
            k = mk.m1.bar5[i]
            if mk.m1.bar5[i + 1] != k:                      # the 5-min bar just closed
                if long:
                    best = max(best, mk.b5.h[k])
                    stop = max(stop, float(OW.floor_tick(best - 2.5 * mk.atr[k])))
                else:
                    best = min(best, mk.b5.l[k])
                    stop = min(stop, float(OW.ceil_tick(best + 2.5 * mk.atr[k])))
            i += 1
        assert (t["exit_idx"], t["exit_price"], t["exit_reason"]) == (got[0], got[1], got[2]), t
        reasons.add(got[2])
    assert reasons == {"initial_stop", "trail_stop", "time"}
