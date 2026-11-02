"""Tests for the IBKR paper bridge (W18-0002). A fake IB stands in for the Gateway: nothing here connects to anything."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from desk import bridge, decision
from desk import config as cfgmod
from desk import pipeline

NOW = datetime(2026, 11, 2, 15, 0, tzinfo=timezone.utc)      # 10:00 in New York
TODAY = "2026-11-02"


def make_cfg(tmp_path=None, **rules):
    cfg = cfgmod.load_config()
    cfg["paper_rules"].update(rules)
    if tmp_path is not None:
        cfg["runs_dir"] = str(tmp_path / "runs")
    return cfg


def brow(ticker="MPC", conv=7, rr=3.0, **over):
    r = {c: "" for c in decision.CSV_COLUMNS}
    r.update(run_date=TODAY, ticker=ticker, rating="Buy", actionable="True", conviction=str(conv), entry="100.0",
             stop="92.0", target="124.0", horizon_days="120", size_shares="1", risk_per_share="8.0",
             reward_risk=str(rr), last_close="100.0", atr14="3.0", watch="False")
    r.update({k: str(v) for k, v in over.items()})
    return r


def hold_row(ticker="AMZN"):
    return brow(ticker, rating="Hold", actionable="False", entry="", stop="", target="", horizon_days="",
                size_shares="0", watch="True", plan_trigger="close_above 101.5", plan_revisit_on="2026-11-04",
                plan_zone_low="102", plan_zone_high="105", plan_stop="95", plan_target="125")


# ------------------------------------------------------------------- fakes

class FakeTrade:
    def __init__(self, contract, order, status="PreSubmitted"):
        self.contract, self.order = contract, order
        self.orderStatus = SimpleNamespace(status=status)
        self.log = []


class FakeIB:
    def __init__(self, accounts=("DU1234567",), positions=(), open_orders=(), funds=19000.0, bad_status=None,
                 fail_on_order=None):
        self.accounts, self._positions, self._open, self.funds = list(accounts), list(positions), list(open_orders), funds
        self.bad_status, self.fail_on_order = bad_status, fail_on_order
        self.connected_with, self.placed, self.cancelled, self.disconnected = None, [], [], False
        self._id = 100
        self.client = SimpleNamespace(getReqId=self._next_id)

    def _next_id(self):
        self._id += 1
        return self._id

    def connect(self, host, port, clientId, timeout, readonly):
        self.connected_with = dict(host=host, port=port, clientId=clientId, readonly=readonly)

    def disconnect(self):
        self.disconnected = True

    def managedAccounts(self):
        return self.accounts

    def positions(self):
        return self._positions

    def reqAllOpenOrders(self):
        return self._open

    def accountValues(self):
        if self.funds is None:
            return []
        return [SimpleNamespace(tag="NetLiquidation", value="19000", currency="USD"),
                SimpleNamespace(tag="AvailableFunds", value=str(self.funds), currency="USD")]

    def qualifyContracts(self, c):
        c.conId = 1
        return [c]

    def placeOrder(self, contract, order):
        if self.fail_on_order is not None and len(self.placed) == self.fail_on_order:
            raise RuntimeError("socket dropped")
        status = self.bad_status if self.bad_status and order.orderType == "STP" else "PreSubmitted"
        t = FakeTrade(contract, order, status)
        if status == "Inactive":
            t.log.append(SimpleNamespace(message="stop price too close to market"))
        self.placed.append(t)
        return t

    def cancelOrder(self, order):
        self.cancelled.append(order.orderId)

    def sleep(self, s):
        pass


def pos(symbol, qty, sec="STK"):
    return SimpleNamespace(contract=SimpleNamespace(symbol=symbol, secType=sec), position=qty)


def open_trade(symbol, ref, action="BUY", status="Submitted"):
    return FakeTrade(SimpleNamespace(symbol=symbol), SimpleNamespace(orderRef=ref, action=action), status)


def stock(symbol, exch, cur, primaryExchange=None):
    return SimpleNamespace(symbol=symbol, conId=0)


def order(**kw):
    return SimpleNamespace(**kw)


# ------------------------------------------------------------- the rules

def test_good_row_is_accepted_and_rounded():
    errs, p = bridge.check_row(brow(entry="100.004", target="124.0"), make_cfg())
    assert errs == [] and p == {"entry": 100.0, "stop": 92.0, "target": 124.0, "shares": 1, "horizon_days": 120}


@pytest.mark.parametrize("over, fragment", [
    ({"ticker": "ZZZZ"}, "not in the desk's list"),
    ({"rating": "Hold"}, "not Buy/Overweight"),
    ({"rating": "Sell"}, "not Buy/Overweight"),
    ({"stop": "100.0"}, "stop < entry < target"),
    ({"target": "100.0"}, "stop < entry < target"),
    ({"stop": "0"}, "positive prices"),
    ({"entry": ""}, "positive prices"),
    ({"entry": "abc"}, "positive prices"),
    ({"target": "nan"}, "positive prices"),
    ({"size_shares": "2"}, "size_shares must be 1"),
    ({"size_shares": "0"}, "size_shares must be 1"),
    ({"size_shares": "1.5"}, "size_shares must be 1"),
    ({"horizon_days": ""}, "horizon_days"),
    ({"horizon_days": "0"}, "horizon_days"),
    ({"horizon_days": "181"}, "horizon_days"),
    ({"last_close": ""}, "no last_close"),
    ({"entry": "103.0", "stop": "95", "target": "130"}, "above the last close"),
])
def test_each_bad_row_is_rejected(over, fragment):
    errs, p = bridge.check_row(brow(**over), make_cfg())
    assert p is None and any(fragment in e for e in errs), errs


def test_entry_slightly_above_close_is_allowed_below_is_always_fine():
    assert bridge.check_row(brow(entry="101.9", stop="95", target="130"), make_cfg())[0] == []
    assert bridge.check_row(brow(entry="80", stop="75", target="100"), make_cfg())[0] == []


def test_short_selling_config_is_refused():
    errs, _ = bridge.check_row(brow(), make_cfg(long_only=False))
    assert any("long_only" in e for e in errs)


# --------------------------------------------------------------- planning

def outcomes(res):
    return {r["ticker"]: r["outcome"] for r in res}


def test_only_todays_actionable_rows_matter_and_holds_are_ignored_not_ordered():
    rows = [brow("MPC"), brow("AMZN", run_date="2026-11-01"), hold_row("INTC"),
            brow("PBF", rating="Underweight", actionable="False", entry="", stop="", target="", watch="False")]
    res = bridge.plan(rows, make_cfg(), TODAY, bridge.BrokerState())
    assert outcomes(res) == {"MPC": "READY", "INTC": "IGNORED"}                  # yesterday's AMZN and the no-position PBF: no line
    assert "no order without a fresh Buy/Overweight" in [r for r in res if r["ticker"] == "INTC"][0]["reason"]


def test_a_corrupt_row_that_is_both_watch_and_actionable_is_never_ordered():
    res = bridge.plan([brow("MPC", watch="True", plan_trigger="close_above 100", plan_revisit_on="2026-11-04")],
                      make_cfg(), TODAY, bridge.BrokerState())
    assert outcomes(res) == {"MPC": "IGNORED"}


def test_a_row_flagged_actionable_but_rated_hold_is_rejected_not_ordered():
    res = bridge.plan([brow("MPC", rating="Hold")], make_cfg(), TODAY, bridge.BrokerState())
    assert outcomes(res) == {"MPC": "REJECTED"}


def test_ranking_decides_who_gets_the_free_slots():
    rows = [brow("MPC", 6, 2.0), brow("AMZN", 9, 1.6), brow("INTC", 6, 3.0), brow("PBF", 3, 5.0)]
    res = bridge.plan(rows, make_cfg(max_open_positions=2), TODAY, bridge.BrokerState())
    assert [r["ticker"] for r in res] == ["AMZN", "INTC", "MPC", "PBF"]               # conviction, then reward:risk
    assert [r["outcome"] for r in res] == ["READY", "READY", "SKIPPED", "SKIPPED"]
    assert "position cap" in res[2]["reason"]


def test_existing_positions_and_pending_entries_use_up_slots():
    st = bridge.BrokerState(checked=True, positions={"BAC": 1.0, "SPY": 5.0}, entry_orders={"CNC"}, funds=19000.0)
    rows = [brow("MPC", 9), brow("AMZN", 8)]
    res = bridge.plan(rows, make_cfg(max_open_positions=3), TODAY, st)      # BAC + CNC count; SPY is not a desk name
    assert outcomes(res) == {"MPC": "READY", "AMZN": "SKIPPED"}


def test_already_held_pending_or_busy_symbols_are_skipped():
    st = bridge.BrokerState(checked=True, positions={"MPC": 1.0}, entry_orders={"AMZN"}, other_orders={"INTC"}, funds=19000.0)
    res = bridge.plan([brow("MPC"), brow("AMZN"), brow("INTC"), brow("PBF")], make_cfg(), TODAY, st)
    assert outcomes(res) == {"MPC": "SKIPPED", "AMZN": "SKIPPED", "INTC": "SKIPPED", "PBF": "READY"}


def test_placed_today_is_not_placed_twice():
    res = bridge.plan([brow("MPC")], make_cfg(), TODAY, bridge.BrokerState(), placed_today={"MPC"})
    assert outcomes(res) == {"MPC": "SKIPPED"} and "already placed" in res[0]["reason"]


def test_funds_are_checked_only_when_the_account_was_looked_at():
    rows = [brow("MPC", 9, entry="100", stop="92", target="124"), brow("AMZN", 8)]
    low = bridge.BrokerState(checked=True, funds=150.0)
    res = bridge.plan(rows, make_cfg(), TODAY, low)
    assert outcomes(res) == {"MPC": "READY", "AMZN": "SKIPPED"} and "funds" in res[1]["reason"]
    unknown = bridge.BrokerState(checked=True, funds=None)
    assert set(outcomes(bridge.plan(rows, make_cfg(), TODAY, unknown)).values()) == {"SKIPPED"}
    assert set(outcomes(bridge.plan(rows, make_cfg(), TODAY, bridge.BrokerState())).values()) == {"READY"}   # offline


def test_ticker_filter():
    res = bridge.plan([brow("MPC"), brow("AMZN")], make_cfg(), TODAY, bridge.BrokerState(), only="AMZN")
    assert outcomes(res) == {"AMZN": "READY"}


# ----------------------------------------------------------------- orders

def ready(**over):
    return {"ticker": "MPC", "run_date": TODAY, "rating": "Buy", "conviction": "7", "outcome": "READY", "reason": "",
            "entry": 100.0, "stop": 92.0, "target": 124.0, "shares": 1, "horizon_days": 120, **over}


def test_bracket_shape():
    parent, tp, sl = bridge.order_specs(ready())
    assert (parent["action"], parent["orderType"], parent["lmtPrice"], parent["tif"]) == ("BUY", "LMT", 100.0, "DAY")
    assert (tp["action"], tp["orderType"], tp["lmtPrice"], tp["tif"]) == ("SELL", "LMT", 124.0, "GTC")
    assert (sl["action"], sl["orderType"], sl["auxPrice"], sl["tif"]) == ("SELL", "STP", 92.0, "GTC")
    assert [s["transmit"] for s in (parent, tp, sl)] == [False, False, True]          # the last one releases all three
    assert {s["orderRef"] for s in (parent, tp, sl)} == {"desk:2026-11-02:MPC"}
    assert all(s["totalQuantity"] == 1 and s["outsideRth"] is False for s in (parent, tp, sl))


def test_specs_are_valid_ib_async_order_fields():
    ib_async = pytest.importorskip("ib_async")
    for i, s in enumerate(bridge.order_specs(ready())):
        o = ib_async.Order(orderId=10 + i, **s)
        assert o.orderRef == "desk:2026-11-02:MPC" and o.totalQuantity == 1


def test_hold_until_is_run_date_plus_horizon():
    assert bridge.hold_until(ready(horizon_days=120)) == "2027-03-02"


def test_place_bracket_sends_parent_first_children_linked_and_returns_ids():
    ib = FakeIB()
    done = bridge.place_bracket(ib, ready(), stock, order, 0)
    assert done["outcome"] == "PLACED" and done["ids"] == [101, 102, 103] and done["broker_status"] == "PreSubmitted"
    parent, tp, sl = (t.order for t in ib.placed)
    assert parent.orderId == 101 and not hasattr(parent, "parentId")
    assert tp.parentId == 101 and sl.parentId == 101 and sl.transmit is True and ib.cancelled == []
    assert ib.placed[0].contract.conId == 1                                           # qualified first


def test_a_refused_leg_cancels_the_whole_bracket_so_no_entry_is_left_without_a_stop():
    ib = FakeIB(bad_status="Inactive")
    done = bridge.place_bracket(ib, ready(), stock, order, 0)
    assert done["outcome"] == "REJECTED" and "stop price too close" in done["reason"]
    assert ib.cancelled == [101, 102, 103]


def test_a_send_failure_cancels_what_was_sent():
    ib = FakeIB(fail_on_order=2)
    done = bridge.place_bracket(ib, ready(), stock, order, 0)
    assert done["outcome"] == "ERROR" and "socket dropped" in done["reason"] and ib.cancelled == [101, 102]


# ------------------------------------------------------------- the broker

def test_live_ports_and_unknown_ports_are_refused_before_any_connection():
    for port, word in ((4001, "LIVE"), (7496, "LIVE"), (4444, "not a known paper port")):
        cfg = make_cfg()
        cfg["ibkr"]["port"] = port
        ib = FakeIB()
        with pytest.raises(bridge.BridgeError, match=word) as e:
            bridge._connect(cfg, False, ib)
        assert e.value.code == 2 and ib.connected_with is None


def test_a_non_paper_account_is_refused_and_disconnected():
    ib = FakeIB(accounts=["DU1", "U9999999"])
    with pytest.raises(bridge.BridgeError, match="not all paper") as e:
        bridge._connect(make_cfg(), False, ib)
    assert e.value.code == 2 and ib.disconnected


def test_connect_uses_the_bridge_client_id_and_passes_readonly_through():
    ib = FakeIB()
    bridge._connect(make_cfg(), True, ib)
    assert ib.connected_with == dict(host="127.0.0.1", port=4002, clientId=92, readonly=True)


def test_connect_failure_is_a_broker_error():
    ib = FakeIB()
    ib.connect = lambda *a, **k: (_ for _ in ()).throw(ConnectionRefusedError("nope"))
    with pytest.raises(bridge.BridgeError, match="cannot connect") as e:
        bridge._connect(make_cfg(), True, ib)
    assert e.value.code == 3


def test_read_state_sees_stocks_desk_entries_other_orders_and_funds():
    ib = FakeIB(positions=[pos("BAC", 1.0), pos("MCL", 2.0, "FUT"), pos("CNC", 0.0)],
                open_orders=[open_trade("AMZN", "desk:2026-11-02:AMZN"), open_trade("MPC", "", "SELL"),
                             open_trade("INTC", "desk:2026-11-01:INTC", status="Cancelled")], funds=12345.5)
    st = bridge.read_state(ib)
    assert st.checked and st.positions == {"BAC": 1.0} and st.entry_orders == {"AMZN"}
    assert st.other_orders == {"MPC"} and st.funds == 12345.5


def test_read_state_without_funds_leaves_none():
    assert bridge.read_state(FakeIB(funds=None)).funds is None


# -------------------------------------------------------------------- log

def entry(t, outcome, **over):
    return {"run_date": TODAY, "ticker": t, "rating": "Buy", "conviction": "7", "outcome": outcome, "reason": "",
            "entry": 100.0, "stop": 92.0, "target": 124.0, "shares": 1, **over}


def test_log_inserts_replaces_sorts_and_keeps_the_column_order(tmp_path):
    p = tmp_path / "orders.csv"
    bridge.log_orders(p, [entry("MPC", "SKIPPED", reason="cap"), entry("AMZN", "PLACED")], NOW)
    bridge.log_orders(p, [entry("MPC", "PLACED", reason="")], NOW)               # a later run replaces a SKIPPED row
    rows = bridge.read_orders(p)
    assert [(r["ticker"], r["outcome"]) for r in rows] == [("AMZN", "PLACED"), ("MPC", "PLACED")]
    assert list(rows[0].keys()) == bridge.ORDER_COLUMNS and rows[0]["logged_at_utc"] == "2026-11-02T15:00:00Z"


def test_a_placed_row_is_never_overwritten_by_a_later_skip(tmp_path):
    p = tmp_path / "orders.csv"
    bridge.log_orders(p, [entry("MPC", "PLACED", parent_order_id=101)], NOW)
    bridge.log_orders(p, [entry("MPC", "SKIPPED", reason="already placed today")], NOW)
    rows = bridge.read_orders(p)
    assert len(rows) == 1 and rows[0]["outcome"] == "PLACED" and rows[0]["parent_order_id"] == "101"


def test_log_entry_carries_risk_hold_until_and_ids():
    e = bridge.log_entry(ready(), {"outcome": "PLACED", "reason": "", "ids": [5, 6, 7], "broker_status": "Submitted"})
    assert (e["risk_usd"], e["hold_until"], e["order_ref"]) == (8.0, "2027-03-02", "desk:2026-11-02:MPC")
    assert (e["parent_order_id"], e["take_profit_order_id"], e["stop_order_id"]) == (5, 6, 7)
    skipped = bridge.log_entry({**ready(), "outcome": "SKIPPED", "reason": "cap"})
    assert skipped["outcome"] == "SKIPPED" and skipped["order_ref"] == ""


# ------------------------------------------------------- command line (end to end)

def setup(tmp_path, rows, **cfg_over):
    cfg = make_cfg(tmp_path)
    cfg.update(cfg_over)
    cfgp = tmp_path / "c.json"
    cfgp.write_text(json.dumps(cfg), encoding="utf-8")
    dp = cfgmod.runs_dir(cfg) / pipeline.DECISIONS_CSV
    dp.parent.mkdir(parents=True, exist_ok=True)
    with dp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=decision.CSV_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    return cfgp, cfgmod.runs_dir(cfg) / pipeline.ORDERS_CSV


def run(argv, ib=None, **kw):
    return bridge.main(argv, _ib=ib, _stock=stock, _order=order, now=NOW, **kw)


class Untouchable:
    def __getattr__(self, name):
        raise AssertionError(f"offline dry-run touched the broker ({name})")


def test_offline_dry_run_never_touches_the_broker_or_writes_orders(tmp_path, capsys):
    cfgp, orders = setup(tmp_path, [brow("MPC"), hold_row("AMZN")])
    assert run(["--config", str(cfgp)], ib=Untouchable()) == 0
    out = capsys.readouterr().out
    assert "MODE offline" in out and "NOT checked" in out
    assert "WOULD_PLACE MPC Buy conv 7: BUY 1 @ 100.00 (day limit), take profit 124.00, stop 92.00" in out
    assert "IGNORED AMZN" in out and not orders.exists()


def test_check_is_read_only_and_places_nothing(tmp_path, capsys):
    cfgp, orders = setup(tmp_path, [brow("MPC")])
    ib = FakeIB(positions=[pos("BAC", 1.0)])
    assert run(["--check", "--config", str(cfgp)], ib=ib) == 0
    out = capsys.readouterr().out
    assert ib.connected_with["readonly"] is True and ib.placed == [] and not orders.exists()
    assert "1 stock positions" in out and "available funds $19,000.00" in out and "WOULD_PLACE MPC" in out
    assert ib.disconnected


def test_place_sends_the_bracket_logs_it_and_a_second_run_does_not_repeat_it(tmp_path, capsys):
    cfgp, orders = setup(tmp_path, [brow("MPC"), brow("AMZN", 9), hold_row("INTC")])
    ib = FakeIB()
    assert run(["--place", "--config", str(cfgp)], ib=ib) == 0
    assert ib.connected_with["readonly"] is False and len(ib.placed) == 6 and ib.disconnected
    rows = {r["ticker"]: r for r in bridge.read_orders(orders)}
    assert set(rows) == {"MPC", "AMZN"} and rows["MPC"]["outcome"] == "PLACED"
    assert rows["AMZN"]["parent_order_id"] == "101" and rows["MPC"]["parent_order_id"] == "104"     # AMZN ranked first
    assert rows["MPC"]["hold_until"] == "2027-03-02" and rows["MPC"]["risk_usd"] == "8.0"
    capsys.readouterr()
    ib2 = FakeIB()
    assert run(["--place", "--config", str(cfgp)], ib=ib2) == 0
    assert ib2.placed == [] and "already placed today" in capsys.readouterr().out


def test_place_with_a_ticker_filter_touches_only_that_ticker(tmp_path):
    cfgp, orders = setup(tmp_path, [brow("MPC"), brow("AMZN", 9)])
    ib = FakeIB()
    assert run(["--place", "--ticker", "mpc", "--config", str(cfgp)], ib=ib) == 0
    assert {t.contract.symbol for t in ib.placed} == {"MPC"} and len(ib.placed) == 3


def test_place_logs_rejections_and_skips_too(tmp_path):
    cfgp, orders = setup(tmp_path, [brow("MPC"), brow("AMZN", size_shares=3)])
    ib = FakeIB(positions=[pos("MPC", 1.0)])
    assert run(["--place", "--config", str(cfgp)], ib=ib) == 0
    rows = {r["ticker"]: r for r in bridge.read_orders(orders)}
    assert rows["MPC"]["outcome"] == "SKIPPED" and rows["AMZN"]["outcome"] == "REJECTED" and ib.placed == []


def test_a_refused_bracket_exits_nonzero_logs_it_and_leaves_no_live_orders(tmp_path):
    cfgp, orders = setup(tmp_path, [brow("MPC")])
    ib = FakeIB(fail_on_order=1)
    assert run(["--place", "--config", str(cfgp)], ib=ib) == 3
    assert bridge.read_orders(orders)[0]["outcome"] == "ERROR" and ib.cancelled == [101]


def test_live_port_is_refused_with_exit_2_and_nothing_sent(tmp_path, capsys):
    cfg = make_cfg(tmp_path)
    cfg["ibkr"]["port"] = 4001
    cfgp, orders = setup(tmp_path, [brow("MPC")], ibkr=cfg["ibkr"])
    ib = FakeIB()
    assert run(["--place", "--config", str(cfgp)], ib=ib) == 2
    assert ib.connected_with is None and ib.placed == [] and "BRIDGE REFUSED" in capsys.readouterr().out


def test_no_decisions_file_and_nothing_actionable(tmp_path, capsys):
    cfgp, _ = setup(tmp_path, [hold_row("AMZN")])
    assert run(["--config", str(cfgp)], ib=Untouchable()) == 0
    assert "IGNORED AMZN" in capsys.readouterr().out
    cfgp2 = tmp_path / "empty" / "c.json"
    cfgp2.parent.mkdir()
    cfg = make_cfg(tmp_path / "empty")
    cfgp2.write_text(json.dumps(cfg), encoding="utf-8")
    assert run(["--config", str(cfgp2)], ib=Untouchable()) == 1


def test_check_and_place_cannot_be_combined(tmp_path):
    cfgp, _ = setup(tmp_path, [brow("MPC")])
    with pytest.raises(SystemExit):
        run(["--check", "--place", "--config", str(cfgp)])


def test_stale_decisions_are_never_ordered(tmp_path, capsys):
    cfgp, orders = setup(tmp_path, [brow("MPC", run_date="2026-11-01")])
    ib = FakeIB()
    assert run(["--place", "--config", str(cfgp)], ib=ib) == 0
    assert ib.placed == [] and "no Buy/Overweight decisions dated 2026-11-02" in capsys.readouterr().out


# ------------------------------------------------------------ shipped config

def test_shipped_bridge_config_is_safe_and_its_client_id_is_free():
    cfg = cfgmod.load_config()
    br = bridge.bridge_cfg(cfg)
    assert br["client_id"] not in (17, 55, 77, 88, cfg["ibkr"]["client_id"])
    assert cfg["ibkr"]["port"] in bridge.fetch_bars.PAPER_PORTS
    assert 0 <= br["max_entry_above_close_pct"] <= 5
