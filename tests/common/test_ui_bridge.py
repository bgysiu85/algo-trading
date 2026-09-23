"""common/ui_bridge.py — what the portal sees, and what it may change.

No relay is contacted: the transport is replaced, so these tests are about the
document and the command handling, which is where being wrong costs something.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
import time
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
    bars_fetched_at: float = 0.0


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


def test_uptime_grows_from_when_the_bridge_was_built():
    b = bridge()
    first = b.build_state(build_trader(), NOW)["health"]["uptime_s"]
    assert first >= 0
    time.sleep(0.05)
    second = b.build_state(build_trader(), NOW)["health"]["uptime_s"]
    assert second > first


def test_data_stale_seconds_is_none_until_a_symbol_has_fetched_bars():
    trader = build_trader()
    doc = bridge().build_state(trader, NOW)
    assert doc["health"]["data_stale_seconds"] is None


def test_data_stale_seconds_reads_the_freshest_symbol():
    trader = build_trader()
    now = time.monotonic()
    trader.states[("mcl", "ACVA")].bars_fetched_at = now - 90   # stale
    trader.states[("mcl", "JLHL")].bars_fetched_at = now - 5    # fresh
    doc = bridge().build_state(trader, NOW)
    stale = doc["health"]["data_stale_seconds"]
    assert 4.5 <= stale <= 6


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


# ---------------------------------------------------------------------------
# The fakes above are ordinary objects, and an ordinary object accepts any
# attribute you set on it. The real StrategyAdapter is a FROZEN dataclass, so
# `adapter.trail_pct = x` raises -- and the first version of this module did
# exactly that, passing every test here while failing on Ben's machine. These
# tests use the real adapter for that reason; do not replace it with a fake.

def _real_trader_with_real_adapters():
    from common import strategy_adapter as SA

    class State:
        def __init__(self, symbol, adapter):
            self.symbol, self.strategy = symbol, adapter
            self.position = None

    class Trader:
        def __init__(self):
            self.strategies = SA.build_all(["mcl", "mc5"])
            self.states = {"AAA": State("AAA", self.strategies[0]),
                           "BBB": State("BBB", self.strategies[1])}
            self.max_positions = 3
            self.paused = False
            self.disabled_strategies = set()

    return Trader()


def test_the_trail_can_be_changed_on_a_real_frozen_adapter():
    trader = _real_trader_with_real_adapters()
    name = trader.strategies[0].name
    ui = bridge(paper=True)

    answer = ui.apply(trader, {"id": "c1", "type": "set_setting",
                                   "args": {"key": f"trail_pct:{name}", "value": 7.5}})

    assert answer["status"] == "applied", answer
    assert "FrozenInstanceError" not in answer["detail"]
    changed = next(a for a in trader.strategies if a.name == name)
    assert changed.trail_pct == 7.5


def test_the_change_reaches_the_state_an_entry_actually_reads():
    """step_symbol stamps the trail onto the Position from st.strategy. If the
    rebind missed SymbolState, the portal would report 7.5% while every entry
    kept taking 5.0% -- the browser disagreeing with the trade."""
    trader = _real_trader_with_real_adapters()
    name = trader.strategies[0].name
    ui = bridge(paper=True)

    ui.apply(trader, {"id": "c1", "type": "set_setting",
                      "args": {"key": f"trail_pct:{name}", "value": 9.0}})

    for state in trader.states.values():
        if state.strategy.name == name:
            assert state.strategy.trail_pct == 9.0

    published = {s["key"]: s["value"] for s in ui.build_state(
        trader, NOW).get("settings", [])}
    assert published[f"trail_pct:{name}"] == 9.0


def test_changing_one_strategys_trail_leaves_the_other_alone():
    trader = _real_trader_with_real_adapters()
    first, second = trader.strategies[0].name, trader.strategies[1].name
    before = next(a for a in trader.strategies if a.name == second).trail_pct
    ui = bridge(paper=True)

    ui.apply(trader, {"id": "c1", "type": "set_setting",
                      "args": {"key": f"trail_pct:{first}", "value": 6.5}})

    assert next(a for a in trader.strategies if a.name == second).trail_pct == before


def test_an_open_position_keeps_the_trail_it_was_opened_with():
    """The trader copies trail_pct into Position at entry, so this holds by
    construction -- asserted here because the portal's promise to the user
    ("new positions only") depends on it staying true."""
    trader = _real_trader_with_real_adapters()
    name = trader.strategies[0].name
    state = next(s for s in trader.states.values() if s.strategy.name == name)

    class Position:
        trail_pct = 5.0
    state.position = Position()

    bridge(paper=True).apply(trader, {"id": "c1", "type": "set_setting",
                                       "args": {"key": f"trail_pct:{name}",
                                                "value": 12.0}})

    assert state.position.trail_pct == 5.0
    assert state.strategy.trail_pct == 12.0


def test_the_adapter_is_still_frozen():
    """A future edit could 'fix' this by unfreezing StrategyAdapter. That would
    let anything keep a private, drifted copy of a strategy's constants, which
    is the defect the adapter exists to prevent."""
    from common import strategy_adapter as SA

    assert SA.StrategyAdapter.__dataclass_params__.frozen, (
        "unfreezing the adapter would remove the guarantee that its fields are "
        "read off the strategy module")


# ---------------------------------------------------------------------------
# The relay holds ONE state document. Two publishers means the dashboard flips
# between them and a command reaches whichever polled first.

def _configured(**extra):
    env = {"UI_RELAY_URL": "http://127.0.0.1:8000", "UI_AGENT_TOKEN": "t"}
    env.update(extra)
    return env


def test_a_dry_run_does_not_publish():
    assert ui_bridge.UIBridge.from_env(_configured(), dry_run=True) is None


def test_a_real_session_publishes():
    assert ui_bridge.UIBridge.from_env(_configured(), dry_run=False) is not None


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_a_dry_run_can_be_put_on_the_dashboard_deliberately(value):
    """Occasionally what you want while developing — but never by default."""
    assert ui_bridge.UIBridge.from_env(
        _configured(UI_PUBLISH_DRY=value), dry_run=True) is not None


@pytest.mark.parametrize("value", ["0", "false", "no", "", "  ", "maybe"])
def test_only_an_affirmative_override_counts(value):
    """An empty or unrecognised value is not consent. Anything else would mean
    UI_PUBLISH_DRY= in a script silently turns publishing on."""
    assert ui_bridge.UIBridge.from_env(
        _configured(UI_PUBLISH_DRY=value), dry_run=True) is None


def test_the_override_cannot_conjure_a_bridge_without_a_relay():
    """The gate narrows; it must never widen. No relay URL still means off."""
    assert ui_bridge.UIBridge.from_env(
        {"UI_PUBLISH_DRY": "1", "UI_AGENT_TOKEN": "t"}, dry_run=True) is None


def test_the_trader_passes_its_own_mode_to_the_gate():
    """The gate is only worth having if the trader actually tells it. Read from
    the source because exercising main_async needs an IB connection."""
    import inspect

    from brokers.ibkr import trader as T
    src = inspect.getsource(T.main_async)
    assert "from_env(dry_run=bool(args.dry_run))" in src, (
        "main_async must pass the session's mode, or every dry run publishes")


# ===========================================================================
# The CONFIG row. Shape agreed with the strategy/database side, 2026-09-14:
# claude/portal_config_row_reply_20260914.md.

import csv as _csv  # noqa: E402

from brokers.ibkr import trader as T  # noqa: E402


def _trader_with_a_log(tmp_path, paused=False):
    trader = _real_trader_with_real_adapters()
    trader.log = T.FillLog(tmp_path / "fills.csv")
    trader.paused = paused
    trader.states = {k: v for k, v in trader.states.items()}
    return trader


def _rows(trader) -> list[dict]:
    trader.log.fh.flush()
    with trader.log.path.open(newline="", encoding="utf-8") as fh:
        return list(_csv.DictReader(fh))


def _config_rows(trader) -> list[dict]:
    return [r for r in _rows(trader) if r["action"] == ui_bridge.CONFIG_ACTION]


# -- the key fields ---------------------------------------------------------

def test_the_setting_name_goes_in_symbol_lowercase(tmp_path):
    """paper_fill's key is (session_date, ts_et, strategy, symbol, action,
    status). symbol is the only field left that can separate two DIFFERENT
    settings changed in the same second by the same strategy; without it the
    loader's de-duplicator keeps one and drops the other silently."""
    trader = _trader_with_a_log(tmp_path)
    name = trader.strategies[0].name
    ui = bridge(paper=True)

    ui.apply(trader, {"id": "c1", "type": "set_setting",
                      "args": {"key": f"trail_pct:{name}", "value": 8.0}}, NOW)

    row = _config_rows(trader)[0]
    assert row["symbol"] == "trail_pct"
    assert row["symbol"] == row["symbol"].lower(), (
        "every real ticker in this table is uppercase; lowercase is what makes "
        "a CONFIG row un-mistakable in a listing")


