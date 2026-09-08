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

def _password_of(url: str) -> str:
    """The password in a URL, or "" -- best effort, for the scrubber.

    Deliberately tolerant: a URL that will not parse is exactly the one whose
    password is about to appear somewhere it should not.
    """
    try:
        from sqlalchemy.engine import make_url
        return make_url(url).password or ""
    except Exception:  # noqa: BLE001
        m = re.search(r"://[^:/]*:([^@]*)@", url)
        return m.group(1) if m else ""


SYM = 24            # generous: the longest US ticker seen in the archive is 8
KEY = 128


# Secrets this process has resolved, so they can be removed from any text by
# VALUE rather than by pattern. See _scrub.
_KNOWN: set[str] = set()


MIN_SECRET = 6      # shorter than this and redaction starts eating prose


def remember_secret(v: str) -> None:
    """Remember a secret AND the pieces of it that can escape on their own.

    A password containing '@' is split by the URL parser, and what reaches the
    error text is the TAIL -- "could not connect to <tail>@localhost". Only the
    fragment leaks, so remembering only the whole value scrubs nothing. That is
    not hypothetical: it is what happened, and the tail reached a chat.

    Fragments are registered on the characters a URL splits at, and only when
    they are long enough that redacting them cannot swallow ordinary words.
    """
    if not v or len(v) < MIN_SECRET:
        return
    _KNOWN.add(v)
    for sep in "@:/?#":
        for part in v.split(sep):
            if len(part) >= MIN_SECRET and part != v:
                _KNOWN.add(part)


def _scrub(text) -> str:
    """Remove a password from text, by value first and pattern second.

    THE PATTERN ALONE WAS NOT ENOUGH, and the way it failed is worth keeping.
    It matched ":<something>@" on the assumption that a URL is well formed. A
    password containing an '@' makes it malformed: the parser splits at the
    first '@', so the tail of the password becomes the HOSTNAME, and the driver
    then helpfully reports "could not connect to <tail-of-password>@localhost".
    The password was no longer in a password-shaped position, so the regex left
    it alone and it went into a terminal and from there into a chat transcript.

    A scrubber that only works on well-formed input is no scrubber: text
    reaching it is by definition an error path, which is exactly where the
    input is malformed. So every resolved secret is remembered and stripped by
    exact value, and the pattern is kept only as a second line for secrets this
    process never saw.
    """
    out = str(text)
    for v in sorted(_KNOWN, key=len, reverse=True):
        out = out.replace(v, "<redacted>")
    return re.sub(r"(?i)(:)([^:@/\s]{3,})(@)", r"\1<redacted>\3", out)


def url_from_parts(host: str, database: str, user: str, password: str,
                   driver: str = "ODBC Driver 18 for SQL Server",
                   trust_cert: bool = True) -> str:
    """Build a URL with the password ESCAPED, rather than pasted into a string.

    URL.create percent-encodes each component, so '@', ':', '/' and '?' in a
    password stop being structure. Hand-assembling the string is what put a
    password in a hostname; this is the same job done by something that knows
    the grammar.
    """
    from sqlalchemy.engine import URL

    remember_secret(password)
    q = {"driver": driver}
    if trust_cert:
        q["TrustServerCertificate"] = "yes"
    return URL.create("mssql+pyodbc", username=user, password=password,
                      host=host, database=database, query=q).render_as_string(
                          hide_password=False)


def _with_password(url: str, var: str) -> str:
    """Inject a separately-stored password into a URL, escaped.

    A password belongs in its own field, not inside a URL that something has
    to parse. When <VAR>_PASSWORD is set, the URL is expected to carry no
    password at all and this puts it in through the URL builder, which encodes
    it. That way a '@' or a ':' in a password is data rather than syntax.
    """
    pw = os.environ.get(f"{var}_PASSWORD", "").strip()
    if not pw:
        return url
    from common import secrets_util as S
    from sqlalchemy.engine import make_url
    if pw.startswith("op://"):
        pw = S.resolve(f"{var}_PASSWORD", "SQL Server password") or pw
    remember_secret(pw)
    u = make_url(url)
    if u.password:
        sys.exit(f"{var} already contains a password and {var}_PASSWORD is "
                 "also set. Use one or the other, so there is no question "
                 "which one is in force.")
    return u.set(password=pw).render_as_string(hide_password=False)


