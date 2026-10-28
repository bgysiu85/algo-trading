"""Tests for deploy/nas_trader/probe_gateway.py (W10-0013 sub 4).

Nothing here touches IBKR or the network: a fake IB object stands in for ib_async.IB and a fake `tcp` for the
socket check. Each test proves a verdict can go BOTH ways, so a probe that always says PASS would fail here.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

PROBE_PATH = Path(__file__).resolve().parents[2] / "deploy" / "nas_trader" / "probe_gateway.py"
_spec = importlib.util.spec_from_file_location("probe_gateway", PROBE_PATH)
probe = importlib.util.module_from_spec(_spec)
sys.modules["probe_gateway"] = probe      # @dataclass looks the module up here
_spec.loader.exec_module(probe)


class Event(list):
    """ib_async-style event: `ev += handler`, `ev -= handler`, `ev.emit(...)`."""

    def __iadd__(self, h):
        self.append(h)
        return self

    def __isub__(self, h):
        if h in self:
            self.remove(h)
        return self

    def emit(self, *args):
        for h in list(self):
            h(*args)


class FakeIB:
    def __init__(self, accounts=("DU1234567",), connect_error=None, server_time=None,
                 whatif="accept", bars=3):
        self.accounts = list(accounts)
        self.connect_error = connect_error
        self.server_time = server_time or datetime.now(timezone.utc)
        self.whatif = whatif                      # "accept" | "readonly" | "silent"
        self.n_bars = bars
        self.errorEvent = Event()
        self.client = SimpleNamespace(serverVersion=lambda: 178)
        self.connected = None
        self.disconnected = False
        self.whatif_sent = []

    def connect(self, host, port, clientId, timeout, readonly):
        if self.connect_error:
            raise self.connect_error
        self.connected = (host, port, clientId, readonly)

    def disconnect(self):
        self.disconnected = True

    def managedAccounts(self):
        return self.accounts

    def reqCurrentTime(self):
        return self.server_time

    def qualifyContracts(self, c):
        return [c]

    def reqHistoricalData(self, contract, **kw):
        return [SimpleNamespace(date=f"2026-10-2{i}", close=500.0 + i) for i in range(self.n_bars)]

    def run(self, awaitable):
        return asyncio.run(awaitable)

    def whatIfOrderAsync(self, contract, order):
        self.whatif_sent.append(order)
        fake = self

        async def answer():
            if fake.whatif == "accept":
                return SimpleNamespace(status="PreSubmitted")
            if fake.whatif == "readonly":
                fake.errorEvent.emit(7, 321, "Error validating request - Read-Only API", None)
            await asyncio.sleep(3600)             # the real future never resolves after a 321 either
        return answer()


def run_main(argv, ibs, tcp=lambda h, p, timeout=3.0: True):
    """Run main() with a factory that hands out the given fakes in order. Returns (exit code, output text)."""
    lines = []
    it = iter(ibs)
    code = probe.main(argv, ib_factory=lambda: next(it), tcp=tcp, out=lines.append)
    return code, "\n".join(lines)


# ---------------------------------------------------------------- refusals
@pytest.mark.parametrize("port", [4001, 4003, 7496, 7498])
def test_live_ports_are_refused(port):
    code, text = run_main(["--port", str(port)], [])
    assert code == 2 and "REFUSED" in text


def test_unknown_port_is_refused_and_live_port_in_ports_list_is_refused():
    assert run_main(["--port", "5555"], [])[0] == 2
    assert run_main(["--ports", "4002,4003"], [])[0] == 2


# ---------------------------------------------------------------- the happy path
def test_all_good_is_a_pass_and_uses_a_read_only_session():
    ib = FakeIB()
    code, text = run_main(["--bars", "SPY"], [ib])
    assert code == 0, text
    assert "VERDICT PASS" in text
    assert ib.connected == ("127.0.0.1", 4002, probe.CLIENT_READONLY, True)       # read-only session
    assert "paper account(s): DU1234567" in text
    assert "3 daily bars" in text and ib.disconnected


# ---------------------------------------------------------------- it can fail
def test_closed_api_port_is_a_fail_and_no_session_is_attempted():
    ib = FakeIB()
    code, text = run_main([], [ib], tcp=lambda h, p, timeout=3.0: p != 4002)
    assert code == 1 and "4002" in text and "CLOSED" in text
    assert ib.connected is None


def test_closed_relay_port_alone_is_only_information():
    """Inside the Gateway's namespace 4004 can be closed while 4002 works (it is the API that matters)."""
    code, text = run_main([], [FakeIB()], tcp=lambda h, p, timeout=3.0: p == 4002)
    assert code == 0 and "4004" in text and "is closed" in text


