"""common/ui_bridge.py — what the portal sees, and what it may change.

No relay is contacted: the transport is replaced, so these tests are about the
document and the command handling, which is where being wrong costs something.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime, time as dtime
from pathlib import Path

import pytest

from common import ui_bridge


# -- a trader shaped like the real one, and nothing more --------------------
@dataclass
class FakeAdapter:
    name: str
    trail_pct: float = 5.0
    price_min: float = 2.0
    price_max: float = 20.0
    session_end: dtime = dtime(9, 30)


@dataclass
class FakePosition:
    symbol: str
    qty: int
    entry_price: float
    entry_time: datetime | None = None
    trail_pct: float = 5.0
    peak: float = 0.0

    def trail_level(self) -> float:
        return (self.peak or self.entry_price) * (1 - self.trail_pct / 100)


@dataclass
class FakeState:
    symbol: str
    strategy: FakeAdapter
    position: FakePosition | None = None
    blocked: bool = False
    retired: bool = False


@dataclass
class FakeLog:
    path: Path | None = None


@dataclass
class FakeTrader:
    states: dict = field(default_factory=dict)
    strategies: list = field(default_factory=list)
    log: FakeLog = field(default_factory=FakeLog)
    max_positions: int = 2
    session_pnl: float = 0.0
    dry_run: bool = False
    paused: bool = False
    disabled_strategies: set = field(default_factory=set)
    ib: object = None

    def quote(self, st):
        return (10.0, 10.10)


def build_trader(tmp_path: Path | None = None, fills: list[dict] | None = None):
    mcl = FakeAdapter("mcl")
    trader = FakeTrader(strategies=[mcl])
    trader.states[("mcl", "ACVA")] = FakeState(
        "ACVA", mcl, FakePosition("ACVA", 100, 9.50, datetime(2026, 9, 14, 11, 0), peak=10.2))
    trader.states[("mcl", "JLHL")] = FakeState("JLHL", mcl, blocked=True)

    if tmp_path is not None:
        path = tmp_path / "mcl_fills_20260914.csv"
        rows = fills if fills is not None else [
            {"ts_et": "2026-09-14 07:02:11", "strategy": "mcl", "symbol": "WXYZ",
             "action": "BUY", "qty": "100", "filled_qty": "100", "fill_price": "6.55",
             "status": "FILLED", "reason": "entry_signal", "trade_pnl": ""},
            {"ts_et": "2026-09-14 07:09:48", "strategy": "mcl", "symbol": "WXYZ",
             "action": "SELL", "qty": "100", "filled_qty": "100", "fill_price": "6.38",
             "status": "FILLED", "reason": "trailing_stop", "trade_pnl": "-23.26"},
            {"ts_et": "2026-09-14 07:11:00", "strategy": "mcl", "symbol": "FTFT",
             "action": "BUY", "qty": "100", "fill_price": "", "status":
             "SKIPPED_CONCURRENCY_CAP", "reason": "entry_signal", "trade_pnl": ""},
        ]
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=sorted({k for r in rows for k in r}))
            writer.writeheader()
            writer.writerows(rows)
        trader.log = FakeLog(path)
    return trader


def bridge(paper: bool = True) -> ui_bridge.UIBridge:
    b = ui_bridge.UIBridge("http://127.0.0.1:8000", "token", agent_id="proart")
    b.note_account("DUM215828" if paper else "U1234567")
    return b


NOW = datetime(2026, 9, 14, 7, 20, 0)          # 07:20 ET, pre-market


# -- configuration ----------------------------------------------------------
def test_it_stays_off_unless_it_is_configured():
    assert ui_bridge.UIBridge.from_env({}) is None
    assert ui_bridge.UIBridge.from_env({"UI_AGENT_TOKEN": "x"}) is None


def test_a_url_without_a_token_does_not_start_it():
    """Half-configured must mean off, not pushing unauthenticated."""
    assert ui_bridge.UIBridge.from_env({"UI_RELAY_URL": "http://127.0.0.1:8000"}) is None


def test_the_token_can_come_from_a_file(tmp_path):
    token = tmp_path / "agent_token.txt"
    token.write_text("  from-the-file \n", encoding="utf-8")
    made = ui_bridge.UIBridge.from_env({"UI_RELAY_URL": "http://127.0.0.1:8000/",
                                        "UI_AGENT_TOKEN_FILE": str(token),
                                        "UI_AGENT_ID": "proart"})
    assert made is not None
    assert made.token == "from-the-file" and made.base_url == "http://127.0.0.1:8000"


# -- the document -----------------------------------------------------------
def test_the_state_describes_the_account_and_the_session():
    doc = bridge().build_state(build_trader(), NOW)
    assert doc["schema_version"] == ui_bridge.CONTRACT_VERSION
    assert doc["account"] == {"broker": "ibkr", "account_id": "DUM215828",
                              "is_paper": True, "mode": "paper"}
    assert doc["session"]["state"] == "premarket"
    assert doc["session"]["clock_et"] == "07:20:00"


@pytest.mark.parametrize("clock,expected", [
    (datetime(2026, 9, 14, 3, 0), "closed"),
    (datetime(2026, 9, 14, 5, 0), "premarket"),
    (datetime(2026, 9, 14, 10, 0), "rth"),
    (datetime(2026, 9, 14, 17, 0), "after"),
    (datetime(2026, 9, 14, 21, 0), "closed"),
])
def test_the_session_follows_the_clock(clock, expected):
    assert ui_bridge._session_state(clock) == expected


def test_an_open_position_carries_its_stop_and_who_holds_it():
    doc = bridge().build_state(build_trader(), NOW)
    assert len(doc["positions"]) == 1
    pos = doc["positions"][0]
    assert pos["symbol"] == "ACVA" and pos["qty"] == 100
    assert pos["last_price"] == 10.05                      # mid of 10.00 / 10.10
    assert pos["unrealized_pnl"] == 55.0                   # (10.05 - 9.50) * 100
    assert pos["stop"]["level"] == pytest.approx(9.69)     # 10.20 peak, 5% trail
    # outside RTH every stop is ours; the portal must show that, it is the risk
    assert pos["stop"]["managed_by"] == "agent"


def test_a_missing_quote_does_not_stop_the_push():
    trader = build_trader()
    trader.quote = lambda st: (_ for _ in ()).throw(RuntimeError("no market data"))
    doc = bridge().build_state(trader, NOW)
    assert doc["positions"][0]["last_price"] is None
    assert doc["positions"][0]["unrealized_pnl"] is None


def test_fills_come_from_the_fill_log_and_skips_are_not_fills(tmp_path):
    doc = bridge().build_state(build_trader(tmp_path), NOW)
    fills = doc["fills_today"]
    assert [f["symbol"] for f in fills] == ["WXYZ", "WXYZ"]     # the SKIPPED row is not one
    assert fills[0]["ts_et"] == "07:02:11" and fills[0]["action"] == "BUY"
    assert fills[1]["trade_pnl"] == -23.26
    assert all(f["friction_charged"] is False for f in fills)


def test_every_pnl_says_whether_friction_is_charged(tmp_path):
    doc = bridge().build_state(build_trader(tmp_path), NOW)
    assert doc["pnl"]["friction_charged"] is False
    assert doc["pnl"]["friction_per_round_trip"] == 4.26
    assert all(s["pnl"]["friction_charged"] is False for s in doc["strategies"])


def test_per_strategy_pnl_counts_only_that_strategy(tmp_path):
    doc = bridge().build_state(build_trader(tmp_path), NOW)
    mcl = doc["strategies"][0]
    assert mcl["name"] == "mcl" and mcl["pnl"]["trades"] == 1
    assert mcl["pnl"]["realized"] == -23.26


def test_the_watchlist_reports_a_blocked_name_as_blocked():
    doc = bridge().build_state(build_trader(), NOW)
    assert {w["symbol"]: w["status"] for w in doc["watchlist"]} == {
        "ACVA": "active", "JLHL": "blocked"}


def test_settings_say_which_command_changes_them():
    doc = bridge().build_state(build_trader(), NOW)
    settings = {s["key"]: s for s in doc["settings"]}
    assert settings["max_concurrent_positions"]["set_command"] == "set_setting"
    assert settings["trail_pct:mcl"]["value"] == 5.0
    assert settings["trail_pct:mcl"]["applies_to"] == "new_positions"
    # the band is enforced at entry and lives in the repo, so it is read-only
    assert settings["price_band:mcl"]["editable_now"] is False
    assert settings["price_band:mcl"]["set_command"] is None


# -- the paper guard --------------------------------------------------------
def test_a_live_account_is_offered_no_commands_at_all():
    doc = bridge(paper=False).build_state(build_trader(), NOW)
    assert doc["account"]["is_paper"] is False
    assert doc["commands_available"] == []


def test_a_live_account_refuses_a_command_even_if_one_arrives():
    trader = build_trader()
    answer = bridge(paper=False).apply(trader, {"id": "c-1", "type": "stop"})
    assert answer["status"] == "rejected"
    assert answer["reason_code"] == "not_paper_account"
    assert trader.paused is False


# -- commands ---------------------------------------------------------------
def test_stop_and_start_only_touch_new_entries():
    trader, b = build_trader(), bridge()
    answer = b.apply(trader, {"id": "c-1", "type": "stop"})
    assert answer["status"] == "applied" and trader.paused is True
    assert "1 open position(s) still managed" in answer["detail"]

    doc = b.build_state(trader, NOW)
    assert [c["type"] for c in doc["commands_available"]][0] == "start"
    assert doc["positions"], "a stopped trader still manages what it holds"

    assert b.apply(trader, {"id": "c-2", "type": "start"})["status"] == "applied"
    assert trader.paused is False


def test_a_strategy_can_be_disabled_and_re_enabled():
    trader, b = build_trader(), bridge()
    assert b.apply(trader, {"id": "c-1", "type": "set_strategy_enabled",
                            "args": {"strategy": "mcl", "enabled": False}
                            })["status"] == "applied"
    assert trader.disabled_strategies == {"mcl"}
    assert b.build_state(trader, NOW)["strategies"][0]["enabled"] is False

    b.apply(trader, {"id": "c-2", "type": "set_strategy_enabled",
                     "args": {"strategy": "mcl", "enabled": True}})
    assert trader.disabled_strategies == set()


def test_an_unknown_strategy_or_a_non_boolean_is_refused():
    trader, b = build_trader(), bridge()
    for args in ({"strategy": "nope", "enabled": True},
                 {"strategy": "mcl", "enabled": "yes"}):
        answer = b.apply(trader, {"id": "c-1", "type": "set_strategy_enabled",
                                  "args": args})
        assert answer["status"] == "rejected" and answer["reason_code"] == "bad_args"


def test_the_position_cap_can_be_changed_within_limits():
    trader, b = build_trader(), bridge()
    assert b.apply(trader, {"id": "c-1", "type": "set_setting",
                            "args": {"key": "max_concurrent_positions", "value": 1}
                            })["status"] == "applied"
    assert trader.max_positions == 1

    for bad in (-1, 11, 1.5, "two"):
        answer = b.apply(trader, {"id": "c-2", "type": "set_setting",
                                  "args": {"key": "max_concurrent_positions",
                                           "value": bad}})
        assert answer["status"] == "rejected", f"{bad!r} was accepted"
    assert trader.max_positions == 1


def test_zero_is_a_legitimate_cap():
    """0 means take no new entries and keep recording signals."""
    trader, b = build_trader(), bridge()
    assert b.apply(trader, {"id": "c-1", "type": "set_setting",
                            "args": {"key": "max_concurrent_positions", "value": 0}
                            })["status"] == "applied"
    assert trader.max_positions == 0


def test_a_trail_change_applies_to_the_strategy_not_to_open_positions():
    trader, b = build_trader(), bridge()
    open_before = trader.states[("mcl", "ACVA")].position.trail_pct

    assert b.apply(trader, {"id": "c-1", "type": "set_setting",
                            "args": {"key": "trail_pct:mcl", "value": 3}
                            })["status"] == "applied"
    assert trader.strategies[0].trail_pct == 3.0
    assert trader.states[("mcl", "ACVA")].position.trail_pct == open_before

    out_of_range = b.apply(trader, {"id": "c-2", "type": "set_setting",
                                    "args": {"key": "trail_pct:mcl", "value": 99}})
    assert out_of_range["status"] == "rejected"
    assert trader.strategies[0].trail_pct == 3.0


def test_a_setting_that_is_not_offered_cannot_be_set():
    answer = bridge().apply(build_trader(), {"id": "c-1", "type": "set_setting",
                                             "args": {"key": "price_band:mcl",
                                                      "value": "$1-50"}})
    assert answer["status"] == "rejected"
    assert answer["reason_code"] == "not_applicable_now"


def test_an_unknown_command_is_rejected_not_ignored():
    answer = bridge().apply(build_trader(), {"id": "c-1", "type": "flatten"})
    assert answer["status"] == "rejected" and answer["reason_code"] == "unknown_command"


def test_a_command_that_raises_is_answered_not_propagated():
    """A failure inside a command must come back as a rejection, not escape
    into the trading loop."""
    trader, b = build_trader(), bridge()
    trader.strategies = property(lambda self: 1 / 0)        # any exploding access
    answer = b.apply(trader, {"id": "c-1", "type": "set_strategy_enabled",
                              "args": {"strategy": "mcl", "enabled": False}})
    assert answer["status"] == "rejected"


# -- messages ---------------------------------------------------------------
def test_messages_are_mirrored_with_their_markup():
    b = bridge()
    b.record_message("<b>[mcl] BUY WXYZ</b>\nprice 6.55", kind="entry")
    doc = b.build_state(build_trader(), NOW)
    note = doc["notifications"][0]
    assert note["format"] == "telegram_html" and note["channel"] == "telegram"
    assert note["text"].startswith("<b>[mcl] BUY WXYZ</b>")
    assert note["kind"] == "entry" and note["status"] == "sent"


def test_the_message_window_is_bounded():
    b = bridge()
    for i in range(ui_bridge.MAX_NOTIFICATIONS + 25):
        b.record_message(f"message {i}")
    kept = b.build_state(build_trader(), NOW)["notifications"]
    assert len(kept) == ui_bridge.MAX_NOTIFICATIONS
    assert kept[-1]["text"] == f"message {ui_bridge.MAX_NOTIFICATIONS + 24}"


# -- failure is silent ------------------------------------------------------
def test_a_relay_that_is_down_is_logged_a_few_times_then_left_alone(caplog):
    b = bridge()
    b.base_url = "http://127.0.0.1:9"                   # nothing listens there
    with caplog.at_level("WARNING"):
        for _ in range(10):
            assert b._post("/api/state", {"x": 1}) is False
    complaints = [r for r in caplog.records if "portal" in r.message]
    assert 0 < len(complaints) <= ui_bridge.QUIET_AFTER + 1, "it kept complaining"


def test_reading_commands_from_a_dead_relay_returns_nothing():
    b = bridge()
    b.base_url = "http://127.0.0.1:9"
    assert b._get("/api/commands") == []
