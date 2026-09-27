#!/usr/bin/env python3
"""G2 pre-flight: counts and $ distances only, no P&L, per baseline/market/
year, and the <300-trades NOT-READ stop rule.
REGISTERED_w16_session_baselines.md sec 0 (G2) and sec 6.2."""
from __future__ import annotations

from zoneinfo import ZoneInfo

import pandas as pd
import pytest

import strategy.w16.preflight as PF

ET = ZoneInfo("America/New_York")


def _bars(date, rows):
    idx, data = [], []
    for hh, mm, o, h, l, c, v in rows:
        ts = pd.Timestamp(f"{date} {hh:02d}:{mm:02d}:00", tz=ET)
        idx.append(ts)
        data.append({"open": o, "high": h, "low": l, "close": c, "volume": v, "held_id": 1})
    return pd.DataFrame(data, index=pd.DatetimeIndex(idx).tz_convert("UTC"))


def _orb_long_day(date, h=100.0, l=99.0):
    rows = [(9, m, 99.5, h if i == 0 else 99.6, l if i == 1 else 99.4, 99.5, 100)
           for i, m in enumerate(range(30, 60))]
    rows += [(10, 0, 99.5, 100.5, 99.4, 100.2, 50)]
    rows += [(10, 1, 100.3, 100.4, 100.2, 100.35, 50)]
    for m in range(2, 350):
        rows.append((10 + (30 + m) // 60, (30 + m) % 60, 101, 101, 101, 101, 10))
    return _bars(date, rows)


def test_preflight_no_module_level_pnl_capability():
    """G2's whole point: this module never binds a name that could compute
    a $ P&L figure -- not merely that the word doesn't appear in prose."""
    assert not hasattr(PF, "pnl_dollars")
    assert not hasattr(PF, "trade_cost")


def test_run_b1_counts_entries_and_skips():
    frames = {"2024-06-06": _orb_long_day("2024-06-06")}
    result = PF.run_b1(frames, "ES", {"2024-06-06"})
    t = result["totals"]
    assert t["sessions"] == 1
    assert t["entries"] == 1
    assert t["stop_dist_usd_median"] is not None
    assert t["range_width_usd_median"] is not None


def test_run_b1_underpowered_below_300():
    frames = {"2024-06-06": _orb_long_day("2024-06-06")}
    result = PF.run_b1(frames, "ES", {"2024-06-06"})
    assert result["totals"]["underpowered"] is True


def test_run_b2_counts_pairs_and_skips_missing():
    day1 = _bars("2024-06-06", [(15, 59, 100.0, 100.0, 100.0, 100.0, 10)])
    day2 = _bars("2024-06-07", [(9, 30, 101.0, 101.0, 101.0, 101.0, 10)])
    frames = {"2024-06-06": day1, "2024-06-07": day2}
    result = PF.run_b2(frames, "ES", ["2024-06-06", "2024-06-07", "2024-06-10"])
    t = result["totals"]
    assert t["entries"] == 1
    assert t["skipped"] == 1     # the 06-07 -> 06-10 pair, missing 06-10


def test_run_b3_reports_flips_per_day():
    rows = []
    for i in range(390):
        hh, mm = 9 + (30 + i) // 60, (30 + i) % 60
        rows.append((hh, mm, 100.0, 100.1, 99.9, 100.0, 100))
    day = _bars("2024-06-06", rows)
    frames = {"2024-06-06": day}
    result = PF.run_b3(frames, "ES", {"2024-06-06"})
    assert "flips_per_day_median" in result["totals"]
