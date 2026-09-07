#!/usr/bin/env python3
"""Stop the test suite writing over real reports.

THE INCIDENT THIS EXISTS TO PREVENT, 2026-09-07
------------------------------------------------
`common.mcp_sql --selftest` defaults `--report` to var/reports/mcp_sql_selftest.txt.
Four tests called `main(["--selftest"])` without overriding it, so running
pytest in D:\\Trading REPLACED the real selftest result -- the file that records
whether the read-only login is actually read-only -- with the output of a test
whose fake connection error is the string

    "mssql+pyodbc://trading-algo:hunter2@localhost/Trading failed"

That is not a crash. It is a plausible-looking failure report, with a real
username in it, sitting at the real path, timestamped minutes ago. It sent us
diagnosing a database connection that was never broken, and it destroyed the
measurement it overwrote.

Nearly every tool in this project defaults --out into var/reports/, by design
(PROGRAM_INDEX section 3: "reports write themselves"). So this is not one
careless test; it is a trap laid for every test that calls a main().

THE RULE
--------
A test may write anywhere except the repo's var/. Tests get tmp_path. If a
test writes a report, it passes an explicit path into tmp_path.

This fails loudly rather than redirecting quietly: a test with an unintended
side effect is a bug in the test, and silently sandboxing it would leave the
same tool free to surprise someone else.
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PROTECTED = (REPO / "var", REPO / "bar_cache", REPO / "bar_cache_db")


def _protected(p: Path) -> Path | None:
    try:
        rp = Path(p).resolve()
    except OSError:
        return None
    for root in PROTECTED:
        try:
            rp.relative_to(root)
        except ValueError:
            continue
        return root
    return None


@pytest.fixture(autouse=True)
def no_writes_to_real_artefacts(monkeypatch):
    """Refuse any report written into the repo's real artefact directories."""
    from common import report_io

    real = report_io.emit

    def guarded(text, out=None, *, header=""):
        if out is not None:
            root = _protected(Path(out))
            if root is not None:
                raise AssertionError(
                    f"a test tried to write {out} inside {root}.\n"
                    "That is a real artefact directory -- this is how the "
                    "mcp_sql selftest report was replaced by a test fixture's "
                    "fake connection error on 2026-09-07.\n"
                    "Pass an explicit path under tmp_path instead.")
        return real(text, out, header=header)

    monkeypatch.setattr(report_io, "emit", guarded)
    yield
