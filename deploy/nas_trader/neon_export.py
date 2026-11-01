#!/usr/bin/env python3
r"""W10-0013 sub 13: copy the portal's trade history out of Neon as a plain SQL file. READ-ONLY on Neon; prints no secret.

    python deploy\nas_trader\neon_export.py --check                         # row counts + totals, nothing written
    python deploy\nas_trader\neon_export.py --out "D:\Trading\Claude outputs\portal_history.sql"

Reads DATABASE_URL from D:\Trading UI\var\neon.env (override with --env). Needs `psycopg` (the system Python has it; the repo
.venv does not). The connection is opened read-only. The file holds history/schema.sql (idempotent) and one INSERT per row of
closed_trades and order_outcomes inside a single transaction, so loading it is all-or-nothing:

    sudo docker exec -i trader-portal-db psql -U portal -d portal -v ON_ERROR_STOP=1 < portal_history.sql

Nothing read from neon.env is printed; errors name the exception type only (a driver message can carry the connection string,
see tools/check_neon.py in the Trading UI repo for the 2026-09-17 leak this rule comes from).
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

UI_ROOT = Path(r"D:\Trading UI")
TABLES = {  # name: ORDER BY (a stable file; the same dump twice is byte-identical)
    "closed_trades": "trade_key",
    "order_outcomes": "session_date, strategy, status",
}
TOTALS = {
    "closed_trades": "count(*), min(session_date), max(session_date), coalesce(sum(net_pnl), 0)",
    "order_outcomes": "count(*), min(session_date), max(session_date), coalesce(sum(n), 0)",
}


def read_url(env: Path) -> str:
    """DATABASE_URL from a KEY=VALUE file, or a bare connection string. Raises SystemExit without printing the value."""
    if not env.exists():
        sys.exit(f"{env} not found")
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("DATABASE_URL="):
            return line.partition("=")[2].strip().strip('"').strip("'")
        if line.startswith(("postgres://", "postgresql://")):
            return line
    sys.exit("no DATABASE_URL line in the env file")


def literal(v) -> str:
    """A SQL literal for the types these two tables hold. No driver, no quoting surprises."""
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, Decimal)):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, (datetime, date)):
        return "'" + v.isoformat(sep=" ") + "'" if isinstance(v, datetime) else "'" + v.isoformat() + "'"
    return "'" + str(v).replace("'", "''") + "'"


def insert_line(table: str, cols: list[str], row) -> str:
    return f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(literal(v) for v in row)});"


def export(conn, schema_sql: str) -> tuple[list[str], dict]:
    """(lines of the SQL file, {table: totals row}) from an open read-only connection."""
    lines = ["-- Neon history copy (W10-0013 sub 13). Load once into an EMPTY portal database.", "BEGIN;", schema_sql.strip()]
    totals = {}
    with conn.cursor() as cur:
        for table, order in TABLES.items():
            cur.execute(f"SELECT {TOTALS[table]} FROM {table}")
            totals[table] = cur.fetchone()
            cur.execute(f"SELECT * FROM {table} ORDER BY {order}")
            cols = [d.name for d in cur.description]
            for row in cur:
                lines.append(insert_line(table, cols, row))
    lines.append("COMMIT;")
    return lines, totals


def describe(totals: dict) -> list[str]:
    out = []
    for table, (n, lo, hi, total) in totals.items():
        what = "sum(net_pnl)" if table == "closed_trades" else "sum(n)"
        out.append(f"{table}: {n} rows, {lo} to {hi}, {what} = {total}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--env", type=Path, default=UI_ROOT / "var" / "neon.env")
    ap.add_argument("--schema", type=Path, default=UI_ROOT / "history" / "schema.sql")
    ap.add_argument("--check", action="store_true", help="print counts and totals only")
    ap.add_argument("--out", type=Path, help="write the SQL file here")
    a = ap.parse_args(argv)
    if not a.check and not a.out:
        ap.error("give --check or --out FILE")
    try:
        import psycopg
    except ImportError:
        sys.exit("psycopg is not installed in this Python (try the system python, or: pip install psycopg[binary])")
    url = read_url(a.env)
    try:
        with psycopg.connect(url, connect_timeout=20, autocommit=False) as conn:
            conn.read_only = True
            lines, totals = export(conn, a.schema.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001 - the message of a driver error can carry the connection string
        sys.exit(f"could not read Neon ({type(e).__name__})")
    for line in describe(totals):
        print(line)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))   # LF, UTF-8
        print(f"wrote {a.out} ({a.out.stat().st_size} bytes). Compare the numbers above with the NAS after loading.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
