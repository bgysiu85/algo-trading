"""Tests for strategy.w16.bb_runner: the sec 7.4 worked example, the
scored controls' shape (each returns a plain trade dict costable by
strategy.w16.runner.price_all), C-N1's replay matching a real NRS trade
exactly under the SAME side (the property bar_batch._nrs_walk_from_entry
exists for), a scoring smoke test end-to-end through run_cell, and the
sec 7.3 neighbour grids' cell count. Board W16-0008 subitem 3.
"""
from __future__ import annotations

from datetime import time as dtime

import numpy as np
import pandas as pd
import pytest

from strategy.w16 import bar_batch as B
from strategy.w16 import bb_holdout as H
from strategy.w16 import bb_runner as BR
from strategy.w16 import preflight as PF
from strategy.w16 import runner as R


# ---------------------------------------------------------------------
# fixtures -- kept self-contained here rather than importing from
# test_bar_batch.py, so this file runs standalone (pytest
# tests/strategy/w16/test_bb_runner.py alone, not the whole suite)
# ---------------------------------------------------------------------

def rth_session(date_str, *, base=100.0, held_id=1, minute_fn=None):
    start = pd.Timestamp(f"{date_str} 09:30:00", tz="America/New_York").tz_convert("UTC")
    idx = pd.date_range(start, periods=390, freq="1min")
    rows = []
    px = base
    for i in range(390):
        o, h, l, c, v = px, px + 0.5, px - 0.5, px + 0.05, 100
        if minute_fn is not None:
            r = minute_fn(i, px)
            if r is not None:
                o, h, l, c, v = r
        rows.append((o, h, l, c, v))
        px = c
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"], index=idx)
    df["instrument_id"] = held_id
    return df


def globex_session(date_str, *, base=100.0, held_id=1, minute_fn=None, days=1):
    start = (pd.Timestamp(f"{date_str} 00:00:00", tz="America/New_York")
            - pd.Timedelta(days=1)).replace(hour=18, minute=0)
    rows, idxs = [], []
    px = base
    cur = start
    end = start + pd.Timedelta(days=days) + pd.Timedelta(hours=23)
    i = 0
    while cur < end:
        if cur.time() == pd.Timestamp("17:00").time():
            cur += pd.Timedelta(hours=1)
            continue
        o, h, l, c, v = px, px + 0.5, px - 0.5, px + 0.02, 50
        if minute_fn is not None:
            r = minute_fn(i, px, cur)
            if r is not None:
                o, h, l, c, v = r
        rows.append((o, h, l, c, v))
        idxs.append(cur.tz_convert("UTC"))
        px = c
        cur += pd.Timedelta(minutes=1)
        i += 1
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"],
                      index=pd.DatetimeIndex(idxs))
    df["instrument_id"] = held_id
    return df.sort_index()


def _squeeze_globex(breakout_hour=30, breakout_minute=5, breakout_up=True, days=3):
    def fn(i, px, ts):
        hour_idx = i // 60
        if hour_idx < breakout_hour:
            amp = max(0.5, 3.0 - hour_idx * 0.1)
            return (px, px + amp, px - amp, px + 0.01, 50)
        if hour_idx == breakout_hour and i % 60 == breakout_minute:
            return ((px, px + 20.0, px, px + 18.0, 200) if breakout_up
                    else (px, px, px - 20.0, px - 18.0, 200))
        return None
    return globex_session("2024-01-08", base=100.0, minute_fn=fn, days=days)

def _trending_frames(seed=0, base=100.0, n_days=40, drift=0.02, vol=0.15):
    """Volatility high enough that SSS/CRT patterns fire reliably across
    seeds (checked 0-9 directly while writing this suite) -- a quiet
    fixture (the original, tighter-volatility draft) produced patterns on
    some seeds and none on others, making a control-shape test flaky by
    the luck of the draw rather than by anything in bb_runner itself."""
    rng = np.random.default_rng(seed)
    dates = [d for d in (f"2020-{m:02d}-{i:02d}" for m in (1, 2) for i in range(1, 29))
            if pd.Timestamp(d).dayofweek < 5][:n_days]
    frames = {}
    px = base
    for d in dates:
        def fn(i, p, rng=rng):
            step = drift + rng.normal(0, vol)
            o, c = p, p + step
            h = max(o, c) + abs(rng.normal(0, vol * 0.6))
            l = min(o, c) - abs(rng.normal(0, vol * 0.6))
            return (o, h, l, c, 100)
        frames[d] = rth_session(d, base=px, minute_fn=fn)
        px = frames[d]["close"].iloc[-1]
    return frames, dates


@pytest.fixture(autouse=True)
def _clean_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(H, "LEDGER_PATH", tmp_path / "holdout_w16_bb.json")
    yield


# ---------------------------------------------------------------------
# sec 7.4 worked example
# ---------------------------------------------------------------------

def test_worked_example_matches_registered_figures():
    we = BR.worked_example_check()
    assert we["target_ok"] and we["stop_ok"]
    assert we["computed_target_dist"] == pytest.approx(35.75)
    assert we["computed_stop_dist"] == pytest.approx(26.75)


# ---------------------------------------------------------------------
# BOOTSTRAP_PASS_PCT identity (why bb_runner reuses runner.score_cell
# unmodified -- see bb_runner's own module docstring)
# ---------------------------------------------------------------------

