#!/usr/bin/env python3
"""Tests for the 27-cell neighbour grid, W15-0016."""
from __future__ import annotations

import numpy as np
import pandas as pd

from strategy.htf import bars as B
from strategy.tl_bounce import grid as G
from strategy.tl_bounce.preflight import prepare_grids
from strategy.tl_bounce.spec import GRID_PIVOT_R, GRID_TOUCH_BUF, GRID_X1_BUF, TRAIN_END, TRAIN_START


def _synthetic_1h(n_sessions=900, seed=4):
    rng = np.random.default_rng(seed)
    n = n_sessions * 23
    start = pd.Timestamp(f"{TRAIN_START}T23:00:00Z") - pd.Timedelta(days=30)
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


def test_cells_are_27_in_fixed_order():
    cells = G.cells()
    assert len(cells) == 27
    assert cells[0] == (GRID_TOUCH_BUF[0], GRID_X1_BUF[0], GRID_PIVOT_R[0])
    assert cells == G.cells()   # reproducible order


def test_run_grid_shape_and_share_positive_consistent():
    df_1h = _synthetic_1h()
    grids = prepare_grids(df_1h)
    hourly = B.back_adjust(B.resample(df_1h, "1H"))
    ef, hf, hh = grids["4H"]
    result = G.run_grid(ef, hf, hh, hourly)
    assert len(result["cells"]) == 27
    assert result["n_total"] == 27
    assert 0 <= result["n_positive"] <= 27
    assert result["share_positive"] == result["n_positive"] / 27
    for row in result["cells"]:
        assert np.isfinite(row["net"])
        assert row["trades"] >= 0
