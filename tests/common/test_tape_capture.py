#!/usr/bin/env python3
"""The ITCH/BASIC pre-market volume ratio: closed-bar rule, populations, chain."""
from __future__ import annotations

import numpy as np
import pandas as pd

from common import tape_capture as T

DAY = "2025-06-09"


def frame(symbol_bars: dict[str, list[tuple[str, int]]]) -> pd.DataFrame:
    """{symbol: [(HH:MM ET, volume), ...]} -> a dbn_io-shaped frame."""
    rows = []
    for sym, bars in symbol_bars.items():
        for hhmm, vol in bars:
            ts = pd.Timestamp(f"{DAY} {hhmm}", tz="America/New_York").tz_convert("UTC")
            rows.append({"ts": ts, "symbol": sym, "open": 5.0, "high": 5.0,
                         "low": 5.0, "close": 5.0, "volume": vol})
    df = pd.DataFrame(rows).set_index("ts").sort_index()
    df.index.name = "ts_event"
    return df


def test_bar_counts_only_once_closed():
    a = frame({"X": [("06:59", 10_000), ("07:00", 90_000)]})
    c = T.cumulative(a, DAY)
    assert c.loc["X", "07:00"] == 10_000          # the 06:59 bar closed at 07:00
    assert c.loc["X", "08:00"] == 100_000         # the 07:00 bar has closed by 08:00


def test_ratios_populations_and_absent_symbol():
    vmin = 55_200
    a = frame({"X": [("05:00", 40_000), ("08:10", 60_000)],      # 100k on BASIC
               "Y": [("05:00", 20_000)],                        # 20k: active, below band
               "Z": [("05:00", 5_000)]})                         # below MIN_TAPE: dropped
    b = frame({"X": [("05:00", 40_000), ("08:10", 20_000)]})    # Y absent from ITCH
    rows = T.compare(a, b, DAY, [{"symbol": "X"}], vmin)
    assert set(rows["symbol"]) == {"X", "Y"}
    x = rows[rows["symbol"] == "X"].iloc[0]
    y = rows[rows["symbol"] == "Y"].iloc[0]
    assert x["r_07:00"] == 1.0 and x["r_09:30"] == 0.6
    assert x["in_pit"] and x["in_band"]
    assert y["r_09:30"] == 0.0 and not y["in_pit"] and not y["in_band"]


def test_summary_chains_capture_and_counts_over_one():
    vmin = 55_200
    a = frame({"X": [("05:00", 100_000)], "W": [("05:00", 100_000)]})
    b = frame({"X": [("05:00", 50_000)], "W": [("05:00", 120_000)]})   # W: impossible
    rows = T.compare(a, b, DAY, [], vmin)
    s = T.summary(rows, vmin)
    head = s["populations"]["band"]["all"]["09:30"]
    assert head["n"] == 2 and head["over_1"] == 1
    assert s["capture_itch"]["p50"] == round(T.CAPTURE_P50 * head["p50"], 3)
    txt = "\n".join(T.render(s, 1, 0.5, 1, "var/reports/tape_capture.json"))
    for must in ("THE BAND", "THE POINT-IN-TIME UNIVERSE", "THE SHAPE THE DIAGNOSIS PREDICTS",
                 "THE CHAINED CAPTURE", ">1: 1", "screen_sim --dataset XNAS.ITCH --capture"):
        assert must in txt, must


def test_empty_population_renders():
    rows = pd.DataFrame(columns=["date", "symbol", "in_pit", "in_band"]
                        + [f"r_{c}" for c in T.CUTOFFS]).astype({"in_pit": bool, "in_band": bool})
    s = T.summary(rows, 55_200)
    assert s["capture_itch"]["p50"] is None
    assert "THE CHAINED CAPTURE" in "\n".join(T.render(s, 0, 0.0, 1, "x.json"))
