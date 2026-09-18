#!/usr/bin/env python3
"""The two constants H-E2 sweeps, as parameters on the engines.

REGISTERED_entry_sweep.md §2 sweeps `mcl.VOL_MULTIPLE` and
`mc5.ENTRY_RSI_ROC_PCT`. Both were module constants; both are now overridable
per call, with None reading the constant. Two things have to hold or the sweep
measures nothing: the override must actually reach the condition, and None
must leave the LIVE path bit-identical -- `evaluate_last_bar` passes neither,
and this project has been split four times by a constant the live path read
differently from the backtest.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from strategy.mc5 import mc5 as MC5
from strategy.mcl import mcl as MCL

ET = ZoneInfo("America/New_York")


def frame(vols, px=3.0, start="2026-09-11 05:00"):
    t0 = pd.Timestamp(start, tz=ET)
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=i) for i in range(len(vols))])
    return pd.DataFrame({"open": px, "high": px, "low": px, "close": px,
                         "volume": list(vols)}, index=idx)


# --- MCL: the volume surge multiple ----------------------------------------

def test_the_surge_multiple_decides_c_vol():
    """A bar at 2x the previous one: the published 3.0 refuses it, 2.0 takes
    it. This is the clause that puts MCL's entry on the spike bar."""
    df = frame([1000] * 5 + [2000])
    assert bool(MCL.signals(df)["c_vol"].iloc[-1]) is False
    assert bool(MCL.signals(df, vol_multiple=3.0)["c_vol"].iloc[-1]) is False
    assert bool(MCL.signals(df, vol_multiple=2.0)["c_vol"].iloc[-1]) is True
    assert bool(MCL.signals(df, vol_multiple=1.5)["c_vol"].iloc[-1]) is True


def test_none_reads_the_module_constant_not_a_hardcoded_copy(monkeypatch):
    """A literal 3.0 in the default would be indistinguishable from reading
    VOL_MULTIPLE until somebody changed the constant."""
    df = frame([1000] * 5 + [2000])
    monkeypatch.setattr(MCL, "VOL_MULTIPLE", 2.0)
    assert bool(MCL.signals(df)["c_vol"].iloc[-1]) is True


def test_a_non_positive_multiple_is_refused_rather_than_run():
    """At 0 every bar surges and c_vol stops being a condition at all."""
    df = frame([1000] * 6)
    for bad in (0.0, -1.0):
        with pytest.raises(ValueError, match="positive"):
            MCL.signals(df, vol_multiple=bad)


def test_the_multiple_does_not_leak_into_the_other_four_clauses():
    """§2: one constant per family. If sweeping the multiple also moved MACD,
    MFI, RSI or the floor, the family would be sweeping two things and V9's
    mistake would be back."""
    df = frame([1000, 1200, 900, 1500, 1100, 2000])
    a, b = MCL.signals(df, vol_multiple=3.0), MCL.signals(df, vol_multiple=1.5)
    for col in ("c_macd", "c_mfi", "c_rsi", "c_floor", "macd", "mfi", "rsi"):
        assert a[col].equals(b[col]), col


def test_the_live_evaluator_never_sees_the_sweep_parameter():
    """`evaluate_last_bar` takes no vol_multiple, so a sweep cannot move the
    trader -- the separation `price_min` already has."""
    import inspect
    assert "vol_multiple" not in inspect.signature(MCL.evaluate_last_bar).parameters
    assert "vol_multiple" in inspect.signature(MCL.backtest_session).parameters


# --- MC5: the RSI rate-of-change threshold ---------------------------------

def wobble(n=60):
    """A series whose RSI actually MOVES. On a steadily rising series RSI pegs
    at 100 and its rate of change is 0 everywhere, so every threshold above
    zero admits nothing and the dial looks inert when it is not."""
    import math
    return [round(3.0 + 0.35 * math.sin(i / 3.0) + 0.012 * i, 4) for i in range(n)]


def mc5_frame(closes):
    t0 = pd.Timestamp("2026-09-11 05:00", tz=ET)
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=5 * i) for i in range(len(closes))])
    return pd.DataFrame({"open": closes, "high": closes, "low": closes,
                         "close": closes, "volume": 10_000}, index=idx)


