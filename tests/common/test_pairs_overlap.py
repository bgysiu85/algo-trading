#!/usr/bin/env python3
"""Two universe files: shared symbol-days, and how far first_seen moved."""
from __future__ import annotations

import json

from common import pairs_overlap as O


def rec(sym, date, hhmm):
    return {"symbol": sym, "date": date,
            "first_seen": f"{date}T{hhmm}:00-04:00", "first_rank": 1,
            "best_rank": 1, "ticks_on": 5, "prior_source": "repaired"}


def test_overlap_counts_and_first_seen_shift(tmp_path):
    a = tmp_path / "a.json"; b = tmp_path / "b.json"
    a.write_text(json.dumps([rec("X", "2025-06-09", "04:30"), rec("Y", "2025-06-09", "07:00"),
                             rec("Z", "2025-06-10", "05:00")]), encoding="utf-8")
    b.write_text(json.dumps([rec("X", "2025-06-09", "04:30"), rec("Y", "2025-06-09", "08:10"),
                             rec("W", "2025-06-10", "04:15")]), encoding="utf-8")
    o = O.overlap(O.load(a), O.load(b))
    assert (o["a"], o["b"], o["both"], o["a_only"], o["b_only"]) == (3, 3, 2, 1, 1)
    assert abs(o["jaccard"] - 0.5) < 1e-9
    s = o["first_seen_shift_min"]
    assert s["same"] == 1 and s["later_on_b"] == 1 and s["p10"] == 7.0 and s["p90"] == 63.0
    assert o["knowable_0430_a"] == 1 and o["knowable_0430_b"] == 2
    txt = "\n".join(O.render(o, "a", "b"))
    assert "in both        2" in txt and "Jaccard        0.500" in txt
