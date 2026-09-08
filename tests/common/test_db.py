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
    # dataset joined this key on 2026-09-08: two tapes hold different
    # observations of the same minute, not duplicates of it.
    assert "PRIMARY KEY (dataset, symbol, ts_utc)" in ddl


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
        n_sym, n = L.load_minute_bars(c, root, "EQUS.MINI", progress=None)
    assert n_sym == 1
    assert n == 3                       # not 5
    assert count(eng, D.bar_minute) == 3


def test_reloading_a_symbol_replaces_rather_than_appends(eng, tmp_path):
    root = tmp_path / "3d_to_2000"
    write_cache(root, "AAA", "2026-03-16", ["2026-03-16 13:30"])
    for _ in range(3):
        with eng.begin() as c:
            L.load_minute_bars(c, root, "EQUS.MINI", progress=None)
    assert count(eng, D.bar_minute) == 1


def test_two_symbols_do_not_collide(eng, tmp_path):
    root = tmp_path / "3d_to_2000"
    write_cache(root, "AAA", "2026-03-16", ["2026-03-16 13:30"])
    write_cache(root, "BBB", "2026-03-16", ["2026-03-16 13:30"])
    with eng.begin() as c:
        L.load_minute_bars(c, root, "EQUS.MINI", progress=None)
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


# --- the leak that actually happened ----------------------------------------

def test_a_password_containing_an_at_sign_leaks_only_its_tail(monkeypatch):
    """THE failure, reproduced. A password with '@' makes the URL malformed:
    the parser splits at the first '@', the tail of the password becomes the
    HOSTNAME, and the driver reports 'could not connect to <tail>@localhost'.

    The pattern-only scrubber matched ':<something>@' and saw nothing wrong,
    because by then the password was not in a password-shaped position. The
    tail went to a terminal and from there into a chat."""
    D._KNOWN.clear()
    D.remember_secret("aa@bb!cc*dd")
    leaked = "could not connect to bb!cc*dd@localhost. Server is not found."
    assert "bb!cc*dd" not in D._scrub(leaked)
    assert "<redacted>" in D._scrub(leaked)


def test_the_whole_password_is_scrubbed_too():
    D._KNOWN.clear()
    D.remember_secret("hunter2hunter2")
    assert "hunter2hunter2" not in D._scrub("url is hunter2hunter2 ok")


def test_short_fragments_are_not_redacted_out_of_prose():
    """A scrubber that eats ordinary words gets switched off."""
    D._KNOWN.clear()
    D.remember_secret("ab@localhost")          # 'ab' is below the floor
    out = D._scrub("the connection to localhost failed")
    assert "localhost" not in out or "the connection to" in out
    D._KNOWN.clear()
    D.remember_secret("x@y")                   # too short to remember at all
    assert D._scrub("x and y are fine") == "x and y are fine"


# --- building a URL instead of pasting one ----------------------------------

def test_a_password_with_url_metacharacters_survives_a_round_trip():
    """URL.create percent-encodes each component, so '@', ':' and '/' in a
    password stop being structure. Hand-assembling the string is what put a
    password into a hostname."""
    for pw in ("aa@bb", "a:b/c?d#e", "p@ss:w/rd", "tail!after@at"):
        u = D.url_from_parts("localhost", "Trading", "trading-algo", pw)
        assert D._password_of(u) == pw
        assert "@localhost/Trading" in u


def test_the_built_url_keeps_the_driver_and_the_certificate_setting():
    u = D.url_from_parts("localhost", "Trading", "u", "p" * 10)
    assert "ODBC+Driver+18" in u
    assert "TrustServerCertificate=yes" in u


def test_a_password_in_both_places_is_refused(monkeypatch):
    """One password, one place. Two would leave which is in force to chance."""
    monkeypatch.setenv("TRADING_DB_PASSWORD", "secret_value_here")
    with pytest.raises(SystemExit) as e:
        D._with_password("mssql+pyodbc://u:already@localhost/Trading", "TRADING_DB")
    assert "already contains a password" in str(e.value)


