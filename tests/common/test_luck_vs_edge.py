#!/usr/bin/env python3
"""Part A's buckets, the trend flag, and the one registered reading."""
from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from common import luck_vs_edge as A
from tests.common.test_first_entry_skip import EARLY, LATE, rows

ET = ZoneInfo("America/New_York")
DAY = date(2026, 3, 2)
CUT = "2026-02-01"
F = A.MEASURED_FRICTION


def days(n, month="01"):
    return [f"2026-{month}-{k:02d}" for k in range(1, n + 1)]


# --- buckets ------------------------------------------------------------------------

def test_per_session_divides_by_all_sessions_in_the_bucket_not_traded_ones():
    sess = days(4)                                   # four sessions, one traded
    trades = rows(sess[0], [10.0, 10.0])             # +20 on one session
    b = A.bucket(trades, sess, CUT)
    assert b["sessions"] == 4 and b["traded"] == 1 and b["trades"] == 2
    assert b["per_session"] == pytest.approx(5.0)
    assert b["per_traded"] == pytest.approx(20.0)
    assert b["per_trade"] == pytest.approx(10.0)


def test_bucket_drops_its_top_three_sessions_and_splits_halves_on_the_cut():
    sess = days(3, "01") + days(3, "03")
    trades = []
    for d, n in zip(sess, [100.0, 50.0, 20.0, -5.0, -5.0, -5.0]):
        trades += rows(d, [n])
    b = A.bucket(trades, sess, CUT)
    assert b["drop3"] == pytest.approx(-15.0 / 6)
    assert b["early"] == pytest.approx(170.0 / 3) and b["late"] == pytest.approx(-5.0)
    assert b["positive"] == pytest.approx(0.5) and b["median"] == pytest.approx(7.5)


def test_thin_bucket_is_flagged():
    assert A.bucket([], days(4), CUT)["thin"] is True
    assert A.bucket([], days(5), CUT)["thin"] is False


def test_trades_on_unlabelled_dates_are_dropped_and_counted():
    sess = days(6)
    labels = {d: "hot" for d in sess[:5]}            # sixth session unlabelled
    trades = rows(sess[5], [100.0]) + rows(sess[0], [1.0])
    r = A.reading(trades, labels, "hot", sess, CUT)
    assert r["dropped_trades"] == 1 and r["n_covered"] == 5
    assert r["hot"]["trades"] == 1


# --- the reading ----------------------------------------------------------------------

def test_breakeven_needs_a_paying_side_and_a_losing_side():
    assert A.breakeven(10.0, -10.0) == pytest.approx(0.5)
    assert A.breakeven(30.0, -10.0) == pytest.approx(0.25)
    assert A.breakeven(-1.0, -10.0) is None
    assert A.breakeven(5.0, 1.0) is None


def test_reading_edge_requires_positive_in_both_halves_and_after_drop3():
    hot = days(6, "01") + days(6, "03")
    rest = days(12, "02")
    sess = hot + rest
    labels = {d: "hot" for d in hot} | {d: "cold" for d in rest}
    trades = []
    for d in hot:
        trades += rows(d, [8.0])
    for d in rest:
        trades += rows(d, [-4.0])
    r = A.reading(trades, labels, "hot", sess, CUT)
    assert r["edge"] is True and r["h"] == pytest.approx(8.0) and r["l"] == pytest.approx(-4.0)
    assert r["fstar"] == pytest.approx(1 / 3) and r["f"] == pytest.approx(0.5)
    # three sessions carry it, spread over both halves so only drop-top-3 can kill it
    trades2 = []
    for k, d in enumerate(hot):
        trades2 += rows(d, [100.0 if k in (0, 1, 6) else -2.0])
    for d in rest:
        trades2 += rows(d, [-4.0])
    r2 = A.reading(trades2, labels, "hot", sess, CUT)
    assert r2["h"] > 0 and r2["edge"] is False


def test_reading_block_says_no_gate_rescues_a_book_with_no_hot_edge():
    hot, rest = days(6, "01"), days(6, "03")
    labels = {d: "hot" for d in hot} | {d: "cold" for d in rest}
    trades = []
    for d in hot + rest:
        trades += rows(d, [-3.0])
    r = A.reading(trades, labels, "hot", hot + rest, CUT)
    text = "\n".join(A.reading_block("MCL", "same-day regime", r))
    assert "NO EDGE EVEN ON THE PAYING SESSIONS" in text and "not read" in text


# --- the trend flag --------------------------------------------------------------------

def bars(symbol, points):
    idx, o, c = [], [], []
    for hhmm, op, cl in points:
        hh, mm = map(int, hhmm.split(":"))
        idx.append(pd.Timestamp(datetime.combine(DAY, dtime(hh, mm), tzinfo=ET)).tz_convert("UTC"))
        o.append(op); c.append(cl)
    return pd.DataFrame({"symbol": symbol, "open": o, "high": [max(a, b) for a, b in zip(o, c)],
                         "low": [min(a, b) for a, b in zip(o, c)], "close": c, "volume": 1}, index=pd.DatetimeIndex(idx))


def test_leader_move_is_first_open_to_last_close_before_0930_over_pit_names_only():
    frame = pd.concat([
        bars("A", [("04:05", 10.0, 12.0), ("09:29", 12.0, 16.0), ("09:30", 16.0, 50.0)]),   # +60%, the 09:30 bar ignored
        bars("B", [("05:00", 5.0, 9.0), ("09:00", 9.0, 4.0)]),                              # ran and gave it back: -20%
        bars("Z", [("05:00", 1.0, 99.0)]),                                                  # not a PIT name
    ])
    uni = [{"symbol": "A"}, {"symbol": "B"}]
    assert A.leader_move(frame, uni, DAY) == pytest.approx(0.6)
    assert A.leader_move(frame, [{"symbol": "B"}], DAY) == pytest.approx(-0.2)
    assert A.leader_move(frame, [{"symbol": "Q"}], DAY) is None


def test_trend_labels_apply_the_fixed_threshold():
    lab = A.trend_labels({"a": 0.5, "b": 0.49, "c": None, "d": 2.0})
    assert lab == {"a": "trend", "b": "not", "c": "not", "d": "trend"}


# --- render ---------------------------------------------------------------------------------

def test_render_carries_every_labelling_and_both_readings(tmp_path):
    sess = days(12, "01") + days(12, "03")
    same = {d: ("hot" if k % 3 == 0 else "cold" if k % 3 == 1 else "mixed") for k, d in enumerate(sess)}
    lag = {d: same[p] for p, d in zip(sess, sess[1:])}
    moves = {d: (0.8 if k % 4 == 0 else 0.1) for k, d in enumerate(sess)}
    trend = A.trend_labels(moves)
    readings = {d: "warm" for d in sess}
    books = {"MCL": [], "MC5": []}
    for d in sess:
        books["MCL"] += rows(d, [-3.0, 2.0])
        books["MC5"] += rows(d, [-6.0])
    meta = {"sessions": sess, "cut": CUT, "symbol_days": 48}
    text = "\n".join(A.render(books, meta, same, lag, trend, moves, readings, 9000, 1.0, 1))
    assert "BY SAME-DAY REGIME" in text and "BY LAGGED REGIME" in text and "BY TREND DAY" in text
    assert "BY THE 07:00 READING" in text
    assert text.count("THE READING: MCL") == 2 and text.count("THE READING: MC5") == 2
    assert "trend days 6 of 24" in text
    p = tmp_path / "labels.csv"
    A.write_labels(p, sess, same, lag, trend, moves, readings)
    lines = p.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "date,same_day,lagged,trend,leader_move,reading_0700" and len(lines) == 25
