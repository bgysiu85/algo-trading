#!/usr/bin/env python3
"""H-B4's 07:00 reading, its point-in-time cut, and the clock veto."""
from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from common import cold_veto as C
from tests.common.test_range_rank import _two_symbol_frame

ET = ZoneInfo("America/New_York")
DAY = date(2026, 3, 2)


def bars(symbol, points):
    """points: (HH:MM, open, high, close) on DAY."""
    idx, o, h, c = [], [], [], []
    for hhmm, op, hi, cl in points:
        hh, mm = map(int, hhmm.split(":"))
        idx.append(pd.Timestamp(datetime.combine(DAY, dtime(hh, mm), tzinfo=ET)).tz_convert("UTC"))
        o.append(op); h.append(hi); c.append(cl)
    return pd.DataFrame({"symbol": symbol, "open": o, "high": h, "low": [min(a, b) for a, b in zip(o, c)],
                         "close": c, "volume": 1000}, index=pd.DatetimeIndex(idx))


def rec(symbol, hhmm="04:00"):
    hh, mm = map(int, hhmm.split(":"))
    fs = pd.Timestamp(datetime.combine(DAY, dtime(hh, mm), tzinfo=ET)).tz_convert("UTC").isoformat()
    return {"symbol": symbol, "date": DAY.isoformat(), "first_seen": fs}


# --- the reading --------------------------------------------------------------------

def test_reading_uses_only_visible_names_and_bars_before_0700():
    frame = pd.concat([
        bars("A", [("04:30", 10.0, 12.0, 11.5), ("06:59", 11.5, 11.6, 11.0),
                   ("07:00", 11.0, 30.0, 29.0), ("07:05", 29.0, 40.0, 39.0)]),   # 07:00 itself is NOT before 07:00
        bars("B", [("05:00", 5.0, 6.0, 5.2)]),          # retained 0.2 of its move: round trip
        bars("C", [("05:00", 3.0, 3.0, 3.0)]),          # no move: excluded from the share
        bars("D", [("05:00", 2.0, 9.0, 9.0)]),          # seen only at 08:00: not visible
    ])
    r = C.reading(frame, [rec("A"), rec("B"), rec("C"), rec("D", "08:00")], DAY)
    assert r["n_visible"] == 3
    assert r["lead"] == pytest.approx(0.2)              # A: 12/10 - 1, NOT the 07:05 spike
    assert r["round_trip"] == pytest.approx(0.5)        # A retained 0.5 (not < 0.5); B 0.2 -> 1 of 2


def test_reading_with_nothing_visible_is_zero_not_an_error():
    r = C.reading(bars("A", [("05:00", 1, 2, 2)]), [rec("A", "08:00")], DAY)
    assert r == {"n_visible": 0, "lead": 0.0, "round_trip": 0.0}


# --- the cut ----------------------------------------------------------------------------

def readings_for(n):
    """n sessions with deterministic, varied components (no ties at the cut)."""
    out = {}
    for k in range(n):
        d = (date(2025, 1, 1) + timedelta(days=k)).isoformat()
        out[d] = {"n_visible": 5 + (k * 13) % 20, "lead": 0.5 + ((k * 37) % 100) / 100.0,
                  "round_trip": ((k * 7) % 10) / 10.0}
    return out


def test_fewer_than_min_names_is_cold_without_rating():
    lab = C.label_sessions({"2025-01-01": {"n_visible": C.MIN_NAMES - 1, "lead": 9.0, "round_trip": 0.0}})
    assert lab["2025-01-01"]["kind"] == "count" and lab["2025-01-01"]["cold"]


def test_inert_until_min_history_then_cut_from_prior_sessions_only():
    rd = readings_for(C.MIN_HISTORY + 5)
    days = sorted(rd)
    # the last session: the coldest reading on every component; the one before: the hottest
    rd[days[-1]] = {"n_visible": 5, "lead": 0.0, "round_trip": 1.0}
    rd[days[-2]] = {"n_visible": 99, "lead": 9.0, "round_trip": 0.0}
    lab = C.label_sessions(rd)
    kinds = [lab[d]["kind"] for d in days]
    assert kinds[0] == "inert"                                   # no prior at all
    assert all(k == "inert" for k in kinds[:C.MIN_HISTORY + 1])  # the first composite is day 2; 60 of them by day 61
    assert kinds[C.MIN_HISTORY + 1] in ("cold", "warm")
    assert lab[days[-1]]["kind"] == "cold"
    assert lab[days[-2]]["kind"] == "warm"
    # today's cut is a quantile of PRIOR composites only
    prior_comps = [lab[d]["composite"] for d in days[1:-1] if lab[d]["composite"] is not None]
    assert lab[days[-1]]["cut"] == pytest.approx(float(np.quantile(prior_comps, 1 / 3)))


