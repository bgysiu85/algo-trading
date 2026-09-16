#!/usr/bin/env python3
"""MCL-PB v3 against its registration, clause by clause.

`MCL.signals` is replaced with a hand-built frame so MACD can be forced on the
exact bar a test needs. The replacement is seen by MCL's own engine too, which
is the point: the exit under test is the published one, not a copy.
"""
from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from strategy.mcl import mcl as MCL
from strategy.mcl import pullback_break as PB

ET = ZoneInfo("America/New_York")
DAY = date(2026, 9, 11)
BASE_VOL = 10_000


def frame(bars, macd_closed=(), vol=None, start=dtime(4, 0)):
    """bars = [(o, h, l, c)]; macd_closed = rows where macd <= signal;
    vol = {row: volume}, default BASE_VOL. Rows 0-19 are warm-up for the
    volume average when the test needs one (the frame is prefixed with 20
    quiet bars)."""
    quiet = [(5.00, 5.01, 4.99, 5.00)] * 20
    bars = quiet + list(bars)
    t0 = datetime.combine(DAY, start, tzinfo=ET)
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=i) for i in range(len(bars))])
    d = pd.DataFrame(bars, columns=["open", "high", "low", "close"], index=idx)
    d["volume"] = BASE_VOL
    for r, x in (vol or {}).items():
        d.iloc[20 + r, d.columns.get_loc("volume")] = x
    d["macd"], d["macd_sig"] = 1.0, 0.0
    for r in macd_closed:
        d.iloc[20 + r, d.columns.get_loc("macd")] = -1.0
    d["entry"] = False
    d["exit_sig"] = False
    return d


def row(sig, r):
    return sig.index[20 + r]


@pytest.fixture
def patched(monkeypatch):
    holder = {}
    monkeypatch.setattr(MCL, "signals",
                        lambda df, require_macd_pos=None: holder["sig"].copy())

    def run(sig, **kw):
        holder["sig"] = sig
        return PB.backtest_session_detail(
            sig[["open", "high", "low", "close", "volume"]], DAY, ET,
            entry_shares=100, **kw)
    return run


G = (5.00, 5.02, 4.99, 5.01)            # a quiet green bar
BIG = 3 * BASE_VOL


def shape():
    """peak 5.10 at row 1, reds at 2 and 3 (armed), bounce high 5.06 at row 4,
    break of 5.07 at row 5 that closes 5.14."""
    return [G,
            (5.00, 5.10, 5.00, 5.08),   # 1 swing high
            (5.07, 5.08, 5.04, 5.05),   # 2 red
            (5.05, 5.07, 5.03, 5.04),   # 3 red -> armed, level = peak 5.10
            (5.04, 5.06, 5.03, 5.05),   # 4 bounce: level -> 5.06
            (5.05, 5.15, 5.04, 5.14),   # 5 break of 5.07
            (5.14, 5.15, 5.13, 5.14)]   # 6


def test_the_shape_enters_at_the_break_bars_close(patched):
    sig = frame(shape() + [G, G], vol={5: BIG})
    r = patched(sig)
    (t,) = r.trades
    assert pd.Timestamp(t.entry_time) == row(sig, 5)
    assert t.entry_price == pytest.approx(5.15)             # close + tick
    s = [x for x in r.setups if x.outcome == PB.TRIGGERED][0]
    assert s.peak == pytest.approx(5.10) and s.level == pytest.approx(5.06)


def test_the_level_is_the_bounce_high_not_the_peak(patched):
    """Row 5 reaches 5.07 but not 5.11. It fires because the level is 5.06."""
    b = shape() + [G, G]
    b[5] = (5.05, 5.09, 5.04, 5.08)
    (t,) = patched(frame(b, vol={5: BIG})).trades
    assert pd.Timestamp(t.entry_time) == row(frame(b), 5)


