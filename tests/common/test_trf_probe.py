#!/usr/bin/env python3
"""The probe's analysis separates a planted reported print from live ones."""
from __future__ import annotations

import numpy as np
import pandas as pd

from common import trf_probe as P


def fake_trades(n=600, seed=1):
    rng = np.random.default_rng(seed)
    t0 = pd.Timestamp("2025-08-11 07:40", tz="America/New_York").tz_convert("UTC")
    recv = t0 + pd.to_timedelta(np.sort(rng.uniform(0, 3600, n)), unit="s")
    px = 8.8 + np.cumsum(rng.normal(0, 0.005, n))
    ev = recv - pd.to_timedelta(rng.uniform(0, 0.5, n), unit="s")
    df = pd.DataFrame({"ts_event": ev, "price": px, "size": 100, "flags": 128,
                       "side": "N", "publisher_id": 1, "action": "T"}, index=recv)
    df.index.name = "ts_recv"
    # plant reported prints at 08:00-08:05 with hours-old execution times and stale prices
    at = pd.Timestamp("2025-08-11 08:00:30", tz="America/New_York").tz_convert("UTC")
    rows = []
    for k in range(12):
        rows.append({"ts_event": at - pd.Timedelta(hours=6) + pd.Timedelta(minutes=k),
                     "price": 19.5 + 0.01 * k, "size": 5000, "flags": 128, "side": "N",
                     "publisher_id": 1, "action": "T"})
    planted = pd.DataFrame(rows, index=pd.DatetimeIndex([at + pd.Timedelta(seconds=20 * k) for k in range(12)], name="ts_recv"))
    return pd.concat([df, planted]).sort_index()


def test_wild_mask_finds_the_planted_prints():
    d = fake_trades()
    w = P.wild_mask(d["price"])
    assert int(w.sum()) == 12


def test_analysis_reports_the_lag_cut_and_execution_times():
    d = fake_trades()
    txt = "\n".join(P.analyse(d, None, "TEST", "2025-08-11"))
    assert "wild prints" in txt and "12" in txt
    assert "|lag| <=    60s   keeps 100.0% of live   drops 100.0% of wild" in txt
    assert "same day before 04:00: 12" in txt


def test_duplicate_receipt_timestamps_do_not_break_the_analysis():
    d = fake_trades()
    d = pd.concat([d, d.iloc[[100, 100, 200]]]).sort_index()      # repeated ts_recv
    txt = "\n".join(P.analyse(d, None, "TEST", "2025-08-11"))
    assert "flags against wild" in txt


def test_rebuild_beside_archive_bars():
    d = fake_trades()
    idx = pd.date_range("2025-08-11 08:00", "2025-08-11 08:40", freq="1min", tz="America/New_York").tz_convert("UTC")
    bars = pd.DataFrame({"open": 8.8, "high": 8.9, "low": 8.7, "close": 8.8, "volume": 1000}, index=idx)
    txt = "\n".join(P.analyse(d, bars, "TEST", "2025-08-11"))
    assert "REBUILT FROM TRADES" in txt and "08:00" in txt