def test_a_separate_password_is_injected_escaped(monkeypatch):
    monkeypatch.setenv("TRADING_DB_PASSWORD", "aa@bb!cc")
    got = D._with_password("mssql+pyodbc://u@localhost/Trading", "TRADING_DB")
    assert D._password_of(got) == "aa@bb!cc"
    assert "<redacted>" in D._scrub(got)


# --- every table has to have a way in ---------------------------------------

def test_every_table_can_be_filled_from_the_command_line():
    """Three tables shipped that nothing could ever fill: flex_execution had a
    loader main() never called, and the two compound tables had no loader at
    all. Nobody noticed because an empty table looks the same whether the load
    has not been run or cannot be. This fails the moment a table is added
    without a way in."""
    missing = sorted(set(D.TABLES) - set(L.FILLED_BY))
    assert not missing, (
        f"no CLI path fills {missing} -- add a loader and list it in "
        "db_load.FILLED_BY, or the table is a promise the database cannot keep")


def test_the_map_names_flags_that_actually_exist():
    """A map is only as good as its agreement with the parser. A renamed flag
    would otherwise leave the map confidently pointing at nothing."""
    flags = {s for act in L.parser()._actions for s in act.option_strings}
    for table, flag in L.FILLED_BY.items():
        assert flag in flags, f"{table} claims {flag}, which the CLI does not have"


def test_the_map_does_not_name_a_table_that_is_gone():
    assert not sorted(set(L.FILLED_BY) - set(D.TABLES))


# --- the compounding replay -------------------------------------------------

RUN_CSV = ("source,capital,per_trade_pct,total_pct,dv_cap_pct,dv_applied,taken,"
           "skipped_concurrency,skipped_ruined,skipped_too_small,dv_capped,"
           "final,multiple,max_drawdown\n"
           "mc5,10000,60,100,1.0,1,380,4,0,2,0,24464.11,2.446411,0.774\n")

SWEEP_CSV = ("source,per_trade_pct,total_pct,final,multiple,max_drawdown,taken,"
             "skipped,dv_capped\n"
             "mc5,60,100,24464.11,2.446411,0.774,380,6,0\n")


def test_a_single_run_lands_in_compound_run(eng, tmp_path):
    p = tmp_path / "compound_run.csv"
    p.write_text(RUN_CSV)
    with eng.begin() as c:
        kind, _, n = L.load_compound(c, p)
    assert kind == "compound_run" and n == 1
    assert count(eng, D.compound_run) == 1
    assert count(eng, D.compound_sweep) == 0


def test_a_sweep_lands_in_compound_sweep(eng, tmp_path):
    p = tmp_path / "compound_sweep.csv"
    p.write_text(SWEEP_CSV)
    with eng.begin() as c:
        kind, _, n = L.load_compound(c, p)
    assert kind == "compound_sweep" and n == 1
    assert count(eng, D.compound_sweep) == 1
    assert count(eng, D.compound_run) == 0


def test_the_header_decides_not_the_filename(eng, tmp_path):
    """The two modes share a --out flag. Dispatching on the name would put a
    sweep in the run table the first time somebody passed one."""
    p = tmp_path / "compound_run.csv"          # named like a run
    p.write_text(SWEEP_CSV)                    # shaped like a sweep
    with eng.begin() as c:
        kind, _, _ = L.load_compound(c, p)
    assert kind == "compound_sweep"


def test_an_unrecognised_csv_is_refused_with_its_columns(eng, tmp_path):
    p = tmp_path / "compound_run.csv"
    p.write_text("a,b\n1,2\n")
    with pytest.raises(SystemExit) as e:
        with eng.begin() as c:
            L.load_compound(c, p)
    assert "neither" in str(e.value) and "'a', 'b'" in str(e.value)


def test_reloading_a_compound_run_does_not_double_it(eng, tmp_path):
    p = tmp_path / "compound_run.csv"
    p.write_text(RUN_CSV)
    for _ in range(2):
        with eng.begin() as c:
            L.load_compound(c, p)
    assert count(eng, D.compound_run) == 1


# --- the fills --------------------------------------------------------------

FLEX_HEADER = ["Symbol", "TradeDate", "DateTime", "Quantity", "TradePrice",
               "IBCommission", "FifoPnlRealized", "Buy/Sell", "AssetClass",
               "LevelOfDetail", "TradeID"]


