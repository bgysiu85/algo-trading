"""W10-0021: the trader waits for the Gateway at start instead of quitting on the first refused connection."""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from brokers.ibkr import trader as T

ET = ZoneInfo("America/New_York")


class FakeIB:
    def __init__(self, refuse_n, exc=ConnectionRefusedError("[Errno 111] refused")):
        self.refuse_n, self.exc, self.calls = refuse_n, exc, 0

    async def connectAsync(self, host, port, clientId):
        self.calls += 1
        if self.calls <= self.refuse_n:
            raise self.exc


class FakeTG:
    def __init__(self):
        self.sent = []

    def send(self, msg, force=False):
        self.sent.append(msg)


def run(ib, wait_s, now=(3, 39), tg=None, retry_s=15.0):
    sleeps = []

    async def fake_sleep(s):
        sleeps.append(s)
        clock["t"] += s

    clock = {"t": 0.0}
    import time as _time
    orig = _time.monotonic
    _time.monotonic = lambda: clock["t"]
    try:
        asyncio.run(T.connect_with_retry(
            ib, "127.0.0.1", 4002, 17, wait_s, tg=tg, retry_s=retry_s,
            now_fn=lambda: datetime(2026, 11, 3, *now, tzinfo=ET), sleep=fake_sleep))
    finally:
        _time.monotonic = orig
    return sleeps


def test_replay_of_3_nov_refused_then_accepts_runs():
    ib = FakeIB(refuse_n=5)
    sleeps = run(ib, 600)
    assert ib.calls == 6 and sleeps == [15.0] * 5


def test_first_try_success_never_sleeps():
    ib = FakeIB(refuse_n=0)
    assert run(ib, 600) == [] and ib.calls == 1


def test_default_zero_is_the_old_single_attempt():
    ib, tg = FakeIB(refuse_n=1), FakeTG()
    with pytest.raises(ConnectionRefusedError):
        run(ib, 0, tg=tg)
    assert ib.calls == 1 and tg.sent == []


def test_gives_up_after_the_wait_reraises_and_sends_one_telegram():
    ib, tg = FakeIB(refuse_n=10**6), FakeTG()
    with pytest.raises(ConnectionRefusedError):
        run(ib, 60, tg=tg)
    assert ib.calls == 5                       # 0, 15, 30, 45 retried; the 5th finds no time left for another wait
    assert len(tg.sent) == 1 and "could not reach" in tg.sent[0]


def test_never_retries_past_session_end():
    ib, tg = FakeIB(refuse_n=10**6), FakeTG()
    with pytest.raises(ConnectionRefusedError):
        run(ib, 600, now=(9, 30), tg=tg)
    assert ib.calls == 1 and len(tg.sent) == 1 and "session end" in tg.sent[0]


def test_timeout_is_retried_too():
    ib = FakeIB(refuse_n=2, exc=asyncio.TimeoutError())
    run(ib, 600)
    assert ib.calls == 3


def test_a_non_connection_error_is_not_swallowed():
    class Boom(FakeIB):
        async def connectAsync(self, *a, **k):
            raise ValueError("bad clientId")
    with pytest.raises(ValueError):
        run(Boom(0), 600)


def test_live_port_is_refused_before_any_connection_attempt():
    ib_made = []
    orig = T.IB
    T.IB = lambda: ib_made.append(1)
    try:
        args = SimpleNamespace(port=4001, connect_wait_s=600)
        with pytest.raises(SystemExit):
            asyncio.run(T.main_async(args))
    finally:
        T.IB = orig
    assert ib_made == []


def test_trader_default_wait_is_off_and_launcher_default_is_600():
    assert T.build_parser().parse_args([]).connect_wait_s == 0.0
    path = Path(__file__).resolve().parents[2] / "deploy" / "nas_trader" / "run_trader.py"
    spec = importlib.util.spec_from_file_location("run_trader_w10_0021", path)
    rt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rt)
    a = rt.build_args({})
    assert a[a.index("--connect-wait-s") + 1] == "600"
    zero = rt.build_args({"TRADER_CONNECT_WAIT_S": "0"})
    assert zero[zero.index("--connect-wait-s") + 1] == "0"
    for bad in ("abc", "-1", "99999"):
        with pytest.raises(rt.Refused):
            rt.build_args({"TRADER_CONNECT_WAIT_S": bad})
    T.build_parser().parse_args(rt.trader_args(a))      # the trader accepts what the launcher sends


def test_compose_and_env_example_carry_the_setting():
    d = Path(__file__).resolve().parents[2] / "deploy" / "nas_trader"
    assert "TRADER_CONNECT_WAIT_S" in (d / "compose.yaml").read_text(encoding="utf-8")
    assert "TRADER_CONNECT_WAIT_S" in (d / ".env.example").read_text(encoding="utf-8")
