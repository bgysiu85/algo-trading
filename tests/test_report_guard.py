#!/usr/bin/env python3
"""The guard in conftest.py has to actually fire.

A guard nobody has seen refuse anything is a guard that may have been
monkeypatched away, scoped to the wrong directory, or silently disabled by an
import order change -- and it would look exactly like a guard that works.
"""
from __future__ import annotations


import os
import subprocess
from pathlib import Path

import pytest

from common import report_io




def _must_be_recognised(path: str) -> None:
    """Assert the guard classifies `path` as protected WITHOUT writing to it.

    This check has to come before the emit() call below, and the ordering is
    the whole point. pytest.raises calls emit first; if the guard is broken,
    emit writes the real file and only then does the test fail -- so the test
    that exists to prevent the overwrite performs it. That happened on
    2026-09-14, running this suite from the production checkout where var/ is
    a junction. A cheap classification check fails first and nothing is
    written.
    """
    from tests.conftest import _protected

    root = _protected(Path(path))
    assert root is not None, (
        f"the guard does not recognise {path} as protected, so emit() would "
        f"write it for real. Roots it knows: "
        f"{[str(r) for r in __import__('tests.conftest', fromlist=['x']).PROTECTED]}")


def test_a_report_written_into_the_real_var_is_refused():
    _must_be_recognised("var/reports/anything.txt")
    with pytest.raises(AssertionError, match="real artefact directory"):
        report_io.emit("x", "var/reports/anything.txt")


def test_the_selftest_default_report_is_a_path_the_guard_refuses():
    """The selftest's --report default is the exact file that was overwritten.
    It SHOULD default into var/ -- that is the point of "reports write
    themselves". So the guard has to cover it, and this pins that the two
    agree rather than each being separately reasonable."""
    import inspect

    from common import mcp_sql as M
    src = inspect.getsource(M.main)
    assert "var/reports/mcp_sql_selftest.txt" in src, \
        "the selftest default moved -- point the guard at wherever it went"
    _must_be_recognised("var/reports/mcp_sql_selftest.txt")
    with pytest.raises(AssertionError):
        report_io.emit("x", "var/reports/mcp_sql_selftest.txt")


def _link_directory(link: Path, target: Path) -> None:
    r"""Make `link` point at directory `target`, however this platform allows.

    On Windows a SYMLINK needs SeCreateSymbolicLinkPrivilege -- an elevated
    shell or Developer Mode -- and raises WinError 1314 without it. A JUNCTION
    needs neither. It is also what D:\TradingProd\var actually is, so this is
    the more faithful reproduction rather than a workaround.

    This matters more than it looks: written with symlink_to, the test for a
    Windows junction bug ran only on Linux, where the bug cannot occur. A test
    that skips the platform it is about is worth very little.
    """
    if os.name == "nt":
        done = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True, text=True)
        if done.returncode != 0:                            # pragma: no cover
            pytest.skip("could not create a junction: "
                        f"{(done.stderr or done.stdout).strip()}")
        return
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as e:                                    # pragma: no cover
        pytest.skip(f"could not create a directory symlink: {e}")


def test_the_guard_sees_through_a_junction(tmp_path, monkeypatch):
    """D:\\TradingProd\\var is a junction to D:\\Trading\\var. A write
    through it resolves to the other repo, so a root that was never resolved
    stops matching and the guard goes quiet -- while the file it protects is
    the same file. Reproduced here with a symlink."""
    from tests import conftest as C

    real = tmp_path / "real" / "var" / "reports"
    real.mkdir(parents=True)
    prod = tmp_path / "prod"
    prod.mkdir()
    _link_directory(prod / "var", tmp_path / "real" / "var")

    monkeypatch.setattr(C, "REPO", prod)
    monkeypatch.setattr(C, "PROTECTED", C._roots())
    monkeypatch.chdir(prod)

    assert C._protected(Path("var/reports/anything.txt")) is not None, \
        "a junction must not make a protected directory look ordinary"


def test_the_guard_still_allows_an_ordinary_path(tmp_path):
    """The junction fix widens what counts as protected. It must not widen it
    so far that normal writes are refused, or somebody removes the guard."""
    from tests.conftest import _protected

    assert _protected(tmp_path / "somewhere" / "r.txt") is None


def test_a_report_written_to_a_temp_path_is_allowed(tmp_path):
    """The guard must not block ordinary use, or somebody removes it."""
    out = tmp_path / "r.txt"
    report_io.emit("hello", out)
    assert "hello" in out.read_text(encoding="utf-8")


def test_the_guard_covers_the_bar_caches_too(tmp_path):
    """var/ is not the only directory holding hours of work."""
    with pytest.raises(AssertionError):
        report_io.emit("x", "bar_cache_db/notes.txt")


def test_on_windows_the_link_is_a_junction_not_a_symlink(monkeypatch, tmp_path):
    """Runs on every platform, so a typo in the Windows-only branch is caught
    here rather than on Ben's machine. A symlink there needs privileges a
    normal shell does not have; a junction needs none."""
    monkeypatch.setattr(os, "name", "nt")
    seen = {}

    class Done:
        returncode = 0
        stdout = stderr = ""

    def fake_run(command, **kwargs):
        seen["command"] = command
        return Done()

    monkeypatch.setattr(subprocess, "run", fake_run)
    _link_directory(tmp_path / "link", tmp_path / "target")

    assert seen["command"][:4] == ["cmd", "/c", "mklink", "/J"]
    assert seen["command"][4:] == [str(tmp_path / "link"), str(tmp_path / "target")]


def test_a_junction_that_cannot_be_made_skips_rather_than_fails(monkeypatch, tmp_path):
    """Not every machine allows it. A skip says "not checked here"; a failure
    would say "the guard is broken", which is a different and wrong claim."""
    monkeypatch.setattr(os, "name", "nt")

    class Done:
        returncode = 1
        stdout = ""
        stderr = "Access is denied."

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Done())

    # Skipped derives from BaseException, so `pytest.raises(Exception)` lets it
    # through and the test skips itself instead of asserting anything.
    with pytest.raises(pytest.skip.Exception) as caught:
        _link_directory(tmp_path / "link", tmp_path / "target")
    assert "Access is denied" in str(caught.value)
