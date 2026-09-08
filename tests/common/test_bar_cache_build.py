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


# --- the two archive layouts ------------------------------------------------
#
# On 2026-09-08 a correctly-downloaded 515 MB XNAS.BASIC pull produced a cache
# of ZERO files. The fetcher writes daily chunks named for their target date;
# this module looked only for monthly ones, found none, and reported every
# counter at zero. Nothing raised. These tests pin both halves of that: that
# each layout is recognised, and -- the part that would have been worse -- that
# the daily one is not read the way the monthly one is.

CAL = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09"]


def _touch(d: Path, names) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    for n in names:
        (d / n).write_bytes(b"")
    return d


def test_monthly_files_are_recognised(tmp_path):
    d = _touch(tmp_path, ["2024-07.dbn.zst", "2024-08.dbn.zst"])
    assert B.archive_layout(d) == "monthly"


def test_daily_files_are_recognised(tmp_path):
    """The bug in one line: this returned nothing usable, so the build read no
    source data and wrote no files, with a report showing 27,877 requested and
    0 of every outcome."""
    d = _touch(tmp_path, ["2024-07-08.dbn.zst", "2024-07-09.dbn.zst"])
    assert B.archive_layout(d) == "daily"


def test_monthly_wins_when_both_are_present(tmp_path):
    """Daily files carry only the symbols each day's request named. Assembling
    one symbol's window from both scopes would narrow it without saying so."""
    d = _touch(tmp_path, ["2024-07.dbn.zst", "2024-07-08.dbn.zst"])
    assert B.archive_layout(d) == "monthly"


def test_an_empty_archive_is_neither(tmp_path):
    assert B.archive_layout(_touch(tmp_path, [])) == "none"


def test_sidecars_are_not_mistaken_for_data(tmp_path):
    """`2024-07.symbology.json` sits beside `2024-07.dbn.zst`. A looser glob
    (`*.dbn.zst` on the stem) would count the sidecar as a chunk."""
    d = _touch(tmp_path, ["2024-07.symbology.json", "manifest.json"])
    assert B.archive_layout(d) == "none"


# --- build(), end to end, against a stubbed archive -------------------------

def _fake_archive(tmp_path, layout: str):
    """An archive whose files hold what the real fetchers put in them.

    DAILY mirrors `databento_fetch --lookback 5`: the file named for a date
    carries that date AND the sessions before it. MONTHLY mirrors
    `overnight_pull`: one file per calendar month, every session in it.
    """
    src = tmp_path / "E" / "XNAS.BASIC" / "ohlcv-1m"
    src.mkdir(parents=True)
    content: dict[str, list[str]] = {}
    if layout == "daily":
        for i, d in enumerate(CAL):
            (src / f"{d}.dbn.zst").write_bytes(b"")
            content[f"{d}.dbn.zst"] = CAL[max(0, i - 2):i + 1]
    else:
        (src / "2026-01.dbn.zst").write_bytes(b"")
        content["2026-01.dbn.zst"] = CAL
    return src, content


def _stub_reads(monkeypatch, content):
    monkeypatch.setattr(B, "trading_calendar", lambda archive, dataset: CAL)
    monkeypatch.setattr(B, "read_dbn", lambda f: bars(content[Path(f).name]))


@pytest.mark.parametrize("layout", ["daily", "monthly"])
def test_both_layouts_build_the_same_file(tmp_path, monkeypatch, layout):
    src, content = _fake_archive(tmp_path, layout)
    _stub_reads(monkeypatch, content)
    out = tmp_path / "cache"

    st = B.build([("AAA", "2026-01-07")], tmp_path / "E", "XNAS.BASIC", out,
                 3, confirm=True)

    assert st["layout"] == layout
    assert st["written"] == 1, st
    written = B.cache_path(out, "AAA", "2026-01-07")
    back = pd.read_csv(written, index_col=0, parse_dates=[0])
    days = sorted(set(back.index.tz_convert(ET).strftime("%Y-%m-%d")))
    assert days == ["2026-01-05", "2026-01-06", "2026-01-07"]
    # `bars()` emits one bar an hour, 04:00-19:00 -> 16 per session.
    assert len(back) == 48


def test_the_daily_layout_does_not_duplicate_bars(tmp_path, monkeypatch):
    """The trap that made the month-grouped fix wrong.

    Daily files OVERLAP: 2026-01-07 holds the 5th, 6th and 7th, and so does
    2026-01-08 for its own three. Grouping them by month and concatenating --
    which is exactly right for monthly chunks -- loads every session three
    times. `write_bars` does not de-duplicate, so the cache fills with
    plausible files carrying three copies of every bar, volume sums treble, and
    nothing raises. Row count is the only thing that catches it.
    """
    src, content = _fake_archive(tmp_path, "daily")
    _stub_reads(monkeypatch, content)
    out = tmp_path / "cache"

    B.build([("AAA", "2026-01-07")], tmp_path / "E", "XNAS.BASIC", out, 3,
            confirm=True)

    back = pd.read_csv(B.cache_path(out, "AAA", "2026-01-07"),
                       index_col=0, parse_dates=[0])
    assert not back.index.duplicated().any()
    assert back["volume"].sum() == 48 * 1000


