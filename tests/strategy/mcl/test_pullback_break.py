#!/usr/bin/env python3
"""MCL-PB against the registration, clause by clause.

`MCL.signals` is replaced with a hand-built frame so every clause can be forced
on the exact bar a test needs. The replacement is seen by MCL's own engine too,
which is the point: the exit under test is the published one, not a copy.
"""
from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from strategy.mcl import mcl as MCL
from strategy.mcl import pullback_break as PB

ET = ZoneInfo("America/New_York")
DAY = date(2026, 9, 11)


def frame(bars, entry=(), macd=None, start=dtime(4, 0)):
    """bars = [(o, h, l, c)]; entry = row numbers with MCL's signal true;
    macd = {row: (macd, macd_sig)} overrides, default (1.0, 0.0) = open."""
    t0 = datetime.combine(DAY, start, tzinfo=ET)
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=i) for i in range(len(bars))])
    d = pd.DataFrame(bars, columns=["open", "high", "low", "close"], index=idx)
    d["volume"] = 10_000
    d["macd"], d["macd_sig"] = 1.0, 0.0
    for r, (m, s) in (macd or {}).items():
        d.iloc[r, d.columns.get_loc("macd")] = m
        d.iloc[r, d.columns.get_loc("macd_sig")] = s
    d["entry"] = False
    for r in entry:
        d.iloc[r, d.columns.get_loc("entry")] = True
    d["exit_sig"] = False
    return d


@pytest.fixture
def patched(monkeypatch):
    holder = {}
    monkeypatch.setattr(MCL, "signals",
                        lambda df, require_macd_pos=None: holder["sig"].copy())

    def run(sig, **kw):
        holder["sig"] = sig
        return PB.backtest_session_detail(sig[["open", "high", "low", "close", "volume"]],
                                          DAY, ET, entry_shares=100, **kw)
    return run


FLAT = (5.05, 5.06, 5.04, 5.05)


def test_the_basic_shape_signal_lower_high_break(patched):
    sig = frame([FLAT,
                 (5.00, 5.10, 5.00, 5.08),   # 1 signal: peak 5.10, base 5.00
                 (5.07, 5.08, 5.06, 5.07),   # 2 lower high -> armed
                 (5.08, 5.15, 5.07, 5.14),   # 3 passes 5.11 -> buy
                 (5.14, 5.16, 5.13, 5.15),
                 FLAT], entry=[1])
    r = patched(sig)
    assert [s.outcome for s in r.setups] == [PB.TRIGGERED]
    (t,) = r.trades
    assert pd.Timestamp(t.entry_time) == sig.index[3]
    assert t.entry_price == pytest.approx(5.12)            # 5.10 + 1c stop + 1 tick
    assert r.setups[0].signal_close == pytest.approx(5.08)


def test_a_gap_through_the_stop_pays_the_open(patched):
    sig = frame([FLAT, (5.00, 5.10, 5.00, 5.08), (5.07, 5.08, 5.06, 5.07),
                 (5.30, 5.35, 5.28, 5.33), (5.33, 5.34, 5.32, 5.33), FLAT],
                entry=[1])
    (t,) = patched(sig).trades
    assert t.entry_price == pytest.approx(5.31)


def test_nothing_fires_without_a_pullback_first(patched):
    """Straight up: every bar a higher high. The rule never arms."""
    bars = [FLAT] + [(5.0 + k / 10, 5.1 + k / 10, 5.0 + k / 10, 5.1 + k / 10)
                     for k in range(6)]
    r = patched(frame(bars, entry=[1]))
    assert r.trades == []
    assert r.setups[0].outcome == PB.WINDOW


def test_a_new_high_before_arming_moves_the_peak(patched):
    sig = frame([FLAT,
                 (5.00, 5.10, 5.00, 5.08),   # peak 5.10
                 (5.09, 5.20, 5.08, 5.19),   # higher high, not armed -> peak 5.20
                 (5.18, 5.19, 5.16, 5.17),   # lower high -> armed
                 (5.18, 5.22, 5.17, 5.21),   # passes 5.21
                 (5.21, 5.22, 5.20, 5.21), FLAT], entry=[1])
    (t,) = patched(sig).trades
    assert pd.Timestamp(t.entry_time) == sig.index[4]
    assert t.entry_price == pytest.approx(5.22)


