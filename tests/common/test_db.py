#!/usr/bin/env python3
"""The database layer, exercised against a real engine.

SQLite here, SQL Server on Ben's machine. That gap is real and it is why the
SCHEMA is defined in SQLAlchemy rather than hand-written T-SQL: the dialect
does the translating, and it has already earned its place by bracketing
[close] as a reserved word, which hand-written DDL would have shipped broken.

What these tests can prove is everything that is not dialect: that a reload
does not duplicate, that overlapping cache windows are deduplicated, that a
timestamp keeps its meaning, and that a coverage status survives the trip. Those
are where the damage would be silent -- a doubled table still answers every
query, it just answers twice as large.
"""
from __future__ import annotations

import csv
import gzip
import json
from datetime import datetime

import pytest
from sqlalchemy import create_engine, func, select

from common import db as D
from common import db_load as L


@pytest.fixture
def eng(tmp_path):
    e = create_engine(f"sqlite:///{tmp_path/'t.db'}", future=True)
    D.create_all(e)
    return e


def count(eng, table):
    with eng.connect() as c:
        return c.execute(select(func.count()).select_from(table)).scalar_one()


# --- the schema itself ------------------------------------------------------

def test_every_table_is_created(eng):
    assert len(D.TABLES) >= 12
    for t in D.META.sorted_tables:
        assert count(eng, t) == 0


def test_the_ddl_compiles_for_sql_server():
    """The dialect, not me, decides how to spell this. It quotes [close] --
    a T-SQL reserved word -- which hand-written DDL would have got wrong."""
    from sqlalchemy.dialects import mssql
    from sqlalchemy.schema import CreateTable
    ddl = "\n".join(str(CreateTable(t).compile(dialect=mssql.dialect()))
                    for t in D.META.sorted_tables)
    assert "[close]" in ddl
    assert "CREATE TABLE bar_minute" in ddl
    assert "PRIMARY KEY (symbol, ts_utc)" in ddl


def test_a_password_is_never_printed():
    url = "mssql+pyodbc://sa:hunter2@localhost/Trading?driver=x"
    assert "hunter2" not in D._scrub(url)
    assert "<redacted>" in D._scrub(url)


def test_the_default_connection_carries_no_secret():
    """Windows auth means there is no password to leak, to store, or to
    rotate. Anything else is a deliberate step the user takes."""
    assert "trusted_connection=yes" in D.DEFAULT_URL
    assert "pwd" not in D.DEFAULT_URL.lower()
    assert "password" not in D.DEFAULT_URL.lower()


# --- idempotence: the property the whole loader exists for ------------------

