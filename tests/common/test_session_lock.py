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
                                "started_at": "x", "started_epoch": time.time()}), encoding="utf-8")
    assert SL.active(lock) is None
    assert not lock.exists(), "a stale lock must be removed, not just ignored"


def test_old_lock_is_stale_even_with_a_live_pid(tmp_path):
    """Backstop for a pid that was recycled onto a long-running process."""
    lock = tmp_path / "session.lock"
    lock.write_text(json.dumps({
        "mode": "paper", "strategy": "mcl", "pid": os.getpid(),
        "started_at": "x",
        "started_epoch": time.time() - (SL.MAX_AGE_H + 1) * 3600}), encoding="utf-8")
    assert SL.active(lock) is None
    assert not lock.exists()


def test_unreadable_lock_does_not_wedge_the_guard(tmp_path):
    lock = tmp_path / "session.lock"
    lock.write_text("{ not json", encoding="utf-8")
    assert SL.active(lock) is None


def test_pid_alive_never_signals_the_process():
    """os.kill(pid, 0) TERMINATES the target on Windows, so it must not be used.

    Checking our own pid is the cheapest proof the probe is non-destructive:
    if it signalled, this test would not finish.
    """
    assert SL._pid_alive(os.getpid()) is True
    assert SL._pid_alive(2 ** 22) is False
    assert SL._pid_alive(-1) is False


# ---------------------------------------------------------------------------
# Heartbeat locks, 2026-10-28 (W10-0013 sub 6): a lock another machine can read.
# ---------------------------------------------------------------------------
import socket


def _settled(lock, tries=100):
    """SL.read, retried: on Windows a read can collide with the heartbeat's rename."""
    for _ in range(tries):
        got = SL.read(lock)
        if got is not None:
            return got
        time.sleep(0.01)
    raise AssertionError(f"{lock} never became readable")


def _hb_lock(path, *, age=0.0, host="nas-box", pid=2 ** 22, **extra):
    """A heartbeat lock as another machine's trader would write it."""
    now = time.time()
    info = {"mode": "paper", "strategy": "mcl", "pid": pid, "host": host,
            "token": "t1", "started_at": "x", "started_epoch": now - 3600,
            "heartbeat_epoch": now - age, **extra}
    Path(path).write_text(json.dumps(info), encoding="utf-8")
    return info


def test_held_writes_host_token_and_heartbeat(tmp_path):
    lock = tmp_path / "session.lock"
    with SL.held("paper", "mcl", path=lock) as info:
        on_disk = json.loads(lock.read_text(encoding="utf-8"))
        assert on_disk["host"] == socket.gethostname()
        assert on_disk["token"] == info["token"] and len(info["token"]) >= 16
        assert abs(on_disk["heartbeat_epoch"] - time.time()) < 5


def test_heartbeat_thread_refreshes_the_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(SL, "HEARTBEAT_S", 0.05)
    lock = tmp_path / "session.lock"
    with SL.held("paper", "mcl", path=lock) as info:
        first = _settled(lock)["heartbeat_epoch"]
        deadline = time.time() + 5
        while time.time() < deadline and _settled(lock)["heartbeat_epoch"] == first:
            time.sleep(0.02)
        assert _settled(lock)["heartbeat_epoch"] > first
        # The refresh keeps everything else, notably the pid and token.
        assert _settled(lock)["token"] == info["token"]
        assert _settled(lock)["pid"] == os.getpid()


def test_heartbeat_stops_on_exit_and_never_recreates_the_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(SL, "HEARTBEAT_S", 0.02)
    lock = tmp_path / "session.lock"
    with SL.held("paper", "mcl", path=lock):
        time.sleep(0.1)
    time.sleep(0.2)
    assert not lock.exists()
    assert not list(tmp_path.glob("*.tmp")), "no temp file may be left behind"


def test_heartbeat_does_not_resurrect_a_lock_someone_else_took(tmp_path, monkeypatch):
    """Container pids repeat: ownership is the token, not the pid."""
    monkeypatch.setattr(SL, "HEARTBEAT_S", 0.03)
    lock = tmp_path / "session.lock"
    with SL.held("paper", "mcl", path=lock):
        _hb_lock(lock, host=socket.gethostname(), pid=os.getpid(), token="someone-else")
        time.sleep(0.3)
        assert _settled(lock)["token"] == "someone-else"
    assert lock.exists(), "exit must not remove a lock that is not ours"


def test_heartbeat_does_not_write_back_a_lock_that_was_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(SL, "HEARTBEAT_S", 0.03)
    lock = tmp_path / "session.lock"
    with SL.held("paper", "mcl", path=lock):
        lock.unlink()
        time.sleep(0.3)
        assert not lock.exists()


def test_fresh_heartbeat_on_another_host_is_live_whatever_the_pid(tmp_path):
    """A pid from another machine says nothing; the heartbeat decides."""
    lock = tmp_path / "session.lock"
    _hb_lock(lock, age=5, host="nas-box", pid=2 ** 22)
    assert SL.active(lock) is not None
    assert lock.exists()


def test_old_heartbeat_is_stale_and_cleared(tmp_path):
    lock = tmp_path / "session.lock"
    _hb_lock(lock, age=SL.HEARTBEAT_STALE_S + 30, host=socket.gethostname(), pid=os.getpid())
    assert SL.active(lock) is None
    assert not lock.exists()


def test_same_host_dead_pid_is_stale_before_the_heartbeat_runs_out(tmp_path):
    lock = tmp_path / "session.lock"
    _hb_lock(lock, age=1, host=socket.gethostname(), pid=2 ** 22)
    assert SL.active(lock) is None
    assert not lock.exists()