def test_macd_closed_on_the_previous_bar_blocks_the_break_and_disarms(patched):
    """macd > signal but <= 0 on bar 3: no MACD cancel, but no entry on bar 4.
    Bar 4's high becomes the new peak and needs its own pullback."""
    sig = frame([FLAT,
                 (5.00, 5.10, 5.00, 5.08),
                 (5.07, 5.08, 5.06, 5.07),   # armed
                 (5.07, 5.08, 5.06, 5.07),   # macd -0.1 > sig -0.2, but not > 0
                 (5.08, 5.14, 5.07, 5.13),   # break, refused -> peak 5.14
                 (5.12, 5.13, 5.11, 5.12),   # lower high -> armed
                 (5.13, 5.16, 5.12, 5.15),   # passes 5.15
                 (5.15, 5.16, 5.14, 5.15), FLAT],
                entry=[1], macd={3: (-0.1, -0.2)})
    (t,) = patched(sig).trades
    assert pd.Timestamp(t.entry_time) == sig.index[6]
    assert t.entry_price == pytest.approx(5.16)


def test_the_macd_test_reads_the_COMPLETED_bar_not_the_trigger_bar(patched):
    """MACD rolls over ON the break bar. The stop was live when the bar opened
    and that bar's MACD was not knowable, so it fills."""
    sig = frame([FLAT, (5.00, 5.10, 5.00, 5.08), (5.07, 5.08, 5.06, 5.07),
                 (5.08, 5.15, 5.07, 5.14), (5.14, 5.15, 5.13, 5.14), FLAT],
                entry=[1], macd={3: (0.1, 0.5)})
    assert len(patched(sig).trades) == 1


def test_depth_cancel_at_half_the_run_from_the_signal_low(patched):
    sig = frame([FLAT,
                 (5.00, 5.10, 5.00, 5.08),   # cancel level 5.10 - 0.05 = 5.05
                 (5.07, 5.08, 5.04, 5.05),   # low 5.04 -> cancelled
                 (5.06, 5.20, 5.05, 5.19),   # would have broken
                 FLAT, FLAT], entry=[1])
    r = patched(sig)
    assert r.trades == []
    assert r.setups[0].outcome == PB.CANCEL_DEPTH


def test_depth_exactly_at_the_level_does_not_cancel(patched):
    sig = frame([FLAT, (5.00, 5.10, 5.00, 5.08), (5.07, 5.08, 5.05, 5.06),
                 (5.07, 5.12, 5.06, 5.11), (5.11, 5.12, 5.10, 5.11), FLAT],
                entry=[1])
    assert len(patched(sig).trades) == 1


def test_macd_cancel_at_the_close(patched):
    sig = frame([FLAT, (5.00, 5.10, 5.00, 5.08), (5.07, 5.08, 5.06, 5.07),
                 (5.08, 5.15, 5.07, 5.14), FLAT, FLAT],
                entry=[1], macd={2: (0.1, 0.2)})
    r = patched(sig)
    assert r.trades == []
    assert r.setups[0].outcome == PB.CANCEL_MACD


def test_the_resting_stop_is_tested_before_the_cancels(patched):
    """Armed bar that breaks AND trades through the depth level: the stop was
    resting, so it filled; the cancel would only have applied at the close."""
    sig = frame([FLAT, (5.00, 5.10, 5.00, 5.08), (5.07, 5.08, 5.06, 5.07),
                 (5.07, 5.12, 4.90, 4.95), (4.95, 4.96, 4.94, 4.95), FLAT],
                entry=[1])
    r = patched(sig)
    assert r.setups[0].outcome == PB.TRIGGERED
    assert len(r.trades) == 1


def test_never_triggers_on_the_final_session_bar(patched):
    sig = frame([FLAT, (5.00, 5.10, 5.00, 5.08), (5.07, 5.08, 5.06, 5.07),
                 (5.08, 5.15, 5.07, 5.14)], entry=[1])
    r = patched(sig)
    assert r.trades == []
    assert r.setups[0].outcome == PB.WINDOW


def test_a_signal_before_the_floor_opens_nothing(patched):
    sig = frame([FLAT, (5.00, 5.10, 5.00, 5.08), (5.07, 5.08, 5.06, 5.07),
                 (5.08, 5.15, 5.07, 5.14), (5.14, 5.15, 5.13, 5.14), FLAT],
                entry=[1])
    r = patched(sig, not_before=dtime(4, 2))
    assert r.setups == [] and r.trades == []


def test_signals_while_in_a_trade_are_ignored_and_the_next_needs_a_fresh_one(patched):
    bars = [FLAT,
            (5.00, 5.10, 5.00, 5.08),   # 1 signal
            (5.07, 5.08, 5.06, 5.07),   # 2 armed
            (5.08, 5.15, 5.07, 5.14),   # 3 buy @ 5.12, peak seeded 5.12
            (5.14, 5.20, 5.13, 5.19),   # 4 signal while long -> ignored
            (5.19, 5.20, 4.80, 4.85),   # 5 trail (5.20*0.95=4.94) -> out
            (4.85, 4.90, 4.84, 4.88),   # 6 signal: fresh setup, peak 4.90
            (4.88, 4.89, 4.87, 4.88),   # 7 armed
            (4.89, 4.95, 4.88, 4.94),   # 8 buy @ 4.92
            (4.94, 4.95, 4.93, 4.94), FLAT]
    r = patched(frame(bars, entry=[1, 4, 6]))
    assert [s.signal_i for s in r.setups] == [1, 6]
    assert [pd.Timestamp(t.entry_time) for t in r.trades] == \
        [frame(bars).index[3], frame(bars).index[8]]
    assert r.trades[0].reason == "trailing_stop"


