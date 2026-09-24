"""Tests for `strategy.orb.tensec_g4` -- the G4 window builder (board
W05-0003 step 6). Pricing/pulling itself is `common.quote_price`'s tested
machinery, reused unchanged; what is specific here, and what a defect could
silently corrupt, is: which trades get a window, the plan-edge/holdout
filter, and the window's own boundaries."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from strategy.orb import tensec_g4 as G

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


def _row(symbol="AAA", day="2026-01-05", why="OK", trigger_sec=34520):
    return dict(symbol=symbol, date=day, t1_why=why, t1_trigger_sec=trigger_sec)


def _df(rows):
    return pd.DataFrame(rows)


def test_trigger_window_is_60s_either_side_of_a_10s_bar():
    lo, hi = G.trigger_window("2026-01-05", 34520)
    d = date(2026, 1, 5)
    bar_start = datetime(d.year, d.month, d.day, tzinfo=ET) + timedelta(seconds=34520)
    assert lo == (bar_start - timedelta(seconds=60)).astimezone(UTC)
    assert hi == (bar_start + timedelta(seconds=10) + timedelta(seconds=60)).astimezone(UTC)
    assert (hi - lo).total_seconds() == 130


def test_windows_keeps_only_ok_triggers():
    df = _df([_row(why="OK"), _row(symbol="BBB", why="NO_TRIGGER"),
              _row(symbol="CCC", why="TOO_LATE")])
    ws = G.windows(df, date(2020, 1, 1), date(2030, 1, 1))
    assert [w.symbol for w in ws] == ["AAA"]


def test_windows_excludes_sessions_before_the_plan_edge():
    df = _df([_row(day="2025-01-01"), _row(symbol="BBB", day="2026-01-05")])
    ws = G.windows(df, date(2026, 1, 1), date(2030, 1, 1))
    assert [w.symbol for w in ws] == ["BBB"]


def test_windows_excludes_the_holdout_even_though_the_source_should_not_have_it():
    """Belt-and-braces: `tensec_hx1_trades.csv.gz` is built in-sample-only, so
    this branch should never fire on the real file -- but if it ever does
    (a schema change, a bad merge), the holdout must still not leak into a
    pull."""
    df = _df([_row(day="2026-06-01")])
    ws = G.windows(df, date(2020, 1, 1), date(2026, 5, 1))
    assert ws == []


def test_windows_sorted_by_day_then_symbol():
    df = _df([_row(symbol="ZZZ", day="2026-01-06"),
              _row(symbol="AAA", day="2026-01-06"),
              _row(symbol="MMM", day="2026-01-05")])
    ws = G.windows(df, date(2020, 1, 1), date(2030, 1, 1))
    assert [(w.day, w.symbol) for w in ws] == [
        ("2026-01-05", "MMM"), ("2026-01-06", "AAA"), ("2026-01-06", "ZZZ")]


def test_load_trades_missing_file_exits(tmp_path):
    with pytest.raises(SystemExit):
        G.load_trades(tmp_path / "nope.csv.gz")


def test_load_trades_missing_columns_exits(tmp_path):
    p = tmp_path / "bad.csv.gz"
    pd.DataFrame({"symbol": ["AAA"]}).to_csv(p, index=False)
    with pytest.raises(SystemExit):
        G.load_trades(p)


def test_main_with_no_ok_trades_writes_report_and_returns_1(tmp_path, monkeypatch):
    trades = tmp_path / "trades.csv.gz"
    _df([_row(why="NO_TRIGGER")]).to_csv(trades, index=False)
    report = tmp_path / "report.txt"
    monkeypatch.chdir(tmp_path)
    rc = G.main(["--trades", str(trades), "--report", str(report)],
                today=date(2026, 9, 24))
    assert rc == 1
    assert "Nothing to price" in report.read_text(encoding="utf-8")