def test_before_any_bounce_bar_the_level_is_the_peak(patched):
    b = shape() + [G, G]
    b[4] = (5.05, 5.15, 5.04, 5.14)      # breaks 5.11 straight after arming
    (t,) = patched(frame(b, vol={4: BIG})).trades
    assert pd.Timestamp(t.entry_time) == row(frame(b), 4)


def test_one_red_bar_is_not_a_pullback(patched):
    b = shape() + [G, G]; del b[3]
    assert patched(frame(b, vol={4: BIG})).trades == []


def test_a_red_peak_bar_counts_as_the_first_red(patched):
    b = shape() + [G, G]
    b[1] = (5.09, 5.10, 5.00, 5.02)      # peak bar red
    del b[3]                             # so only one more red
    (t,) = patched(frame(b, vol={4: BIG})).trades
    assert pd.Timestamp(t.entry_time) == row(frame(b), 4)


def test_a_doji_is_not_red(patched):
    b = shape() + [G, G]
    b[3] = (5.05, 5.07, 5.03, 5.05)      # doji where the 2nd red was
    assert patched(frame(b, vol={5: BIG})).trades == []


def test_volume_at_or_below_the_prior_20_average_refuses_and_raises_the_level(patched):
    b = shape() + [(5.14, 5.20, 5.13, 5.19), (5.19, 5.20, 5.18, 5.19), G]
    r = patched(frame(b, vol={5: BASE_VOL, 7: BIG}))       # row 5 refused, row 7 fires on 5.16
    (t,) = r.trades
    assert pd.Timestamp(t.entry_time) == row(frame(b), 7)
    assert t.entry_price == pytest.approx(5.20)
    assert r.refused["vol"] == 1
    s = [x for x in r.setups if x.outcome == PB.TRIGGERED][0]
    assert s.level == pytest.approx(5.15)                   # raised by the refused bar


def test_a_bar_crossing_two_setups_is_credited_to_the_latest_armed(patched):
    """Outer top 6.79, inner top 6.20 armed later. Their levels coincide (the
    outer setup's bounce top is the inner setup's peak), so one bar closes
    through both: one trade, credited to the 6.20 setup; 6.79 is consumed."""
    b = [G,
         (6.00, 6.79, 6.00, 6.70),   # 1 outer top
         (6.70, 6.72, 6.10, 6.15),   # 2 red
         (6.15, 6.16, 5.80, 5.90),   # 3 red -> armed (A), level = 6.79
         (5.90, 6.05, 5.85, 6.00),   # 4 A's bounce 6.05; candidate 6.05
         (6.02, 6.20, 6.00, 6.10),   # 5 inner top 6.20; A's bounce 6.20
         (6.10, 6.12, 5.95, 5.98),   # 6 red
         (5.98, 6.00, 5.90, 5.93),   # 7 red -> armed (B), level = 6.20
         (5.95, 7.00, 5.94, 6.95),   # 8 through both, closes above both, on volume
         (6.95, 6.96, 6.90, 6.94), G, G]
    r = patched(frame(b, vol={8: BIG}))
    assert len(r.trades) == 1
    trig = [s for s in r.setups if s.outcome == PB.TRIGGERED]
    assert len(trig) == 1 and trig[0].peak == pytest.approx(6.20)
    assert [s.outcome for s in r.setups if s.peak == pytest.approx(6.79)] == [PB.REFUSED_BUSY]


def test_a_break_that_closes_at_or_below_the_level_is_refused(patched):
    b = shape() + [G, G]
    b[5] = (5.05, 5.15, 5.04, 5.06)      # wick through, closes at the level
    r = patched(frame(b, vol={5: BIG}))
    assert r.trades == [] and r.refused["close"] == 1


def test_macd_is_read_on_the_break_bar(patched):
    b = shape() + [G, G]
    assert patched(frame(b, vol={5: BIG}, macd_closed=[5])).trades == []
    assert len(patched(frame(b, vol={5: BIG}, macd_closed=[4])).trades) == 1