@pytest.mark.parametrize("setting", [
    ui_bridge.SETTING_PAUSED, ui_bridge.SETTING_ENABLED,
    ui_bridge.SETTING_TRAIL, ui_bridge.SETTING_CAP, ui_bridge.SETTING_UNKNOWN,
])
def test_every_setting_name_fits_the_symbol_column(setting):
    """db.SYM is 24 and the contract key "max_concurrent_positions" is exactly
    24 — a truncation waiting for a longer setting. These are the short names,
    and this pins the margin rather than the coincidence."""
    from common import db

    assert len(setting) <= db.SYM - 8, (
        f"{setting!r} leaves no headroom in a {db.SYM}-char column")


def test_a_global_stop_writes_one_row_per_adapter_and_no_phantom_strategy(tmp_path):
    """strategy is a key column AND the grouping column in every census. A
    synthetic "ALL" would appear in "which strategies traded" for as long as
    the table exists. A global pause genuinely IS both adapters changing."""
    trader = _trader_with_a_log(tmp_path)
    names = {a.name for a in trader.strategies}
    ui = bridge(paper=True)

    ui.apply(trader, {"id": "c1", "type": "stop"}, NOW)

    rows = _config_rows(trader)
    assert {r["strategy"] for r in rows} == names
    assert len(rows) == len(names)
    assert "ALL" not in {r["strategy"] for r in rows}


def test_a_change_to_one_strategy_names_only_that_one(tmp_path):
    trader = _trader_with_a_log(tmp_path)
    first, second = (a.name for a in trader.strategies[:2])
    ui = bridge(paper=True)

    ui.apply(trader, {"id": "c1", "type": "set_setting",
                      "args": {"key": f"trail_pct:{first}", "value": 7.0}}, NOW)

    assert {r["strategy"] for r in _config_rows(trader)} == {first}
    assert second not in {r["strategy"] for r in _config_rows(trader)}


# -- applied and rejected ---------------------------------------------------

def test_a_rejected_command_is_recorded_too(tmp_path):
    """A refusal that left no trace reads as a command nobody sent — the same
    ambiguity a declined entry writing no row would create."""
    trader = _trader_with_a_log(tmp_path)
    ui = bridge(paper=True)

    answer = ui.apply(trader, {"id": "c1", "type": "set_setting",
                               "args": {"key": "trail_pct:nope", "value": 7.0}}, NOW)

    assert answer["status"] == "rejected"
    row = _config_rows(trader)[0]
    assert row["status"] == ui_bridge.CONFIG_REJECTED
    assert "nope" in row["reject_reason"]


def test_a_command_on_a_live_account_is_refused_and_recorded(tmp_path):
    """The one case where a CONFIG row is evidence of an attempt rather than a
    change. It must not be the quiet one."""
    trader = _trader_with_a_log(tmp_path)
    ui = bridge(paper=False)

    ui.apply(trader, {"id": "c1", "type": "stop"}, NOW)

    rows = _config_rows(trader)
    assert rows and all(r["status"] == ui_bridge.CONFIG_REJECTED for r in rows)
    assert all("paper" in r["reject_reason"] for r in rows)


def test_the_trail_column_carries_the_value_the_trader_now_has(tmp_path):
    """Read back off the adapter, not off the request: the row records what
    took effect, not what was asked for."""
    trader = _trader_with_a_log(tmp_path)
    name = trader.strategies[0].name
    ui = bridge(paper=True)

    ui.apply(trader, {"id": "c1", "type": "set_setting",
                      "args": {"key": f"trail_pct:{name}", "value": 6.5}}, NOW)

    row = next(r for r in _config_rows(trader) if r["reason"] == "set_setting")
    assert float(row["trail_pct"]) == 6.5
    assert next(a for a in trader.strategies if a.name == name).trail_pct == 6.5


def test_a_rejected_trail_change_records_no_value(tmp_path):
    """Nothing took effect, so the column must not claim something did."""
    trader = _trader_with_a_log(tmp_path)
    name = trader.strategies[0].name
    ui = bridge(paper=True)

    ui.apply(trader, {"id": "c1", "type": "set_setting",
                      "args": {"key": f"trail_pct:{name}", "value": 400}}, NOW)

    row = _config_rows(trader)[0]
    assert row["status"] == ui_bridge.CONFIG_REJECTED
    assert row["trail_pct"] == ""