def test_same_host_live_pid_with_fresh_heartbeat_is_live(tmp_path):
    lock = tmp_path / "session.lock"
    _hb_lock(lock, age=1, host=socket.gethostname(), pid=os.getpid())
    assert SL.active(lock) is not None


def test_a_refreshed_session_is_not_stale_just_because_it_is_old(tmp_path):
    """The 24h age backstop is for pid locks; a beating lock proves itself."""
    lock = tmp_path / "session.lock"
    _hb_lock(lock, age=2, host="nas-box")
    info = json.loads(lock.read_text(encoding="utf-8"))
    info["started_epoch"] = time.time() - (SL.MAX_AGE_H + 5) * 3600
    lock.write_text(json.dumps(info), encoding="utf-8")
    assert SL.active(lock) is not None


def test_a_few_seconds_of_clock_skew_does_not_kill_a_live_lock(tmp_path):
    lock = tmp_path / "session.lock"
    _hb_lock(lock, age=-8)           # the NAS clock is 8 s ahead of ours
    assert SL.active(lock) is not None


# ---- reading another machine's lock ----------------------------------------

def test_remote_live_lock_is_found_and_marked_remote(tmp_path):
    lock = tmp_path / "state" / "session.lock"
    lock.parent.mkdir()
    _hb_lock(lock, age=10)
    found = SL.active_remote(lock)
    assert found and found["remote"] == str(lock) and found["host"] == "nas-box"


def test_remote_stale_lock_is_ignored_and_never_deleted(tmp_path):
    """The share is read-only and the stale lock is the NAS's to clear."""
    lock = tmp_path / "session.lock"
    _hb_lock(lock, age=SL.HEARTBEAT_STALE_S + 60)
    assert SL.active_remote(lock) is None
    assert lock.exists()


def test_remote_lock_without_heartbeat_is_ignored_with_a_warning(tmp_path, capsys):
    lock = tmp_path / "session.lock"
    lock.write_text(json.dumps({"mode": "paper", "strategy": "mcl", "pid": os.getpid(),
                                "started_epoch": time.time()}), encoding="utf-8")
    assert SL.active_remote(lock) is None
    assert "no heartbeat" in capsys.readouterr().err


def test_unreachable_share_fails_open_but_says_so(tmp_path, capsys):
    gone = tmp_path / "not-mounted" / "state" / "session.lock"
    assert SL.active_remote(gone) is None
    err = capsys.readouterr().err
    assert "NOT checked" in err and str(gone) in err


def test_reachable_share_with_no_lock_is_silent(tmp_path, capsys):
    assert SL.active_remote(tmp_path / "session.lock") is None
    assert capsys.readouterr().err == ""


def test_unreadable_remote_lock_is_retried(tmp_path, monkeypatch):
    lock = tmp_path / "session.lock"
    _hb_lock(lock, age=1)
    real = SL.read
    calls = {"n": 0}

    def flaky(path=lock):
        calls["n"] += 1
        return None if calls["n"] < 3 else real(path)
    monkeypatch.setattr(SL, "read", flaky)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    assert SL.active_remote(lock) is not None and calls["n"] == 3


def test_remote_paths_come_from_the_environment():
    sep = os.pathsep
    env = {SL.REMOTE_ENV: f"share_a/state/session.lock{sep}share_b/x.lock{sep} "}
    assert [Path(p).as_posix() for p in SL.remote_paths(env)] == ["share_a/state/session.lock", "share_b/x.lock"]
    assert SL.remote_paths({}) == []


def test_active_anywhere_sees_a_remote_session(tmp_path):
    remote = tmp_path / "nas" / "session.lock"
    remote.parent.mkdir()
    _hb_lock(remote, age=3)
    found = SL.active_anywhere(tmp_path / "local.lock", {SL.REMOTE_ENV: str(remote)})
    assert found and found["remote"] == str(remote)


def test_active_anywhere_prefers_the_local_session(tmp_path):
    remote = tmp_path / "nas.lock"
    _hb_lock(remote, age=3)
    with SL.held("paper", "mcl", path=tmp_path / "local.lock"):
        found = SL.active_anywhere(tmp_path / "local.lock", {SL.REMOTE_ENV: str(remote)})
        assert found and "remote" not in found


def test_active_anywhere_without_remote_config_is_just_the_local_check(tmp_path):
    assert SL.active_anywhere(tmp_path / "local.lock", {}) is None


def test_describe_names_the_machine_and_heartbeat_age(tmp_path):
    lock = tmp_path / "session.lock"
    _hb_lock(lock, age=12, tree="/app")
    info = SL.active_remote(lock)
    text = SL.describe(info)
    assert "nas-box" in text and "heartbeat" in text and "/app" in text
    assert str(lock) in text
    # a legacy lock still describes without the new fields
    assert "mcl" in SL.describe({"mode": "paper", "strategy": "mcl", "pid": 1, "started_at": "x"})


def test_cli_reports_where_it_looked_and_the_verdict(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(SL, "LOCK_PATH", tmp_path / "local.lock")
    assert SL.main([], {}) == 0
    out = capsys.readouterr().out
    assert "no live session" in out and "SESSION_LOCK_REMOTE is not set" in out

    remote = tmp_path / "nas.lock"
    _hb_lock(remote, age=4)
    monkeypatch.setattr(SL.active_anywhere, "__defaults__", (tmp_path / "local.lock", None))
    assert SL.main([], {SL.REMOTE_ENV: str(remote)}) == 1
    out = capsys.readouterr().out
    assert "LIVE SESSION" in out and "nas-box" in out and str(remote) in out
