#!/usr/bin/env python3
"""The two things that would corrupt a backtest silently.

Mixing price bases in one cache, and writing a file whose warm-up is short. In
both cases everything runs, a number comes out, and nothing says it is wrong.
"""
from __future__ import annotations

import gzip
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from common import bar_cache_build as B

ET = ZoneInfo("America/New_York")


def bars(dates, start_min=4 * 60, end_min=20 * 60, step=60):
    """Minute bars at `step` minutes through each ET session."""
    idx, rows = [], []
    for d in dates:
        for m in range(start_min, end_min, step):
            ts = pd.Timestamp(f"{d} {m//60:02d}:{m%60:02d}", tz=ET)
            idx.append(ts.tz_convert("UTC"))
            rows.append((5.0, 5.1, 4.9, 5.0, 1000))
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"],
                      index=pd.DatetimeIndex(idx))
    df["symbol"] = "AAA"
    return df


# --- the trading calendar ---------------------------------------------------

def test_the_window_counts_trading_sessions_not_calendar_days():
    """A calendar-day guess is wrong across every market holiday and long
    weekend, and the file that results is short of warm-up rather than absent
    -- which downstream reads as the strategy having no signal."""
    cal = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"]  # weekend gap
    assert B.window_for(cal, "2026-01-07", 3) == [
        "2026-01-05", "2026-01-06", "2026-01-07"]


def test_a_date_without_enough_history_yields_no_window():
    cal = ["2026-01-02", "2026-01-05"]
    assert B.window_for(cal, "2026-01-05", 3) == []


def test_a_date_not_in_the_calendar_yields_no_window():
    assert B.window_for(["2026-01-02"], "2026-01-03", 1) == []


def test_previous_month_wraps_the_year():
    assert B._prev_month("2026-01") == "2025-12"
    assert B._prev_month("2026-09") == "2026-08"


# --- slicing ----------------------------------------------------------------

def test_only_the_window_dates_survive():
    df = bars(["2026-01-05", "2026-01-06", "2026-01-07"])
    out = B.slice_window(df, ["2026-01-06", "2026-01-07"])
    days = set(out.index.tz_convert(ET).strftime("%Y-%m-%d"))
    assert days == {"2026-01-06", "2026-01-07"}


def test_bars_outside_the_session_are_dropped():
    """Databento carries prints outside 04:00-20:00 ET. The engines' superset
    is defined as that window, so anything else would shift every index."""
    df = bars(["2026-01-06"], start_min=0, end_min=24 * 60, step=30)
    out = B.slice_window(df, ["2026-01-06"])
    et = out.index.tz_convert(ET)
    mins = et.hour * 60 + et.minute
    assert mins.min() >= 4 * 60
    assert mins.max() < 20 * 60


def test_gaps_are_not_filled():
    """No bar exists for a minute with no trade. Inventing one invents a price
    the market never made, and a strategy that reads volume would see it."""
    df = bars(["2026-01-06"], step=60)          # hourly, deliberately sparse
    out = B.slice_window(df, ["2026-01-06"])
    assert len(out) == 16                        # 04:00..19:00, not 960


# --- the file the engines read ----------------------------------------------

def test_the_written_file_round_trips_through_the_engines_reader(tmp_path):
    """load_sessions() does pd.read_csv(index_col=0, parse_dates=[0]) and then
    converts to UTC. Whatever is written has to survive exactly that."""
    df = bars(["2026-01-06"])
    p = tmp_path / "AAA_2026-01-06.csv.gz"
    n = B.write_bars(p, B.slice_window(df, ["2026-01-06"]))

    back = pd.read_csv(p, index_col=0, parse_dates=[0])
    back.index = (back.index.tz_localize("UTC") if back.index.tz is None
                  else back.index.tz_convert("UTC"))
    assert len(back) == n
    assert list(back.columns) == ["open", "high", "low", "close", "volume"]
    assert back.index.is_monotonic_increasing
    assert back["volume"].iloc[0] == 1000


# --- refusing to mix price bases --------------------------------------------

def test_writing_into_the_ib_cache_is_refused(tmp_path):
    """bar_cache/ holds SPLIT-ADJUSTED IB bars; this writes RAW ones. A mixed
    directory does not fail -- load_sessions reads both, the backtest runs, and
    the result is part one basis and part the other with nothing recording
    which trade came from where."""
    (tmp_path / B.WINDOW_DIR).mkdir(parents=True)
    (tmp_path / B.WINDOW_DIR / "AAA_2026-01-06.csv.gz").write_bytes(b"")
    with pytest.raises(SystemExit, match="Refusing to write into it"):
        B.check_source(tmp_path, "EQUS.MINI", "ohlcv-1m")


def test_a_disagreeing_source_marker_is_refused(tmp_path):
    B.check_source(tmp_path, "EQUS.MINI", "ohlcv-1m")
    with pytest.raises(SystemExit, match="Refusing to mix price bases"):
        B.check_source(tmp_path, "XNAS.ITCH", "ohlcv-1m")


def test_a_matching_source_marker_is_accepted_so_runs_resume(tmp_path):
    B.check_source(tmp_path, "EQUS.MINI", "ohlcv-1m")
    B.check_source(tmp_path, "EQUS.MINI", "ohlcv-1m")      # must not raise
    marker = (tmp_path / B.SOURCE_NAME).read_text()
    assert "RAW" in marker and "EQUS.MINI" in marker


def test_an_empty_directory_gets_a_marker(tmp_path):
    B.check_source(tmp_path, "EQUS.MINI", "ohlcv-1m")
    assert (tmp_path / B.SOURCE_NAME).exists()


# --- pair loading -----------------------------------------------------------

def test_pairs_merge_and_dedupe_across_files(tmp_path):
    """The screened candidates and Ben's traded symbol-days overlap. Building
    a file twice is wasted work; missing one is a hole in the backtest."""
    import json
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    json.dump([{"symbol": "AAA", "date": "2026-01-06"}], open(a, "w"))
    json.dump([{"symbol": "AAA", "date": "2026-01-06"},
               {"symbol": "BBB", "date": "2026-01-06"}], open(b, "w"))
    assert B.load_pairs([a, b]) == [("AAA", "2026-01-06"), ("BBB", "2026-01-06")]
