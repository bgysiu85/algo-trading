#!/usr/bin/env python3
"""The guard in conftest.py has to actually fire.

A guard nobody has seen refuse anything is a guard that may have been
monkeypatched away, scoped to the wrong directory, or silently disabled by an
import order change -- and it would look exactly like a guard that works.
"""
from __future__ import annotations


import pytest

from common import report_io




def test_a_report_written_into_the_real_var_is_refused():
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
    with pytest.raises(AssertionError):
        report_io.emit("x", "var/reports/mcp_sql_selftest.txt")


def test_a_report_written_to_a_temp_path_is_allowed(tmp_path):
    """The guard must not block ordinary use, or somebody removes it."""
    out = tmp_path / "r.txt"
    report_io.emit("hello", out)
    assert "hello" in out.read_text(encoding="utf-8")


def test_the_guard_covers_the_bar_caches_too(tmp_path):
    """var/ is not the only directory holding hours of work."""
    with pytest.raises(AssertionError):
        report_io.emit("x", "bar_cache_db/notes.txt")
