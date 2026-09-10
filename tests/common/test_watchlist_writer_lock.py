#!/usr/bin/env python3
"""One writer for var/watchlist.txt.

The rule existed only as a sentence in two file headers -- "Run one or the
other, never both, or they overwrite each other every few seconds" -- and
nothing enforced it. Two writers do not error: they take turns, and the trader
sees the watchlist flip between two answers every few seconds while names
appear and vanish for no visible reason.

It became load-bearing on 2026-09-10, when main.py --mode paper started running
the feed itself: the obvious mistake is now to run the combined command AND
leave run_tv_feed.ps1 up in the other terminal.
"""
from __future__ import annotations

import inspect
import json
import os

import pytest

from brokers.ibkr import scanner
from common import session_lock as L
from common import tv_feed


def test_the_writer_lock_is_a_separate_file_from_the_session_lock():
    """Sharing one file would make the trader's own session lock block the feed
    it starts, and main.py's combined command could never run at all."""
    assert L.WRITER_LOCK_PATH != L.LOCK_PATH


def test_a_live_writer_lock_is_seen(tmp_path):
    p = tmp_path / "w.lock"
    with L.held("watchlist-writer", "tv_feed", p):
        got = L.active(p)
        assert got and got["strategy"] == "tv_feed"
    assert L.active(p) is None, "the lock outlived its context manager"


def test_a_dead_writer_does_not_block_forever(tmp_path):
    """A crashed feed must not stop tomorrow's session. Same staleness rules as
    the session lock -- this reuses that code rather than reimplementing it."""
    p = tmp_path / "w.lock"
    p.write_text(json.dumps({"mode": "watchlist-writer", "strategy": "tv_feed",
                             "pid": 999_999_999, "started_epoch": 0}))
    assert L.active(p) is None
    assert not p.exists(), "a stale lock should be reaped, not just ignored"


def test_both_writers_take_the_lock():
    """If either one skipped it the guard would be half a guard, and the half
    that skipped is the one that would silently win the race."""
    for mod, name in ((tv_feed, "tv_feed"), (scanner, "scanner")):
        src = inspect.getsource(mod.main)
        assert "WRITER_LOCK_PATH" in src, f"{name}.main does not take the lock"
        assert "session_lock.held" in src, f"{name}.main never holds it"


def test_the_read_only_modes_neither_take_nor_are_blocked():
    """--dry-run and --preview write nothing. Blocking them would make it
    impossible to check what the OTHER tool would pick while a feed runs, which
    is exactly when someone asks."""
    feed = inspect.getsource(tv_feed.main)
    assert "a.dry_run" in feed
    assert feed.index("a.dry_run") < feed.index("WRITER_LOCK_PATH"), (
        "dry-run must return before the lock is consulted")
    scan = inspect.getsource(scanner.main)
    assert "args.preview" in scan
    assert scan.index("args.preview") < scan.index("WRITER_LOCK_PATH")


def test_tv_feed_main_takes_argv():
    """main.py runs the feed in a thread beside the trader. Without argv the
    embedded call reads sys.argv and picks up the TRADER's flags, then dies on
    an unrecognized argument the moment it starts."""
    assert "argv" in inspect.signature(tv_feed.main).parameters