def test_the_rsi_roc_threshold_decides_c_rsi():
    """MC5's one 'how much confirmation' dial. A lower bar admits bars a
    higher one refuses, and nothing else about the signal moves."""
    df = mc5_frame(wobble())
    counts = {thr: int(MC5.signals(df, entry_rsi_roc=thr)["c_rsi"].sum())
              for thr in (1.0, 5.0, 10.0, 1000.0)}
    # Strictly monotone: a lower bar admits everything a higher one does, and
    # more. That ordering is the whole content of the dial.
    assert counts[1.0] > counts[5.0] > counts[10.0] > counts[1000.0] == 0, counts
    loose = MC5.signals(df, entry_rsi_roc=1.0)["c_rsi"]
    tight = MC5.signals(df, entry_rsi_roc=10.0)["c_rsi"]
    assert (tight & ~loose).sum() == 0, "a lower threshold refused a bar a higher one took"


def test_mc5_none_reads_the_constant(monkeypatch):
    df = mc5_frame(wobble())
    assert MC5.signals(df)["c_rsi"].any(), "fixture fires nothing at the published 5.0"
    monkeypatch.setattr(MC5, "ENTRY_RSI_ROC_PCT", 1000.0)
    assert not MC5.signals(df)["c_rsi"].any()


def test_the_rsi_threshold_does_not_leak_into_the_other_two_clauses():
    df = mc5_frame(wobble())
    a, b = MC5.signals(df, entry_rsi_roc=1.0), MC5.signals(df, entry_rsi_roc=9.0)
    for col in ("c_ema", "c_macd", "macd", "rsi", "ema_fast", "ema_slow"):
        assert a[col].equals(b[col]), col


def test_mc5_live_evaluator_never_sees_the_sweep_parameter():
    import inspect
    assert "entry_rsi_roc" not in inspect.signature(MC5.evaluate_last_bar).parameters
    assert "entry_rsi_roc" in inspect.signature(MC5.backtest_session).parameters


# --- both: None is bit-identical -------------------------------------------

def test_none_is_bit_identical_on_both_engines():
    df = frame([1000, 1200, 900, 1500, 1100, 2000] * 8)
    assert MCL.signals(df).equals(MCL.signals(df, vol_multiple=None))
    d5 = mc5_frame(wobble())
    assert MC5.signals(d5).equals(MC5.signals(d5, entry_rsi_roc=None))


def tradeable(n=120):
    """A session that actually produces trades, so backtest_session's WIRING
    can be tested and not just signals()."""
    import math
    closes = [round(3.0 + 0.45 * math.sin(i / 7.0) + 0.02 * i, 4) for i in range(n)]
    t0 = pd.Timestamp("2026-09-11 05:00", tz=ET)
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=i) for i in range(n)])
    return pd.DataFrame({"open": closes, "high": [c * 1.02 for c in closes],
                         "low": [c * 0.98 for c in closes], "close": closes,
                         "volume": [1000 + 800 * (i % 4) for i in range(n)]}, index=idx)


def test_backtest_session_actually_passes_the_sweep_down_to_signals():
    """THE GAP A None-IS-IDENTICAL TEST LEAVES. If backtest_session called
    signals() without the parameter, every cell in a family would run the
    published constant and the sweep would print five identical rows -- the
    same silent-duplicate failure as merging the configs the wrong way round.
    """
    day = datetime(2026, 9, 11).date()
    df = tradeable()
    mc5_counts = [len(MC5.backtest_session(df, day, ET, entry_shares=100,
                                           entry_rsi_roc=thr)) for thr in (1.0, 5.0, 25.0)]
    assert mc5_counts[0] > mc5_counts[1] > mc5_counts[2], mc5_counts
    mcl_counts = [len(MCL.backtest_session(df, day, ET, entry_shares=100,
                                           vol_multiple=vm)) for vm in (1.2, 8.0)]
    assert mcl_counts[0] > mcl_counts[1], mcl_counts


def test_backtest_session_with_no_sweep_argument_matches_the_published_run():
    """The guarantee every parameter added to these engines has carried."""
    day = datetime(2026, 9, 11).date()
    closes = [2.0 + 0.02 * i for i in range(60)]
    t0 = pd.Timestamp("2026-09-11 05:00", tz=ET)
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=i) for i in range(60)])
    df = pd.DataFrame({"open": closes, "high": [c * 1.01 for c in closes],
                       "low": [c * 0.99 for c in closes], "close": closes,
                       "volume": [1000 + 300 * (i % 5) for i in range(60)]}, index=idx)
    a = MCL.backtest_session(df, day, ET, entry_shares=100)
    b = MCL.backtest_session(df, day, ET, entry_shares=100, vol_multiple=None)
    assert [t.net for t in a] == [t.net for t in b]
    c = MC5.backtest_session(df, day, ET, entry_shares=100)
    d = MC5.backtest_session(df, day, ET, entry_shares=100, entry_rsi_roc=None)
    assert [t.net for t in c] == [t.net for t in d]
