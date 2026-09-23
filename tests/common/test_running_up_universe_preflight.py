#!/usr/bin/env python3
"""W05-0006: the universe-preflight's core arithmetic, off synthetic frames.

`symbol_lead_time` and `load_first_entries` are pulled out of `run_day` and
the CLI precisely so they are testable without mocking `read_dbn` /
`build_frame` -- see the module docstring on why.
"""
from __future__ import annotations

import csv
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from common import running_up as RU
from common.running_up_universe_preflight import load_first_entries, symbol_lead_time


def bars(closes, day="2026-09-10", start_hour=4, volume=10_000):
    t0 = pd.Timestamp(f"{day} {start_hour:02d}:00", tz=RU.ET)
    idx = [t0 + timedelta(minutes=i) for i in range(len(closes))]
    return pd.DataFrame({"open": closes, "high": closes, "low": closes,
                         "close": closes, "volume": volume},
                        index=pd.DatetimeIndex(idx))


def test_symbol_lead_time_finds_the_pre_entry_peak_and_its_lag():
    # Flat, then a clear 5-minute burst at bar 10, then flat again; entry at
    # bar 15 -- five bars (five minutes) after the peak.
    closes = [3.0] * 10 + [3.3] + [3.3] * 4 + [3.35] * 5
    df = bars(closes)
    entry_ts = df.index[15]
    out = symbol_lead_time(df, entry_ts)
    assert out["pre_bars"] > 0
    # ret_5m at bar 10 is (3.3 / 3.0) - 1 = 0.10, the largest pre-entry value
    assert out["peak_ret5m"] == pytest.approx(0.10, abs=1e-9)
    assert out["lag_min"] == pytest.approx(5.0)


def test_symbol_lead_time_zero_pre_bars_when_entry_is_the_first_bar():
    df = bars([3.0, 3.1, 3.2])
    entry_ts = df.index[0]
    out = symbol_lead_time(df, entry_ts)
    assert out["pre_bars"] == 0
    assert out["peak_ret5m"] != out["peak_ret5m"]  # NaN
    assert out["lag_min"] != out["lag_min"]


def test_symbol_lead_time_never_reads_the_entry_bar_or_later():
    # If the peak sat AT or AFTER the entry bar this would be a hindsight
    # leak -- PROGRAM_INDEX §4: a comparison must be knowable at entry.
    closes = [3.0] * 5 + [3.5] * 5  # the burst is bars 5-9
    df = bars(closes)
    entry_ts = df.index[5]  # entry is exactly the first burst bar
    out = symbol_lead_time(df, entry_ts)
    # everything before bar 5 is flat, so no positive peak should be found
    assert out["peak_ret5m"] != out["peak_ret5m"] or out["peak_ret5m"] <= 0


def test_symbol_lead_time_empty_frame():
    out = symbol_lead_time(pd.DataFrame(), pd.Timestamp("2026-09-10 07:00", tz=RU.ET))
    assert out["pre_bars"] == 0
    assert out["peak_ret5m"] != out["peak_ret5m"]
    assert out["lag_min"] != out["lag_min"]


def test_load_first_entries_picks_the_earliest_across_books(tmp_path):
    p = tmp_path / "trades.csv"
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["book", "symbol", "date", "ordinal", "entry_et", "entry_px",
                    "exit_et", "exit_px", "reason", "bars_held", "net"])
        w.writerow(["MCL", "ABC", "2026-09-10", "1", "07:10", "1", "07:20", "1",
                    "trailing_stop", "1", "0"])
        w.writerow(["MC5", "ABC", "2026-09-10", "1", "07:05", "1", "07:20", "1",
                    "trailing_stop", "1", "0"])
        w.writerow(["MC5", "ABC", "2026-09-10", "2", "07:30", "1", "07:40", "1",
                    "trailing_stop", "1", "0"])
    by_day = load_first_entries(p)
    assert len(by_day["2026-09-10"]) == 1  # one NAME, not one per trade/book
    row = by_day["2026-09-10"][0]
    assert row["symbol"] == "ABC"
    assert row["first_et"] == "07:05"  # earliest across both books and both entries