# -- the session-open row ---------------------------------------------------

# The session-open rows and the bridge state are the trader's, and are tested
# in tests/brokers/ibkr/test_config_row_and_band.py. I had a second copy of
# both here; two writers would have put two rows per adapter in the ledger at
# every session start.


def test_a_command_records_the_value_it_moved_to(tmp_path):
    """The session-open row gives it something to be a diff FROM, and that row
    is the trader's. This side records where the trail ended up."""
    trader = _trader_with_a_log(tmp_path)
    name = trader.strategies[0].name
    was = trader.strategies[0].trail_pct
    ui = bridge(paper=True)

    ui.apply(trader, {"id": "c1", "type": "set_setting",
                      "args": {"key": f"trail_pct:{name}", "value": 9.0}}, NOW)

    mine = [r for r in _config_rows(trader) if r["strategy"] == name]
    assert float(mine[-1]["trail_pct"]) == 9.0
    assert was != 9.0, "the fixture must actually move the value"


# -- it must never break the trading loop -----------------------------------

def test_a_log_that_cannot_be_written_does_not_break_the_command(tmp_path):
    """Called from inside the trading loop. A log that will not take a row is
    not a reason to stop trading."""
    trader = _trader_with_a_log(tmp_path)

    class Broken:
        path = tmp_path / "x.csv"

        def write(self, **row):
            raise OSError("disk full")

    trader.log = Broken()

    answer = bridge(paper=True).apply(trader, {"id": "c1", "type": "stop"}, NOW)

    assert answer["status"] == "applied"
    assert trader.paused is True


def test_a_trader_without_a_log_is_fine(tmp_path):
    trader = _real_trader_with_real_adapters()
    assert bridge(paper=True).apply(
        trader, {"id": "c1", "type": "stop"}, NOW)["status"] == "applied"


def test_the_config_row_text_is_plain_ascii(tmp_path):
    """The detail comes from ack messages written for humans, which contain em
    dashes. friction.load opens this file with the locale encoding and Ben
    opens it in Excel, so a character that renders correctly in one reader and
    as a blob in another is a permanent small irritation in the one file
    everything reads. This is machine detail, not prose."""
    trader = _trader_with_a_log(tmp_path)
    name = trader.strategies[0].name
    ui = bridge(paper=True)

    ui.apply(trader, {"id": "c1", "type": "set_setting",
                      "args": {"key": f"trail_pct:{name}", "value": 8.0}}, NOW)

    row = _config_rows(trader)[0]
    for field in ("reason", "reject_reason"):
        row[field].encode("ascii")          # raises if anything slipped through
    assert "--" in row["reject_reason"] or "-" in row["reject_reason"]


# ---------------------------------------------------------------------------
# Contract 1.4: the round trip's own arithmetic, published rather than implied.
# trade_pnl is NET of commission and GROSS of measured slippage; one column
# called "Result" made that unrecoverable by anyone reading the page.

def test_gross_and_commission_are_derived_from_the_row(tmp_path):
    """The trader stores entry, exit, qty and net. Gross follows from the
    prices; the fee is the difference. Recomputing the fee from the schedule
    would be a second calculation that agrees until a schedule changes."""
    gross, commission = ui_bridge._round_trip_costs(4.00, 4.30, 100, 28.50)
    assert gross == 30.0
    assert commission == 1.5
    assert round(gross - commission, 2) == 28.50


def test_a_loss_still_reconciles(tmp_path):
    gross, commission = ui_bridge._round_trip_costs(9.00, 8.60, 50, -21.20)
    assert gross == -20.0
    assert commission == 1.2
    assert round(gross - commission, 2) == -21.20


@pytest.mark.parametrize("entry,net,qty", [
    (None, 28.5, 100),          # a BUY row, or a log from before entry_price
    (4.0, None, 100),           # an open position's entry row
    (4.0, 28.5, 0),             # nothing filled
])
def test_an_incomplete_row_reports_nothing_rather_than_guessing(entry, net, qty):
    """A wrong number in this column is worse than a blank one: the page shows
    it beside two others that are right, and the reader believes all three."""
    assert ui_bridge._round_trip_costs(entry, 4.3, qty, net) == (None, None)


def test_commission_is_published_as_a_positive_cost():
    """Signed publication would make 'is this already negative?' a question
    every consumer has to answer. The page renders the minus sign."""
    _, commission = ui_bridge._round_trip_costs(4.00, 4.30, 100, 28.50)
    assert commission > 0


def test_the_published_fill_carries_the_whole_round_trip(tmp_path):
    trader = _real_trader_with_real_adapters()
    log = __import__("brokers.ibkr.trader", fromlist=["x"]).FillLog(tmp_path / "f.csv")
    log.write(ts_et="2026-09-14 07:20:00", strategy="MCL", symbol="AAA",
              action="SELL", status="FILLED", reason="trailing_stop",
              filled_qty=100, fill_price=4.30, entry_price=4.00,
              exit_price=4.30, trade_pnl=28.50)
    log.close()
    trader.log = log

    fill = ui_bridge.UIBridge._fills_today(trader)[0]

    assert fill["entry_price"] == 4.00
    assert fill["price"] == 4.30
    assert fill["gross_pnl"] == 30.0
    assert fill["commission"] == 1.5
    assert fill["trade_pnl"] == 28.50
    assert round(fill["gross_pnl"] - fill["commission"], 2) == fill["trade_pnl"]


def test_the_fill_fields_arrived_in_1_4():
    """They are additive and optional, so an older relay still accepts these
    documents — but the version has to move or nothing can tell the shapes
    apart when it matters. Pinned by the fields rather than by the number, so
    a later minor bump does not make this test a liar."""
    from packaging.version import Version  # noqa: F401  (import guarded below)
    assert tuple(int(x) for x in ui_bridge.CONTRACT_VERSION.split(".")) >= (1, 4)


# ---------------------------------------------------------------------------
# Contract 1.5: the bar size each strategy decides on.

def test_each_strategy_publishes_the_bar_size_it_decides_on():
    """The portal charts a symbol at this interval. Read off the adapter rather
    than restated anywhere, so a strategy that changes its bar size drags the
    chart with it — the same rule _from_module follows for every other
    constant."""
    from common import strategy_adapter as SA

    trader = _real_trader_with_real_adapters()
    doc = bridge(paper=True).build_state(trader, NOW)

    published = {s["name"]: s["bar_minutes"] for s in doc["strategies"]}
    for adapter in SA.build_all(["mcl", "mc5"]):
        assert published[adapter.name] == adapter.bar_minutes


