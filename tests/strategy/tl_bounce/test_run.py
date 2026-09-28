#!/usr/bin/env python3
"""End-to-end smoke test for the run.py pipeline, W15-0016."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.tl_bounce import run as RUN
from strategy.tl_bounce.spec import TRAIN_START


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


def test_run_end_to_end(tmp_path):
    df_1h = _synthetic_1h()
    rep = RUN.run(archive=None, out_dir=tmp_path, stamp="test",
                  loader=lambda archive: df_1h)
    assert rep.exists()
    text = rep.read_text(encoding="utf-8")
    assert "sec 4: the bar to clear" in text
    assert "neighbour grid" in text
    csv_path = tmp_path / "tl_bounce_backtest_trades_test.csv"
    assert csv_path.exists()
    trades = pd.read_csv(csv_path)
    if len(trades):
        assert set(trades["variant"]) <= set(RUN.BUILT_VARIANTS)
        assert (trades["session"] >= TRAIN_START).all()


def test_holdout_flag_refused():
    with pytest.raises(RUN.RunRefused):
        RUN.main(["--holdout"])


def test_limit_flag_refused():
    with pytest.raises(RUN.RunRefused):
        RUN.main(["--limit", "10"])