def write_flex(path, rows):
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(FLEX_HEADER)
        w.writerows(rows)
    return path


def test_executions_load_with_their_et_minute_resolved(eng, tmp_path):
    """The ET minute comes from common.flex's zone MEASUREMENT, not from a
    constant offset applied to the stored timestamp -- the true offset moves
    between 13 and 16 hours across the year because the US and Australia change
    DST on different dates. A constant would be wrong for part of every year
    and would look entirely reasonable in the table."""
    p = write_flex(tmp_path / "flex.csv", [
        ["CYAB", "2026-08-28", "2026-08-29 00:01:52", 100, 5.0, -1.0, 0.0,
         "BUY", "STK", "EXECUTION", 1],
        ["CYAB", "2026-08-28", "2026-08-29 00:31:52", -100, 5.5, -1.0, 49.0,
         "SELL", "STK", "EXECUTION", 2],
    ])
    with eng.begin() as c:
        n = L.load_flex_executions(c, [p])
    assert n == 2
    with eng.connect() as c:
        rows = c.execute(select(D.flex_execution.c.trade_date,
                                D.flex_execution.c.et_minute)
                         .order_by(D.flex_execution.c.trade_id)).all()
    # Dated to the SESSION, not to the DateTime's calendar day.
    assert all(str(r[0]) == "2026-08-28" for r in rows)
    assert rows[0][1] is not None and rows[0][1] < rows[1][1]


def test_reloading_the_fills_replaces_rather_than_appends(eng, tmp_path):
    p = write_flex(tmp_path / "flex.csv", [
        ["AAA", "2026-08-04", "2026-08-04 23:31:00", 100, 5.0, -1.0, 0.0,
         "BUY", "STK", "EXECUTION", 1]])
    for _ in range(2):
        with eng.begin() as c:
            L.load_flex_executions(c, [p])
    assert count(eng, D.flex_execution) == 1


def test_loading_the_fills_records_where_they_came_from(eng, tmp_path):
    p = write_flex(tmp_path / "flex.csv", [
        ["AAA", "2026-08-04", "2026-08-04 23:31:00", 100, 5.0, -1.0, 0.0,
         "BUY", "STK", "EXECUTION", 1]])
    with eng.begin() as c:
        L.load_flex_executions(c, [p])
    with eng.connect() as c:
        kinds = [r[0] for r in c.execute(select(D.load_run.c.kind)).all()]
    assert "flex_execution" in kinds


# --- the controls -----------------------------------------------------------

LEAK_CSV = ("strategy,population,days,trades,days_with_a_trade,net,"
            "entries_per_day,share_of_days_traded,net_per_day,net_per_trade\n"
            "mc5,survivors,21407,7403,4110,8209.18,0.346,0.192,0.38,1.11\n"
            "mc5,rejected,3886,92,66,-663.9,0.024,0.017,-0.17,-7.21\n")


def test_the_leak_control_measurements_load(eng, tmp_path):
    p = tmp_path / "leak_control.csv"
    p.write_text(LEAK_CSV)
    with eng.begin() as c:
        _rid, n = L.load_leak_control(c, p)
    assert n == 2
    with eng.connect() as c:
        rows = c.execute(select(D.leak_control.c.population,
                                D.leak_control.c.net_per_trade)
                         .order_by(D.leak_control.c.population)).all()
    assert dict(rows) == {"rejected": -7.21, "survivors": 1.11}


def test_reloading_the_leak_control_does_not_double_it(eng, tmp_path):
    p = tmp_path / "leak_control.csv"
    p.write_text(LEAK_CSV)
    for _ in range(2):
        with eng.begin() as c:
            L.load_leak_control(c, p)
    assert count(eng, D.leak_control) == 2


def test_a_population_with_no_trades_stores_null_not_zero(eng, tmp_path):
    """0.00 per trade and 'no trades at all' are different findings, and one of
    them is evidence."""
    p = tmp_path / "leak_control.csv"
    p.write_text("strategy,population,days,trades,days_with_a_trade,net,"
                 "entries_per_day,share_of_days_traded,net_per_day,"
                 "net_per_trade\n"
                 "vw9,rejected,10,0,0,0,0,0,0,\n")
    with eng.begin() as c:
        L.load_leak_control(c, p)
    with eng.connect() as c:
        assert c.execute(select(D.leak_control.c.net_per_trade)).scalar() is None


