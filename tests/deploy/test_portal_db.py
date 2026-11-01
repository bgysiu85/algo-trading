"""W10-0013 sub 13: the portal's own Postgres, its backup, the .env helper and the Neon export. No network, no NAS, no Neon."""
from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import time
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy" / "nas_trader"
COMPOSE = (DEPLOY / "compose.yaml").read_text(encoding="utf-8")
ENV_EXAMPLE = (DEPLOY / ".env.example").read_text(encoding="utf-8")


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, DEPLOY / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


watch = _load("nas_watch2", "watch.py")
export = _load("neon_export", "neon_export.py")


def block(name: str) -> str:
    m = re.search(rf"^  {name}:\r?\n(.*?)(?=^  [a-z][\w-]*:\r?\n|^\w+:)", COMPOSE, re.S | re.M)
    assert m, name
    return "\n".join(ln for ln in m.group(1).splitlines() if not ln.lstrip().startswith("#"))


# ---------------------------------------------------------------- compose
def test_portal_db_is_on_the_private_network_only_and_publishes_nothing():
    b = block("portal-db")
    assert re.search(r"^\s+networks:\n\s+- portaldb\s*$", b, re.M)
    assert not re.search(r"^\s+(ports|expose|network_mode):", b, re.M)
    assert 'profiles: ["portal"]' in b and "container_name: trader-portal-db" in b
    assert "${PORTAL_DB_PASSWORD:-}" in b and "${PORTAL_DB_PASSWORD:?" not in COMPOSE   # ":?" would stop the Gateway too


def test_the_private_network_is_internal_and_only_relay_db_and_backup_use_it():
    services, top = COMPOSE.split("\nnetworks:\n", 1)
    assert re.search(r"^  portaldb:\r?\n(?:    #.*\r?\n)*    internal: true", top, re.M)
    names = re.findall(r"^  ([a-z][\w-]*):\r?\n", services, re.M)
    users = [n for n in names if n != "name" and "portaldb" in block(n)]
    assert sorted(users) == ["portal-db", "portal-db-backup", "relay"]
    for n in ("ib-gateway", "trader", "watch"):
        assert "portaldb" not in block(n)


def test_backup_service_writes_only_its_folder_and_never_starts_with_the_project():
    b = block("portal-db-backup")
    assert 'profiles: ["portal"]' in b and "read_only: true" in b
    assert re.search(r":/backup\s*$", b, re.M) and "portal_db_backup.sh:/app/portal_db_backup.sh:ro" in b
    assert not re.search(r"^\s+(ports|expose):", b, re.M)


def test_watcher_sees_the_backup_folder_read_only():
    assert re.search(r":/portal-backups:ro\b", block("watch"))


def test_env_example_has_the_database_lines_and_no_password():
    assert re.search(r"^PORTAL_DB_PASSWORD=\s*$", ENV_EXAMPLE, re.M)
    assert re.search(r"^RELAY_DATABASE_URL=\s*$", ENV_EXAMPLE, re.M)


# ---------------------------------------------------------------- watcher backup check
def test_backup_check(tmp_path):
    now = time.time()
    assert watch.backup_problem(tmp_path / "missing", now, 26) is None            # not mounted = feature off
    assert "no backup yet" in watch.backup_problem(tmp_path, now, 26)
    f = tmp_path / "portal-20261101-0100.dump"
    f.write_bytes(b"x")
    os.utime(f, (now - 3600, now - 3600))
    assert watch.backup_problem(tmp_path, now, 26) is None
    os.utime(f, (now - 30 * 3600, now - 30 * 3600))
    assert "no portal database backup for 30 h" in watch.backup_problem(tmp_path, now, 26)


# ---------------------------------------------------------------- Neon export
def test_literals():
    assert export.literal(None) == "NULL"
    assert export.literal(True) == "true"
    assert export.literal(3) == "3" and export.literal(Decimal("12.50")) == "12.50"
    assert export.literal("it's") == "'it''s'"
    assert export.literal(date(2026, 10, 30)) == "'2026-10-30'"
    assert export.literal(datetime(2026, 10, 30, 9, 31, 2)) == "'2026-10-30 09:31:02'"
    assert export.literal(datetime(2026, 10, 30, 9, 31, tzinfo=timezone.utc)).endswith("+00:00'")


class FakeCursor:
    def __init__(self, tables):
        self.tables, self.rows, self.description = tables, [], []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql):
        t = next(n for n in self.tables if f"FROM {n}" in sql)
        cols, rows = self.tables[t]
        if sql.startswith("SELECT count"):
            self.rows = [(len(rows), rows[0][1], rows[-1][1], sum(r[2] for r in rows))]
            self.description = []
        else:
            self.rows = rows
            self.description = [type("D", (), {"name": c}) for c in cols]

    def fetchone(self):
        return self.rows[0]

    def __iter__(self):
        return iter(self.rows)


