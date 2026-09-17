#!/usr/bin/env python3
"""The two-tape report prints the registered readings."""
from __future__ import annotations

from common import tape_compare as S


def rows(date, nets, hour=8):
    return [{"symbol": "X", "date": date, "net": n + S.MEASURED_FRICTION, "entry_hour": hour,
             "reason": "trailing_stop", "entry_px": 5.0, "exit_px": 5.0} for n in nets]


def test_render_prints_split_hours_and_pairing():
    got = {
        "2025-08-11": {"trades": {S.A: rows("2025-08-11", [-30, -20]), S.B: rows("2025-08-11", [-5])},
                       "spikes": {S.A: (1000, 40), S.B: (900, 1)}, "symdays": 10, "b_missing": 1,
                       "a_bars": 3000, "b_bars": 2000, "errors": []},
        "2026-06-01": {"trades": {S.A: rows("2026-06-01", [-8], 6), S.B: rows("2026-06-01", [-7], 6)},
                       "spikes": {S.A: (1000, 2), S.B: (900, 1)}, "symdays": 10, "b_missing": 0,
                       "a_bars": 3000, "b_bars": 2100, "errors": []},
    }
    txt = "\n".join(S.render(["2025-08-11", "2026-06-01"], got, 1.0, 1))
    for must in ("COVERAGE", "no XNAS.ITCH bars at all: 1 of 20", "THE SPLIT AT 2026-03-30",
                 "before", "after", "BY ENTRY HOUR", "PAIRED BY SYMBOL-DAY", "better on XNAS.ITCH: 2",
                 "spike bars, whole slices: XNAS.BASIC 42 of 2,000   XNAS.ITCH 2 of 1,800"):
        assert must in txt, must