def test_a_setup_pending_ignores_new_signals(patched):
    sig = frame([FLAT, (5.00, 5.10, 5.00, 5.08), (5.07, 5.08, 5.06, 5.07),
                 (5.07, 5.08, 5.06, 5.07),   # signal again, setup keeps its peak
                 (5.08, 5.12, 5.07, 5.11), (5.11, 5.12, 5.10, 5.11), FLAT],
                entry=[1, 3])
    r = patched(sig)
    assert len(r.setups) == 1 and r.setups[0].peak == pytest.approx(5.10)


def test_engine_owned_kwargs_are_refused():
    with pytest.raises(TypeError):
        PB.backtest_session_detail(frame([FLAT]), DAY, ET, entry_bars=None)


def test_band_refusal_is_recorded_not_dropped(patched):
    bars = [(1.50, 1.51, 1.49, 1.50), (1.40, 1.60, 1.40, 1.55),
            (1.55, 1.56, 1.54, 1.55), (1.56, 1.70, 1.55, 1.69),
            (1.69, 1.70, 1.68, 1.69), (1.69, 1.70, 1.68, 1.69)]
    r = patched(frame(bars, entry=[1]))
    assert r.trades == [] and r.setups[0].outcome == PB.BAND


def test_a_refused_break_needs_a_NEW_pullback_before_the_next_break(patched):
    """Bar 4's break is refused on MACD. Bar 5 goes straight on to another high
    with MACD open again -- that is not a pullback-then-break, so no entry until
    bar 6 pulls back and bar 7 breaks."""
    sig = frame([FLAT,
                 (5.00, 5.10, 5.00, 5.08),
                 (5.07, 5.08, 5.06, 5.07),   # 2 armed
                 (5.07, 5.08, 5.06, 5.07),   # 3 macd not > 0
                 (5.08, 5.14, 5.07, 5.13),   # 4 refused -> peak 5.14, disarmed
                 (5.13, 5.18, 5.12, 5.17),   # 5 higher again: NOT an entry
                 (5.16, 5.17, 5.15, 5.16),   # 6 lower high -> armed
                 (5.17, 5.20, 5.16, 5.19),   # 7 passes 5.19
                 (5.19, 5.20, 5.18, 5.19), FLAT],
                entry=[1], macd={3: (-0.1, -0.2)})
    (t,) = patched(sig).trades
    assert pd.Timestamp(t.entry_time) == sig.index[7]
    assert t.entry_price == pytest.approx(5.20)


def test_the_pole_starts_at_the_lowest_low_of_the_five_bars_to_the_signal(patched):
    """Pole low 4.80 (4 bars before the signal), peak 5.10 -> cancel below 4.95.
    A pullback to 5.00 is inside it; against the signal bar alone (5.05) it
    would have cancelled."""
    sig = frame([FLAT, FLAT,
                 (4.85, 4.90, 4.80, 4.88),   # 2  pole low
                 (4.88, 4.95, 4.87, 4.94),
                 (4.94, 4.99, 4.93, 4.98),
                 (4.98, 5.02, 4.97, 5.01),
                 (5.01, 5.10, 5.00, 5.08),   # 6  signal
                 (5.07, 5.08, 5.00, 5.02),   # 7  lower high, low 5.00 -> armed, alive
                 (5.03, 5.12, 5.02, 5.11),   # 8  passes 5.11
                 (5.11, 5.12, 5.10, 5.11), FLAT], entry=[6])
    r = patched(sig)
    assert r.setups[0].outcome == PB.TRIGGERED


def test_a_low_six_bars_back_is_not_in_the_pole(patched):
    sig = frame([FLAT,
                 (4.85, 4.90, 4.50, 4.88),   # 1  six bars before the signal
                 FLAT, FLAT, FLAT, FLAT,
                 (5.00, 5.10, 5.00, 5.08),   # 6  signal; pole low 5.00 -> cancel < 5.05
                 (5.07, 5.08, 5.02, 5.03),   # 7  cancelled
                 (5.03, 5.12, 5.02, 5.11), (5.11, 5.12, 5.10, 5.11), FLAT],
                entry=[6])
    assert patched(sig).setups[0].outcome == PB.CANCEL_DEPTH
