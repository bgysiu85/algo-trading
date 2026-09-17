#!/usr/bin/env python3
"""ITCH against consolidated cleared volume: the ladder, its freshness, the JSON."""
from __future__ import annotations

import pandas as pd

from common import itch_capture as C

DAY = "2025-06-09"


def ts(hhmm):
    return pd.Timestamp(f"{DAY} {hhmm}", tz="America/New_York").tz_convert("UTC")


def tape(symbol_bars):
    rows = [{"ts": ts(h), "symbol": s, "open": 5.0, "high": 5.0, "low": 5.0, "close": 5.0,
             "volume": v} for s, bars in symbol_bars.items() for h, v in bars]
    df = pd.DataFrame(rows).set_index("ts").sort_index()
    df.index.name = "ts_event"
    return df


def stats(rows):
    """rows: (symbol, HH:MM, cleared quantity) -> a statistics frame as dbn_io shapes it."""
    df = pd.DataFrame([{"ts": ts(h), "symbol": s, "stat_type": C.CLEARED_VOLUME, "quantity": q}
                       for s, h, q in rows]).set_index("ts").sort_index()
    df.index.name = "ts_event"
    return df


def test_capture_by_cutoff_and_stat_age():
    t = tape({"X": [("05:00", 30_000), ("08:10", 20_000)]})
    s = stats([("X", "04:50", 40_000), ("X", "06:55", 60_000), ("X", "08:20", 200_000),
               ("X", "09:20", 250_000)])
    rows = C.compare(t, s, DAY, [{"symbol": "X"}])
    x = rows.iloc[0]
    assert x["r_07:00"] == 30_000 / 60_000          # bar at 05:00 closed; stat from 06:55
    assert x["age_07:00"] == 5.0                      # 07:00 minus 06:55
    assert x["r_08:30"] == 50_000 / 200_000
    assert x["r_09:30"] == 50_000 / 250_000 and x["in_band"] and x["in_pit"]


def test_band_is_on_the_consolidated_figure_and_absent_tape_is_zero():
    t = tape({"X": [("05:00", 1_000)]})
    s = stats([("X", "09:00", 600_000),      # above 5x 100k: active, not band
               ("Y", "09:00", 80_000),       # band, no ITCH bars at all
               ("Z", "09:00", 5_000)])       # below MIN_CONS: dropped
    rows = C.compare(t, s, DAY, [])
    assert set(rows["symbol"]) == {"X", "Y"}
    y = rows[rows["symbol"] == "Y"].iloc[0]
    assert y["in_band"] and y["r_09:30"] == 0.0
    assert not rows[rows["symbol"] == "X"].iloc[0]["in_band"]


def test_summary_ladder_is_keyed_by_et_minute_and_renders():
    t = tape({"X": [("05:00", 30_000)], "W": [("05:00", 50_000)]})
    s = stats([("X", "05:10", 100_000), ("W", "05:10", 100_000)])
    rows = C.compare(t, s, DAY, [])
    out = C.summary(rows)
    lad = out["ladder"]["before"]
    assert lad["330"] == 0.4 and lad["570"] == 0.4          # 05:30 and 09:30, same stat
    assert lad["270"] is None                                # 04:30: nothing published yet
    assert out["ladder"]["after"]["570"] is None
    txt = "\n".join(C.render(out, 1, 0, 0.1, 1, "var/reports/itch_capture.json"))
    for must in ("THE LADDER", "HOW FRESH THE STATISTIC IS", "--capture-ladder",
                 "IN CONSOLIDATED UNITS"):
        assert must in txt, must
