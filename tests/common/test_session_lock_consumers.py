#!/usr/bin/env python3
"""The three tools that must refuse while a session runs ON THE NAS.

session_lock.active() only sees this PC's disk. The NAS trader's lock lives on
another machine, so each guard has to ask active_anywhere() or the NAS session
is invisible and a backtest throttles it -- silently, because IB reports
throttling as empty results. Each test sets up a live lock on a pretend share
and checks the real tool turns away from it, so swapping a call back to
active() fails here.
"""
import asyncio
import json
import time
from types import SimpleNamespace

import pytest

from common import session_lock as SL


@pytest.fixture
def nas_session(tmp_path, monkeypatch):
    share = tmp_path / "share" / "state"
    share.mkdir(parents=True)
    lock = share / "session.lock"
    now = time.time()
    lock.write_text(json.dumps({
        "mode": "paper", "strategy": "mcl,mc5", "pid": 7, "host": "nas-box",
        "token": "t", "started_at": "x", "started_epoch": now,
        "heartbeat_epoch": now}), encoding="utf-8")
    monkeypatch.setenv(SL.REMOTE_ENV, str(lock))
    # and no session on this machine
    monkeypatch.setattr(SL, "LOCK_PATH", tmp_path / "local" / "session.lock")
    monkeypatch.setattr(SL.active, "__defaults__", (tmp_path / "local" / "session.lock",))
    monkeypatch.setattr(SL.active_anywhere, "__defaults__",
                        (tmp_path / "local" / "session.lock", None))
    return lock


def test_backtest_refuses_while_the_nas_trades(nas_session, capsys):
    from common import backtest
    rc = asyncio.run(backtest.main_async(SimpleNamespace(force=False)))
    out = capsys.readouterr().out
    assert rc == 1 and "REFUSING" in out and "nas-box" in out


def test_backtest_force_still_skips_the_check(nas_session):
    """--force exists for a reason; the lock check is skipped before anything else."""
    from common import backtest
    src = __import__("inspect").getsource(backtest.main_async)
    assert "None if args.force else session_lock.active_anywhere()" in src


def test_probe_window_refuses_while_the_nas_trades(nas_session, capsys):
    from common import probe_window
    rc = asyncio.run(probe_window.main_async(SimpleNamespace(port=4002)))
    assert rc == 1 and "REFUSING" in capsys.readouterr().out


def test_main_refuses_a_second_session_while_the_nas_trades(nas_session, monkeypatch, capsys):
    import main as M
    import brokers.ibkr.trader as T
    ran = []
    monkeypatch.setattr(T, "main", lambda a: ran.append(a) or 0)
    rc = M.run(["--mode", "dry", "--strategy", "mcl", "--yes"])
    assert rc != 0 and not ran
    assert "already running" in capsys.readouterr().err
