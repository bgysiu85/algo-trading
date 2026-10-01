"""Shared fixtures for the CHARTMARK-CLONE tests: a synthetic pool built through the same functions the real builder uses."""
from __future__ import annotations

from pathlib import Path

from strategy.chartmark import book as BK
from strategy.chartmark import data as D
from strategy.chartmark import engine as E
from strategy.chartmark import spec as V1
from strategy.chartmark_clone import build as B
from strategy.chartmark_clone import spec as S
from tests.strategy.chartmark.synth import walk


def pool(seed: int = 1, n: int = 6000):
    fr = walk(n, seed, drift=0.01, start="2015-01-05 00:00")
    ind = D.indicators(fr)
    trades, _ = E.simulate(fr, ind, V1.BASE)
    return fr, ind, trades


def write_trades_csv(path: Path, fr, trades) -> Path:
    BK.trade_frame(trades, fr).to_csv(path, index=False, encoding="utf-8")     # carries every outcome column, on purpose
    return path


def built(tmp_path: Path, seed: int = 1, n: int = 6000):
    """Run the real builder on a synthetic pool into tmp_path. Returns (result, fr, out_dir, cache_path)."""
    fr, ind, trades = pool(seed, n)
    out = tmp_path / "out"
    csv_path = write_trades_csv(tmp_path / "trades.csv", fr, trades)
    cache = tmp_path / "cache" / S.FRAME_CACHE_FILE
    res = B.build(fr, ind, trades, out, cache, csv_path, repo_root=tmp_path, check_registered=False, log=lambda *_: None)
    return res, fr, out, cache
