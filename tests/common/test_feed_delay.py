#!/usr/bin/env python3
"""H-D1: the delayed floor, and the things that would make the reading wrong.

Registered in docs/research/REGISTERED_feed_delay_cost.md. The study's claim
is "the published book with the floor moved by 15 minutes". The failures that
would break it silently: a floor that does not move (offset 0 and 15 give the
same book), a floor clamped back into the session, a classification that
chooses its own words, and a +0 book that is not the published one.
"""
from __future__ import annotations

from datetime import date, time
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from common import feed_delay as FD

ET = FD.ET


def row(net=10.0, d="2026-09-10", bars=5, ret5=0.02, entry="05:00", exit_="05:05", symbol="X"):
    return {"symbol": symbol, "date": d, "ordinal": 1, "net": float(net),
            "entry_et": entry, "entry_px": 3.0, "exit_et": exit_, "exit_px": 3.1,
            "reason": "trailing_stop", "bars_held": bars, "ret_5m": ret5,
            "hold_min": FD.hold_minutes({"entry_et": entry, "exit_et": exit_})}


# --- the floor ----------------------------------------------------------------

def test_the_floor_moves_by_the_offset_and_is_not_clamped():
    d = date(2026, 9, 10)
    assert FD.delayed_floor(time(4, 31), 0, d) == time(4, 31)
    assert FD.delayed_floor(time(4, 31), 15, d) == time(4, 46)
    assert FD.delayed_floor(time(4, 50), 15, d) == time(5, 5)
    # A name first seen at 09:20 could not have been on the delayed feed
    # before the session ended: the floor lands AFTER 09:30, not at it.
    assert FD.delayed_floor(time(9, 20), 15, d) > time(9, 30)


def test_the_books_are_the_registrations_four_offsets_for_both_strategies():
    """§1 fixed 0 / 5 / 15 / 30 before any code. A fifth offset is a search."""
    assert FD.OFFSETS == (0, 5, 15, 30)
    assert FD.DELAY == 15
    names = [n for n, _, _ in FD.BOOKS]
    assert len(names) == len(set(names)) == 8
    assert {s for _, s, _ in FD.BOOKS} == {"mcl", "mc5"}


def test_run_universe_hands_each_book_its_own_floor_and_the_base_the_raw_one():
    """THE BUG THIS EXISTS FOR: an unwired offset gives eight identical books
    and a table that reads 'the delay costs nothing'."""
    seen = {}

    class FakeMod:
        @staticmethod
        def backtest_session(df, d, tz, **kw):
            seen.setdefault(kw["not_before"], 0)
            seen[kw["not_before"]] += 1
            return []

    idx = pd.date_range("2026-09-10 04:00", periods=30, freq="1min", tz=ET)
    frame = pd.DataFrame({"symbol": "ABC", "open": 3.0, "high": 3.1, "low": 2.9,
                          "close": 3.0, "volume": 1000}, index=idx)
    universe = [{"symbol": "ABC", "date": "2026-09-10",
                 "first_seen": "2026-09-10T08:31:00Z"}]      # 04:31 ET
    engines = {"mcl": (FakeMod, {}), "mc5": (FakeMod, {})}
    res = FD.run_universe(frame, "2026-09-10", universe, engines)
    assert res["symdays"] == 1 and res["errors"] == 0
    assert set(seen) == {time(4, 31), time(4, 36), time(4, 46), time(5, 1)}
    assert all(v == 2 for v in seen.values())               # once per strategy


def test_a_symbol_day_that_raises_in_one_book_is_dropped_from_all():
    class Flaky:
        @staticmethod
        def backtest_session(df, d, tz, **kw):
            if kw["not_before"] >= time(4, 46):
                raise RuntimeError("boom")
            return [SimpleNamespace(net=1.0, entry_time=pd.Timestamp("2026-09-10 04:40", tz=ET),
                                    exit_time=pd.Timestamp("2026-09-10 04:45", tz=ET),
                                    entry_price=3.0, exit_price=3.1, reason="x", bars_held=5)]

    idx = pd.date_range("2026-09-10 04:00", periods=30, freq="1min", tz=ET)
    frame = pd.DataFrame({"symbol": "ABC", "open": 3.0, "high": 3.1, "low": 2.9,
                          "close": 3.0, "volume": 1000}, index=idx)
    universe = [{"symbol": "ABC", "date": "2026-09-10", "first_seen": "2026-09-10T08:31:00Z"}]
    res = FD.run_universe(frame, "2026-09-10", universe, {"mcl": (Flaky, {}), "mc5": (Flaky, {})})
    assert res["symdays"] == 0 and res["errors"] == 1
    assert all(not rows for rows in res["books"].values())


# --- the shape ----------------------------------------------------------------

