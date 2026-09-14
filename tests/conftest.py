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
NAMES = ("var", "bar_cache", "bar_cache_db")


def _roots() -> tuple[Path, ...]:
    r"""Every spelling of a protected directory, resolved AND literal.

    D:\TradingProd\var is a junction to D:\Trading\var. The path being
    written resolves through it; a root that does not is then a different
    string, relative_to says no, and the guard waves through a write into the
    very directory it exists to protect. That is not hypothetical -- running
    this suite from the production checkout on 2026-09-14 replaced
    var/reports/mcp_sql_selftest.txt for the second time, the first being the
    incident this guard was written for.

    Both spellings are kept because either can be the one that matches: the
    resolved root catches a write through the junction, the literal root
    catches a path that was never resolved (a non-existent parent on some
    platforms, or a root that is itself unreadable).
    """
    roots: list[Path] = []
    for name in NAMES:
        here = REPO / name
        roots.append(here)
        try:
            roots.append(here.resolve())
        except OSError:                                     # pragma: no cover
            pass
    return tuple(dict.fromkeys(roots))


PROTECTED = _roots()


def _protected(p: Path) -> Path | None:
    """The protected root `p` sits inside, or None.

    Checks the path both as given and resolved, so neither a junction in the
    path nor one in the root can make a protected location look ordinary.
    """
    candidates = []
    try:
        candidates.append(Path(p).resolve())
    except OSError:
        pass
    candidates.append(Path(p) if Path(p).is_absolute() else Path.cwd() / p)

    for candidate in candidates:
        for root in PROTECTED:
            try:
                candidate.relative_to(root)
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

def pytest_configure(config):
    """Register the markers this suite uses.

    Unregistered marks are only a warning, which is how a typo'd @pytest.mark
    silently marks nothing. `slow` gates the dry-session replays: they step a
    synthetic session minute by minute through the real trader and cost
    seconds rather than milliseconds. Run `pytest -m "not slow"` to skip them.
    """
    config.addinivalue_line(
        "markers", "slow: steps a session through the real trader; seconds")