class FakeConn:
    def __init__(self, tables):
        self.tables = tables

    def cursor(self):
        return FakeCursor(self.tables)


def test_export_builds_one_transaction_with_schema_and_rows():
    tables = {
        "closed_trades": (["trade_key", "session_date", "net_pnl"],
                          [("a", date(2026, 10, 1), Decimal("10.5")), ("b", date(2026, 10, 2), Decimal("-4.25"))]),
        "order_outcomes": (["session_date", "strategy", "n"], [(date(2026, 10, 1), "mcl", 3)]),
    }
    lines, totals = export.export(FakeConn(tables), "CREATE TABLE IF NOT EXISTS x (a int);")
    assert lines[0].startswith("--") and lines[1] == "BEGIN;" and lines[-1] == "COMMIT;"
    assert "CREATE TABLE IF NOT EXISTS x (a int);" in lines
    assert "INSERT INTO closed_trades (trade_key, session_date, net_pnl) VALUES ('a', '2026-10-01', 10.5);" in lines
    assert sum(ln.startswith("INSERT") for ln in lines) == 3
    assert totals["closed_trades"][0] == 2 and totals["closed_trades"][3] == Decimal("6.25")
    assert "2 rows" in export.describe(totals)[0]


def test_export_never_prints_the_connection_string(tmp_path, capsys):
    env = tmp_path / "neon.env"
    env.write_text("DATABASE_URL=postgresql://user:SECRETPW@nowhere.invalid/db\n", encoding="utf-8")
    schema = tmp_path / "schema.sql"
    schema.write_text("SELECT 1;", encoding="utf-8")
    msg = ""
    try:
        export.main(["--check", "--env", str(env), "--schema", str(schema)])
    except SystemExit as e:
        msg = str(e)
    out = capsys.readouterr()
    assert "SECRETPW" not in msg + out.out + out.err


# ---------------------------------------------------------------- the .env helper and the backup script (bash)
def _bash():
    for c in (r"C:\Program Files\Git\bin\bash.exe", "/bin/bash", "/usr/bin/bash"):
        if Path(c).exists():
            return c
    return None


needs_bash = pytest.mark.skipif(_bash() is None, reason="no bash")


def run_helper(tmp_path, *args):
    r = subprocess.run([_bash(), (DEPLOY / "portal_db.sh").as_posix(), *args], cwd=tmp_path, capture_output=True, text=True,
                       env={**os.environ, "ENV_FILE": ".env"})
    return r.returncode, r.stdout + r.stderr


@needs_bash
def test_helper_makes_a_password_once_and_switches_and_rolls_back(tmp_path):
    env = tmp_path / ".env"
    env.write_bytes(b"A=1\nRELAY_DATABASE_URL=postgresql://neon_user:neonpw@ep-x.neon.tech/neondb\nB=2\n")
    rc, out = run_helper(tmp_path, "password")
    assert rc == 0 and "written" in out
    pw = re.search(r"^PORTAL_DB_PASSWORD=([0-9a-f]{48})$", env.read_text(), re.M).group(1)
    assert pw not in out
    rc, out = run_helper(tmp_path, "password")
    assert "already set" in out and env.read_text().count("PORTAL_DB_PASSWORD=") == 1
    rc, out = run_helper(tmp_path, "switch")
    text = env.read_text()
    assert rc == 0 and f"RELAY_DATABASE_URL=postgresql://portal:{pw}@portal-db:5432/portal" in text
    assert "NEON_DATABASE_URL=postgresql://neon_user:neonpw@ep-x.neon.tech/neondb" in text
    assert text.count("RELAY_DATABASE_URL=") == 1 and "A=1" in text and "B=2" in text
    assert pw not in out and "neonpw" not in out
    assert "portal-db (NAS)" in run_helper(tmp_path, "status")[1]
    rc, out = run_helper(tmp_path, "rollback")
    relay_line = [ln for ln in env.read_text().splitlines() if ln.startswith("RELAY_DATABASE_URL=")]
    assert rc == 0 and len(relay_line) == 1 and "neon.tech" in relay_line[0]
    assert "another database (Neon)" in run_helper(tmp_path, "status")[1]


@needs_bash
def test_helper_switch_needs_a_password_first(tmp_path):
    (tmp_path / ".env").write_text("A=1\n")
    rc, out = run_helper(tmp_path, "switch")
    assert rc != 0 and "password" in out


def test_backup_script_checks_each_dump_and_keeps_the_newest_three():
    s = (DEPLOY / "portal_db_backup.sh").read_text(encoding="utf-8")
    assert "pg_restore --list" in s and "tail -n +4" in s and "-mmin" in s
    assert "rm -f --" in s and "portal-*.dump" in s