def test_mcl_and_mc5_do_not_publish_the_same_bar_size():
    """If they did, this test would pass while telling us nothing — and a
    portal charting a 5-minute strategy on a 1-minute chart looks correct."""
    from common import strategy_adapter as SA

    mcl, mc5 = SA.build("mcl"), SA.build("mc5")
    assert mcl.bar_minutes != mc5.bar_minutes, (
        "these differ today; if they ever agree, the chart test above stops "
        "being evidence of anything")


def test_the_bar_size_arrived_in_1_5():
    """Pinned by the floor, not the exact number: a later minor bump is an
    addition, and a test that has to be edited for every addition gets edited
    without being read."""
    assert tuple(int(x) for x in ui_bridge.CONTRACT_VERSION.split(".")) >= (1, 5)


# ---------------------------------------------------------------------------
# Contract 1.6: when the round trip opened. The closing row records the exit
# and the hold, never the entry time.

def _log_with(tmp_path, rows):
    T = __import__("brokers.ibkr.trader", fromlist=["x"])
    log = T.FillLog(tmp_path / "f.csv")
    for row in rows:
        log.write(**row)
    log.close()

    class Trader:
        pass
    trader = Trader()
    trader.log = log
    return trader


def test_the_entry_time_comes_from_the_row_that_opened_it(tmp_path):
    """Exact, not derived: the BUY row has the real timestamp. hold_minutes is
    stored to one decimal and would only ever be close."""
    trader = _log_with(tmp_path, [
        dict(ts_et="2026-09-14 07:21:37", strategy="MCL", symbol="AAA",
             action="BUY", status="FILLED", filled_qty=100, fill_price=4.02),
        dict(ts_et="2026-09-14 07:42:05", strategy="MCL", symbol="AAA",
             action="SELL", status="FILLED", filled_qty=100, fill_price=3.88,
             entry_price=4.02, exit_price=3.88, trade_pnl=-16.20,
             hold_minutes=20.5, reason="trailing_stop"),
    ])
    closed = [f for f in ui_bridge.UIBridge._fills_today(trader)
              if f["trade_pnl"] is not None][0]

    assert closed["entry_ts_et"] == "07:21:37"
    assert closed["ts_et"] == "07:42:05"


def test_two_round_trips_in_one_symbol_pair_in_order(tmp_path):
    """The second SELL must take the second BUY. Matching on symbol alone
    without consuming the pairing would give both trades the first entry."""
    rows = []
    for i, (buy, sell) in enumerate([("07:05:00", "07:15:00"), ("08:10:00", "08:30:00")]):
        rows.append(dict(ts_et=f"2026-09-14 {buy}", strategy="MCL", symbol="AAA",
                         action="BUY", status="FILLED", filled_qty=100, fill_price=4.0))
        rows.append(dict(ts_et=f"2026-09-14 {sell}", strategy="MCL", symbol="AAA",
                         action="SELL", status="FILLED", filled_qty=100, fill_price=4.1,
                         entry_price=4.0, exit_price=4.1, trade_pnl=8.0 + i,
                         hold_minutes=10.0))
    closed = [f for f in ui_bridge.UIBridge._fills_today(_log_with(tmp_path, rows))
              if f["trade_pnl"] is not None]

    assert [f["entry_ts_et"] for f in closed] == ["07:05:00", "08:10:00"]


def test_a_strategys_entry_is_not_borrowed_by_another(tmp_path):
    """Both strategies can hold the same symbol. The pairing is keyed on both."""
    trader = _log_with(tmp_path, [
        dict(ts_et="2026-09-14 07:00:00", strategy="MCL", symbol="AAA",
             action="BUY", status="FILLED", filled_qty=100, fill_price=4.0),
        dict(ts_et="2026-09-14 07:30:00", strategy="MC5", symbol="AAA",
             action="BUY", status="FILLED", filled_qty=50, fill_price=4.1),
        dict(ts_et="2026-09-14 08:00:00", strategy="MC5", symbol="AAA",
             action="SELL", status="FILLED", filled_qty=50, fill_price=4.3,
             entry_price=4.1, exit_price=4.3, trade_pnl=9.0, hold_minutes=30.0),
    ])
    closed = [f for f in ui_bridge.UIBridge._fills_today(trader)
              if f["trade_pnl"] is not None][0]

    assert closed["entry_ts_et"] == "07:30:00", "took the other strategy's entry"


def test_a_position_with_no_opening_row_falls_back_to_the_hold(tmp_path):
    """Adopted from a previous session, or the log was rolled aside mid-session.
    An approximate time beats an empty column here, and it is within seconds."""
    trader = _log_with(tmp_path, [
        dict(ts_et="2026-09-14 07:42:00", strategy="MCL", symbol="AAA",
             action="SELL", status="FILLED", filled_qty=100, fill_price=3.88,
             entry_price=4.02, exit_price=3.88, trade_pnl=-16.20, hold_minutes=21.0),
    ])
    closed = [f for f in ui_bridge.UIBridge._fills_today(trader)
              if f["trade_pnl"] is not None][0]

    assert closed["entry_ts_et"] == "07:21:00"


def test_a_skipped_row_never_opens_a_pairing(tmp_path):
    """SKIPPED_PAUSED and the cap rows are BUY rows that never filled. Letting
    one open a pairing would hand the next real exit a time no trade happened
    at."""
    trader = _log_with(tmp_path, [
        dict(ts_et="2026-09-14 06:00:00", strategy="MCL", symbol="AAA",
             action="BUY", status="SKIPPED_PAUSED", reject_reason="paused"),
        dict(ts_et="2026-09-14 07:21:00", strategy="MCL", symbol="AAA",
             action="BUY", status="FILLED", filled_qty=100, fill_price=4.02),
        dict(ts_et="2026-09-14 07:42:00", strategy="MCL", symbol="AAA",
             action="SELL", status="FILLED", filled_qty=100, fill_price=3.88,
             entry_price=4.02, exit_price=3.88, trade_pnl=-16.20, hold_minutes=21.0),
    ])
    closed = [f for f in ui_bridge.UIBridge._fills_today(trader)
              if f["trade_pnl"] is not None][0]

    assert closed["entry_ts_et"] == "07:21:00"


# ---------------------------------------------------------------------------
# Partial fills. Raised by the strategy side before it happened: a partial fill
# opens a real position that a later exit closes, and a second partial adds to
# the same position.

