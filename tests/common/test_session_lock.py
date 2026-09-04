#!/usr/bin/env python3
"""The session lock, including the paths that decide whether a backtest runs.

This guard is the reason a scheduled backtest cannot throttle a live session
against IB's account-wide request cap, and IB reports that throttling as
empty results rather than errors -- so a broken guard fails silently on both
sides. The stale-lock branches matter as much as the happy path: a guard that
never releases after a crash would block every subsequent backtest, which is
worse than no guard at all.
"""
import json
import os
import time
from pathlib import Path

import pytest

from common import session_lock as SL


def test_no_lock_means_no_session(tmp_path):
    assert SL.active(tmp_path / "session.lock") is None


def test_held_creates_and_releases(tmp_path):
    lock = tmp_path / "session.lock"
    with SL.held("paper", "mcl", path=lock) as info:
        assert lock.exists()
        assert info["mode"] == "paper" and info["strategy"] == "mcl"
        assert info["pid"] == os.getpid()
        assert SL.active(lock) is not None
    assert not lock.exists()
    assert SL.active(lock) is None


def test_released_even_when_the_body_raises(tmp_path):
    """A Ctrl-C must not leave a lock that blocks tonight's backtest."""
    lock = tmp_path / "session.lock"
    with pytest.raises(KeyboardInterrupt):
        with SL.held("paper", "mcl", path=lock):
            raise KeyboardInterrupt
    assert not lock.exists()


def test_dead_pid_is_stale_and_cleared(tmp_path):
    lock = tmp_path / "session.lock"
    lock.write_text(json.dumps({"mode": "paper", "strategy": "mcl",
                                "pid": 2 ** 22,          # not a live pid
                                "started_at": "x", "started_epoch": time.time()}))
    assert SL.active(lock) is None
    assert not lock.exists(), "a stale lock must be removed, not just ignored"


def test_old_lock_is_stale_even_with_a_live_pid(tmp_path):
    """Backstop for a pid that was recycled onto a long-running process."""
    lock = tmp_path / "session.lock"
    lock.write_text(json.dumps({
        "mode": "paper", "strategy": "mcl", "pid": os.getpid(),
        "started_at": "x",
        "started_epoch": time.time() - (SL.MAX_AGE_H + 1) * 3600}))
    assert SL.active(lock) is None
    assert not lock.exists()


def test_unreadable_lock_does_not_wedge_the_guard(tmp_path):
    lock = tmp_path / "session.lock"
    lock.write_text("{ not json")
    assert SL.active(lock) is None


def test_pid_alive_never_signals_the_process():
    """os.kill(pid, 0) TERMINATES the target on Windows, so it must not be used.

    Checking our own pid is the cheapest proof the probe is non-destructive:
    if it signalled, this test would not finish.
    """
    assert SL._pid_alive(os.getpid()) is True
    assert SL._pid_alive(2 ** 22) is False
    assert SL._pid_alive(-1) is False
