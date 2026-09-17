#!/usr/bin/env python3
"""Halt intervals from status records, the windows, and the trade join."""
from __future__ import annotations

from collections import Counter

import pandas as pd

from common import halt_census as H

DAY = "2025-06-09"


def status(rows):
    """rows: (symbol, HH:MM:SS, action, reason, is_trading)"""
    recs = [{"ts": pd.Timestamp(f"{DAY} {t}", tz="America/New_York").tz_convert("UTC"),
             "symbol": s, "action": a, "reason": r, "is_trading": tr} for s, t, a, r, tr in rows]
    df = pd.DataFrame(recs).set_index("ts").sort_index()
    df.index.name = "ts_event"
    return df


def test_halt_opens_on_halt_and_closes_on_trading_and_repeats_extend():
    f = H.et_frame(status([("X", "04:00:00", 1, 0, False), ("X", "07:10:00", 8, 30, False),
                           ("X", "07:20:00", 8, 30, False), ("X", "08:00:00", 7, 0, True),
                           ("X", "09:45:30", 9, 50, False), ("X", "09:51:00", 7, 0, True),
                           ("Y", "10:00:00", 8, 30, False)]))          # Y never resumes
    hs = H.halts(f)
    assert len(hs) == 3
    x1, x2, y = hs
    assert (x1["reason"], H.hhmm(x1["start_min"]), H.hhmm(x1["end_min"]), x1["dur_min"]) == ("NEWS_PENDING", "07:10", "08:00", 50.0)
    assert x2["action"] == "PAUSE" and x2["reason"] == "LULD_PAUSE" and H.window(x2) == "rth"
    assert y["open_at_close"] and y["end_min"] == 20 * 60
    assert H.window(x1) == "pre"


def test_summary_counts_universe_and_marks_trades():
    f = H.et_frame(status([("X", "07:10:00", 8, 30, False), ("X", "08:00:00", 7, 0, True),
                           ("Z", "09:40:00", 9, 50, False), ("Z", "09:46:00", 7, 0, True)]))
    hs = H.halts(f)
    universe = {("X", DAY)}
    trades = H.mark_trades([
        {"book": "MCL", "symbol": "X", "date": DAY, "entry_min": 7 * 60, "exit_min": 8 * 60, "net": -40.0, "reason": "trailing_stop"},
        {"book": "MCL", "symbol": "X", "date": DAY, "entry_min": 8 * 60 + 5, "exit_min": 8 * 60 + 30, "net": 6.0, "reason": "signal"},
        {"book": "MC5", "symbol": "Z", "date": DAY, "entry_min": 9 * 60 + 35, "exit_min": 9 * 60 + 50, "net": -3.0, "reason": "x"},
    ], hs)
    assert trades[0]["halt_inside"] and trades[0]["exit_on_resume"]
    assert not trades[1]["halt_inside"] and not trades[1]["exit_on_resume"]
    assert trades[2]["halt_inside"] and not trades[2]["exit_on_resume"]
    s = H.summary(H.crosstab(f), hs, universe, {DAY: [{"symbol": "X"}]}, 1, trades)
    assert s["halts_universe"] == 1 and s["universe"]["pre"]["n"] == 1 and s["all"]["rth"]["n"] == 1
    assert s["all"]["luld_before_0930"] == 0 and s["all"]["rth_first_half_hour_share"] == 1.0
    assert s["books"]["MCL"]["halt_inside"] == 1 and abs(s["books"]["MCL"]["per_trade_halted"] - (-44.26)) < 1e-9
    txt = "\n".join(H.render(s, 0.1, 1))
    for must in ("WHAT THE SCHEMA HOLDS", "THE POINT-IN-TIME UNIVERSE", "THE BOOKS", "NEWS_PENDING", "LULD_PAUSE"):
        assert must in txt, must