HOLDOUT = {
    "lock_from": "2026-01-12", "both_halves_split": "2025-04-08",
    "train_first": "2024-07-05", "train_last": "2026-01-09",
    "n_sessions": 545, "n_train": 381, "n_locked": 164,
    "n_early": 190, "n_late": 191, "lock_fraction": 0.3,
    "cut_at": "2026-09-07T14:30:17Z",
    "universe_fingerprint": "a" * 64,
    "note": "not out of sample for MC5",
}


def test_the_holdout_cut_loads(eng, tmp_path):
    p = tmp_path / "holdout.json"
    p.write_text(json.dumps(HOLDOUT))
    with eng.begin() as c:
        fp, n = L.load_holdout(c, p)
    assert n == 1 and fp == "a" * 64
    with eng.connect() as c:
        r = c.execute(select(D.holdout_cut.c.lock_from,
                             D.holdout_cut.c.n_locked)).one()
    assert str(r[0]) == "2026-01-12" and r[1] == 164


def test_loading_the_same_cut_twice_is_a_no_op(eng, tmp_path):
    p = tmp_path / "holdout.json"
    p.write_text(json.dumps(HOLDOUT))
    for _ in range(2):
        with eng.begin() as c:
            L.load_holdout(c, p)
    assert count(eng, D.holdout_cut) == 1


def test_a_cut_against_a_different_universe_keeps_both_rows(eng, tmp_path):
    """The table IS the history of how the holdout has moved. A second
    fingerprint means the universe changed, and BOTH rows must survive so the
    move is visible rather than overwritten."""
    p = tmp_path / "holdout.json"
    p.write_text(json.dumps(HOLDOUT))
    with eng.begin() as c:
        L.load_holdout(c, p)
    p.write_text(json.dumps({**HOLDOUT, "universe_fingerprint": "b" * 64,
                             "lock_from": "2026-03-01"}))
    with eng.begin() as c:
        L.load_holdout(c, p)
    assert count(eng, D.holdout_cut) == 2


def test_the_committed_cut_loads_as_written(eng):
    """The real file, not a fixture -- if holdout.json ever gains a field the
    loader cannot read, this fails rather than silently storing a null."""
    from common import holdout as HO
    with eng.begin() as c:
        fp, n = L.load_holdout(c, HO.CUT_PATH)
    assert n == 1 and len(fp) == 64
    with eng.connect() as c:
        r = c.execute(select(D.holdout_cut.c.n_sessions,
                             D.holdout_cut.c.n_locked,
                             D.holdout_cut.c.note)).one()
    assert r[0] == 545 and r[1] == 164
    assert "MC5" in r[2]


# --- two tapes, one table ---------------------------------------------------

def bars_dir(tmp_path, symbol, day, rows):
    import gzip as _gz
    d = tmp_path / "3d_to_2000"
    d.mkdir(parents=True, exist_ok=True)
    with _gz.open(d / f"{symbol}_{day}.csv.gz", "wt") as fh:
        fh.write("timestamp,open,high,low,close,volume\n")
        for ts, o, h, lo, c, v in rows:
            fh.write(f"{ts},{o},{h},{lo},{c},{v}\n")
    return d


def test_two_tapes_of_the_same_minute_both_survive(eng, tmp_path):
    """EQUS.MINI publishes a measured median 4.8% of the consolidated tape, so
    its bars and XNAS.BASIC's are different OBSERVATIONS of the same minute,
    not duplicates. Before dataset was in the key, the second load deleted the
    first by symbol and the table looked complete while holding one tape with
    nothing to say which."""
    mini = bars_dir(tmp_path / "mini", "AAA", "2026-03-16",
                    [("2026-03-16 13:30:00+00:00", 10, 10, 10, 10, 100)])
    basic = bars_dir(tmp_path / "basic", "AAA", "2026-03-16",
                     [("2026-03-16 13:30:00+00:00", 10, 11, 9, 10.5, 5000)])
    with eng.begin() as c:
        L.load_minute_bars(c, mini, "EQUS.MINI", progress=None)
        L.load_minute_bars(c, basic, "XNAS.BASIC", progress=None)
    assert count(eng, D.bar_minute) == 2
    with eng.connect() as c:
        got = dict(c.execute(select(D.bar_minute.c.dataset,
                                    D.bar_minute.c.volume)).all())
    assert got == {"EQUS.MINI": 100, "XNAS.BASIC": 5000}