def test_an_archive_with_no_minute_files_counts_every_pair(tmp_path,
                                                           monkeypatch):
    """A --confirm run that writes nothing has to say so in the COUNTERS. The
    original failure was legible only as an absence: 27,877 requested, zero
    written, zero of every reason."""
    (tmp_path / "E" / "XNAS.BASIC" / "ohlcv-1m").mkdir(parents=True)
    monkeypatch.setattr(B, "trading_calendar", lambda archive, dataset: CAL)

    st = B.build([("AAA", "2026-01-07"), ("BBB", "2026-01-08")],
                 tmp_path / "E", "XNAS.BASIC", tmp_path / "cache", 3,
                 confirm=True)

    assert st["layout"] == "none"
    assert st["no_source"] == 2
    assert st["written"] == 0
    assert st["pairs"] == st["no_source"] + st["written"] + st["no_window"]


def test_a_missing_daily_chunk_is_counted_not_silent(tmp_path, monkeypatch):
    src, content = _fake_archive(tmp_path, "daily")
    (src / "2026-01-08.dbn.zst").unlink()
    _stub_reads(monkeypatch, content)

    st = B.build([("AAA", "2026-01-07"), ("AAA", "2026-01-08")],
                 tmp_path / "E", "XNAS.BASIC", tmp_path / "cache", 3,
                 confirm=True)

    assert st["written"] == 1 and st["no_source"] == 1


def test_files_already_on_disk_are_not_rebuilt(tmp_path, monkeypatch):
    src, content = _fake_archive(tmp_path, "daily")
    _stub_reads(monkeypatch, content)
    out = tmp_path / "cache"

    first = B.build([("AAA", "2026-01-07")], tmp_path / "E", "XNAS.BASIC",
                    out, 3, confirm=True)
    again = B.build([("AAA", "2026-01-07")], tmp_path / "E", "XNAS.BASIC",
                    out, 3, confirm=True)

    assert first["written"] == 1 and first["existing"] == 0
    assert again["written"] == 0 and again["existing"] == 1


def test_a_window_reaching_past_the_chunk_is_short_not_truncated(
        tmp_path, monkeypatch):
    """A daily file carries `--lookback` calendar days. Ask for a deeper window
    than that and the superset cannot be built -- it must be COUNTED short, not
    written with a missing session, because the engine reads a short file,
    finds too little warm-up and drops the symbol-day, which reads downstream
    as the strategy having no signal."""
    src, content = _fake_archive(tmp_path, "daily")
    _stub_reads(monkeypatch, content)

    st = B.build([("AAA", "2026-01-09")], tmp_path / "E", "XNAS.BASIC",
                 tmp_path / "cache", 4, confirm=True)   # file holds only 3

    assert st["written"] == 0 and st["short"] == 1
    assert not B.cache_path(tmp_path / "cache", "AAA", "2026-01-09").exists()


def test_the_report_says_which_layout_and_why_nothing_was_written(
        tmp_path, monkeypatch):
    """The failure was legible only as an absence -- 27,877 requested and zero
    of every outcome, with nothing naming the cause. Run the actual CLI and
    read what it writes, because the counters are only useful if they reach
    the report."""
    import json
    (tmp_path / "E" / "XNAS.BASIC" / "ohlcv-1m").mkdir(parents=True)
    monkeypatch.setattr(B, "trading_calendar", lambda archive, dataset: CAL)
    pairs = tmp_path / "p.json"
    json.dump([{"symbol": "AAA", "date": "2026-01-07"}], open(pairs, "w"))
    report = tmp_path / "r.txt"

    assert B.main(["--pairs", str(pairs), "--archive", str(tmp_path / "E"),
                   "--dataset", "XNAS.BASIC", "--out", str(tmp_path / "cache"),
                   "--report", str(report), "--confirm"]) == 0

    text = report.read_text()
    assert "archive layout          none" in text
    assert "NO SOURCE FILE          1" in text
    assert "neither monthly" in text


def test_the_report_flags_the_daily_layouts_winter_hour(tmp_path, monkeypatch):
    """The daily fetch's end bound is midnight UTC, which is 19:00 ET in
    winter. That hour is missing from those files and the note has to travel
    with the cache, not live only in a docstring."""
    import json
    src, content = _fake_archive(tmp_path, "daily")
    _stub_reads(monkeypatch, content)
    pairs = tmp_path / "p.json"
    json.dump([{"symbol": "AAA", "date": "2026-01-07"}], open(pairs, "w"))
    report = tmp_path / "r.txt"

    B.main(["--pairs", str(pairs), "--archive", str(tmp_path / "E"),
            "--dataset", "XNAS.BASIC", "--out", str(tmp_path / "cache"),
            "--report", str(report), "--confirm"])

    text = report.read_text()
    assert "archive layout          daily" in text
    assert "19:00 ET in winter" in text
    assert "WRITTEN                 1" in text


def test_a_dry_run_writes_nothing_and_still_names_the_layout(tmp_path,
                                                            monkeypatch):
    src, content = _fake_archive(tmp_path, "daily")
    _stub_reads(monkeypatch, content)
    out = tmp_path / "cache"

    st = B.build([("AAA", "2026-01-07")], tmp_path / "E", "XNAS.BASIC", out,
                 3, confirm=False)

    assert st["layout"] == "daily" and st["written"] == 0
    assert not out.exists()