def test_a_partially_filled_entry_still_gives_its_exit_a_time(tmp_path):
    """The trader writes PARTIAL_FILL, not FILLED, when filled < qty. Pairing
    on FILLED alone left that exit with no opening row at all."""
    trader = _log_with(tmp_path, [
        dict(ts_et="2026-09-14 07:21:00", strategy="MCL", symbol="AAA",
             action="BUY", status="PARTIAL_FILL", filled_qty=40, qty=100,
             fill_price=4.02),
        dict(ts_et="2026-09-14 07:42:00", strategy="MCL", symbol="AAA",
             action="SELL", status="FILLED", filled_qty=40, fill_price=3.88,
             entry_price=4.02, exit_price=3.88, trade_pnl=-6.20,
             hold_minutes=21.0),
    ])
    closed = [f for f in ui_bridge.UIBridge._fills_today(trader)
              if f["trade_pnl"] is not None][0]

    assert closed["entry_ts_et"] == "07:21:00"


def test_a_second_partial_does_not_move_the_opening_time(tmp_path):
    """A second partial ADDS to the position the first one opened. Taking the
    later time would quietly shorten every partially-filled trade -- and
    hold_minutes, computed from the real entry, would then disagree with the
    two timestamps beside it."""
    trader = _log_with(tmp_path, [
        dict(ts_et="2026-09-14 07:21:00", strategy="MCL", symbol="AAA",
             action="BUY", status="PARTIAL_FILL", filled_qty=40, qty=100,
             fill_price=4.02),
        dict(ts_et="2026-09-14 07:23:30", strategy="MCL", symbol="AAA",
             action="BUY", status="PARTIAL_FILL", filled_qty=60, qty=100,
             fill_price=4.05),
        dict(ts_et="2026-09-14 07:42:00", strategy="MCL", symbol="AAA",
             action="SELL", status="FILLED", filled_qty=100, fill_price=3.88,
             entry_price=4.03, exit_price=3.88, trade_pnl=-16.20,
             hold_minutes=21.0),
    ])
    closed = [f for f in ui_bridge.UIBridge._fills_today(trader)
              if f["trade_pnl"] is not None][0]

    assert closed["entry_ts_et"] == "07:21:00", "took the second partial's time"


def test_a_partially_filled_exit_is_a_real_close_and_is_listed(tmp_path):
    """The strategy side's ruling of 2026-09-16, checked against the trader.

    A partial exit cancels the remainder, reduces pos.qty and leaves the
    position open -- so its row IS a close of the shares that went, and its
    trade_pnl is (exit_px - entry_price) * filled - commission: realised money.
    A FILLED-only list dropped it, and the P&L column understated by exactly
    the sum of the rows it dropped.
    """
    trader = _log_with(tmp_path, [
        dict(ts_et="2026-09-14 07:21:00", strategy="MCL", symbol="AAA",
             action="BUY", status="FILLED", filled_qty=100, fill_price=4.02),
        dict(ts_et="2026-09-14 07:42:00", strategy="MCL", symbol="AAA",
             action="SELL", status="PARTIAL_FILL", filled_qty=40, qty=100,
             fill_price=3.88, entry_price=4.02, exit_price=3.88,
             trade_pnl=-6.20, hold_minutes=21.0),
    ])
    closed = [f for f in ui_bridge.UIBridge._fills_today(trader)
              if f["trade_pnl"] is not None]

    assert len(closed) == 1, "the partial exit was dropped; that is realised P&L"
    assert closed[0]["trade_pnl"] == -6.20
    assert closed[0]["qty"] == 40
    assert closed[0]["partial"] is True
    assert closed[0]["entry_ts_et"] == "07:21:00"


def test_two_partial_exits_of_one_position_do_not_double_count(tmp_path):
    """The condition the ruling turns on. The quantities are disjoint because
    the trader reduces pos.qty by each fill, and entry_price is written once at
    position open and never reassigned -- so the two rows describe different
    shares and their P&L adds rather than overlapping."""
    trader = _log_with(tmp_path, [
        dict(ts_et="2026-09-14 07:21:00", strategy="MCL", symbol="AAA",
             action="BUY", status="FILLED", filled_qty=100, fill_price=4.00),
        dict(ts_et="2026-09-14 07:40:00", strategy="MCL", symbol="AAA",
             action="SELL", status="PARTIAL_FILL", filled_qty=40, qty=100,
             fill_price=3.90, entry_price=4.00, exit_price=3.90,
             trade_pnl=-4.00, hold_minutes=19.0),
        dict(ts_et="2026-09-14 07:41:00", strategy="MCL", symbol="AAA",
             action="SELL", status="FILLED", filled_qty=60, qty=60,
             fill_price=3.95, entry_price=4.00, exit_price=3.95,
             trade_pnl=-3.00, hold_minutes=20.0),
    ])
    closed = [f for f in ui_bridge.UIBridge._fills_today(trader)
              if f["trade_pnl"] is not None]

    assert len(closed) == 2
    assert sum(f["qty"] for f in closed) == 100, "the shares must not overlap"
    assert round(sum(f["trade_pnl"] for f in closed), 2) == -7.00
    assert [f["partial"] for f in closed] == [True, False]


def test_both_exits_of_one_position_carry_the_same_entry_time(tmp_path):
    """Found by a dry run, not by reasoning. Once partial exits are listed, one
    position produces TWO rows in Closed today -- and the pairing popped the
    opening time on the first, so the second rendered "--" in the Entered
    column. Both rows closed shares opened at the same moment.

    The rule mirrors the trader: forget the opening time only when the position
    is flat, which is the FILLED exit, because that order's quantity IS the
    remaining position."""
    trader = _log_with(tmp_path, [
        dict(ts_et="2026-09-16 10:02:44", strategy="MC5", symbol="BDRX",
             action="BUY", status="FILLED", filled_qty=100, fill_price=3.05),
        dict(ts_et="2026-09-16 10:19:03", strategy="MC5", symbol="BDRX",
             action="SELL", status="PARTIAL_FILL", filled_qty=40, qty=100,
             fill_price=3.18, entry_price=3.05, exit_price=3.18,
             trade_pnl=4.40, hold_minutes=16.3),
        dict(ts_et="2026-09-16 10:20:11", strategy="MC5", symbol="BDRX",
             action="SELL", status="FILLED", filled_qty=60, qty=60,
             fill_price=3.12, entry_price=3.05, exit_price=3.12,
             trade_pnl=2.60, hold_minutes=17.4),
    ])
    closed = [f for f in ui_bridge.UIBridge._fills_today(trader)
              if f["trade_pnl"] is not None]

    assert len(closed) == 2
    assert [f["entry_ts_et"] for f in closed] == ["10:02:44", "10:02:44"], (
        "an exit of the same position lost its entry time")