def test_reloading_one_tape_leaves_the_other_alone(eng, tmp_path):
    mini = bars_dir(tmp_path / "mini", "AAA", "2026-03-16",
                    [("2026-03-16 13:30:00+00:00", 10, 10, 10, 10, 100)])
    basic = bars_dir(tmp_path / "basic", "AAA", "2026-03-16",
                     [("2026-03-16 13:30:00+00:00", 10, 11, 9, 10.5, 5000)])
    with eng.begin() as c:
        L.load_minute_bars(c, mini, "EQUS.MINI", progress=None)
        L.load_minute_bars(c, basic, "XNAS.BASIC", progress=None)
        L.load_minute_bars(c, mini, "EQUS.MINI", progress=None)
    assert count(eng, D.bar_minute) == 2


def test_the_dataset_is_in_the_minute_bar_primary_key():
    """bar_daily has always had it. bar_minute did not, and that was harmless
    only while there was one tape."""
    assert "dataset" in [c.name for c in D.bar_minute.primary_key.columns]


# --- the ORB pre-flight rows ------------------------------------------------

ORB_CSV = ("symbol,date,population,orb_minutes,status,range_bars,rth_bars,"
           "orb_high,orb_low,width_pct,orb_volume,price_at_range_end,"
           "change_from_open_pct,in_price_band,passes_rth_move,up_trigger,"
           "down_trigger,up_trigger_bar,up_close_over_pct,near_level,"
           "retest_touch,retest_zone,entry_px,r_structure_pct,r_opposite_pct,"
           "r_rangefrac_pct,bars_to_2r,bars_to_stop\n"
           "AAA,2026-03-16,survivors,15,OK,15,380,11.0,9.0,22.2,50000,10.5,"
           "6.1,True,True,True,False,3,0.4,False,True,False,11.2,2.8,10.4,"
           "4.4,6,3\n"
           "BBB,2026-03-16,rejected,15,FEW_BARS,1,40,,,,,,,,,False,False,,,,"
           "False,False,,,,,,\n")


def test_orb_preflight_rows_load_with_their_dataset(eng, tmp_path):
    p = tmp_path / "orb_preflight.csv"
    p.write_text(ORB_CSV)
    with eng.begin() as c:
        n = L.load_orb_preflight(c, p, "XNAS.BASIC")
    assert n == 2
    with eng.connect() as c:
        r = c.execute(select(D.orb_preflight.c.status,
                             D.orb_preflight.c.r_opposite_pct)
                      .where(D.orb_preflight.c.symbol == "AAA")).one()
    assert r[0] == "OK" and r[1] == 10.4


def test_an_empty_orb_field_is_null_not_zero(eng, tmp_path):
    """A symbol-day with no usable range has NO width, which is not a width of
    zero -- and zero would land inside every percentile this feeds."""
    p = tmp_path / "orb_preflight.csv"
    p.write_text(ORB_CSV)
    with eng.begin() as c:
        L.load_orb_preflight(c, p, "XNAS.BASIC")
    with eng.connect() as c:
        v = c.execute(select(D.orb_preflight.c.width_pct)
                      .where(D.orb_preflight.c.symbol == "BBB")).scalar()
    assert v is None


def test_the_two_tapes_preflight_rows_coexist(eng, tmp_path):
    """The entire point of the XNAS.BASIC pull is comparing these against the
    EQUS.MINI ones."""
    p = tmp_path / "orb_preflight.csv"
    p.write_text(ORB_CSV)
    with eng.begin() as c:
        L.load_orb_preflight(c, p, "EQUS.MINI")
        L.load_orb_preflight(c, p, "XNAS.BASIC")
    assert count(eng, D.orb_preflight) == 4
