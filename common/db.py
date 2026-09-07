#!/usr/bin/env python3
"""The relational store: connection, schema, and nothing else.

    python -m common.db --create              # build the schema
    python -m common.db --check               # what is connected, what is in it

WHAT GOES IN HERE, AND WHAT DOES NOT
-------------------------------------
The Databento archive stays on disk as .dbn.zst and is NOT loaded. That is not
a size limit talking -- Standard Developer has none worth counting -- it is
that a tick archive is columnar, immutable, and read in bulk slices, which is
exactly what the files already do well. As relational rows the quote and
statistics schemas are 200-300 GB, and every read of them would be slower than
it is today.

What lives here is everything DERIVED: the daily bars the screen runs on, the
minute bars the backtests read, the screen's own output, Ben's executions, and
every backtest, comparison and simulation result. Roughly 2 GB plus the minute
bars.

MINUTE BARS ARE KEYED (symbol, ts), NOT BY CACHE FILE
------------------------------------------------------
bar_cache_db holds WINDOWS: SYMBOL_DATE.csv.gz is three sessions ending 20:00
on DATE, so consecutive dates for one symbol repeat two sessions each. Loading
them file-by-file would store every bar about three times and make any
aggregate query silently wrong. They are deduplicated on (symbol, ts_utc)
instead, which is both correct and about a third of the rows.

EVERY LOAD IS IDEMPOTENT
-------------------------
A loader that appends turns "I re-ran that" into duplicated rows and doubled
sums, and nothing about the result looks wrong. So each artefact carries a
run_id derived from its source file and that file's modification time, and
loading deletes the run before inserting it. Re-running a load is a no-op;
loading a changed file replaces its rows.

NO PASSWORD EVER GOES IN A FILE OR A FLAG
------------------------------------------
The default connection is Windows authentication, which carries no secret at
all. If a URL is configured it resolves through common.secrets_util, so an
op:// reference works the same way it does for every other credential here, and
the URL is scrubbed before it is printed.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from sqlalchemy import (BigInteger, Boolean, Column, Date, DateTime, Float,
                        Integer, MetaData, String, Table, create_engine,
                        func, select)

# Resolution order, first hit wins -- the same shape as .databento_archive,
# for the same reason: an environment variable is session-scoped in PowerShell
# and would have to be re-set in every terminal.
#
#   1. --url on the command line
#   2. the TRADING_DB_URL environment variable (may be an op:// reference)
#   3. .database_url in the repo root, holding one URL
#   4. the local default below
URL_CONFIG = Path(".database_url")

# Windows auth against the default local instance. No password, and nothing
# here is a secret. ODBC Driver 18 defaults to requiring encryption and then
# rejecting the self-signed certificate a local install ships with, which
# presents as a login failure rather than a certificate problem -- hence
# TrustServerCertificate, which is safe for a loopback connection and is the
# single most common reason a first connection fails.
DEFAULT_URL = (
    "mssql+pyodbc://@localhost/Trading"
    "?driver=ODBC+Driver+18+for+SQL+Server"
    "&trusted_connection=yes&TrustServerCertificate=yes"
)

SYM = 24            # generous: the longest US ticker seen in the archive is 8
KEY = 128


def _scrub(text) -> str:
    """Never let a password reach a log, however it got into a URL."""
    return re.sub(r"(?i)(:)([^:@/]{3,})(@)", r"\1<redacted>\3", str(text))


def database_url(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    from common import secrets_util as S

    v = S.resolve("TRADING_DB_URL", "SQL Server connection URL")
    if v:
        return v
    try:
        if URL_CONFIG.exists():
            t = URL_CONFIG.read_text(encoding="utf-8").strip()
            if t:
                return t
    except OSError:
        pass
    return DEFAULT_URL


def engine(url: str | None = None, echo: bool = False):
    """A connected engine, with the fast insert path enabled where it exists.

    fast_executemany turns pyodbc's row-at-a-time parameter binding into one
    batched call. On the minute-bar load that is the difference between a job
    measured in hours and one measured in minutes; it is a no-op on any other
    driver, so it is set by dialect rather than by flag.
    """
    u = database_url(url)
    kw = {"echo": echo, "future": True}
    if u.startswith("mssql+pyodbc"):
        kw["fast_executemany"] = True
    return create_engine(u, **kw)


META = MetaData()

# --- market data -----------------------------------------------------------

bar_daily = Table(
    "bar_daily", META,
    Column("dataset", String(24), primary_key=True),
    Column("symbol", String(SYM), primary_key=True),
    Column("session_date", Date, primary_key=True),
    Column("open", Float), Column("high", Float), Column("low", Float),
    Column("close", Float), Column("volume", BigInteger),
    Column("dollar_volume", Float),
)

bar_minute = Table(
    "bar_minute", META,
    # (symbol, ts) and NOT (symbol, cache_date, ts): see the module docstring.
    # The cache stores overlapping three-session windows, so file-keyed rows
    # would trebly count every bar.
    Column("symbol", String(SYM), primary_key=True),
    Column("ts_utc", DateTime, primary_key=True),
    Column("open", Float), Column("high", Float), Column("low", Float),
    Column("close", Float), Column("volume", BigInteger),
)

day_dollar_volume = Table(
    "day_dollar_volume", META,
    Column("symbol", String(SYM), primary_key=True),
    Column("session_date", Date, primary_key=True),
    Column("close", Float), Column("volume", BigInteger),
    Column("dollar_volume", Float),
)

# --- the screen ------------------------------------------------------------

screen_run = Table(
    "screen_run", META,
    Column("run_id", String(KEY), primary_key=True),
    Column("run_at", DateTime), Column("dataset", String(24)),
    Column("archive", String(255)),
    Column("min_rvol", Float), Column("min_range_pct", Float),
    Column("min_avg_dollar_vol", Float), Column("max_per_day", Integer),
    Column("price_min", Float), Column("price_max", Float),
    Column("reject_seed", Integer),
    Column("n_candidates", Integer), Column("n_rejects", Integer),
)

screen_candidate = Table(
    "screen_candidate", META,
    Column("run_id", String(KEY), primary_key=True),
    Column("symbol", String(SYM), primary_key=True),
    Column("session_date", Date, primary_key=True),
    # The control sample lives in the SAME table, flagged. Two tables would
    # let the populations drift apart and would make "is this day in both?"
    # -- the one thing that invalidates the control -- a join rather than a
    # constraint.
    Column("is_reject", Boolean),
)

# --- real trades -----------------------------------------------------------

flex_execution = Table(
    "flex_execution", META,
    Column("trade_id", String(64), primary_key=True),
    Column("symbol", String(SYM)), Column("trade_date", Date),
    Column("dt_utc", DateTime), Column("et_minute", Integer),
    Column("qty", Float), Column("price", Float),
    Column("commission", Float), Column("fifo_pnl", Float),
    Column("side", String(8)), Column("time_known", Boolean),
)

flex_round_trip = Table(
    "flex_round_trip", META,
    Column("symbol", String(SYM), primary_key=True),
    Column("trade_date", Date, primary_key=True),
    Column("seq", Integer, primary_key=True),
    Column("entry_et", String(5)), Column("exit_et", String(5)),
    Column("fills", Integer), Column("shares", Float),
    Column("max_position", Integer),
    Column("avg_buy_price", Float), Column("avg_sell_price", Float),
    Column("gross_pnl", Float), Column("commission", Float),
    Column("net_pnl", Float), Column("open_at_end", Boolean),
)

# --- backtests -------------------------------------------------------------

backtest_run = Table(
    "backtest_run", META,
    Column("run_id", String(KEY), primary_key=True),
    Column("run_at", DateTime), Column("strategy", String(24)),
    Column("universe", String(32)),      # traded | screened | ...
    Column("pairs", String(512)), Column("cache_dir", String(255)),
    Column("size_from", String(255)), Column("offline", Boolean),
    Column("exit_mode", String(24)),
    Column("n_trades", Integer), Column("n_pairs", Integer),
)

backtest_trade = Table(
    "backtest_trade", META,
    Column("run_id", String(KEY), primary_key=True),
    Column("seq", Integer, primary_key=True),
    Column("symbol", String(SYM)), Column("session_date", Date),
    Column("entry_ts", DateTime), Column("exit_ts", DateTime),
    Column("entry_price", Float), Column("exit_price", Float),
    Column("qty", Integer), Column("reason", String(32)),
    Column("bars_held", Integer),
    Column("gross", Float), Column("commission", Float), Column("net", Float),
    # Strategy-specific, all nullable: MCL emits the scaling columns, VW9 the
    # setup ones, MC5 neither. One table with nulls beats three tables that
    # every query has to union.
    Column("cycles", Integer), Column("shares_traded", Integer),
    Column("adds", Integer), Column("max_qty", Integer),
    Column("timeframe", Integer), Column("setup_kind", String(32)),
    Column("trade_exit_mode", String(24)), Column("r_multiple", Float),
    Column("session_block", String(24)),
)

backtest_coverage = Table(
    "backtest_coverage", META,
    Column("run_id", String(KEY), primary_key=True),
    Column("symbol", String(SYM), primary_key=True),
    Column("session_date", Date, primary_key=True),
    # The status is the whole point of this table. Without it a symbol-day
    # with no trades is indistinguishable from one that could not be
    # evaluated, and every average over the run is quietly wrong.
    Column("status", String(24)),
    Column("bars", Integer), Column("session_bars", Integer),
    Column("trades", Integer), Column("net", Float),
)

# --- simulation ------------------------------------------------------------

compound_run = Table(
    "compound_run", META,
    Column("run_id", String(KEY), primary_key=True),
    Column("source", String(24), primary_key=True),
    Column("run_at", DateTime),
    Column("capital", Float), Column("per_trade_pct", Float),
    Column("total_pct", Float), Column("dv_cap_pct", Float),
    Column("dv_applied", Boolean),
    Column("taken", Integer), Column("skipped_concurrency", Integer),
    Column("skipped_ruined", Integer), Column("skipped_too_small", Integer),
    Column("dv_capped", Integer),
    Column("final", Float), Column("multiple", Float),
    Column("max_drawdown", Float),
)

compound_sweep = Table(
    "compound_sweep", META,
    Column("run_id", String(KEY), primary_key=True),
    Column("source", String(24), primary_key=True),
    Column("per_trade_pct", Float, primary_key=True),
    Column("total_pct", Float, primary_key=True),
    Column("final", Float), Column("multiple", Float),
    Column("max_drawdown", Float), Column("taken", Integer),
    Column("skipped", Integer), Column("dv_capped", Integer),
)

# --- provenance ------------------------------------------------------------

load_run = Table(
    "load_run", META,
    # Which file produced which rows, and when it was last modified. Without
    # this a table is just numbers: nothing says whether they came from the
    # current backtest or one from three days ago, and both look equally
    # authoritative.
    Column("run_id", String(KEY), primary_key=True),
    Column("kind", String(32)),
    Column("source_path", String(512)),
    Column("source_mtime", DateTime),
    Column("loaded_at", DateTime),
    Column("rows", Integer),
    Column("notes", String(512)),
)


TABLES = [t.name for t in META.sorted_tables]


def create_all(eng) -> list[str]:
    META.create_all(eng)
    return TABLES


def counts(eng) -> dict:
    out = {}
    with eng.connect() as c:
        for t in META.sorted_tables:
            try:
                out[t.name] = c.execute(
                    select(func.count()).select_from(t)).scalar_one()
            except Exception:  # noqa: BLE001 -- a missing table is a 0, not a crash
                out[t.name] = None
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Trading database: schema and status")
    ap.add_argument("--url", help="SQLAlchemy URL (default: see module docstring)")
    ap.add_argument("--create", action="store_true", help="create missing tables")
    ap.add_argument("--check", action="store_true", help="connect and report")
    ap.add_argument("--ddl", action="store_true",
                    help="print the T-SQL without connecting to anything")
    a = ap.parse_args(argv)

    if a.ddl:
        from sqlalchemy.dialects import mssql
        from sqlalchemy.schema import CreateTable
        for t in META.sorted_tables:
            print(str(CreateTable(t).compile(dialect=mssql.dialect())).strip() + ";\n")
        return 0

    url = database_url(a.url)
    print(f"url  {_scrub(url)}")
    try:
        eng = engine(url)
        with eng.connect() as c:
            ver = c.exec_driver_sql("SELECT @@VERSION").scalar_one()
        print(f"connected: {str(ver).splitlines()[0]}")
    except Exception as e:  # noqa: BLE001
        print(f"\nCOULD NOT CONNECT: {_scrub(e)}\n")
        print("Most first-connection failures are one of three things:")
        print("  * the instance name. A default install is 'localhost'; a named")
        print("    one is 'localhost\\\\SQLEXPRESS' (double the backslash in a")
        print("    URL, or put the URL in .database_url instead of a flag).")
        print("  * ODBC Driver 18 is not installed. It ships separately from")
        print("    the engine: search 'Microsoft ODBC Driver 18 for SQL Server'.")
        print("  * the database does not exist yet. This tool creates TABLES,")
        print("    not the database: CREATE DATABASE Trading; first.")
        return 1

    if a.create:
        made = create_all(eng)
        print(f"schema ensured: {len(made)} table(s)")
    if a.check or a.create:
        print()
        for name, n in counts(eng).items():
            print(f"  {name:<22} {'-' if n is None else format(n, ',')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