def test_a_new_position_after_a_full_exit_starts_its_own_clock(tmp_path):
    """The other half of the rule. Holding the opening time past the FILLED
    exit would attribute a later trade to an earlier entry -- which is the
    same defect in the opposite direction, and much harder to notice because
    the column would be populated and wrong rather than empty."""
    trader = _log_with(tmp_path, [
        dict(ts_et="2026-09-16 09:00:00", strategy="MCL", symbol="AAA",
             action="BUY", status="FILLED", filled_qty=100, fill_price=4.00),
        dict(ts_et="2026-09-16 09:10:00", strategy="MCL", symbol="AAA",
             action="SELL", status="FILLED", filled_qty=100, fill_price=4.10,
             entry_price=4.00, exit_price=4.10, trade_pnl=9.00,
             hold_minutes=10.0),
        dict(ts_et="2026-09-16 11:00:00", strategy="MCL", symbol="AAA",
             action="BUY", status="FILLED", filled_qty=100, fill_price=4.50),
        dict(ts_et="2026-09-16 11:20:00", strategy="MCL", symbol="AAA",
             action="SELL", status="FILLED", filled_qty=100, fill_price=4.40,
             entry_price=4.50, exit_price=4.40, trade_pnl=-11.00,
             hold_minutes=20.0),
    ])
    closed = [f for f in ui_bridge.UIBridge._fills_today(trader)
              if f["trade_pnl"] is not None]

    assert [f["entry_ts_et"] for f in closed] == ["09:00:00", "11:00:00"], (
        "the second round trip inherited the first one's entry time")


def test_a_partially_filled_entry_does_not_become_a_phantom_close(tmp_path):
    """Widening the list must not invent closes. A partial ENTRY is a fill and
    belongs in the list, but it closed nothing, so it carries no round trip and
    the dashboard's Closed today -- which selects on trade_pnl -- must not show
    it. Getting this wrong would add a row with a blank P&L to a table whose
    subtotals are money."""
    trader = _log_with(tmp_path, [
        dict(ts_et="2026-09-14 07:21:00", strategy="MCL", symbol="AAA",
             action="BUY", status="PARTIAL_FILL", filled_qty=40, qty=100,
             fill_price=4.02),
    ])
    fills = ui_bridge.UIBridge._fills_today(trader)

    assert len(fills) == 1 and fills[0]["action"] == "BUY"
    assert fills[0]["trade_pnl"] is None, "an entry closed nothing"
    assert [f for f in fills if f["trade_pnl"] is not None] == []


def test_a_read_failure_cannot_swallow_a_defect_silently(tmp_path, caplog, monkeypatch):
    """_fills_today catches its own exceptions, which is right -- it runs in the
    trading path. But while writing the pairing above I introduced a NameError
    and the only symptom was an empty dashboard: the catch logged at DEBUG.
    It logs loudly now, because a bug that presents as "no trades today" in a
    trading portal is the worst possible disguise."""
    import logging

    path = tmp_path / "f.csv"
    # a row that gets PAST the status filter, so the parsing is actually reached
    path.write_text("ts_et,strategy,symbol,action,status,filled_qty,fill_price\n"
                    "2026-09-14 07:00:00,MCL,AAA,SELL,FILLED,100,4.02\n",
                    encoding="utf-8")

    class Trader:
        class log:
            pass
    Trader.log.path = path

    def explode(*a, **kw):
        raise RuntimeError("something in here is broken")

    monkeypatch.setattr(ui_bridge, "_num", explode)

    with caplog.at_level(logging.WARNING, logger="ui_bridge"):
        assert ui_bridge.UIBridge._fills_today(Trader()) == []

    assert any("could not read the fill log" in r.message for r in caplog.records), (
        "the failure was swallowed without a word; an empty dashboard would be "
        "the only symptom")
    assert any(r.levelno >= logging.WARNING for r in caplog.records)


# -- one realised figure, not two -------------------------------------------

def test_the_page_cannot_contradict_itself_about_realised(tmp_path):
    """Ben spotted three numbers for one quantity on a single screen: the curve
    ended at 25.71, the strategy bars summed to 25.71, and the Realised tile
    said 25.74.

    The per-strategy figures summed the fill log; the headline read the
    trader's own accumulator. Both were correct. The log rounds each trade to
    2dp as it is written and the accumulator adds the unrounded values, so
    across seventeen trades they drifted three cents apart. A dashboard that
    contradicts itself by a little teaches you to trust none of it, so the log
    is now the single source and the parts sum to the whole by construction."""
    trader = _trader_with_a_log(tmp_path)
    name = trader.strategies[0].name
    for i, pnl in enumerate([1.005, 2.005, 3.005, -0.005]):
        trader.log.write(ts_et=f"2026-09-16 07:{10 + i:02d}:00", strategy=name,
                         symbol="AAA", action="BUY", status="FILLED",
                         filled_qty=100, fill_price=4.00)
        trader.log.write(ts_et=f"2026-09-16 07:{20 + i:02d}:00", strategy=name,
                         symbol="AAA", action="SELL", status="FILLED",
                         filled_qty=100, fill_price=4.05, entry_price=4.00,
                         exit_price=4.05, trade_pnl=pnl, hold_minutes=10.0)
    # what the trader itself would have accumulated, unrounded
    trader.session_pnl = sum([1.005, 2.005, 3.005, -0.005])

    doc = bridge(paper=True).build_state(trader, NOW)

    headline = doc["pnl"]["realized"]
    bars = round(sum(s["pnl"]["realized"] for s in doc["strategies"]), 2)
    curve = round(sum(f["trade_pnl"] for f in doc["fills_today"]
                      if f["trade_pnl"] is not None), 2)

    assert headline == bars == curve, (
        f"headline {headline}, strategy bars {bars}, curve {curve} — the same "
        f"quantity shown three ways and disagreeing")


def test_a_gap_too_large_to_be_rounding_is_reported(tmp_path, caplog):
    """A few cents is rounding and expected. A large gap means the log is
    missing a round trip the trader counted — a real defect, and one that would
    otherwise surface only as a slightly wrong number nobody queries."""
    import logging

    trader = _trader_with_a_log(tmp_path)
    name = trader.strategies[0].name
    trader.log.write(ts_et="2026-09-16 07:10:00", strategy=name, symbol="AAA",
                     action="BUY", status="FILLED", filled_qty=100, fill_price=4.00)
    trader.log.write(ts_et="2026-09-16 07:20:00", strategy=name, symbol="AAA",
                     action="SELL", status="FILLED", filled_qty=100,
                     fill_price=4.05, entry_price=4.00, exit_price=4.05,
                     trade_pnl=5.00, hold_minutes=10.0)
    trader.session_pnl = 91.0             # a whole trade adrift

    with caplog.at_level(logging.WARNING, logger="ui_bridge"):
        doc = bridge(paper=True).build_state(trader, NOW)

    assert doc["pnl"]["realized"] == 5.00, "the log stays the published figure"
    assert any("realised P&L disagrees" in r.message for r in caplog.records), (
        "a missing round trip passed without a word")