def test_a_later_session_cannot_change_an_earlier_label():
    rd = readings_for(C.MIN_HISTORY + 10)
    days = sorted(rd)
    a = C.label_sessions(rd)
    rd2 = dict(rd)
    rd2[days[-1]] = {"n_visible": 50, "lead": 9.0, "round_trip": 0.0}
    b = C.label_sessions(rd2)
    assert all(a[d] == b[d] for d in days[:-1])


def test_a_tie_at_the_cut_is_cold():
    cold, cut = C.is_cold(0.5, [0.5, 0.5, 0.9, 0.9])
    assert cold and cut == pytest.approx(0.5)
    assert C.is_cold(0.51, [0.5, 0.5, 0.9, 0.9])[0] is False


def test_pct_rank_counts_prior_values_at_or_below():
    assert C.pct_rank(2.0, [1.0, 2.0, 3.0]) == pytest.approx(2 / 3)
    assert C.pct_rank(2.0, []) == 0.0


# --- the gate ---------------------------------------------------------------------------

def test_gate_is_a_clock_on_cold_sessions_and_inert_on_warm_ones():
    idx = pd.DatetimeIndex([pd.Timestamp(datetime.combine(DAY, dtime(h, m), tzinfo=ET))
                            for h, m in ((6, 59), (7, 0), (8, 30))]
                           + [pd.Timestamp(datetime.combine(DAY - timedelta(days=1), dtime(8, 0), tzinfo=ET))])
    assert C.gate_series(True, idx, DAY).tolist() == [True, False, False, False]
    assert C.gate_series(False, idx, DAY).tolist() == [True, True, True, False]


# --- run_day against the real engines -------------------------------------------------

def _run(monkeypatch, cold, seed):
    df = _two_symbol_frame(seed=seed)
    monkeypatch.setattr("common.dbn_io.read_dbn", lambda p, df=df: df)
    uni = [rec("AAA"), rec("BBB")]
    return C.run_day(([f"{DAY.isoformat()}.dbn"], DAY.isoformat(), uni, cold))


def test_run_day_cold_refuses_every_entry_from_0700_and_nothing_before(monkeypatch):
    hit = None
    for seed in range(60):
        day, res, err = _run(monkeypatch, True, seed)
        assert err == "" and res["errors"] == 0
        after = [r for r in res["books"]["MCL"] if r["entry_et"] >= "07:00"]
        before = [r for r in res["books"]["MCL"] if r["entry_et"] < "07:00"]
        if after and before:
            hit = res
            break
    assert hit, "no seed produced MCL entries on both sides of 07:00"
    veto = hit["books"]["MCL-veto"]
    assert all(r["entry_et"] < "07:00" for r in veto)
    assert [r["entry_et"] for r in veto] == [r["entry_et"] for r in hit["books"]["MCL"] if r["entry_et"] < "07:00"]
    could, total, detail = hit["binding"]["MCL-veto"]
    assert total == len(hit["books"]["MCL"]) and could == len(after)
    assert len(hit["refused"]["MCL-veto"]) == len(after)
    assert "after 07:00 on a cold session" in detail and "before 07:00" in detail


def test_run_day_warm_is_the_baseline_and_refuses_nothing_even_after_0700(monkeypatch):
    hit = None
    for seed in range(60):
        day, res, err = _run(monkeypatch, False, seed)
        if any(r["entry_et"] >= "07:00" for r in res["books"]["MCL"]):
            hit = res
            break
    assert hit, "no seed produced an MCL entry after 07:00"
    assert hit["books"]["MCL-veto"] == hit["books"]["MCL"]
    assert hit["books"]["MC5-veto"] == hit["books"]["MC5"]
    assert hit["refused"]["MCL-veto"] == [] and hit["refused"]["MC5-veto"] == []
    assert hit["binding"]["MCL-veto"][0] > 0          # it could have bound; the session was warm


def test_sessions_block_and_readings_file(tmp_path):
    rd = readings_for(C.MIN_HISTORY + 1)
    rd["2024-12-31"] = {"n_visible": 1, "lead": 0.1, "round_trip": 0.0}
    lab = C.label_sessions(rd)
    text = "\n".join(C.sessions_block(lab, sorted(rd)))
    assert "cold by count (< 5 names visible at 07:00)  1" in text and "vetoed (cold) 1 " in text
    p = tmp_path / "r.csv"
    C.write_readings(p, lab)
    rows = p.read_text(encoding="utf-8").splitlines()
    assert rows[0].startswith("date,kind,cold,composite") and len(rows) == len(rd) + 1
