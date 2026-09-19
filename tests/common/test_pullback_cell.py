#!/usr/bin/env python3
"""H-P2: the pullback cell, and what would make its reading wrong.

Registered in docs/research/REGISTERED_pullback_cell.md. The failures that
would break it silently: a gate that admits on missing evidence (H-P1's
convention, the wrong one here), thresholds that drift from the registered
pair, a cell that is not a subset of both of its halves, and a gate that never
reaches the engine.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from common import pullback_cell as P

ET = P.ET


def frame(closes, day="2026-09-10", start="04:00", symbol="ABC"):
    idx = pd.date_range(f"{day} {start}", periods=len(closes), freq="1min", tz=ET)
    c = np.array(closes, dtype=float)
    return pd.DataFrame({"symbol": symbol, "open": c, "high": c, "low": c,
                         "close": c, "volume": 1000.0}, index=idx)


# --- the registered constants -------------------------------------------------

def test_the_thresholds_are_the_registrations_and_shared_by_both_books():
    assert (P.D_NEAR, P.C_CALM) == (0.05, 0.03)
    assert P.TIGHT == (0.03, 0.01) and P.LOOSE == (0.10, 0.05)
    cells = [spec for _, _, spec in P.BOOKS if spec and spec[0] == "cell" and len(spec) == 3]
    assert (0.05, 0.03) in {(s[1], s[2]) for s in cells}
    names = [n for n, _, _ in P.BOOKS]
    assert len(names) == len(set(names)) == 12
    assert P.PAIRED == (("MCL", "MCL-cell"), ("MC5", "MC5-cell"))
    assert len(P.REPORTED) == 8


# --- the gate -------------------------------------------------------------------

def test_nan_never_admits_and_the_cell_is_a_subset_of_both_halves():
    # 3 bars of history: dist is defined from bar 1, ret_5m only from bar 6.
    closes = [1.00, 1.02, 1.04, 1.06, 1.08, 1.10, 1.105, 1.11, 1.00, 1.01]
    df = frame(closes)
    cell = P.gate_for(df, ("cell", 0.05, 0.03))
    dist = P.gate_for(df, ("dist", 0.05))
    calm = P.gate_for(df, ("calm", 0.03))
    # the first bars have no five-minute return -> the cell and calm refuse them
    assert not cell.iloc[:5].any() and not calm.iloc[:5].any()
    # while the distance half, defined from the first bar, admits at the high
    assert dist.iloc[0]
    # subset property, everywhere
    assert bool(((cell & ~dist) | (cell & ~calm)).sum()) is False
    assert cell.dtype == bool and dist.dtype == bool and calm.dtype == bool


def test_the_cell_admits_at_the_high_and_calm_and_refuses_the_extension_and_the_dip():
    # a calm grind to a new high: at bar 7 ret_5m = 1.07/1.02-1 = +4.9% -> too extended;
    # a slower grind of +0.5%/min: ret_5m = +2.5%, at the high -> admitted.
    slow = [1.00 + 0.005 * i for i in range(12)]
    g = P.gate_for(frame(slow), ("cell", 0.05, 0.03))
    assert g.iloc[-1]
    fast = [1.00 + 0.02 * i for i in range(12)]           # ret_5m ~ +8.6% -> refused
    assert not P.gate_for(frame(fast), ("cell", 0.05, 0.03)).iloc[-1]
    dip = [1.00 + 0.005 * i for i in range(8)] + [0.90, 0.90, 0.90, 0.90]   # 13% off the high
    assert not P.gate_for(frame(dip), ("cell", 0.05, 0.03)).iloc[-1]
    # and the distance half alone refuses the dip too, while the calm half admits it
    assert not P.gate_for(frame(dip), ("dist", 0.05)).iloc[-1]
    assert P.gate_for(frame(dip), ("calm", 0.03)).iloc[-1]


def test_nan_only_marks_refusals_the_existing_features_would_have_admitted():
    closes = [1.00, 1.01, 1.02, 1.03]                         # no ret_5m anywhere; all at the high
    df = frame(closes)
    n = P.nan_only(df, ("cell", 0.05, 0.03))
    assert n.all()
    dip = [1.00, 0.90, 0.90, 0.90]                             # off the high AND no ret_5m
    assert not P.nan_only(frame(dip), ("cell", 0.05, 0.03)).iloc[-1]


def test_stamp_on_carries_the_minute_gate_onto_the_five_minute_index_by_ffill():
    idx1 = pd.date_range("2026-09-10 04:00", periods=10, freq="1min", tz=ET)
    g = pd.Series([False] * 4 + [True] * 6, index=idx1)
    idx5 = pd.date_range("2026-09-10 04:00", periods=2, freq="5min", tz=ET)
    s = P.stamp_on(g, idx5)
    assert list(s) == [False, True] and s.dtype == bool


# --- the engine sees the gate -------------------------------------------------

def test_run_universe_gates_every_book_but_the_baseline_and_counts_binding():
    seen = {}

    class FakeMod:
        @staticmethod
        def backtest_session(df, d, tz, **kw):
            g = kw.get("entry_gate")
            seen[len(seen)] = None if g is None else int(g.sum())
            # one trade at the last bar, so the binding pass has an entry to classify
            ts = df.index[-1]
            return [SimpleNamespace(net=-3.0, entry_time=ts, exit_time=ts, entry_price=1.0,
                                    exit_price=0.97, reason="x", bars_held=1)]

    slow = [1.00 + 0.005 * i for i in range(12)]
    df = frame(slow)
    universe = [{"symbol": "ABC", "date": "2026-09-10", "first_seen": "2026-09-10T08:01:00Z"}]
    engines = {"mcl": (FakeMod, {}), "mc5": (FakeMod, {})}
    res = P.run_universe(df, "2026-09-10", universe, engines,
                         idx5_of=lambda d: d.index[::5])
    assert res["symdays"] == 1 and res["errors"] == 0
    gates = list(seen.values())
    assert gates.count(None) == 2                              # the two baselines only
    assert all(g is not None for i, g in enumerate(gates) if i % 6 != 0)
    # every gated book classified the baseline's one entry
    for g in P.GATED:
        assert res["binding"][g][1] == 1
    # the cell admitted the last bar (calm grind at the high) -> not refused
    assert res["binding"]["MCL-cell"][2][1] == 1
    assert res["refused"]["MCL-cell"] == []


def test_a_symbol_day_that_raises_in_one_book_is_dropped_from_all():
    class Flaky:
        @staticmethod
        def backtest_session(df, d, tz, **kw):
            if kw.get("entry_gate") is not None:
                raise RuntimeError("boom")
            return []

    df = frame([1.0 + 0.005 * i for i in range(12)])
    universe = [{"symbol": "ABC", "date": "2026-09-10", "first_seen": "2026-09-10T08:01:00Z"}]
    res = P.run_universe(df, "2026-09-10", universe, {"mcl": (Flaky, {}), "mc5": (Flaky, {})},
                         idx5_of=lambda d: d.index[::5])
    assert res["symdays"] == 0 and res["errors"] == 1
    assert all(not rows for rows in res["books"].values())


# --- the blocks -------------------------------------------------------------------

def test_mechanism_block_names_the_bar_and_whether_the_cell_holds():
    onebar = {n: [0, 0] for n, _, _ in P.BOOKS}
    onebar["MCL"] = [126, 1000]
    onebar["MCL-cell"] = [3, 100]
    onebar["MC5"] = [372, 1000]
    onebar["MC5-cell"] = [30, 100]
    text = "\n".join(P.mechanism_block(onebar))
    assert "MCL-cell" in text and "HOLDS" in text
    assert "FAILS the mechanism bar" in text                   # MC5 at 30% > 22%
