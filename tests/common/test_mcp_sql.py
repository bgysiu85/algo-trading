#!/usr/bin/env python3
"""The read-only MCP server.

The statement guard here is a convenience, not a security boundary -- the
read-only login is the control, and these tests do not pretend otherwise. What
they pin is that the guard fails in the safe direction, that comments cannot
smuggle a second statement past it, and that it does not reject the ordinary
queries it exists alongside. A guard that cries wolf gets switched off.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, insert

from common import db as D
from common import mcp_sql as M


# --- what the guard allows --------------------------------------------------

@pytest.mark.parametrize("sql", [
    "SELECT 1",
    "select top 10 * from bar_daily",
    "SELECT * FROM backtest_trade WHERE net < 0 ORDER BY net",
    "WITH x AS (SELECT 1 AS a) SELECT * FROM x",
    "  \n SELECT 1 ;  ",
    "(SELECT 1)",
    # A column whose NAME contains a forbidden word. Substring matching would
    # reject this, and a guard that is wrong on ordinary queries is a guard
    # somebody turns off.
    "SELECT updated_at, created_at FROM load_run",
    "SELECT COUNT(*) FROM bar_minute WHERE symbol = 'AAA'",
])
def test_ordinary_reads_are_allowed(sql):
    assert M.check_select(sql)


# --- what it refuses --------------------------------------------------------

@pytest.mark.parametrize("sql", [
    "DROP TABLE bar_daily",
    "delete from bar_daily",
    "UPDATE bar_daily SET close = 0",
    "INSERT INTO bar_daily VALUES (1)",
    "TRUNCATE TABLE bar_minute",
    "ALTER TABLE bar_daily ADD x INT",
    "EXEC sp_who",
    "GRANT CONTROL ON DATABASE::Trading TO public",
    "BACKUP DATABASE Trading TO DISK = 'x'",
])
def test_writes_and_ddl_are_refused(sql):
    with pytest.raises(ValueError):
        M.check_select(sql)


def test_a_second_statement_is_refused():
    """The classic. One SELECT to get past the first check, one write after."""
    with pytest.raises(ValueError, match="one statement"):
        M.check_select("SELECT 1; DROP TABLE bar_daily")


def test_a_trailing_semicolon_is_fine():
    assert M.check_select("SELECT 1;")


def test_comments_cannot_hide_a_second_statement():
    """The rule has to be judged on what RUNS, not on what reads. Checking the
    raw text would let a line comment carry a write past a check that only
    looked at the first word."""
    with pytest.raises(ValueError):
        M.check_select("SELECT 1 -- harmless\n; DROP TABLE bar_daily")
    with pytest.raises(ValueError):
        M.check_select("SELECT 1 /* nothing to see */ ; DELETE FROM bar_daily")
    with pytest.raises(ValueError):
        M.check_select("/* SELECT */ DROP TABLE bar_daily")


def test_a_comment_only_statement_is_refused():
    with pytest.raises(ValueError, match="empty"):
        M.check_select("-- just a thought")


def test_an_empty_statement_is_refused():
    with pytest.raises(ValueError):
        M.check_select("   ")


# --- the two connection variables must not be confused ----------------------

def test_the_read_only_url_is_a_different_variable(monkeypatch):
    """Pointing the server at the loaders' read-write connection would give an
    agent exactly the rights this design exists to withhold, and a working
    server would look identical. Two names, so the mistake has to be typed."""
    import inspect
    src = inspect.getsource(M.read_only_engine)
    assert "TRADING_DB_RO_URL" in src
    assert "TRADING_DB_URL\"" not in src


def test_an_unset_read_only_url_refuses_to_fall_back(monkeypatch):
    """Falling back to the default connection would be the same failure,
    arrived at by kindness."""
    monkeypatch.setattr("common.secrets_util.resolve", lambda *a, **k: "")
    with pytest.raises(SystemExit) as e:
        M.read_only_engine()
    assert "READ-ONLY" in str(e.value)


# --- the tools, against a real engine ---------------------------------------

@pytest.fixture
def eng(tmp_path):
    e = create_engine(f"sqlite:///{tmp_path/'t.db'}", future=True)
    D.create_all(e)
    with e.begin() as c:
        c.execute(insert(D.day_dollar_volume), [
            {"symbol": "AAA", "session_date": date(2026, 3, 16), "close": 4.0,
             "volume": 1000, "dollar_volume": 4000.0}])
    return e


def tool(server, name):
    """FastMCP keeps the callable on its tool manager."""
    import asyncio
    return lambda **kw: asyncio.get_event_loop_policy().new_event_loop(
    ).run_until_complete(server.call_tool(name, kw))


def test_list_tables_reports_every_table(eng):
    srv = M.build(lambda: eng)
    out = str(tool(srv, "list_tables")())
    for t in ("bar_daily", "bar_minute", "backtest_trade", "load_run"):
        assert t in out


def test_describe_table_names_the_primary_key(eng):
    srv = M.build(lambda: eng)
    out = str(tool(srv, "describe_table")(name="bar_minute"))
    assert "ts_utc" in out and "PK" in out


def test_describe_an_unknown_table_lists_the_real_ones(eng):
    srv = M.build(lambda: eng)
    out = str(tool(srv, "describe_table")(name="nope"))
    assert "no table" in out and "bar_daily" in out


def test_read_query_returns_rows(eng):
    srv = M.build(lambda: eng)
    out = str(tool(srv, "read_query")(sql="SELECT symbol, close FROM day_dollar_volume"))
    assert "AAA" in out and "4.0" in out


def test_read_query_refuses_a_write_and_says_so(eng):
    srv = M.build(lambda: eng)
    out = str(tool(srv, "read_query")(sql="DELETE FROM day_dollar_volume"))
    assert "REFUSED" in out
    with eng.connect() as c:
        from sqlalchemy import func, select
        assert c.execute(select(func.count()).select_from(
            D.day_dollar_volume)).scalar_one() == 1


def test_a_broken_query_returns_the_error_not_a_traceback(eng):
    srv = M.build(lambda: eng)
    out = str(tool(srv, "read_query")(sql="SELECT nope FROM day_dollar_volume"))
    assert "QUERY FAILED" in out


# --- output shape -----------------------------------------------------------

def test_a_large_result_is_truncated_with_a_visible_note():
    out = M.rows_to_text(("a",), [(i,) for i in range(3)], truncated=True)
    assert "truncated at" in out


def test_no_rows_says_so_rather_than_returning_nothing():
    assert M.rows_to_text(("a",), [], False) == "(no rows)"


# --- the selftest has to be able to FAIL ------------------------------------

def test_the_selftest_fails_when_the_login_can_write(eng, monkeypatch, capsys):
    """The statement guard is mine and advisory; the login is the control. So
    the selftest asks SQL Server itself, by attempting a write with the guard
    deliberately bypassed. A selftest that could only pass would be decoration
    -- this one returns non-zero and says the guard it leaves behind will not
    save you."""
    monkeypatch.setattr(M, "read_only_engine", lambda *a, **k: eng)
    rc = M.main(["--selftest"])          # sqlite lets anyone write
    out = capsys.readouterr().out
    assert rc == 1
    assert "THE LOGIN CAN WRITE" in out
    assert "advisory" in out


def test_the_selftest_leaves_no_row_behind(eng, monkeypatch):
    """It writes to prove it can. It must not then leave that proof in a table
    somebody later counts."""
    from sqlalchemy import func, select
    monkeypatch.setattr(M, "read_only_engine", lambda *a, **k: eng)
    M.main(["--selftest"])
    with eng.connect() as c:
        assert c.execute(select(func.count()).select_from(
            D.load_run)).scalar_one() == 0
