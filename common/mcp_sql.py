#!/usr/bin/env python3
"""A read-only MCP server over the trading database.

    python -m common.mcp_sql                    # stdio, for Claude Desktop
    python -m common.mcp_sql --selftest         # connect, list tables, exit

WHY THIS IS HERE AND NOT AN INSTALL
------------------------------------
There are half a dozen community mssql MCP servers and any of them would work.
Each is also unreviewed code that receives a live connection to the database
holding every trade Ben has made. This is roughly 150 lines against the
official MCP SDK, it lives in the repo, it is covered by the same test suite as
everything else, and it exposes exactly three tools instead of twenty.

TWO GUARDS, AND ONLY ONE OF THEM IS REAL
-----------------------------------------
1. THE LOGIN. The connection this server uses should be a SQL login with
   db_datareader on one database and nothing else. That is the control. It is
   enforced by SQL Server, it does not depend on any code here being correct,
   and it is what makes a mistake survivable.

2. THE STATEMENT CHECK below. It refuses anything that is not a single SELECT
   or WITH. This is a convenience guard against a careless query -- mine -- and
   it is NOT a security boundary. Keyword filtering of SQL is famously leaky,
   and anyone claiming otherwise has not tried hard enough to break it. It is
   worth having because it turns an obvious mistake into an obvious error; it
   is worth nothing at all if the login is wrong.

Saying that plainly matters more than the code: a guard described as security
invites someone to rely on it.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

MAX_ROWS = 500          # a chat is not a place to render 100,000 rows
TIMEOUT_S = 30          # a runaway query must not hang the session

# Whole words only. Substring matching would reject a column called
# "updated_at" for containing UPDATE, which is the kind of guard that gets
# switched off the first time it is wrong.
FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|truncate|alter|create|grant|revoke|deny"
    r"|merge|exec|execute|backup|restore|shutdown|xp_\w+|sp_\w+)\b",
    re.IGNORECASE)

COMMENT = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)


def strip_comments(sql: str) -> str:
    return COMMENT.sub(" ", sql)


def check_select(sql: str) -> str:
    """Return the statement, or raise ValueError saying why not.

    Comments are stripped BEFORE the checks, because a rule that reads the
    comment rather than the code is not a rule -- `SELECT 1 -- ; DROP TABLE x`
    and `SELECT 1 /* */ ; DROP TABLE x` must be judged on what runs.
    """
    body = strip_comments(sql).strip()
    if not body:
        raise ValueError("empty statement")
    # One statement. A trailing semicolon is fine; a second statement is not.
    if body.rstrip().rstrip(";").count(";"):
        raise ValueError("one statement at a time -- found a ';' mid-query")
    head = body.lstrip("( \t\r\n").split(None, 1)[0].lower()
    if head not in ("select", "with"):
        raise ValueError(f"only SELECT and WITH are allowed, not {head.upper()}")
    bad = FORBIDDEN.search(body)
    if bad:
        raise ValueError(f"refusing a statement containing {bad.group(0).upper()}")
    return body


def rows_to_text(cols, rows, truncated: bool) -> str:
    """Fixed-width text, because a model reads a table better than JSON and a
    person reading the transcript reads it better still."""
    if not rows:
        return "(no rows)"
    cols = list(cols)
    w = [max(len(str(c)), *(len(str(r[i])) for r in rows)) for i, c in enumerate(cols)]
    w = [min(x, 40) for x in w]
    def fmt(vals):
        return "  ".join(str(v)[:40].ljust(w[i]) for i, v in enumerate(vals))
    out = [fmt(cols), "  ".join("-" * x for x in w)]
    out += [fmt(r) for r in rows]
    if truncated:
        out.append(f"... truncated at {MAX_ROWS} rows. Add a TOP or a WHERE.")
    return "\n".join(out)


def build(engine_factory):
    """The MCP server, with its engine injected so it can be tested.

    MCPServer is the mcp 2.x name; it was FastMCP in 1.x. The first version of
    this module imported FastMCP because that is what happened to be installed
    in the container it was written in, and shipped a requirement of mcp>=1.2 --
    which cheerfully allows the 2.x that a fresh install actually gets. Every
    test here passed and every one of them failed on Ben's machine. The pin
    below now names the major that was tested, not the one that was handy.
    """
    from mcp.server.mcpserver import MCPServer

    mcp = MCPServer("trading-sql")

    @mcp.tool()
    def list_tables() -> str:
        """Every table in the trading database, with its row count."""
        from sqlalchemy import func, select
        from common import db as D
        eng = engine_factory()
        out = []
        with eng.connect() as c:
            for t in D.META.sorted_tables:
                try:
                    n = c.execute(select(func.count()).select_from(t)).scalar_one()
                except Exception:  # noqa: BLE001
                    n = None
                out.append((t.name, "-" if n is None else f"{n:,}"))
        return rows_to_text(("table", "rows"), out, False)

    @mcp.tool()
    def describe_table(name: str) -> str:
        """Columns and types for one table."""
        from common import db as D
        t = D.META.tables.get(name)
        if t is None:
            return (f"no table called {name!r}. Known: "
                    + ", ".join(sorted(D.META.tables)))
        rows = [(c.name, str(c.type), "PK" if c.primary_key else "")
                for c in t.columns]
        return rows_to_text(("column", "type", "key"), rows, False)

    @mcp.tool()
    def read_query(sql: str) -> str:
        """Run one read-only SELECT (or WITH) and return the rows.

        Refuses anything else. The refusal is a guard against a careless
        query, not a security boundary -- the read-only login is what makes a
        mistake survivable.
        """
        try:
            body = check_select(sql)
        except ValueError as e:
            return f"REFUSED: {e}"
        from sqlalchemy import text
        eng = engine_factory()
        try:
            with eng.connect().execution_options(timeout=TIMEOUT_S) as c:
                res = c.execute(text(body))
                cols = list(res.keys())
                rows = res.fetchmany(MAX_ROWS + 1)
        except Exception as e:  # noqa: BLE001
            from common import db as D
            return f"QUERY FAILED: {D._scrub(e)}"
        truncated = len(rows) > MAX_ROWS
        return rows_to_text(cols, rows[:MAX_ROWS], truncated)

    return mcp


def read_only_engine(url: str | None = None):
    """The engine this server uses.

    TRADING_DB_RO_URL, deliberately NOT the same variable the loaders use.
    Pointing this at the read-write connection would silently give an agent
    the rights the whole design exists to withhold, and nothing about a
    working server would show it. Two names, so that mistake has to be typed.
    """
    from common import db as D
    if url:
        return D.engine(url)
    from common import secrets_util as S
    v = S.resolve("TRADING_DB_RO_URL", "read-only SQL Server URL")
    if v:
        # Remember it before anything can fail with it in the message. A
        # malformed URL is precisely the one whose password reaches an error.
        D.remember_secret(D._password_of(v))
        v = D._with_password(v, "TRADING_DB_RO")
        return D.engine(v)
    if not v:
        sys.exit(
            "TRADING_DB_RO_URL is not set.\n\n"
            "It must be a READ-ONLY login -- a SQL user with db_datareader on\n"
            "the Trading database and nothing else. Pointing it at your own\n"
            "Windows account would work and would defeat the point.\n\n"
            "It may be an op:// reference; it is resolved through 1Password\n"
            "the same way every other credential in this project is.")
    return D.engine(v)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Read-only MCP server over the DB")
    ap.add_argument("--url", help="override TRADING_DB_RO_URL (testing only)")
    ap.add_argument("--selftest", action="store_true",
                    help="connect, list the tables, and exit without serving")
    ap.add_argument("--report", default="var/reports/mcp_sql_selftest.txt",
                    help="where the selftest result is written "
                         "(default: %(default)s)")
    a = ap.parse_args(argv)

    if a.selftest:
        from sqlalchemy import func, select
        from common import db as D

        # EVERY MEASUREMENT IN THIS PROJECT GOES TO A FILE. This one printed
        # and nothing else, so its result -- the one that says whether the
        # login is actually read-only -- existed only in whichever terminal
        # happened to run it. That is the same omission three other tools here
        # made, and the reason for the rule.
        lines: list[str] = []

        def say(*parts):
            msg = " ".join(str(x) for x in parts)
            print(msg)
            lines.append(msg)

        def finish(rc: int) -> int:
            from common.report_io import emit
            # The URL is never written. A report is a file that gets copied
            # around, and this one exists to be read by someone else.
            emit("\n".join(lines), a.report,
                 header="common.mcp_sql --selftest")
            return rc

        eng = read_only_engine(a.url)
        try:
            with eng.connect() as c:
                c.exec_driver_sql("SELECT 1")
        except Exception as e:  # noqa: BLE001
            # A traceback is not a diagnosis. common/db.py already learned this
            # for the read-write path; the selftest, whose entire job is to
            # diagnose, was shipped without it.
            say(f"\nCOULD NOT CONNECT: {D._scrub(e)}\n")
            if "18456" in str(e) or "Login failed" in str(e):
                say("Login failed (18456). The server answered and rejected")
                say("the credentials, so the URL and the driver are fine. In")
                say("order of how often it is each one:\n")
                say("  1. THE INSTANCE ONLY ACCEPTS WINDOWS LOGINS. A fresh")
                say("     install defaults to Windows Authentication mode")
                say("     unless Mixed Mode was chosen, and then a SQL login")
                say("     fails with 18456 whatever its password is.")
                say("       SELECT SERVERPROPERTY('IsIntegratedSecurityOnly');")
                say("     1 means Windows-only. Change it in SSMS under")
                say("     Server Properties > Security, then RESTART the")
                say("     service -- it does not take effect until you do.\n")
                say("  2. A database USER exists but no server LOGIN. These")
                say("     are different objects: the login authenticates, the")
                say("     user authorises. A user with no login has nothing to")
                say("     log in with.")
                say("       SELECT name, type_desc, is_disabled")
                say("         FROM sys.server_principals WHERE name = "
                      "'trading-algo';")
                say("       SELECT name, type_desc")
                say("         FROM sys.database_principals WHERE name = "
                      "'trading-algo';\n")
                say("  3. The password is wrong, or CHECK_POLICY forced a")
                say("     change on first use (MUST_CHANGE), which also")
                say("     presents as 18456.\n")
                say("Run those three queries as yourself; between them they")
                say("tell the three cases apart.")
            return finish(1)
        with eng.connect() as c:
            for t in D.META.sorted_tables:
                n = c.execute(select(func.count()).select_from(t)).scalar_one()
                say(f"  {t.name:<22} {n:,}")
        # THE CHECK THAT MATTERS. The statement guard is mine and it is
        # advisory; this asks SQL SERVER whether the login can write, by
        # trying, deliberately bypassing the guard. If this INSERT succeeds
        # the login has more rights than the design assumes and every
        # assurance built on it is void -- so it is loud, and it fails the
        # selftest rather than printing a warning nobody reads.
        say("\nIS THE LOGIN ACTUALLY READ-ONLY?")
        writable = False
        try:
            with eng.begin() as c:
                c.exec_driver_sql(
                    "INSERT INTO load_run (run_id, kind) "
                    "VALUES ('__selftest__', 'selftest')")
            writable = True
        except Exception as e:  # noqa: BLE001
            say(f"  GOOD -- the server refused the write: "
                  f"{str(D._scrub(e)).splitlines()[0][:120]}")
        if writable:
            with eng.begin() as c:
                try:
                    c.exec_driver_sql(
                        "DELETE FROM load_run WHERE run_id = '__selftest__'")
                except Exception:  # noqa: BLE001
                    pass
            say("  *** THE LOGIN CAN WRITE. ***")
            say("  This connection is NOT read-only, so the one real guard")
            say("  in this design is absent. Fix the login before wiring the")
            say("  server into anything; the statement check in this module")
            say("  is advisory and will not save you.")
            return finish(1)

        say("\nread_query guard (advisory only -- the login is the control):")
        for probe in ("SELECT TOP 5 * FROM bar_daily",
                      "DROP TABLE bar_daily",
                      "SELECT 1; DELETE FROM bar_daily"):
            try:
                check_select(probe)
                say(f"  ALLOW   {probe}")
            except ValueError as e:
                say(f"  REFUSE  {probe}   ({e})")
        return finish(0)

    build(lambda: read_only_engine(a.url)).run(transport="stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