def test_shape_reads_win_rate_R_hold_and_the_short_bucket():
    rows = [row(net=20.26, entry="05:00", exit_="05:01"),      # +16 after $4.26, 1 min
            row(net=-5.74, entry="05:00", exit_="05:10"),      # -10, 10 min
            row(net=-5.74, entry="05:00", exit_="05:30"),      # -10, 30 min
            row(net=-3.74, entry="05:00", exit_="05:02")]      # -8, 2 min
    s = FD.shape(rows)
    assert s["n"] == 4
    assert s["win"] == pytest.approx(0.25)
    assert s["R"] == pytest.approx(16.0 / ((10 + 10 + 8) / 3))
    assert s["hold_med"] == pytest.approx(6.0)
    assert s["short"] == pytest.approx(0.5)
    assert s["per_trade"] == pytest.approx((16 - 10 - 10 - 8) / 4)


def test_shape_of_nothing_is_nan_not_a_crash():
    s = FD.shape([])
    assert s["n"] == 0 and np.isnan(s["win"]) and np.isnan(s["R"])


def test_marginal_trade_is_what_the_removed_trades_were_worth():
    base = [row(net=-5.0)] * 10 + [row(net=-20.0)] * 5
    cell = [row(net=-5.0)] * 10                              # the delay removed the five (20)s
    assert FD.marginal(base, cell, f=0.0) == pytest.approx(-20.0)
    assert np.isnan(FD.marginal(base, base))


# --- the classification -------------------------------------------------------

def test_the_three_words_are_fixed_and_read_from_half_the_distance():
    live = {"win": 0.47, "R": 0.72}
    sim0 = {"win": 0.22, "R": 1.67}
    # +15 closes neither
    assert FD.classify(sim0, {"win": 0.23, "R": 1.60}, live)[0] == "NOT IT"
    # closes win rate more than half, R not
    assert FD.classify(sim0, {"win": 0.36, "R": 1.60}, live)[0] == "PART OF IT"
    # closes both
    assert FD.classify(sim0, {"win": 0.36, "R": 1.10}, live)[0] == "THE SHAPE"
    # overshoot still counts as closed (moved past, not away)
    assert FD.classify(sim0, {"win": 0.55, "R": 0.60}, live)[0] == "THE SHAPE"
    # moving AWAY is negative and never counts
    word, det = FD.classify(sim0, {"win": 0.15, "R": 2.0}, live)
    assert word == "NOT IT" and det["win"]["closed"] < 0


def test_monotone_reads_the_curve():
    assert FD.monotone([1, 2, 3, 4]) == "rising"
    assert FD.monotone([4, 3, 3, 1]) == "falling"
    assert FD.monotone([1, 3, 2, 4]) == "mixed"
    assert FD.monotone([1, float("nan")]) == "n/a"


# --- the population stop ------------------------------------------------------

def test_a_plus_zero_book_that_is_not_the_published_one_stops_the_run(monkeypatch):
    monkeypatch.setattr(FD, "published_mcl_trades", lambda p: 3)
    books = {n: [] for n, _, _ in FD.BOOKS}
    books[FD.book_name("mcl", 0)] = [row(), row()]           # 2, published says 3
    text, ok = FD.render(books, 2, 0, ["2026-09-10"], 1.0, 1, [],
                         universe="v2.json", dataset="XNAS.ITCH", live={})
    assert not ok
    assert "DOES NOT MATCH" in text and "THE FOUR FLOORS" not in text


def test_a_universe_with_no_published_count_is_read_not_stopped(monkeypatch):
    monkeypatch.setattr(FD, "published_mcl_trades", lambda p: None)
    books = {n: [row(d="2026-09-10"), row(d="2026-09-12")] for n, _, _ in FD.BOOKS}
    text, ok = FD.render(books, 2, 0, ["2026-09-10", "2026-09-12"], 1.0, 1, [],
                         universe="ext.json", dataset="XNAS.ITCH", live={})
    assert ok and "THE FOUR FLOORS" in text and "no live round trips" in text


def test_the_live_block_classifies_mcl_and_only_prints_mc5():
    books = {n: [row(net=-5.0, d="2026-09-10"), row(net=-5.0, d="2026-09-12")]
             for n, _, _ in FD.BOOKS}
    live = {"mcl": {"n": 17, "per_trade": -4.79, "win": 0.471, "R": 0.72, "hold_med": 3.0,
                    "short": 0.3, "sessions": ["2026-09-10"]},
            "mc5": {"n": 59, "per_trade": -6.27, "win": 0.119, "R": 2.71, "hold_med": 2.0,
                    "short": 0.5, "sessions": ["2026-09-10"]}}
    text = "\n".join(FD.live_block(books, live, ["2026-09-10", "2026-09-12"]))
    assert "THE DELAY IS" in text
    assert "apex-ON" in text and "NOT classified" in text