def test_no_depth_cancel(patched):
    b = [G, (5.00, 6.00, 5.00, 5.90), (5.80, 5.85, 5.00, 5.10), (5.10, 5.12, 4.70, 4.80),
         (4.80, 4.90, 4.75, 4.85), (4.90, 6.10, 4.88, 6.05), (6.05, 6.06, 6.0, 6.02), G, G]
    (t,) = patched(frame(b, vol={5: BIG})).trades
    assert t.entry_price == pytest.approx(6.06)


def test_time_limit_expires_the_setup(patched):
    b = shape()[:4] + [(5.04, 5.05, 5.03, 5.04)] * 58 + [(5.05, 5.15, 5.04, 5.14), (5.14, 5.15, 5.13, 5.14), G]
    r = patched(frame(b, vol={62: BIG}))
    assert r.trades == [] and PB.EXPIRED in [s.outcome for s in r.setups]


def test_never_on_the_final_session_bar(patched):
    b = shape()[:5] + [(5.05, 5.15, 5.04, 5.14)]
    r = patched(frame(b, vol={5: BIG}))
    assert r.trades == [] and PB.WINDOW in [x.outcome for x in r.setups]


def test_the_floor_blocks_the_entry_but_state_still_builds(patched):
    b = shape() + [(5.14, 5.12, 5.10, 5.11),   # 7 red
                   (5.11, 5.12, 5.08, 5.09),   # 8 red -> armed on the 5.15 peak (row 5)
                   (5.10, 5.20, 5.09, 5.19),   # 9 break of 5.16 on volume
                   (5.19, 5.20, 5.18, 5.19), G]
    sig = frame(b, vol={5: BIG, 9: BIG})
    r = patched(sig, not_before=dtime(4, 26))              # row 6 is 04:26; row 5 is before the floor
    (t,) = r.trades
    assert pd.Timestamp(t.entry_time) == row(sig, 9)


def test_green_hold_reaches_the_engine_and_frees_the_next_entry(patched):
    b = shape() + [(5.14, 5.15, 5.13, 5.14),   # 7
                   (5.14, 5.16, 5.13, 5.15),   # 8: 3 bars after entry, green -> out
                   (5.15, 5.16, 5.12, 5.13),   # 9 red
                   (5.13, 5.14, 5.10, 5.11),   # 10 red -> armed on peak 5.16 (row 8)
                   (5.11, 5.13, 5.10, 5.12),   # 11 bounce 5.13
                   (5.12, 5.25, 5.11, 5.24),   # 12 breaks 5.14 on volume
                   (5.24, 5.25, 5.23, 5.24), G, G, G]
    sig = frame(b, vol={5: BIG, 12: BIG})
    r = patched(sig, green_hold_bars=3)
    assert [t.reason for t in r.trades][0] == "green_hold"
    assert len(r.trades) == 2


def test_while_long_a_crossed_level_is_consumed_not_entered(patched):
    b = shape() + [(5.14, 5.30, 5.13, 5.28), (5.28, 5.29, 5.20, 5.22), (5.22, 5.23, 5.15, 5.17),
                   (5.17, 5.35, 5.16, 5.34), (5.34, 5.35, 5.33, 5.34), G]
    r = patched(frame(b, vol={5: BIG, 10: BIG}))
    assert len(r.trades) == 1
    assert PB.REFUSED_BUSY in [s.outcome for s in r.setups]


def test_engine_owned_kwargs_are_refused():
    with pytest.raises(TypeError):
        PB.backtest_session_detail(frame([G]), DAY, ET, entry_bars=None)


def test_band_refusal_is_recorded(patched):
    b = [(1.50, 1.51, 1.49, 1.50), (1.40, 1.60, 1.40, 1.55), (1.55, 1.56, 1.50, 1.52),
         (1.52, 1.53, 1.49, 1.50), (1.51, 1.70, 1.50, 1.69), (1.69, 1.70, 1.68, 1.69), G, G]
    r = patched(frame(b, vol={4: BIG}))
    assert r.trades == [] and PB.BAND in [s.outcome for s in r.setups]