def test_connection_refused_and_handshake_timeout_are_explained_differently():
    code, text = run_main([], [FakeIB(connect_error=ConnectionRefusedError("refused"))])
    assert code == 1 and "not up" in text
    code, text = run_main([], [FakeIB(connect_error=asyncio.TimeoutError())])
    assert code == 1 and "never answered" in text


def test_a_live_looking_account_is_a_fail():
    code, text = run_main([], [FakeIB(accounts=("DU1234567", "U7654321"))])
    assert code == 1 and "U7654321" in text and "STOP" in text


def test_no_accounts_is_a_fail():
    assert run_main([], [FakeIB(accounts=())])[0] == 1


def test_clock_drift_is_a_warning_not_a_fail():
    ib = FakeIB(server_time=datetime.now(timezone.utc) - timedelta(seconds=40))
    code, text = run_main([], [ib])
    assert code == 0 and "PASS with warnings" in text and "NTP" in text


def test_no_bars_is_a_fail():
    code, text = run_main(["--bars", "SPY"], [FakeIB(bars=0)])
    assert code == 1 and "no daily bars" in text


# ---------------------------------------------------------------- risk B (Read-Only API)
def test_orders_pass_when_the_whatif_is_answered_and_nothing_is_placed():
    first, second = FakeIB(), FakeIB(whatif="accept")
    code, text = run_main(["--check-orders"], [first, second])
    assert code == 0 and "Read-Only API is OFF" in text and "Nothing was placed" in text
    assert second.connected[3] is False                                  # this session is not read-only
    assert len(second.whatif_sent) == 1 and second.whatif_sent[0].orderType == "LMT"
    assert second.disconnected


def test_orders_fail_on_error_321():
    code, text = run_main(["--check-orders", "--timeout", "1"], [FakeIB(), FakeIB(whatif="readonly")])
    assert code == 1 and "Read-Only API is ON" in text and "READ_ONLY_API=no" in text


def test_orders_silence_is_inconclusive_never_a_pass():
    code, text = run_main(["--check-orders", "--timeout", "0.2"], [FakeIB(), FakeIB(whatif="silent")])
    assert code == 0 and "INCONCLUSIVE" in text and "PASS with warnings" in text
    assert "Read-Only API is OFF" not in text


def test_orders_session_that_cannot_connect_is_a_fail():
    code, text = run_main(["--check-orders"], [FakeIB(), FakeIB(connect_error=ConnectionRefusedError("x"))])
    assert code == 1


def test_orders_check_is_skipped_when_the_api_session_failed():
    code, text = run_main(["--check-orders"], [FakeIB(connect_error=ConnectionRefusedError("x"))])
    names = [ln.split()[1] for ln in text.splitlines() if len(ln.split()) > 1]
    assert code == 1 and "orders" not in names


# ---------------------------------------------------------------- the real socket check
def test_tcp_open_is_true_for_a_listener_and_false_for_a_closed_port():
    import socket
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        assert probe.tcp_open("127.0.0.1", port, timeout=1.0) is True
    finally:
        srv.close()
    assert probe.tcp_open("127.0.0.1", port, timeout=0.5) is False