def database_url(explicit: str | None = None) -> str:
    if explicit:
        return _with_password(explicit, "TRADING_DB")
    from common import secrets_util as S

    v = S.resolve("TRADING_DB_URL", "SQL Server connection URL")
    if v:
        remember_secret(_password_of(v))
        return _with_password(v, "TRADING_DB")
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
    # DATASET IS IN THE KEY, added 2026-09-08, for the reason bar_daily has
    # always had it: the same symbol-minute exists on more than one tape and
    # the two do not agree. EQUS.MINI publishes a MEASURED MEDIAN 4.8% of the
    # consolidated tape (var/reports/capture_ratio.txt), so its bars and
    # XNAS.BASIC's are different observations of the same minute, not
    # duplicates of it.
    #
    # Without this column load_minute_bars -- which deletes by symbol and
    # re-inserts -- would have silently REPLACED one tape's bars with the
    # other's, leaving a table that looks complete and cannot say which tape
    # produced it. Comparing results across the two tapes is the entire point
    # of holding both.
    Column("dataset", String(24), primary_key=True),
    # (dataset, symbol, ts) and NOT (dataset, symbol, cache_date, ts): see the
    # module docstring. The cache stores overlapping three-session windows, so
    # file-keyed rows would trebly count every bar.
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

orb_preflight = Table(
    "orb_preflight", META,
    # One row per symbol-day per ORB_MINUTES. The report renders distributions;
    # these are the rows behind them, so a later question ("what does the R
    # distribution look like above $5?") is a query rather than a re-run over
    # 25,769 symbol-days.
    #
    # dataset is in the key for the same reason as bar_minute's: the whole
    # purpose of the 2026-09-08 XNAS.BASIC pull is to compare these
    # measurements against the EQUS.MINI ones.
    Column("dataset", String(24), primary_key=True),
    Column("symbol", String(SYM), primary_key=True),
    Column("session_date", Date, primary_key=True),
    Column("orb_minutes", Integer, primary_key=True),
    Column("population", String(12)),
    Column("status", String(16)),
    Column("range_bars", Integer), Column("rth_bars", Integer),
    Column("orb_high", Float), Column("orb_low", Float),
    Column("width_pct", Float), Column("orb_volume", Float),
    Column("price_at_range_end", Float),
    Column("change_from_open_pct", Float),
    Column("in_price_band", Boolean), Column("passes_rth_move", Boolean),
    Column("up_trigger", Boolean), Column("down_trigger", Boolean),
    Column("up_trigger_bar", Integer), Column("up_close_over_pct", Float),
    Column("near_level", Boolean),
    Column("retest_touch", Boolean), Column("retest_zone", Boolean),
    Column("entry_px", Float),
    Column("r_structure_pct", Float), Column("r_opposite_pct", Float),
    Column("r_rangefrac_pct", Float),
    Column("bars_to_2r", Integer), Column("bars_to_stop", Integer),
)


# --- controls --------------------------------------------------------------

leak_control = Table(
    "leak_control", META,
    # Two rows per strategy per run: the survivor population and the rejected
    # one. Rows rather than columns, so a third population -- a locked holdout,
    # say -- needs no schema change.
    Column("run_id", String(KEY), primary_key=True),
    Column("strategy", String(24), primary_key=True),
    Column("population", String(12), primary_key=True),
    Column("run_at", DateTime),
    Column("days", Integer), Column("trades", Integer),
    Column("days_with_a_trade", Integer),
    Column("net", Float),
    Column("entries_per_day", Float),
    Column("share_of_days_traded", Float),
    Column("net_per_day", Float),
    # The cut the entry-rate test does not make: is the population different in
    # KIND. Nullable, because a population with no trades has no per-trade
    # figure and 0.0 would be a lie.
    Column("net_per_trade", Float),
)

