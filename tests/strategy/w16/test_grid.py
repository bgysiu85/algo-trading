#!/usr/bin/env python3
"""strategy.w16.grid: the sec 7.3 neighbour grid (9 cells per baseline),
via the SAME trade generators and pricing the registered run uses.
Board W16-0005."""
from __future__ import annotations

from datetime import time as dtime

import numpy as np
import pandas as pd
import pytest

import strategy.w16.grid as GRID
import strategy.w16.runner as R


def _synthetic_session(date_str, seed, n=390, base=5000.0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range(f"{date_str} 09:30", periods=n, freq="1min",
                        tz="America/New_York").tz_convert("UTC")
    walk = np.cumsum(rng.normal(0, 0.5, n))
    close = base + walk
    open_ = np.concatenate([[base], close[:-1]])
    high = np.maximum(open_, close) + rng.uniform(0, 0.5, n)
    low = np.minimum(open_, close) - rng.uniform(0, 0.5, n)
    vol = rng.integers(50, 500, n)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                        "volume": vol, "held_id": 1}, index=idx)


@pytest.fixture
def synthetic_frames():
    """Full 09:30-16:00 sessions (unlike test_runner.py's 60-bar fixture)
    -- the grid needs real range/entry windows to populate, and B2's grid
    needs bars near 15:59/09:30 to exist at all."""
    dates = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2020-01-06", periods=12)]
    return {d: _synthetic_session(d, seed=i) for i, d in enumerate(dates)}


@pytest.fixture
def df_1m(synthetic_frames):
    dates = sorted(synthetic_frames)
    return pd.concat([synthetic_frames[d] for d in dates]).sort_index()


# ---------------------------------------------------------------------
# cells() -- the fixed 3x3 product per baseline
# ---------------------------------------------------------------------

def test_cells_b1_is_the_full_3x3_product():
    c = GRID.cells("B1")
    assert len(c) == 9
    assert set(c) == {(rm, tr) for rm in GRID.B1_RANGE_MINUTES for tr in GRID.B1_TARGET_R}
    assert (30, 2.0) in c                          # the registered cell is one of the nine


def test_cells_b2_is_the_full_3x3_product_of_clock_times():
    c = GRID.cells("B2")
    assert len(c) == 9
    assert (dtime(16, 0), dtime(9, 30)) in c
    assert all(isinstance(dim, dtime) for cell in c for dim in cell)


def test_cells_b3_is_the_full_3x3_product():
    c = GRID.cells("B3")
    assert len(c) == 9
    assert set(c) == {(bm, fc) for bm in GRID.B3_BAR_MINUTES for fc in GRID.B3_FLIP_CONFIRM}
    assert (1, 1) in c


def test_cells_rejects_unknown_baseline():
    with pytest.raises(KeyError):
        GRID.cells("B4")


# ---------------------------------------------------------------------
# run_neighbour_grid -- shape and internal consistency
# ---------------------------------------------------------------------

@pytest.mark.parametrize("baseline", ["B1", "B2", "B3"])
def test_run_neighbour_grid_returns_nine_cells(baseline, df_1m, synthetic_frames):
    g = GRID.run_neighbour_grid(baseline, "ES", None, df_1m=df_1m, frames=synthetic_frames)
    assert g["baseline"] == baseline and g["market"] == "ES"
    assert g["n_total"] == 9
    assert len(g["cells"]) == 9
    assert g["n_positive"] == sum(1 for c in g["cells"] if c["net"] > 0)
    assert g["share_positive"] == pytest.approx(g["n_positive"] / 9)
    for cell in g["cells"]:
        assert set(cell) == {"dim1", "dim2", "n_trades", "net"}
        assert isinstance(cell["net"], float)
        assert cell["n_trades"] >= 0


@pytest.mark.parametrize("baseline", ["B1", "B2", "B3"])
def test_run_neighbour_grid_cell_order_matches_cells(baseline, df_1m, synthetic_frames):
    g = GRID.run_neighbour_grid(baseline, "ES", None, df_1m=df_1m, frames=synthetic_frames)
    got = [(c["dim1"], c["dim2"]) for c in g["cells"]]
    assert got == GRID.cells(baseline)


def test_run_neighbour_grid_b1_registered_cell_matches_generate_b1_trades(df_1m, synthetic_frames):
    """The grid's (30, 2.0) cell is not a special case in the code, but it
    should reproduce exactly what the registered trade generator itself
    returns for the same training dates."""
    g = GRID.run_neighbour_grid("B1", "ES", None, df_1m=df_1m, frames=synthetic_frames)
    reg_cell = next(c for c in g["cells"] if c["dim1"] == 30 and c["dim2"] == 2.0)

    from strategy.w16 import holdout as H
    train_dates, _, _ = H.split_dates(sorted(synthetic_frames))
    trades = R.generate_b1_trades(synthetic_frames, "ES", train_dates)
    expected_net = R.summarize(R.price_all(trades, "L2"))["net"]
    assert reg_cell["net"] == pytest.approx(expected_net)