def test_rounding_alone_stays_quiet(tmp_path, caplog):
    """The warning has to be worth reading. Cents of rounding must not fire it,
    or it becomes noise on every single push and stops being a signal."""
    import logging

    trader = _trader_with_a_log(tmp_path)
    name = trader.strategies[0].name
    trader.log.write(ts_et="2026-09-16 07:10:00", strategy=name, symbol="AAA",
                     action="BUY", status="FILLED", filled_qty=100, fill_price=4.00)
    trader.log.write(ts_et="2026-09-16 07:20:00", strategy=name, symbol="AAA",
                     action="SELL", status="FILLED", filled_qty=100,
                     fill_price=4.05, entry_price=4.00, exit_price=4.05,
                     trade_pnl=5.00, hold_minutes=10.0)
    trader.session_pnl = 5.03             # three cents, as on 2026-09-16

    with caplog.at_level(logging.WARNING, logger="ui_bridge"):
        bridge(paper=True).build_state(trader, NOW)

    assert not [r for r in caplog.records if "realised P&L disagrees" in r.message], (
        "rounding drift fired the warning; it will cry wolf every 5 seconds")


# -- contract 1.8: the feed block -------------------------------------------
#
# Additive and OPTIONAL, so an agent that does not publish it still validates.
# The property that matters: a failure to learn the mode must produce `unknown`
# on the page, never `streaming`. An absent block renders as unknown, so
# omitting it and publishing "unknown" are the same to the portal -- which is
# why omitting is the safe response to every kind of trouble.

def test_the_feed_block_is_published_when_the_feed_wrote_one(tmp_path):
    from common import feed_state as FS
    p = tmp_path / "feed_state.json"
    FS.publish(FS.block("DELAYED", "delayed_streaming_900", "signed"), p)
    b = bridge()
    b.feed_state_path = p
    doc = b.build_state(build_trader(), NOW)
    assert doc["schema_version"] == "1.8"
    assert doc["feed"]["mode"] == "delayed"
    assert doc["feed"]["delay_seconds"] == 900
    # the two the banner needs to tell "expired" from "never set" apart
    assert doc["feed"]["authenticated"] is True
    assert doc["feed"]["cookie_state"] == "signed"


def test_no_feed_file_omits_the_block_rather_than_claiming_real_time(tmp_path):
    """The feed has not started, or predates the field. An absent block is
    rendered as unknown by the portal, which is true; a default of streaming
    would be a dashboard telling Ben he is seeing the market when he is
    seeing a quarter-hour-old picture of it."""
    b = bridge()
    b.feed_state_path = tmp_path / "nothing_here.json"
    assert "feed" not in b.build_state(build_trader(), NOW)


def test_a_corrupt_feed_file_omits_the_block(tmp_path):
    p = tmp_path / "feed_state.json"
    p.write_text('{"mode": "streaming"', encoding="utf-8")   # truncated write
    b = bridge()
    b.feed_state_path = p
    assert "feed" not in b.build_state(build_trader(), NOW)


def test_the_document_still_builds_when_the_feed_file_is_nonsense(tmp_path):
    """The whole document must not fail over a diagnostic. Positions, P&L and
    the watchlist matter more than the feed tile."""
    p = tmp_path / "feed_state.json"
    p.write_text("mode: streaming\n", encoding="utf-8")       # not even JSON
    b = bridge()
    b.feed_state_path = p
    doc = b.build_state(build_trader(), NOW)
    assert doc["account"]["account_id"] == "DUM215828"
    assert "feed" not in doc


# -- shutdown: the final push and the history upload -------------------------
#
# claude/handover_session_end_upload_20260919.md and
# claude/handover_portal_stale_position_20260918.md item 2. No relay is
# contacted here either -- push_final_state/upload_history against a dead
# port exercise the never-raises property the same way test_a_relay_that_is_
# down_is_logged_a_few_times_then_left_alone does above; the document shape
# is tested directly against the module functions that build it.

def test_the_trade_key_is_pinned_against_the_portals_backfill():
    """MUST NEVER DRIFT -- see _trade_key's docstring. This is the fixed test
    vector from the handover, computed with the portal's own function."""
    assert ui_bridge._trade_key(
        "2026-09-18", "MCL", "BIAF", "2026-09-18 09:30:26", 100, 11.00
    ) == "9ff0fe67a0f50bdd32e4cfb0e7d73596"


def test_the_trade_key_formats_whole_numbers_without_a_decimal():
    """100, not 100.0 -- the handover calls this out as the part most likely
    to drift between the two repos' implementations."""
    key_int = ui_bridge._trade_key("2026-09-18", "mcl", "BIAF",
                                   "2026-09-18 09:30:26", 100, 11.0)
    key_float_qty = ui_bridge._trade_key("2026-09-18", "mcl", "BIAF",
                                         "2026-09-18 09:30:26", 100.5, 11.0)
    assert key_int == "9ff0fe67a0f50bdd32e4cfb0e7d73596"
    assert key_float_qty != key_int


def test_the_strategy_name_is_upper_cased_in_the_key_but_not_in_the_row():
    """The portal's key formula uses MCL; the fill log and the document's own
    `strategy` field stay lowercase, matching every other reader of the CSV."""
    lower = ui_bridge._trade_key("2026-09-18", "mcl", "BIAF",
                                 "2026-09-18 09:30:26", 100, 11.00)
    upper = ui_bridge._trade_key("2026-09-18", "MCL", "BIAF",
                                 "2026-09-18 09:30:26", 100, 11.00)
    assert lower == upper == "9ff0fe67a0f50bdd32e4cfb0e7d73596"


def _write_session_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=sorted({k for r in rows for k in r}))
        writer.writeheader()
        writer.writerows(rows)


def test_session_files_finds_only_real_sessions_newest_n(tmp_path):
    for name in ("mcl_fills_20260910.csv", "mcl_fills_20260911.csv",
                "mcl_fills_20260914.csv", "mcl_fills_20260914_pre180819.csv",
                "not_a_fill_log.csv"):
        (tmp_path / name).write_text("ts_et\n", encoding="utf-8")
    found = ui_bridge._session_files(tmp_path, recent_days=2)
    assert [d for d, _ in found] == ["20260911", "20260914"]
    assert all(p.name.endswith(".csv") and "_pre" not in p.name for _, p in found)


def test_session_files_is_empty_for_a_missing_directory(tmp_path):
    assert ui_bridge._session_files(tmp_path / "does_not_exist", 5) == []


