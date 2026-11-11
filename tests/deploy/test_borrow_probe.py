"""W05-0022 / W10-0022: the borrow probe is read-only, paper-only, and writes what it saw."""
from __future__ import annotations

import importlib.util
import json
import re
import sys
import types
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "deploy" / "nas_trader" / "borrow_probe.py"
_spec = importlib.util.spec_from_file_location("borrow_probe", SRC)
bp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bp)

NAN = float("nan")


class FakeStock:
    def __init__(self, symbol, exchange, currency):
        self.symbol = symbol


class FakeTicker:
    def __init__(self, shortable, shares, last, tick_types):
        self.shortable, self.shortableShares, self.last = shortable, shares, last
        self.ticks = [types.SimpleNamespace(tickType=t) for t in tick_types]


class FakeIB:
    instances: list = []

    def __init__(self, accounts=("DUM1",)):
        self.accounts, self.connected, self.cancelled, self.requests = list(accounts), None, [], []
        FakeIB.instances.append(self)

    def connect(self, host, port, clientId, timeout, readonly):
        self.connected = dict(host=host, port=port, clientId=clientId, readonly=readonly)

    def managedAccounts(self):
        return self.accounts

    def qualifyContracts(self, c):
        return [] if c.symbol == "NOPE" else [c]

    def reqMktData(self, c, genericTickList="", snapshot=False, regulatorySnapshot=False):
        self.requests.append((c.symbol, genericTickList))
        if c.symbol == "HARD":
            return FakeTicker(1.0, 0.0, 4.2, [46, 89, 4])
        return FakeTicker(3.0, 250000.0, 5.5, [46, 89, 4, 1])

    def cancelMktData(self, c):
        self.cancelled.append(c.symbol)

    def sleep(self, s):
        pass

    def disconnect(self):
        self.connected = None


@pytest.fixture(autouse=True)
def fake_ib_async(monkeypatch):
    mod = types.ModuleType("ib_async")
    mod.Stock = FakeStock
    monkeypatch.setitem(sys.modules, "ib_async", mod)
    FakeIB.instances.clear()


def test_source_has_no_order_call_and_opens_a_readonly_session():
    code = SRC.read_text(encoding="utf-8")
    assert not re.search(r"placeOrder|whatIf|cancelOrder|LimitOrder|MarketOrder|reqGlobalCancel", code)
    assert "readonly=True" in code and bp.CLIENT_ID == 96


def test_live_and_unknown_ports_are_refused_before_any_connection(tmp_path):
    for port in (4001, 4003, 7496, 7498, 9999):
        assert bp.main(["--symbols", "AAA", "--port", str(port), "--out-dir", str(tmp_path)],
                       ib_factory=FakeIB, out=lambda *_: None) == 1
    assert FakeIB.instances == []


def test_symbols_are_deduplicated_upper_cased_and_capped():
    assert bp.read_symbols("aaa, bbb aaa", None) == ["AAA", "BBB"]
    with pytest.raises(bp.Refused):
        bp.read_symbols(None, None)
    with pytest.raises(bp.Refused):
        bp.read_symbols(",".join(f"S{i}" for i in range(bp.MAX_SYMBOLS + 1)), None)


def test_a_run_records_shortability_and_the_tick_types_seen(tmp_path):
    lines = []
    rc = bp.main(["--symbols", "EASY,HARD,NOPE", "--out-dir", str(tmp_path), "--wait", "0"], ib_factory=FakeIB, out=lines.append)
    assert rc == 0
    ib = FakeIB.instances[0]
    assert ib.connected is None                                            # disconnected at the end
    assert ib.requests == [("EASY", "236"), ("HARD", "236")]
    assert ib.cancelled == ["EASY", "HARD"]
    rows = [json.loads(x) for x in (tmp_path / "borrow_probe.jsonl").read_text(encoding="utf-8").splitlines()]
    by = {r["symbol"]: r for r in rows}
    assert by["EASY"]["shortable_label"] == "easy" and by["EASY"]["shortable_shares"] == 250000.0
    assert by["EASY"]["ticks"] == [1, 4, 46, 89]
    assert by["HARD"]["shortable_label"] == "not shortable" and by["HARD"]["last"] == 4.2
    assert by["NOPE"]["error"] == "did not qualify"
    assert all("at" in r for r in rows)


def test_appends_rather_than_overwrites(tmp_path):
    for _ in range(2):
        bp.main(["--symbols", "EASY", "--out-dir", str(tmp_path), "--wait", "0"], ib_factory=FakeIB, out=lambda *_: None)
    assert len((tmp_path / "borrow_probe.jsonl").read_text(encoding="utf-8").splitlines()) == 2


def test_a_non_paper_account_stops_the_run_and_writes_nothing(tmp_path):
    rc = bp.main(["--symbols", "EASY", "--out-dir", str(tmp_path)], ib_factory=lambda: FakeIB(accounts=("U123",)), out=lambda *_: None)
    assert rc == 1 and not (tmp_path / "borrow_probe.jsonl").exists()
    assert FakeIB.instances[0].requests == []


def test_nan_ticks_become_unknown_not_numbers():
    assert bp._num(NAN) is None and bp._num(None) is None and bp._num("x") is None and bp._num(2) == 2.0
    assert bp.shortable_label(NAN) == "unknown" and bp.shortable_label(2.0) == "available"
