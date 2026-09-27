#!/usr/bin/env python3
"""End-to-end wiring test for the G2 pre-flight (REGISTERED_tl_bounce.md
sec 5.2): prepare_grids -> run_variant -> summarize logic, on a small
synthetic 1-hour archive (no real market data). Asserts what the module
promises structurally (no P&L field, no exit price anywhere in Counts/Entry)
rather than pinning exact counts to a random series."""
from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd

from strategy.tl_bounce.preflight import BUILT_VARIANTS, prepare_grids, run_variant


def _synthetic_1h(n_sessions=120, seed=4):
    rng = np.random.default_rng(seed)
    n = n_sessions * 23
    start = pd.Timestamp("2016-01-04T23:00:00Z")
    t = start + pd.to_timedelta(
        np.concatenate([np.arange(23) + s * 24 for s in range(n_sessions)]), unit="h")
    tt = np.arange(n)
    close = 60 + np.sin(tt / 200) * 12 + np.cumsum(rng.normal(0, 0.25, n))
    high = close + np.abs(rng.normal(0, 0.5, n))
    low = close - np.abs(rng.normal(0, 0.5, n))
    open_ = close + rng.normal(0, 0.2, n)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close,
         "volume": rng.integers(100, 1000, n),
         "held_id": np.full(n, 999, dtype="int64")},
        index=pd.DatetimeIndex(t, name="ts_event"))


def test_prepare_grids_shapes():
    df_1h = _synthetic_1h()
    grids = prepare_grids(df_1h)
    assert set(grids) == {"4H", "1H"}
    ef4, hf4, hh4 = grids["4H"]
    assert hh4 == 24
    assert "close_adj" in ef4.columns and "close_adj" in hf4.columns
    ef1, hf1, hh1 = grids["1H"]
    assert hh1 == 4
    assert len(ef1) > len(ef4)      # 1H has more bars than 4H over the same span


def test_run_variant_no_pnl_fields_anywhere():
    """G2's own promise (sec 5.2): no exit price, no P&L. Every field on
    every Entry/Counts object is a bar index, a price LEVEL used for the
    stop-distance stat, a reason string, or a count -- never a $ result."""
    df_1h = _synthetic_1h()
    grids = prepare_grids(df_1h)
    ef, hf, hh = grids["4H"]
    entries, counts, sessions = run_variant(ef, hf, hh, **BUILT_VARIANTS["bounce"])
    forbidden = {"pnl", "net", "gross", "profit", "loss", "exit_px", "exit_price"}
    entry_fields = {f.name for f in dataclasses.fields(entries[0])} if entries else set()
    counts_fields = set(counts.as_dict())
    assert not (entry_fields & forbidden)
    assert not (counts_fields & forbidden)


def test_all_built_variants_run_without_error():
    df_1h = _synthetic_1h(n_sessions=200, seed=9)
    grids = prepare_grids(df_1h)
    for variant, opts in BUILT_VARIANTS.items():
        for entry_chart, (ef, hf, hh) in grids.items():
            entries, counts, sessions = run_variant(ef, hf, hh, **opts)
            assert counts.entries == len(entries)
            assert counts.entries >= counts.re_entries