holdout_cut = Table(
    "holdout_cut", META,
    # KEYED BY THE UNIVERSE, not by a run id. Re-cutting against the same
    # universe replaces the row; cutting against a genuinely different one adds
    # a second. So the table IS the history of how the holdout has moved, which
    # is the first question anyone should ask before believing an out-of-sample
    # figure. holdout.json is the same record in the git tree; this is the copy
    # that can be joined against a backtest_run.
    Column("universe_fingerprint", String(64), primary_key=True),
    Column("cut_at", DateTime),
    Column("lock_from", Date),
    Column("both_halves_split", Date),
    Column("train_first", Date), Column("train_last", Date),
    Column("lock_fraction", Float),
    Column("n_sessions", Integer), Column("n_train", Integer),
    Column("n_locked", Integer),
    Column("n_early", Integer), Column("n_late", Integer),
    Column("note", String(512)),
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


# Tables holding nothing a file cannot reproduce. Dropping one costs the time to
# re-run its loader and nothing else, which is what makes --rebuild-table safe
# for these and unsafe for anything else. An explicit allowlist, not inferred:
# "derived" is a fact about where the rows came from, and only someone who knows
# the pipeline can assert it.
DERIVED_TABLES = {
    "bar_minute": "python -m common.db_load --minute-bars <CACHE_ROOT> <DATASET>",
    "bar_daily": "python -m common.db_load --daily-bars <ARCHIVE> <DATASET>",
    "orb_preflight": "python -m common.db_load --orb-preflight <CSV> <DATASET>",
    "day_dollar_volume": "python -m common.db_load --dollar-volume <CSV>",
}


def schema_drift(eng) -> dict[str, list[str]]:
    """Columns the model has and the live database does not, per table.

    WHY THIS EXISTS. `META.create_all` is create-if-not-exists. It never ALTERS
    an existing table, so a column added to a model after that table was made is
    simply absent, and nothing says so: `--create` prints "schema ensured",
    `--check` prints healthy row counts, and the gap surfaces only when a query
    naming the column fails.

    Which is how it surfaced on 2026-09-08. `dataset` went into bar_minute's
    primary key so two tapes could coexist. The live table predated that, and a
    27,777-file load died on its first DELETE with "Invalid column name
    'dataset'" -- after the schema check had reported everything fine.

    Only ADDITIONS are reported. A column the database has and the model does
    not is usually an older shape rather than a fault, and this tool has no
    business proposing to drop one.
    """
    from sqlalchemy import inspect as _inspect

    insp = _inspect(eng)
    live = set(insp.get_table_names())
    out: dict[str, list[str]] = {}
    for t in META.sorted_tables:
        if t.name not in live:
            continue           # a missing table is create_all's job, not drift
        have = {c["name"] for c in insp.get_columns(t.name)}
        missing = [c.name for c in t.columns if c.name not in have]
        if missing:
            out[t.name] = missing
    return out


def rebuild_table(eng, name: str) -> int:
    """Drop and recreate ONE derived table. Returns the row count discarded.

    The alternative is an ALTER path per change: add the column, backfill it,
    drop and recreate the primary key. For a table whose every row is
    reproducible from files on disk that is more machinery to get wrong than
    the work it saves -- and the backfill would have to GUESS which tape the
    existing rows came from, inventing provenance, which is the exact failure
    the dataset column was added to prevent.

    So: drop, recreate, reload from the caches. Refused for anything outside
    DERIVED_TABLES, where the rows may be the only copy.
    """
    if name not in DERIVED_TABLES:
        raise ValueError(
            f"{name} is not a derived table, so its rows may be the only copy "
            f"of something. Rebuildable: {', '.join(sorted(DERIVED_TABLES))}")
    table = META.tables[name]
    with eng.begin() as c:
        try:
            n = c.execute(select(func.count()).select_from(table)).scalar_one()
        except Exception:  # noqa: BLE001 -- absent is a 0, not an error
            n = 0
        table.drop(c, checkfirst=True)
        table.create(c)
    return n


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


def ensure_database(url: str) -> str:
    """Create the target database if it is not there, then return its URL.

    This tool otherwise creates TABLES, and a missing DATABASE presents as a
    login failure -- which sends the reader off to check permissions and
    drivers for a problem that is neither. Doing it here saves needing SSMS or
    sqlcmd just to type one statement.

    CREATE DATABASE cannot run inside a transaction, hence AUTOCOMMIT, and the
    name is validated rather than interpolated: it arrives from a URL, and a
    database name is not a place to find out what f-strings will do.
    """
    import re as _re
    from sqlalchemy.engine import make_url

    u = make_url(url)
    name = u.database or "Trading"
    if not _re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,120}", name):
        sys.exit(f"refusing to create a database named {name!r}: letters, "
                 "digits and underscores only")
    master = create_engine(str(u.set(database="master")), future=True)
    with master.connect().execution_options(
            isolation_level="AUTOCOMMIT") as c:
        existed = c.exec_driver_sql(
            f"SELECT DB_ID('{name}')").scalar_one() is not None
        if not existed:
            c.exec_driver_sql(f"CREATE DATABASE [{name}]")
    print(f"database {name}: {'already present' if existed else 'CREATED'}")
    return url


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Trading database: schema and status")
    ap.add_argument("--url", help="SQLAlchemy URL (default: see module docstring)")
    ap.add_argument("--create-database", action="store_true",
                    help="create the database itself first (connects to "
                         "master). Without it, a missing database presents as "
                         "a login failure.")
    ap.add_argument("--create", action="store_true", help="create missing tables")
    ap.add_argument("--check", action="store_true", help="connect and report")
    ap.add_argument("--rebuild-table", metavar="NAME",
                    help="drop and recreate one DERIVED table, discarding its "
                         "rows, then reload it with its own loader. This is how "
                         "a column added to a model reaches a table that "
                         "already exists: create_all never alters one.")
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
    if a.create_database:
        try:
            ensure_database(url)
        except Exception as e:  # noqa: BLE001
            print(f"\nCOULD NOT CREATE THE DATABASE: {_scrub(e)}")
            return 1
    try:
        eng = engine(url)
        with eng.connect() as c:
            # Dialect-aware so this tool can be exercised against SQLite in a
            # test. It could not be: `SELECT @@VERSION` is T-SQL, so every path
            # below it -- including the schema-drift report -- was unreachable
            # without a live SQL Server, which is precisely the report that was
            # missing when a 27,777-file load died on a column that was not
            # there.
            ver = (c.exec_driver_sql("SELECT @@VERSION").scalar_one()
                   if eng.dialect.name == "mssql"
                   else f"{eng.dialect.name} (not SQL Server)")
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

    if a.rebuild_table:
        try:
            n = rebuild_table(eng, a.rebuild_table)
        except ValueError as e:
            print(f"\nREFUSED: {e}")
            return 1
        print(f"\n{a.rebuild_table}: dropped and recreated, "
              f"{n:,} row(s) discarded")
        print(f"  reload with:  {DERIVED_TABLES[a.rebuild_table]}")

    if a.create:
        made = create_all(eng)
        print(f"schema ensured: {len(made)} table(s)")

    # ALWAYS after --create, never before: create_all makes missing tables, and
    # a table that did not exist a moment ago has no drift to report.
    if a.check or a.create or a.rebuild_table:
        drift = schema_drift(eng)
        if drift:
            print("\nSCHEMA DRIFT -- the model has columns these tables do not:")
            for t, cols in sorted(drift.items()):
                print(f"  {t:<22} missing: {', '.join(cols)}")
            print("\n  create_all() only CREATES tables; it never alters one, so"
                  " a column added")
            print("  to a model after its table was made is silently absent "
                  "until a query")
            print("  naming it fails mid-load.")
            fixable = sorted(t for t in drift if t in DERIVED_TABLES)
            if fixable:
                print("\n  These hold only what a file can reproduce, so they "
                      "can be rebuilt:")
                for t in fixable:
                    print(f"    python -m common.db --rebuild-table {t}")
                    print(f"      then:  {DERIVED_TABLES[t]}")
            other = sorted(t for t in drift if t not in DERIVED_TABLES)
            if other:
                print("\n  NOT auto-rebuildable, because their rows may be the "
                      "only copy:")
                print(f"    {', '.join(other)}")
                print("    Migrate these by hand, or reload them from source "
                      "after a rebuild.")
        else:
            print("\nschema matches the model")

    if a.check or a.create:
        print()
        for name, n in counts(eng).items():
            print(f"  {name:<22} {'-' if n is None else format(n, ',')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
