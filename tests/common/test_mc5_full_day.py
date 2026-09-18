#!/usr/bin/env python3
"""The full-day MC5 study reads REGISTERED_mc5_full_day.md §4 and amendment C."""
from __future__ import annotations

import argparse
from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from common import mc5_full_day as F
from strategy.mc5 import mc5 as MC5

ET = ZoneInfo("America/New_York")
FR = F.MEASURED_FRICTION
EARLY, LATE = "2026-01-10", "2026-03-10"
CUT = "2026-02-01"
DAY = date(2026, 9, 11)


def tr(day, et, net_after_f, symbol="X", exit_et="09:29", reason="trailing_stop"):
    return {"symbol": symbol, "date": day, "ordinal": 1, "net": net_after_f + FR,
            "entry_et": et, "entry_px": 5.0, "exit_et": exit_et, "exit_px": 5.0,
            "reason": reason, "bars_held": 3}


def spread(n_syms, per_sym, et="10:05"):
    out = []
    for i in range(n_syms):
        for d in (EARLY, LATE):
            out += [tr(d, et, v, f"S{i}") for v in per_sym]
    return out


# --- what counts as an added trade ------------------------------------------------

def test_blocks_are_read_off_the_entry_time():
    assert F.block_of("04:00") == "PRE" and F.block_of("09:29") == "PRE"
    assert F.block_of("09:30") == "RTH" and F.block_of("15:59") == "RTH"
    assert F.block_of("16:00") == "POST" and F.block_of("19:59") == "POST"


def test_added_is_entries_from_0930_not_exits():
    rows = [tr(EARLY, "09:29", 5, exit_et="14:00"), tr(EARLY, "09:30", 5),
            tr(EARLY, "16:30", 5)]
    assert [r["entry_et"] for r in F.added(rows)] == ["09:30", "16:30"]


def test_carried_pairs_premarket_entries_and_ignores_the_rest():
    base = [tr(EARLY, "07:00", -5, exit_et="09:29"), tr(EARLY, "08:00", -5)]
    ext = [tr(EARLY, "07:00", 20, exit_et="13:10"), tr(EARLY, "10:00", 3)]
    pairs = F.carried(base, ext)
    assert len(pairs) == 1
    b, x = pairs[0]
    assert b["exit_et"] == "09:29" and x["exit_et"] == "13:10"


# --- the five readings ------------------------------------------------------------

def test_a_clean_extension_passes():
    add = spread(40, [3, 3])
    tag, why, n = F.verdict(add, CUT, True)
    assert tag == "PASSES", why
    assert n["per_trade"] == pytest.approx(3.0)


def test_no_verdict_when_the_published_baseline_is_not_reproduced():
    tag, why, _ = F.verdict(spread(40, [3]), CUT, False)
    assert tag == "NO VERDICT" and "amendment C" in why


def test_an_extension_that_adds_nothing_is_nothing():
    tag, why, n = F.verdict([], CUT, True)
    assert tag == "NOTHING" and "no trades" in why and n["n"] == 0


def test_a_losing_extension_fails_reading_one():
    tag, why, _ = F.verdict(spread(40, [-3]), CUT, True)
    assert tag == "NOTHING" and "1 (per trade" in why


def test_one_good_half_is_not_enough():
    add = [tr(EARLY, "10:05", -2, f"S{i}") for i in range(40)]
    add += [tr(LATE, "10:05", 9, f"S{i}") for i in range(40)]
    tag, why, _ = F.verdict(add, CUT, True)
    assert tag == "NOTHING" and "2 (both halves" in why


def test_a_gain_carried_by_five_names_fails_drop_top_five():
    add = spread(40, [-1])
    for r in add:
        if r["symbol"] in {f"S{i}" for i in range(5)}:
            r["net"] += 400
    tag, why, n = F.verdict(add, CUT, True)
    assert n["per_trade"] > 0 and n["drop5"] <= 0
    assert "3 (drop-top-5 symbols" in why


def test_the_session_median_is_scored_on_traded_sessions_and_the_zero_fill_is_printed():
    add = spread(40, [3])
    _tag, _why, n = F.verdict(add, CUT, True, sessions=400)
    assert n["sessions_traded"] == 2
    assert n["median"] > 0 and n["median_all"] == 0.0


def test_drop_top_symbols_removes_names_not_trades():
    rows = [tr(EARLY, "10:05", 10, "A"), tr(LATE, "10:05", 10, "A"),
            tr(EARLY, "10:05", 5, "B"), tr(EARLY, "10:05", 1, "C")]
    assert F.drop_top_symbols(rows, FR, n=1) == pytest.approx(6.0)


# --- amendment C: the two controls -------------------------------------------------