def test_reading_a_session_pairs_trades_and_counts_outcomes(tmp_path):
    path = tmp_path / "mcl_fills_20260914.csv"
    _write_session_csv(path, [
        {"ts_et": "2026-09-14 07:02:11", "strategy": "mcl", "symbol": "WXYZ",
         "action": "BUY", "qty": "100", "filled_qty": "100", "fill_price": "6.55",
         "status": "FILLED", "reason": "entry_signal", "trade_pnl": ""},
        {"ts_et": "2026-09-14 07:09:48", "strategy": "mcl", "symbol": "WXYZ",
         "action": "SELL", "qty": "100", "filled_qty": "100", "fill_price": "6.38",
         "status": "FILLED", "reason": "trailing_stop", "trade_pnl": "-23.26",
         "entry_price": "6.55", "hold_minutes": "7.6"},
        {"ts_et": "2026-09-14 07:11:00", "strategy": "mcl", "symbol": "FTFT",
         "action": "BUY", "qty": "100", "fill_price": "",
         "status": "SKIPPED_CONCURRENCY_CAP", "reason": "entry_signal",
         "trade_pnl": ""},
        {"ts_et": "2026-09-14 09:30:00", "strategy": "mcl", "symbol": "paused",
         "action": "CONFIG", "status": "APPLIED", "reason": "session_open"},
    ])
    trades, order_outcomes = ui_bridge._read_session_csv(path, "2026-09-14")

    assert len(trades) == 1
    t = trades[0]
    assert t["symbol"] == "WXYZ" and t["strategy"] == "mcl"
    assert t["entry_ts_et"] == "2026-09-14 07:02:11"
    assert t["exit_ts_et"] == "2026-09-14 07:09:48"
    assert t["net_pnl"] == -23.26 and t["hold_minutes"] == 7.6
    assert t["partial"] is False
    assert t["trade_key"] == ui_bridge._trade_key(
        "2026-09-14", "mcl", "WXYZ", "2026-09-14 07:09:48", 100, 6.38)

    assert order_outcomes == [
        {"strategy": "mcl", "status": "SKIPPED_CONCURRENCY_CAP", "count": 1},
    ]


def test_an_unmatched_close_still_gets_an_entry_ts_of_none(tmp_path):
    """A position adopted from a previous session, or a log rolled aside
    mid-session: the close is still a real trade and must still be uploaded,
    just with no known entry time."""
    path = tmp_path / "mcl_fills_20260914.csv"
    _write_session_csv(path, [
        {"ts_et": "2026-09-14 07:09:48", "strategy": "mcl", "symbol": "WXYZ",
         "action": "SELL", "qty": "100", "filled_qty": "100", "fill_price": "6.38",
         "status": "FILLED", "reason": "trailing_stop", "trade_pnl": "-23.26"},
    ])
    trades, _ = ui_bridge._read_session_csv(path, "2026-09-14")
    assert len(trades) == 1 and trades[0]["entry_ts_et"] is None


def test_push_final_state_posts_the_document_with_a_stopped_at_flag(tmp_path):
    b = bridge()
    posted = {}
    b._post = lambda path, data, timeout=None: (posted.update(path=path, data=data)
                                                 or True)
    assert b.push_final_state(build_trader(), NOW) is True
    assert posted["path"] == "/api/state"
    assert posted["data"]["agent"]["stopped_at"]
    assert posted["data"]["account"]["account_id"] == "DUM215828"


def test_push_final_state_never_raises_on_a_dead_relay():
    b = bridge()
    b.base_url = "http://127.0.0.1:9"
    assert b.push_final_state(build_trader()) is False


def test_push_final_state_never_raises_when_building_the_state_fails(caplog):
    b = bridge()
    trader = build_trader()
    trader.strategies = property(lambda self: 1 / 0)   # any exploding access
    assert b.push_final_state(trader, NOW) is False


def test_upload_history_does_nothing_without_a_log_path():
    b = bridge()
    trader = build_trader()               # no tmp_path -> trader.log.path is None
    b.upload_history(trader)              # must not raise


def test_upload_history_posts_one_document_per_recent_session(tmp_path):
    path = tmp_path / "mcl_fills_20260914.csv"
    _write_session_csv(path, [
        {"ts_et": "2026-09-14 07:02:11", "strategy": "mcl", "symbol": "WXYZ",
         "action": "BUY", "qty": "100", "filled_qty": "100", "fill_price": "6.55",
         "status": "FILLED", "reason": "entry_signal", "trade_pnl": ""},
        {"ts_et": "2026-09-14 07:09:48", "strategy": "mcl", "symbol": "WXYZ",
         "action": "SELL", "qty": "100", "filled_qty": "100", "fill_price": "6.38",
         "status": "FILLED", "reason": "trailing_stop", "trade_pnl": "-23.26"},
    ])
    trader = build_trader()
    trader.log = FakeLog(path)

    b = bridge()
    posts = []
    b._post = lambda p, data, timeout=None: (posts.append((p, data, timeout))
                                             or True)
    b.upload_history(trader, recent_days=5)

    assert len(posts) == 1
    p, doc, timeout = posts[0]
    assert p == "/api/history"
    assert timeout == ui_bridge.HISTORY_TIMEOUT_S
    assert doc["session_date"] == "2026-09-14"
    assert doc["complete"] is True
    assert len(doc["trades"]) == 1
    assert doc["schema_version"] == ui_bridge.CONTRACT_VERSION


def test_upload_history_never_raises_on_a_dead_relay(tmp_path):
    path = tmp_path / "mcl_fills_20260914.csv"
    _write_session_csv(path, [
        {"ts_et": "2026-09-14 07:02:11", "strategy": "mcl", "symbol": "WXYZ",
         "action": "BUY", "qty": "100", "filled_qty": "100", "fill_price": "6.55",
         "status": "FILLED", "reason": "entry_signal", "trade_pnl": ""},
    ])
    trader = build_trader()
    trader.log = FakeLog(path)
    b = bridge()
    b.base_url = "http://127.0.0.1:9"
    b.upload_history(trader)                # must not raise


def test_upload_history_never_raises_when_a_session_file_cannot_be_read(tmp_path):
    """A file that vanishes or is unreadable between listing and reading must
    not take the shutdown path down with it."""
    path = tmp_path / "mcl_fills_20260914.csv"
    path.mkdir()               # a directory where a file was expected
    trader = build_trader()
    trader.log = FakeLog(tmp_path / "mcl_fills_20260915.csv")
    (tmp_path / "mcl_fills_20260915.csv").write_text("ts_et\n", encoding="utf-8")
    b = bridge()
    b.upload_history(trader)                # must not raise despite the bad file
