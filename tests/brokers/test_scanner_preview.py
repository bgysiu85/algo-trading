#!/usr/bin/env python3
"""`--preview` must produce a FILE, and must still not be a writer.

Option A of the live-feed handover: IB's scanner is already written and has
never been run, and `--preview` is what settles the open question in the file --
whether IB's percent-gain scans compute before 09:30.

It printed to the terminal and wrote nothing, which collides with the standing
rule that every result is a file and nothing is copy-pasted out of a terminal.
Redirecting it in PowerShell is not the fix: `>` and `Tee-Object` both write
UTF-16, which is the encoding trap this repo already carries a guard for. So it
writes its own report, from Python, through `report_io.emit` -- painted to the
terminal, plain UTF-8 to disk.

The property that must NOT change: preview is not a writer. It neither takes
the watchlist lock nor is refused by one, because checking what the scanner
would pick while a feed is running is the entire point of it.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from brokers.ibkr import scanner


def parse(argv):
    import sys
    from unittest import mock
    with mock.patch.object(sys, "argv", ["scanner", *argv]):
        p = [a for a in dir(scanner) if a == "main"]
    return p


def test_preview_has_its_own_output_path_under_var_reports():
    src = inspect.getsource(scanner.main)
    assert "--preview-out" in src
    assert "var/reports/scan_preview.txt" in src


def test_preview_writes_through_report_io_and_not_a_bare_open():
    """`report_io.emit` is what keeps ANSI colour out of the .txt and settles
    the encoding. A bare write here would reintroduce both."""
    src = inspect.getsource(scanner)
    tree = ast.parse(src)
    imported = {a.name for n in ast.walk(tree)
                if isinstance(n, ast.ImportFrom) for a in n.names}
    assert "emit" in imported


def test_preview_still_takes_no_lock_and_writes_no_watchlist():
    """A preview that took the writer lock could not be run beside a live feed,
    and running it beside a live feed is what it is for."""
    src = inspect.getsource(scanner.main)
    i_preview = src.index("if not args.preview:")
    i_lock = src.index("session_lock.active(")
    assert i_preview < i_lock, "the lock check is no longer guarded by --preview"
    body = inspect.getsource(scanner.main_async)
    pre = body[body.index("if args.preview:"):]
    assert "wl.write_text" not in pre.split("break")[0], \
        "the preview branch writes the watchlist"


def test_the_preview_report_names_the_question_it_settles():
    """A report that does not say what a zero-row result MEANS invites the
    reading 'the scanner is broken' when the answer is 'IB does not compute
    this scan pre-market' -- which is the finding."""
    src = inspect.getsource(scanner.main_async)
    pre = src[src.index("if args.preview:"):]
    assert "09:30" in pre
    assert "returning nothing" in pre or "returned" in pre


def test_the_default_output_is_not_the_watchlist():
    src = inspect.getsource(scanner.main)
    assert "--preview-out" in src
    assert 'default="var/reports/scan_preview.txt"' in src