def frame(rows, start="03:00"):
    """1-minute bars; `rows` are (minute offset, close)."""
    t0 = datetime.combine(DAY, dtime(*(int(x) for x in start.split(":"))), tzinfo=ET)
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=m) for m, _c in rows])
    px = [c for _m, c in rows]
    return pd.DataFrame({"open": px, "high": px, "low": px, "close": px,
                         "volume": 10_000}, index=idx)


class FakeEngine:
    """Records how each arm was called; the engine itself is tested elsewhere."""
    def __init__(self):
        self.calls = []

    def backtest_session(self, df, d, tz, **kw):
        self.calls.append({"rows": len(df), "session_end": kw.get("session_end"),
                           "not_before": kw.get("not_before")})
        return []


def test_the_arms_differ_only_in_frames_and_window():
    M = FakeEngine()
    pre, day = frame([(0, 5.0)]), frame([(0, 5.0), (1, 5.0)])
    F.engine_arms(M, pre, day, DAY, dtime(7, 0))
    a, a2, b = M.calls
    assert a["session_end"] is None and a["rows"] == 1      # published frames, 09:30
    assert a2["session_end"] is None and a2["rows"] == 2    # full-day frames, 09:30
    assert b["session_end"] == dtime(20, 0) and b["rows"] == 2
    assert {c["not_before"] for c in M.calls} == {dtime(7, 0)}


def test_the_published_arm_does_not_pass_a_window_at_all():
    """Passing 09:30 back in would be equivalent but not bit-identical by
    construction, and the reconciliation's whole job is bit-identity."""
    import inspect
    src = inspect.getsource(F.engine_arms)
    assert src.count("session_end=DAY_END") == 1


def test_mc5_session_end_none_is_bit_identical_and_2000_extends_the_window():
    import numpy as np
    # Bursty, two-sided noise -- a near-monotonic ramp pins RSI at 100 where
    # its rate of change is zero and MC5 can never fire. Same shape as the
    # fixture in tests/strategy/mc5/test_mc5_strategy.py, and the entries it
    # produces are what makes this test say anything.
    rng = np.random.default_rng(11)
    px, rows, burst = 3.0, [], 0
    for m in range(16 * 60):
        if burst == 0 and rng.random() < 0.02:
            burst = int(rng.integers(15, 50))
        drift = 0.004 if burst > 0 else 0.0
        if burst:
            burst -= 1
        px *= 1.0 + drift + rng.normal(0, 0.004)
        rows.append((m, round(max(px, 0.5), 2)))
    df = frame(rows, start="04:00")
    a = MC5.backtest_session(df, DAY, ET, entry_shares=100)
    b = MC5.backtest_session(df, DAY, ET, entry_shares=100, session_end=None)
    c = MC5.backtest_session(df, DAY, ET, entry_shares=100, session_end=dtime(20, 0))
    assert [t.__dict__ for t in a] == [t.__dict__ for t in b]
    assert len(c) >= len(a)
    assert max(pd.Timestamp(t.entry_time).tz_convert(ET).time() for t in a) < dtime(9, 30)
    assert max(pd.Timestamp(t.exit_time).tz_convert(ET).time() for t in c) >= dtime(9, 30)


# --- the run ------------------------------------------------------------------------

def test_baseline_check_needs_count_and_per_trade():
    rows = [tr(EARLY, "07:00", -8.57, f"S{i}") for i in range(10)]
    assert F.baseline_check(rows, (10, -8.57))[0]
    assert not F.baseline_check(rows, (11, -8.57))[0]
    assert not F.baseline_check(rows, (10, -8.40))[0]
    assert not F.baseline_check(rows, None)[0]


def test_the_published_figure_is_the_v2_book():
    assert F.PUBLISHED[F.PAIRS] == (6462, -8.57)


def test_the_wrong_tape_is_refused():
    with pytest.raises(SystemExit) as e:
        F.main(["--dataset", "XNAS.BASIC"])
    assert "REFUSED" in str(e.value)


def test_render_prints_both_controls_the_verdict_and_the_carried_line():
    books = {"A": [tr(EARLY, "07:00", -8.57, f"S{i}") for i in range(10)],
             "A2": [tr(EARLY, "07:00", -8.0, f"S{i}") for i in range(10)],
             "B": spread(40, [3]), "C": spread(40, [3])}
    books["A2"] += [tr(LATE, "07:05", -2, "Q", exit_et="09:29")]
    books["C"] += [tr(LATE, "07:05", 6, "Q", exit_et="15:00")]
    a = argparse.Namespace(dataset="XNAS.ITCH", pairs="p.json", day_pairs="d.json")
    L = "\n".join(F.render(books, 100, 120, CUT, 2, 1.0, 1, a, (10, -8.57), 0, []))
    assert "PASSES" in L and "WARM-UP, PRICED" in L
    assert "CARRIED TRADES: C against A'" in L
    assert "P/L change" in L