def test_bootstrap_threshold_is_99_percent_matching_runner():
    assert BR.BOOTSTRAP_PASS_PCT == R.BOOTSTRAP_PASS_PCT == 0.99
    assert BR.MIN_TRADES == R.MIN_TRADES == 300


# ---------------------------------------------------------------------
# scored controls: shape and costability
# ---------------------------------------------------------------------

def test_c_s1_draw_is_costable():
    frames, dates = _trending_frames(seed=1)
    trades = B.generate_sss_trades(frames, "NQ", dates)
    assert trades, "fixture must produce at least one real SSS trade to draw a control against"
    draw = BR.c_s1_draw(trades, frames, 0)
    assert draw
    priced = R.price_all(draw, "L2")
    assert all("net" not in t for t in draw)      # raw trades carry no $ yet
    assert priced and all("net" in t for t in priced)


def test_c_c1_draw_flips_side_deterministically_by_seed():
    frames, dates = _trending_frames(seed=2)
    trades = B.generate_crt_trades(frames, "NQ", dates)
    assert trades, "fixture must produce at least one real CRT trade to draw a control against"
    d1 = BR.c_c1_draw(trades, frames, draw_idx=0)
    d1b = BR.c_c1_draw(trades, frames, draw_idx=0)
    assert [t["direction"] for t in d1] == [t["direction"] for t in d1b], \
        "same draw index must be reproducible (seed = zlib.crc32 of the draw number)"


def test_c_n1_replay_matches_real_trade_under_same_direction():
    """This is C-N1's whole point (sec 7.1: 'the real entry minute and
    fill ... the same chandelier ... the same roll and training-end
    exits'): replaying a real NRS trade's own entry under its OWN
    direction must reproduce its exit exactly."""
    df = _squeeze_globex(days=3)
    dates = B.nrs_cme_trading_days(df)
    pre = B._nrs_precompute(df)
    trades = B.generate_nrs_trades(df, "NQ", dates, _pre=pre)
    assert trades
    t = trades[0]
    replay = B._nrs_walk_from_entry(
        pre, t["direction"], t["fill_price"], t["entry_idx_1m"], t["entry_hourly_idx"],
        t["date"], t["squeeze_bar_time"], "NQ")
    for field in ("exit_time", "exit_price", "exit_reason", "stop"):
        assert replay[field] == t[field]


def test_c_n1_draw_produces_costable_trades():
    df = _squeeze_globex(days=3)
    dates = B.nrs_cme_trading_days(df)
    pre = B._nrs_precompute(df)
    trades = B.generate_nrs_trades(df, "NQ", dates, _pre=pre)
    assert trades
    draw = BR.c_n1_draw(trades, pre, "NQ", 0)
    assert draw
    priced = R.price_all(draw, "L2")
    assert priced and "net" in priced[0]


# ---------------------------------------------------------------------
# scoring smoke test: run_cell end to end (monkeypatched archive load)
# ---------------------------------------------------------------------

def test_run_cell_sss_end_to_end(monkeypatch):
    frames, dates = _trending_frames(seed=3, n_days=22)
    full_df = pd.concat(frames.values()).sort_index()

    def fake_load_root_bars(archive, root):
        return full_df.copy()
    monkeypatch.setattr(PF, "load_root_bars", fake_load_root_bars)
    monkeypatch.setattr(BR, "load_root_bars", fake_load_root_bars)

    result = BR.run_cell("SSS", "NQ", archive="FAKE", compute_controls_flag=True,
                         n_control_draws=5, compute_grid_flag=True, progress=False)
    assert result["rule"] == "SSS" and result["market"] == "NQ"
    assert set(result["criteria"]) >= {"1_net_positive", "4_month_bootstrap", "5_beats_control",
                                       "8_neighbour_grid_6_of_9", "9_min_trades", "passes_all_computed"}
    assert result["neighbour_grid"]["n_total"] == 9
    for lvl in ("L1", "L2", "L3"):
        assert lvl in result["by_level"]


def test_run_backtest_covers_all_six_scored_cells(monkeypatch):
    frames, dates = _trending_frames(seed=4, n_days=22)
    full_df = pd.concat(frames.values()).sort_index()

    def fake_load_root_bars(archive, root):
        return full_df.copy()
    monkeypatch.setattr(PF, "load_root_bars", fake_load_root_bars)
    monkeypatch.setattr(BR, "load_root_bars", fake_load_root_bars)

    bt = BR.run_backtest("FAKE", compute_controls_flag=False, compute_grid_flag=False,
                         include_reported_variants=False, progress=False)
    assert set(bt["cells"]) == set(BR.SCORED_CELLS)
    for candidate, cell in bt["cells"].items():
        assert cell["candidate"] == candidate
        assert "criteria" in cell and "by_level" in cell


def test_run_backtest_refuses_unregistered_holdout_spend():
    with pytest.raises(SystemExit):
        BR.run_backtest("FAKE", spend_holdout="ABD-ES")   # reported only, not one of the six scored cells


# ---------------------------------------------------------------------
# neighbour grids: 9 cells, registered cell present in each
# ---------------------------------------------------------------------

def test_grid_has_nine_cells_with_registered_flagged():
    frames, dates = _trending_frames(seed=5, n_days=22)
    grid = BR.run_neighbour_grid("SSS", frames, "NQ", dates)
    assert grid["n_total"] == 9
    registered = [r for r in grid["cells"] if r["is_registered_cell"]]
    assert len(registered) == 1
    assert registered[0]["wick_mult"] == 2.0 and registered[0]["hold_bars"] == 1