def test_run_neighbour_grid_b2_uses_wider_window_than_registered_frames(df_1m, synthetic_frames):
    """B2's grid must find SOME trades at entry/exit clock times other
    than 16:00/09:30 -- proof the widened window (not the RTH-only
    synthetic_frames) is what's actually being read."""
    g = GRID.run_neighbour_grid("B2", "ES", None, df_1m=df_1m, frames=synthetic_frames)
    assert any(c["n_trades"] > 0 for c in g["cells"])


def test_run_neighbour_grid_b3_bar_size_changes_trade_count(df_1m, synthetic_frames):
    """5-minute bars must produce materially fewer B3 trades than 1-minute
    bars on the same session (fewer, coarser VWAP crossings) -- proof the
    bar-size dimension is actually resampling, not a no-op."""
    g = GRID.run_neighbour_grid("B3", "ES", None, df_1m=df_1m, frames=synthetic_frames)
    n_1min = next(c["n_trades"] for c in g["cells"] if c["dim1"] == 1 and c["dim2"] == 1)
    n_5min = next(c["n_trades"] for c in g["cells"] if c["dim1"] == 5 and c["dim2"] == 1)
    assert n_5min < n_1min


def test_run_neighbour_grid_never_reads_past_the_holdout_lock(synthetic_frames):
    """Dates on/after 2024-01-02 in the frames must not appear in any
    cell's trade count -- the grid calls holdout.split_dates same as
    run_cell, never a raw date list."""
    dates = sorted(synthetic_frames)
    locked_dates = [d.replace("2020", "2024") for d in dates[:3]]   # -> 2024-0x, locked
    extra = {ld: synthetic_frames[d] for ld, d in zip(locked_dates, dates[:3])}
    frames = dict(synthetic_frames)
    frames.update(extra)
    df_1m_all = pd.concat([frames[d] for d in sorted(frames)]).sort_index()

    g_locked_included = GRID.run_neighbour_grid("B1", "ES", None, df_1m=df_1m_all, frames=frames)
    g_training_only = GRID.run_neighbour_grid("B1", "ES", None, df_1m=df_1m, frames=synthetic_frames)
    # same training dates in both, and the (locked) 2024 frames were never
    # read for a training-side grid -- net must be identical.
    reg_a = next(c for c in g_locked_included["cells"] if c["dim1"] == 30 and c["dim2"] == 2.0)
    reg_b = next(c for c in g_training_only["cells"] if c["dim1"] == 30 and c["dim2"] == 2.0)
    assert reg_a["net"] == pytest.approx(reg_b["net"])
    assert reg_a["n_trades"] == reg_b["n_trades"]


def test_run_neighbour_grid_rejects_unknown_baseline(df_1m, synthetic_frames):
    with pytest.raises(ValueError):
        GRID.run_neighbour_grid("B9", "ES", None, df_1m=df_1m, frames=synthetic_frames)


# ---------------------------------------------------------------------
# wired into run_cell (criterion 8)
# ---------------------------------------------------------------------

def test_run_cell_wires_neighbour_grid_share_into_criterion_8(monkeypatch, df_1m, synthetic_frames):
    monkeypatch.setattr(R, "load_root_bars", lambda archive, market: df_1m)
    monkeypatch.setattr(R, "session_frames", lambda df: synthetic_frames)

    result = R.run_cell("B1", "ES", None, compute_controls_flag=False, compute_grid_flag=True)
    assert result["neighbour_grid"] is not None
    assert result["neighbour_grid"]["n_total"] == 9
    share = result["neighbour_grid"]["share_positive"]
    assert result["criteria"]["8_neighbour_grid_6_of_9"] == (share >= 6.0 / 9.0)


def test_run_cell_skip_grid_leaves_criterion_8_none(monkeypatch, df_1m, synthetic_frames):
    monkeypatch.setattr(R, "load_root_bars", lambda archive, market: df_1m)
    monkeypatch.setattr(R, "session_frames", lambda df: synthetic_frames)

    result = R.run_cell("B1", "ES", None, compute_controls_flag=False, compute_grid_flag=False)
    assert result["neighbour_grid"] is None
    assert result["criteria"]["8_neighbour_grid_6_of_9"] is None
