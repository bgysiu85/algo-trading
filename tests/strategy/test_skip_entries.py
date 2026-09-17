#!/usr/bin/env python3
"""`skip_entries`: the first N entries the engine would have taken are passed
over, and the engine then runs as the rule says -- on both engines.

Registered in docs/research/REGISTERED_first_entry_skip.md (H-B1). The tests
pin the three things the registration says about the parameter: that `0` is
bit-identical to the engine before it existed; that it is the SIGNAL-ORDINAL
form (the skipped book can contain an entry the baseline never took, because
the baseline was in a position on that bar); and that a band-refused signal is
not an entry and does not spend the budget.
"""
from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from strategy.mc5 import mc5 as MC5
from strategy.mcl import mcl as MCL

ET = ZoneInfo("America/New_York")
DAY = date(2026, 9, 11)

F = (5.00, 5.00, 5.00, 5.00)           # flat bar: entry 5.01, 5% trail 4.7595
STOP = (5.00, 5.02, 4.70, 4.80)        # low through the trail: exits the trade
CHEAP = (1.00, 1.00, 1.00, 1.00)       # below PRICE_MIN: a band-refused signal


# --- MCL ---------------------------------------------------------------------

def mcl_run(bars, signal_at, **kw):
    """Hand-built 1-minute bars from 07:00 ET; `signal_at` are the bar indices
    on which the rule is made to fire, via the engine's own `entry_bars`
    hook, so the test controls WHERE signals fall without needing the
    indicator stack to produce them."""
    t0 = datetime.combine(DAY, dtime(7, 0), tzinfo=ET)
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=i) for i in range(len(bars))])
    df = pd.DataFrame(bars, columns=["open", "high", "low", "close"], index=idx)
    df["volume"] = 10_000
    take = pd.Series(False, index=idx)
    for i in signal_at:
        take.iloc[i] = True
    return MCL.backtest_session(df, DAY, ET, entry_bars=take, entry_shares=100,
                                use_apex=False, **kw)


def entries(trades):
    return [pd.Timestamp(t.entry_time).tz_convert(ET).strftime("%H:%M") for t in trades]


def test_mcl_zero_is_bit_identical_to_the_default():
    bars = [F, STOP, F, F, STOP, F]
    a = [t.__dict__ for t in mcl_run(bars, [0, 3])]
    b = [t.__dict__ for t in mcl_run(bars, [0, 3], skip_entries=0)]
    assert a == b and len(a) == 2


def test_mcl_skip_one_takes_the_second_entry_and_not_the_first():
    bars = [F, STOP, F, F, STOP, F]
    base = mcl_run(bars, [0, 3])
    skip = mcl_run(bars, [0, 3], skip_entries=1)
    assert entries(base) == ["07:00", "07:03"]
    assert entries(skip) == ["07:03"]
    # The trade that survives is bar-for-bar the baseline's second one.
    assert skip[0].__dict__ == base[1].__dict__


def test_mcl_is_signal_ordinal_not_an_accounting_filter():
    """The baseline is in a position on bar 1, so its signal there is
    suppressed and the baseline books ONE trade. The skip book never opens
    bar 0's position, so bar 1 is a live signal and it enters there -- an
    entry the baseline does not contain. This is what the registration
    means by 'not a subset', and it is the difference between the rule a
    live trader would follow and deleting a row from a finished book."""
    bars = [F, F, STOP, F]
    base = mcl_run(bars, [0, 1])
    skip = mcl_run(bars, [0, 1], skip_entries=1)
    assert entries(base) == ["07:00"]
    assert entries(skip) == ["07:01"]
    assert not set(entries(skip)) <= set(entries(base))


def test_mcl_skip_with_one_signal_books_nothing():
    assert mcl_run([F, STOP, F], [0], skip_entries=1) == []


def test_mcl_a_band_refused_signal_does_not_spend_the_budget():
    """Bar 0 fires at $1.00, outside the price band: the engine refuses it
    and it is not an entry. skip=1 must therefore pass over bar 2's entry
    (the first the engine would have taken) and take bar 4's."""
    bars = [CHEAP, F, F, STOP, F, STOP, F]
    base = mcl_run(bars, [0, 2, 4])
    skip = mcl_run(bars, [0, 2, 4], skip_entries=1)
    assert entries(base) == ["07:02", "07:04"]
    assert entries(skip) == ["07:04"]


def test_mcl_skip_two():
    bars = [F, STOP, F, STOP, F, STOP, F]
    assert entries(mcl_run(bars, [0, 2, 4], skip_entries=2)) == ["07:04"]
    assert entries(mcl_run(bars, [0, 2, 4], skip_entries=3)) == []


def test_mcl_negative_is_refused():
    with pytest.raises(ValueError):
        mcl_run([F, STOP], [0], skip_entries=-1)


# --- MC5 ---------------------------------------------------------------------

def mc5_run(bars, signal_at, monkeypatch, **kw):
    """Five-minute bars from 07:00 ET (so the engine does not resample), with
    `signals` replaced by one that fires on the chosen bars. MC5 has no
    `entry_bars` hook; patching the signal function is the same control
    applied one layer up."""
    t0 = datetime.combine(DAY, dtime(7, 0), tzinfo=ET)
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=5 * i) for i in range(len(bars))])
    df = pd.DataFrame(bars, columns=["open", "high", "low", "close"], index=idx)
    df["volume"] = 10_000

    def fake_signals(df5):
        out = df5.copy()
        out["entry"] = False
        for i in signal_at:
            out.iloc[i, out.columns.get_loc("entry")] = True
        out["exit_sig"] = False
        return out

    monkeypatch.setattr(MC5, "signals", fake_signals)
    return MC5.backtest_session(df, DAY, ET, entry_shares=100, use_apex=False, **kw)


def test_mc5_zero_is_bit_identical_to_the_default(monkeypatch):
    bars = [F, STOP, F, F, STOP, F]
    a = [t.__dict__ for t in mc5_run(bars, [0, 3], monkeypatch)]
    b = [t.__dict__ for t in mc5_run(bars, [0, 3], monkeypatch, skip_entries=0)]
    assert a == b and len(a) == 2


def test_mc5_skip_one_takes_the_second_entry(monkeypatch):
    bars = [F, STOP, F, F, STOP, F]
    base = mc5_run(bars, [0, 3], monkeypatch)
    skip = mc5_run(bars, [0, 3], monkeypatch, skip_entries=1)
    assert entries(base) == ["07:00", "07:15"]
    assert entries(skip) == ["07:15"]
    assert skip[0].__dict__ == base[1].__dict__


def test_mc5_is_signal_ordinal(monkeypatch):
    bars = [F, F, STOP, F]
    base = mc5_run(bars, [0, 1], monkeypatch)
    skip = mc5_run(bars, [0, 1], monkeypatch, skip_entries=1)
    assert entries(base) == ["07:00"]
    assert entries(skip) == ["07:05"]


def test_mc5_a_band_refused_signal_does_not_spend_the_budget(monkeypatch):
    bars = [CHEAP, F, F, STOP, F, STOP, F]
    skip = mc5_run(bars, [0, 2, 4], monkeypatch, skip_entries=1)
    assert entries(skip) == ["07:20"]


def test_mc5_negative_is_refused(monkeypatch):
    with pytest.raises(ValueError):
        mc5_run([F, STOP], [0], monkeypatch, skip_entries=-1)
