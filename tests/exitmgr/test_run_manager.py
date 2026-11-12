"""run_manager.py: the paper lock at the entry point (rail 10), reconnects, and the dry smoke run against the fake IB."""
from __future__ import annotations

from exitmgr import run_manager
from exitmgr.eventlog import read_events
from tests.exitmgr import smoke_dry
from tests.exitmgr.fake_ib import ACCOUNT, T0, FakeClock, FakeIB, fut


def _main(tmp_path, ib=None, env=None, steps=5):
    clock = ib.clock if ib else FakeClock(T0)
    ib = ib or FakeIB(clock)
    out = []
    e = {"XM_OUT_DIR": str(tmp_path / "o")}
    e.update(env or {})
    rc = run_manager.main([], env=e, ib_factory=lambda: ib, clock=clock.now, out=out.append, max_steps=steps)
    return rc, ib, out


def test_live_port_refused_before_connecting(tmp_path):
    rc, ib, out = _main(tmp_path, env={"XM_PORT": "4001"})
    assert rc == 1 and ib.connect_calls == [] and "LIVE" in out[0]


def test_live_mode_refused(tmp_path):
    rc, ib, out = _main(tmp_path, env={"XM_MODE": "live"})
    assert rc == 1 and ib.connect_calls == []


def test_non_paper_account_refused_after_connect(tmp_path):
    ib = FakeIB(FakeClock(T0), accounts=("U7654321",))
    rc, ib, out = _main(tmp_path, ib=ib)
    assert rc == 1 and ib.placed == [] and not ib.connected


def test_paper_account_must_match(tmp_path):
    rc, ib, out = _main(tmp_path, env={"XM_MODE": "paper", "XM_ACCOUNT": "DU0000001"})
    assert rc == 1 and ib.placed == []


def test_connects_as_client_31_readonly_in_dry(tmp_path):
    rc, ib, out = _main(tmp_path)
    assert rc == 0 and ib.connect_calls[0]["clientId"] == 31 and ib.connect_calls[0]["readonly"] is True
    rc, ib, out = _main(tmp_path / "p", env={"XM_MODE": "paper", "XM_ACCOUNT": ACCOUNT})
    assert rc == 0 and ib.connect_calls[0]["readonly"] is False


def test_paper_places_the_stop_through_the_entry_point(tmp_path):
    clock = FakeClock(T0)
    ib = FakeIB(clock)
    ib.at(1, lambda: ib.manual_fill(fut("MCL"), "BOT", 1, 70.0))
    rc, ib, out = _main(tmp_path, ib=ib, env={"XM_MODE": "paper", "XM_ACCOUNT": ACCOUNT}, steps=15)
    assert rc == 0 and [p["type"] for p in ib.placed] == ["STP"]


def test_reconnects_with_backoff_and_reconciles(tmp_path):
    clock = FakeClock(T0)
    ib = FakeIB(clock)
    ib.at(1, ib.drop)
    ib.at(1.1, lambda: setattr(ib, "fail_connect", 1))
    rc, ib, out = _main(tmp_path, ib=ib, steps=40)
    ev = read_events(tmp_path / "o" / "events.jsonl")
    kinds = [e["kind"] for e in ev]
    assert rc == 0 and "reconnect_failed" in kinds and "reconnected" in kinds
    assert [e for e in ev if e["kind"] == "reconcile" and e["reason"] == "reconnect"]


def test_stop_manager_file_ends_the_run(tmp_path):
    clock = FakeClock(T0)
    ib = FakeIB(clock)
    ctl = tmp_path / "o" / "control"
    ib.at(2, lambda: (ctl.mkdir(parents=True, exist_ok=True), (ctl / "STOP_MANAGER").write_text("", encoding="utf-8")))
    rc, ib, out = _main(tmp_path, ib=ib, steps=1000)
    assert rc == 0 and clock.now() < T0.replace(second=10)


def test_dry_smoke_run(tmp_path):
    r = smoke_dry.run(tmp_path / "smoke", echo=lambda s: None)
    assert r["rc"] == 0 and r["placed"] == [] and r["cancelled"] == []
    verbs = [(w[0], w[1], w[2], w[3]) for w in r["would"]]
    assert verbs[0] == ("place", "STP", "SELL", 2)
    assert ("modify", "STP", "SELL", 3) in verbs and ("modify", "STP", "SELL", 2) in verbs
    assert ("place", "MKT", "SELL", 2) in verbs                            # 16:55 flat
    codes = {c for c, _ in r["alerts"]}
    assert {"RAIL7", "ALERT_ONLY", "DISCONNECTED"} <= codes
    assert r["kinds"].get("order_would_cancel", 0) >= 1 and r["connects"] >= 2
