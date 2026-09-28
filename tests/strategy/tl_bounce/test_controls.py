#!/usr/bin/env python3
"""Tests for C1 (Donchian) and C2 (random entries), W15-0016.
REGISTERED_tl_bounce.md sec 3."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.htf import bars as B
from strategy.tl_bounce import controls as CT
from strategy.tl_bounce import engine as E
from strategy.tl_bounce.preflight import BUILT_VARIANTS, prepare_grids


def _synthetic_1h(n_sessions=260, seed=4):
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


@pytest.fixture(scope="module")
def rig():
    df_1h = _synthetic_1h()
    grids = prepare_grids(df_1h)
    hourly = B.back_adjust(B.resample(df_1h, "1H"))
    ef, hf, hh = grids["4H"]
    bounce_trades, _ = E.simulate_market(ef, hf, hh, hourly, **BUILT_VARIANTS["bounce"])
    return ef, hourly, bounce_trades


def test_c1_runs_and_books_dollars(rig):
    ef, hourly, _ = rig
    trades, counts = CT.run_c1(ef)
    assert counts["trades_taken"] == len(trades)
    for t in trades:
        assert np.isfinite(t.net_pnl("MCL", "mid"))
        assert t.exit_reason in ("channel_exit", "data_end")


def test_c1_channel_never_uses_the_trigger_bar_itself():
    n = 40
    entry_frame = pd.DataFrame({
        "t_open": pd.date_range("2020-01-06 18:00", periods=n, freq="4h", tz="UTC"),
        "session": [f"s{i}" for i in range(n)],
        "open_adj": np.full(n, 10.0), "high_adj": np.full(n, 10.5),
        "low_adj": np.full(n, 9.5), "close_adj": np.full(n, 10.0),
        "adj_offset": np.zeros(n), "held_id": np.ones(n, dtype=int),
    })
    entries, counts = CT.detect_c1(entry_frame)
    assert entries == []   # flat series, no 20-bar breakout possible


def test_c2_pool_excludes_bounce_trade_windows(rig):
    ef, hourly, bounce_trades = rig
    pool = CT.flat_pool(ef, bounce_trades)
    t = ef["t_open"]
    for tr in bounce_trades:
        covered = ((t >= pd.Timestamp(tr.entry_t)) & (t < pd.Timestamp(tr.exit_t))).to_numpy()
        assert not (covered[pool]).any()


def test_c2_percentiles_ordered_and_matched_mix(rig):
    ef, hourly, bounce_trades = rig
    if not bounce_trades:
        pytest.skip("synthetic series produced no bounce trades to match against")
    result = CT.run_c2(ef, hourly, bounce_trades, n_draws=40, seed_prefix="test-")
    assert result["n_trades_per_draw"] == len(bounce_trades)
    if result["p5"] is not None:
        assert result["p5"] <= result["p50"] <= result["p95"]


def test_c2_never_draws_from_holdout_or_seen_window():
    """Independent-review finding (2026-09-28): flat_pool/run_c2 used to
    draw from the FULL archive (prepare_grids never truncates it), leaking
    holdout (>= common.tl_bounce_holdout.LOCK_FROM) and seen-window
    (>= 2025-09-23) data into criterion 6, part of the training-side
    verdict (sec 4/6). A synthetic archive that extends well past
    TRAIN_END must never produce a pool position or a drawn trade dated on
    or after TRAIN_END."""
    from strategy.tl_bounce.spec import TRAIN_END

    n_sessions = 4400   # ~2010-06 through well past 2021-12-31
    df_1h = _synthetic_1h(n_sessions=n_sessions, seed=31)
    grids = prepare_grids(df_1h)
    hourly = B.back_adjust(B.resample(df_1h, "1H"))
    ef, hf, hh = grids["4H"]
    bounce_trades, _ = E.simulate_market(ef, hf, hh, hourly, **BUILT_VARIANTS["bounce"])

    pool = CT.flat_pool(ef, bounce_trades)
    sessions = ef["session"].astype(str).to_numpy()
    assert pool.size > 0
    assert (sessions[pool] <= TRAIN_END).all()

    bounce_train = [t for t in bounce_trades if str(t.session)[:10] <= TRAIN_END]
    if not bounce_train:
        pytest.skip("no training-side bounce trades on this synthetic series")
    result = CT.run_c2(ef, hourly, bounce_train, n_draws=25, seed_prefix="boundary-")
    assert result["pool_size"] == pool.size