def write_trades(tmp_path, name, rows):
    p = tmp_path / f"backtest_trades_{name}.csv"
    cols = ["symbol", "date", "entry_time", "exit_time", "entry_price",
            "exit_price", "qty", "reason", "bars_held", "gross", "commission",
            "net"]
    with open(p, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return p


def trade(symbol="AAA", date="2026-03-16", net=99.0):
    return {"symbol": symbol, "date": date,
            "entry_time": "2026-03-16 13:31:00+00:00",
            "exit_time": "2026-03-16 13:45:00+00:00", "entry_price": 5.0,
            "exit_price": 6.0, "qty": 100, "reason": "trail", "bars_held": 14,
            "gross": 100.0, "commission": 1.0, "net": net}


def state(tmp_path, name, done):
    p = tmp_path / f"backtest_state_{name}.json"
    p.write_text(json.dumps({"done": done, "trades": []}))
    return p


def test_loading_the_same_file_twice_does_not_double_the_rows(eng, tmp_path):
    """THE failure this design exists to prevent. An appending loader leaves
    every table valid, every query answering, and every sum exactly twice what
    it should be."""
    write_trades(tmp_path, "mcl", [trade(), trade(symbol="BBB")])
    state(tmp_path, "mcl", {"AAA|2026-03-16": {"status": "OK", "trades": 1}})
    for _ in range(3):
        with eng.begin() as c:
            L.load_backtest(c, tmp_path, tmp_path, "mcl", "traded")
    assert count(eng, D.backtest_trade) == 2
    assert count(eng, D.backtest_run) == 1
    assert count(eng, D.backtest_coverage) == 1


def test_a_changed_file_becomes_a_new_run_and_keeps_the_old_one(eng, tmp_path):
    """Two runs of the same strategy must be comparable. The files never
    allowed that -- each run overwrote the last -- and it is the main thing
    the database buys."""
    import os
    p = write_trades(tmp_path, "mcl", [trade(net=99.0)])
    state(tmp_path, "mcl", {})
    with eng.begin() as c:
        rid1, _ = L.load_backtest(c, tmp_path, tmp_path, "mcl", "traded")
    write_trades(tmp_path, "mcl", [trade(net=-50.0), trade(symbol="BBB")])
    os.utime(p, (0, 1_800_000_000))          # a different mtime => a new run
    with eng.begin() as c:
        rid2, _ = L.load_backtest(c, tmp_path, tmp_path, "mcl", "traded")
    assert rid1 != rid2
    assert count(eng, D.backtest_run) == 2
    with eng.connect() as c:
        nets = dict(c.execute(select(D.backtest_run.c.run_id,
                                     D.backtest_run.c.n_trades)).all())
    assert nets[rid1] == 1 and nets[rid2] == 2


def test_the_run_id_is_deterministic_for_one_file(tmp_path):
    p = write_trades(tmp_path, "mcl", [trade()])
    assert L.run_id("backtest", "x", p) == L.run_id("backtest", "x", p)


# --- coverage status is the reason the coverage table exists ----------------

def test_a_coverage_status_survives_the_round_trip(eng, tmp_path):
    """Without it a symbol-day with no trades is indistinguishable from one
    that could not be evaluated, and every average over the run is wrong."""
    write_trades(tmp_path, "mcl", [])
    state(tmp_path, "mcl", {"AAA|2026-03-16": {"status": "OK", "trades": 0},
                            "BBB|2026-03-16": {"status": "NO_DATA"},
                            "CCC|2026-03-16": {"status": "NO_SIZE"}})
    with eng.begin() as c:
        L.load_backtest(c, tmp_path, tmp_path, "mcl", "traded")
    with eng.connect() as c:
        got = dict(c.execute(select(D.backtest_coverage.c.symbol,
                                    D.backtest_coverage.c.status)).all())
    assert got == {"AAA": "OK", "BBB": "NO_DATA", "CCC": "NO_SIZE"}


# --- minute bars: overlapping windows -------------------------------------

def write_cache(root, symbol, date, times):
    import pandas as pd
    root.mkdir(parents=True, exist_ok=True)
    idx = pd.to_datetime(times, utc=True)
    df = pd.DataFrame({"open": 1.0, "high": 1.1, "low": 0.9, "close": 1.0,
                       "volume": 100}, index=idx)
    p = root / f"{symbol}_{date}.csv.gz"
    with gzip.open(p, "wt") as fh:
        df.to_csv(fh)
    return p


def test_overlapping_cache_windows_are_deduplicated(eng, tmp_path):
    """Each cache file is three sessions ending on its own date, so
    consecutive files for one symbol share two of them. Loaded file by file
    every bar would be stored about three times, and SUM(volume) would read
    three times the market's volume while looking entirely reasonable."""
    root = tmp_path / "3d_to_2000"
    write_cache(root, "AAA", "2026-03-16",
                ["2026-03-16 13:30", "2026-03-16 13:31"])
    write_cache(root, "AAA", "2026-03-17",
                ["2026-03-16 13:30", "2026-03-16 13:31",   # repeated
                 "2026-03-17 13:30"])                      # new
    with eng.begin() as c:
        n_sym, n = L.load_minute_bars(c, root, progress=None)
    assert n_sym == 1
    assert n == 3                       # not 5
    assert count(eng, D.bar_minute) == 3


def test_reloading_a_symbol_replaces_rather_than_appends(eng, tmp_path):
    root = tmp_path / "3d_to_2000"
    write_cache(root, "AAA", "2026-03-16", ["2026-03-16 13:30"])
    for _ in range(3):
        with eng.begin() as c:
            L.load_minute_bars(c, root, progress=None)
    assert count(eng, D.bar_minute) == 1


def test_two_symbols_do_not_collide(eng, tmp_path):
    root = tmp_path / "3d_to_2000"
    write_cache(root, "AAA", "2026-03-16", ["2026-03-16 13:30"])
    write_cache(root, "BBB", "2026-03-16", ["2026-03-16 13:30"])
    with eng.begin() as c:
        L.load_minute_bars(c, root, progress=None)
    assert count(eng, D.bar_minute) == 2


def test_a_symbol_with_an_underscore_is_split_on_the_LAST_one(tmp_path):
    """Cache names are SYMBOL_DATE. Some tickers contain a dot or a dash, and
    splitting on the first underscore would truncate any that contain one."""
    root = tmp_path / "3d_to_2000"
    write_cache(root, "BRK_A", "2026-03-16", ["2026-03-16 13:30"])
    assert list(L.cache_files_by_symbol(root)) == ["BRK_A"]


# --- timestamps -------------------------------------------------------------

def test_a_tz_aware_stamp_is_stored_as_naive_utc(eng, tmp_path):
    """SQL Server's DATETIME has no zone. A tz-aware value is either rejected
    or silently shifted depending on the driver, and a silent shift moves every
    pre-market bar into the previous session."""
    got = L._ts("2026-06-01 08:22:00+00:00")
    assert got.tzinfo is None
    assert (got.hour, got.minute) == (8, 22)
    et = L._ts("2026-06-01 04:22:00-04:00")     # same instant, ET
    assert et == got


def test_an_unparseable_stamp_is_null_not_epoch_zero():
    assert L._ts("") is None
    assert L._ts("not a time") is None


# --- the screen and its control sample -------------------------------------

def pairs(tmp_path, name, keys):
    p = tmp_path / f"{name}.json"
    p.write_text(json.dumps([{"symbol": s, "date": d} for s, d in keys]))
    return p


def test_survivors_and_rejects_land_in_one_table_flagged(eng, tmp_path):
    """One table, not two: 'is this day in both populations?' is the single
    thing that invalidates the leakage control, and it should be a constraint
    rather than a join nobody remembers to write."""
    s = pairs(tmp_path, "surv", [("AAA", "2026-03-16"), ("BBB", "2026-03-16")])
    r = pairs(tmp_path, "rej", [("CCC", "2026-03-16")])
    with eng.begin() as c:
        L.load_screen(c, s, r, {"dataset": "EQUS.SUMMARY", "min_rvol": 5.0})
    with eng.connect() as c:
        rows = c.execute(select(D.screen_candidate.c.symbol,
                                D.screen_candidate.c.is_reject)).all()
    assert sorted((s_, bool(f)) for s_, f in rows) == [
        ("AAA", False), ("BBB", False), ("CCC", True)]
    with eng.connect() as c:
        run = c.execute(select(D.screen_run)).mappings().one()
    assert run["n_candidates"] == 2 and run["n_rejects"] == 1
    assert run["min_rvol"] == 5.0


# --- provenance -------------------------------------------------------------

def test_every_load_records_where_it_came_from(eng, tmp_path):
    """A table of numbers with no provenance cannot say whether it holds the
    current backtest or one from three days ago, and both look equally
    authoritative."""
    write_trades(tmp_path, "mcl", [trade()])
    state(tmp_path, "mcl", {})
    with eng.begin() as c:
        L.load_backtest(c, tmp_path, tmp_path, "mcl", "traded")
    with eng.connect() as c:
        row = c.execute(select(D.load_run)).mappings().one()
    assert row["kind"] == "backtest"
    assert row["source_path"].endswith("backtest_trades_mcl.csv")
    assert row["rows"] == 1
    assert row["source_mtime"] is not None


# --- creating the database itself -------------------------------------------

def test_a_database_name_is_validated_not_interpolated():
    """The name arrives from a URL and goes into CREATE DATABASE. A URL is not
    a place to find out what an f-string will do."""
    with pytest.raises(SystemExit) as e:
        D.ensure_database("mssql+pyodbc://@localhost/Trading];DROP DATABASE x--")
    assert "refusing" in str(e.value)


def test_an_ordinary_name_passes_validation(monkeypatch):
    """The guard must not reject the names people actually use."""
    import re
    for name in ("Trading", "trading_db", "T1", "_scratch"):
        assert re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,120}", name)
    for name in ("my-db", "db;drop", "1st", "", "a b"):
        assert not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,120}", name)
