#!/usr/bin/env python3
r"""Publish the live trader's state to the portal, and take commands back.

    https://github.com/bgysiu85/algo-trading-ui

The portal is a separate program in a separate repo. It knows nothing about
this one: it renders whatever document arrives and offers whatever commands
that document advertises. This module is the only place that knows both, and
it is deliberately dumb -- it reads the trader's own state and reshapes it.

WHAT THIS MUST NEVER DO
-----------------------
* **Never block the trading loop.** Every network call runs in a worker thread
  with a short timeout, and every failure is swallowed and logged. A relay that
  is down, slow or lying must be indistinguishable, from the trader's point of
  view, from one that was never configured.
* **Never place or cancel an order.** It changes flags the trader already
  honours -- paused, the position cap, a trail percentage for new positions.
* **Never act on a command unless the account is paper.** The trader's own
  `DU` check is the first guard, the relay's is the second, and this is the
  third. Three, because the cost of being wrong is a real order.

It is off unless configured. `from_env()` returns None when `UI_RELAY_URL` is
unset, and the trader then runs exactly as it did before this file existed.

Environment:
    UI_RELAY_URL        e.g. http://127.0.0.1:8000
    UI_AGENT_TOKEN      the relay's agent token, or
    UI_AGENT_TOKEN_FILE a path to read it from (D:\Trading UI\var\agent_token.txt)
    UI_AGENT_ID         a name for this trader in the portal (default: hostname)
"""
from __future__ import annotations

import asyncio
import csv
import dataclasses
import json
import logging
import os
import socket
import time
import urllib.error
import urllib.request
from datetime import datetime, time as dtime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any

LOG = logging.getLogger("ui_bridge")

# Every module in this repo names the exchange clock for itself; this is a
# fact about the market, not a value anyone configures.
ET = ZoneInfo("America/New_York")

CONTRACT_VERSION = "1.4"
PUSH_EVERY_S = 5.0
HTTP_TIMEOUT_S = 3.0
MAX_FILLS = 500
MAX_NOTIFICATIONS = 100
MAX_EVENTS = 20

# After this many consecutive failures, complain once and then stay quiet:
# a relay that is down for an hour must not write 700 lines into the session log.
QUIET_AFTER = 3

# -- the CONFIG row --------------------------------------------------------
# A command applied from a browser changes how the session trades. The fill log
# is where that belongs: durable, time-ordered WITH the trades, and the one
# ledger every reader already opens. SKIPPED_PAUSED is the precedent -- a row
# that records a decision rather than a trade.
#
# paper_fill's primary key is (session_date, ts_et, strategy, symbol, action,
# status) at second resolution, and that decides three fields:
#
#   symbol    the SETTING NAME, lowercase. It is the only key field left that
#             can separate two different settings changed in the same second by
#             the same strategy; without it the second one silently replaces the
#             first in the loader's de-duplicator, and the row that vanishes is
#             the one from the busy moment. Lowercase because every real ticker
#             in this table is uppercase, so a listing shows at a glance that
#             the row is not a symbol.
#   strategy  the adapter the change applied to, ONE ROW PER ADAPTER, never a
#             synthetic "ALL". strategy is both a key column and the grouping
#             column in every census; a phantom name would appear in "which
#             strategies traded" for as long as the table exists. A global pause
#             genuinely IS both adapters changing.
#   status    APPLIED or REJECTED, so both in the same second are two rows.
#
# Everything else fits columns that already exist, so no schema change and no
# loader change -- which matters, because a column added to FIELDS and
# db.paper_fill but not to load_paper_fills loads as null on every row while
# every test passes. That happened today, to trail_pct.
CONFIG_ACTION = "CONFIG"
CONFIG_APPLIED = "APPLIED"
CONFIG_REJECTED = "REJECTED"

# Short, stable names -- NOT the contract keys. db.SYM is 24 and
# "max_concurrent_positions" is exactly 24, which is a truncation waiting for a
# longer setting. A test pins every name against db.SYM with room to spare.
SETTING_PAUSED = "paused"
SETTING_ENABLED = "enabled"
SETTING_TRAIL = "trail_pct"
SETTING_CAP = "max_positions"
SETTING_UNKNOWN = "command"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _session_state(now_et: datetime) -> str:
    """Which part of the US equities day this is, for the portal's header."""
    t = now_et.time()
    if t < dtime(4, 0):
        return "closed"
    if t < dtime(9, 30):
        return "premarket"
    if t < dtime(16, 0):
        return "rth"
    if t < dtime(20, 0):
        return "after"
    return "closed"


def _rebind_adapter(trader, old, new) -> None:
    """Swap one StrategyAdapter for another everywhere the trader holds it.

    StrategyAdapter is a frozen dataclass, and should stay that way: it is a
    VALUE describing a strategy, and the whole point of reading its fields off
    the strategy module is that nobody gets to keep a private, drifted copy.
    So changing the trail does not mutate the adapter -- it builds the next
    value and rebinds every reference to it.

    Both places matter. `trader.strategies` is what the next state document
    reports and what a later command looks the adapter up in; `SymbolState
    .strategy` is what an ENTRY reads to stamp the trail onto the Position. Miss
    the second and the portal would report the new trail while entries kept
    taking the old one -- a number in a browser disagreeing with the trade.

    Open positions are untouched by construction: the trader copies trail_pct
    into Position at entry, so a position carries the trail it was opened with
    and no later change reaches it.
    """
    for i, a in enumerate(getattr(trader, "strategies", [])):
        if a is old:
            trader.strategies[i] = new
    for st in getattr(trader, "states", {}).values():
        if getattr(st, "strategy", None) is old:
            st.strategy = new


def _ascii(text: str) -> str:
    """Plain ASCII, for the two free-text columns of a CONFIG row.

    The fill log is written UTF-8 and every reader in this repo should open it
    the same way -- but `friction.load` opens it with the locale encoding, and a
    log is also something Ben opens in Excel. An em dash that renders as a
    mojibake blob in one reader and correctly in another is a small, permanent
    irritation in the one file everything reads. The text here is machine
    detail, not prose, so it loses nothing by being ASCII.
    """
    return (text or "").replace("\u2014", "--").replace("\u2013", "-") \
                       .replace("\u2192", "->").encode("ascii", "replace") \
                       .decode("ascii")


def _round_trip_costs(entry: float | None, exit_px: float, qty: float,
                      net: float | None) -> tuple[float | None, float | None]:
    """(gross, commission) for a closed round trip, or (None, None).

    The trader computes net as (exit - entry) * qty - commission, charging both
    legs from common/commissions.py. So gross is recoverable from the prices on
    the row, and the fee is the difference.

    DERIVED, not recomputed. Calling order_cost again here would be a second
    calculation of the same number, agreeing with the first until someone
    changes a schedule and only one of them follows. Subtracting guarantees the
    three figures reconcile on screen, which is the property a reader checks by
    eye.

    Commission is returned POSITIVE, as a cost. The page renders it negative;
    publishing it signed would make "is this already negative?" a question
    every consumer has to ask.
    """
    if entry is None or net is None or not qty:
        return None, None
    gross = round((exit_px - entry) * qty, 2)
    return gross, round(gross - net, 2)


class UIBridge:
    """One-way state out, commands back. Constructed by `from_env`."""

    def __init__(self, base_url: str, token: str, agent_id: str = "",
                 push_every_s: float = PUSH_EVERY_S,
                 timeout_s: float = HTTP_TIMEOUT_S):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.agent_id = agent_id or socket.gethostname().lower()
        self.push_every_s = push_every_s
        self.timeout_s = timeout_s

        self._last_push = 0.0
        self._failures = 0
        self._notifications: list[dict[str, Any]] = []
        self._events: list[dict[str, Any]] = []
        self._seq = 0
        self.account_id = ""
        self.is_paper = False
        self._session_open_written = False

    # -- construction ------------------------------------------------------
    @classmethod
    def from_env(cls, env: dict[str, str] | None = None, *,
                 dry_run: bool = False) -> "UIBridge | None":
        """The bridge, or None when it should stay off.

        `dry_run` is the mode the trader was started in, and it is a gate
        because the relay holds ONE state document. A dry session and the
        production session both publishing means the dashboard flips between
        two traders and a command reaches whichever polled first -- with
        `stop` and the position cap among the commands, that is not cosmetic.

        Gating here rather than asking the operator to remember is the point:
        the settings can then live at machine level, where they survive a
        reboot, instead of being two lines that have to be typed into the right
        window every session. UI_PUBLISH_DRY=1 puts a dry run on the dashboard
        deliberately, which is occasionally what you want while developing.
        """
        env = os.environ if env is None else env
        url = (env.get("UI_RELAY_URL") or "").strip()
        if not url:
            return None

        if dry_run and (env.get("UI_PUBLISH_DRY") or "").strip().lower() \
                not in ("1", "true", "yes", "on"):
            LOG.info("portal: a dry run does not publish (UI_PUBLISH_DRY=1 "
                     "if you want it to)")
            return None

        token = (env.get("UI_AGENT_TOKEN") or "").strip()
        if not token:
            path = (env.get("UI_AGENT_TOKEN_FILE") or "").strip()
            if path and Path(path).exists():
                token = Path(path).read_text(encoding="utf-8").strip()
        if not token:
            LOG.warning("UI_RELAY_URL is set but no agent token is; the portal "
                        "bridge stays off rather than pushing unauthenticated")
            return None

        return cls(url, token, agent_id=(env.get("UI_AGENT_ID") or "").strip())

    # -- what the trader tells us -----------------------------------------
    def note_account(self, account_id: str) -> None:
        """Called once at startup, with the account the trader connected to."""
        self.account_id = account_id or ""
        self.is_paper = self.account_id.upper().startswith("DU")

    def record_message(self, text: str, kind: str = "other",
                       status: str = "sent", error: str | None = None) -> None:
        """Mirror a Telegram message into the portal's Messages tab.

        The text is passed through unchanged, Telegram markup and all: the
        portal renders that markup itself, from an allowlist.
        """
        self._seq += 1
        self._notifications.append({
            "id": f"n-{datetime.now().strftime('%Y%m%d')}-{self._seq:05d}",
            "sent_at": _utc_now(),
            "channel": "telegram",
            "status": status,
            "kind": kind,
            "format": "telegram_html",
            "text": text,
            "error": error,
        })
        del self._notifications[:-MAX_NOTIFICATIONS]

    def record_event(self, level: str, text: str) -> None:
        self._events.append({"ts": _utc_now(), "level": level, "text": text})
        del self._events[:-MAX_EVENTS]

    # -- building the document --------------------------------------------
    def build_state(self, trader, now_et: datetime) -> dict[str, Any]:
        """The whole of what the portal shows, read off the trader.

        A full snapshot every time, never a delta: a push that goes missing
        then costs nothing.
        """
        positions = []
        for st in getattr(trader, "states", {}).values():
            pos = getattr(st, "position", None)
            if pos is None:
                continue
            last = self._last_price(trader, st)
            positions.append({
                "strategy": getattr(getattr(st, "strategy", None), "name", "") or "",
                "symbol": st.symbol,
                "qty": pos.qty,
                "avg_price": round(float(pos.entry_price), 4),
                "opened_at": _iso(getattr(pos, "entry_time", None)),
                "last_price": last,
                "unrealized_pnl": (None if last is None
                                   else round((last - pos.entry_price) * pos.qty, 2)),
                "stop": {
                    "type": "trailing_pct",
                    "level": round(pos.trail_level(), 4),
                    # Outside regular hours IBKR takes Day Limit orders only,
                    # so every stop here is ours to enforce. The portal shows
                    # that, because it is the risk if this process dies.
                    "managed_by": "agent",
                },
            })

        fills = self._fills_today(trader)
        strategies = []
        for adapter in getattr(trader, "strategies", []):
            name = getattr(adapter, "name", "")
            closed = [f for f in fills
                      if f.get("strategy") == name and f.get("trade_pnl") is not None]
            strategies.append({
                "name": name,
                "enabled": name not in getattr(trader, "disabled_strategies", set()),
                "paused": bool(getattr(trader, "paused", False)),
                "paused_since": None,
                "pnl": {
                    "realized": round(sum(f["trade_pnl"] for f in closed), 2),
                    "unrealized": round(sum(p["unrealized_pnl"] or 0.0 for p in positions
                                            if p["strategy"] == name), 2),
                    "friction_charged": False,
                    "trades": len(closed),
                },
            })

        unrealized = round(sum(p["unrealized_pnl"] or 0.0 for p in positions), 2)
        return {
            "schema_version": CONTRACT_VERSION,
            "sent_at": _utc_now(),
            "agent": {"id": self.agent_id, "kind": "trader", "version": "1"},
            "session": {
                "state": _session_state(now_et),
                "opened_at": None,
                "clock_et": now_et.strftime("%H:%M:%S"),
                "exchange": "US equities",
            },
            "account": {
                "broker": "ibkr",
                "account_id": self.account_id,
                "is_paper": self.is_paper,
                "mode": "dry" if getattr(trader, "dry_run", False) else "paper",
            },
            "strategies": strategies,
            "positions": positions,
            "fills_today": fills[-MAX_FILLS:],
            "pnl": {
                "realized": round(float(getattr(trader, "session_pnl", 0.0)), 2),
                "unrealized": unrealized,
                "commission": None,
                # The fill log charges commission only. Saying so is the rule:
                # a commission-only number is not "after costs".
                "friction_charged": False,
                "friction_per_round_trip": 4.26,
                "currency": "USD",
            },
            "watchlist": self._watchlist(trader),
            "settings": self._settings(trader),
            "commands_available": self._commands(trader),
            "health": {
                "broker_connected": bool(getattr(getattr(trader, "ib", None),
                                                 "isConnected", lambda: False)()),
                "data_stale_seconds": None,
                "uptime_s": None,
                "last_error": None,
            },
            "events": list(self._events),
            "notifications": list(self._notifications),
            "links": [],
        }

    @staticmethod
    def _last_price(trader, st) -> float | None:
        """Mid of the streaming quote, or nothing. Never an exception: a
        missing quote must not stop the push."""
        try:
            bid, ask = trader.quote(st)
        except Exception:                                   # noqa: BLE001
            return None
        prices = [p for p in (bid, ask) if p and p > 0]
        return round(sum(prices) / len(prices), 4) if prices else None

    @staticmethod
    def _fills_today(trader) -> list[dict[str, Any]]:
        """Read the session's fill log — the same file every study reads.

        Deliberately not a second record kept in memory: one source, and the
        portal then cannot disagree with the CSV that the analysis uses.
        """
        log = getattr(trader, "log", None)
        path = getattr(log, "path", None)
        if not path or not Path(path).exists():
            return []
        out: list[dict[str, Any]] = []
        try:
            with Path(path).open(newline="", encoding="utf-8-sig") as fh:
                for i, row in enumerate(csv.DictReader(fh)):
                    if (row.get("status") or "").upper() != "FILLED":
                        continue
                    qty = _num(row.get("filled_qty")) or _num(row.get("qty")) or 0
                    price = _num(row.get("fill_price")) or 0.0
                    entry = _num(row.get("entry_price"))
                    net = _num(row.get("trade_pnl"))
                    gross, commission = _round_trip_costs(entry, price, qty, net)
                    out.append({
                        "id": f"f-{i:05d}",
                        "ts_et": (row.get("ts_et") or "").split(" ")[-1],
                        "strategy": row.get("strategy") or "",
                        "symbol": row.get("symbol") or "",
                        "action": (row.get("action") or "").upper(),
                        "qty": qty,
                        "entry_price": entry,
                        "price": price,
                        "commission": commission,
                        "reason": row.get("reason") or None,
                        "gross_pnl": gross,
                        "trade_pnl": net,
                        "friction_charged": False,
                    })
        except Exception as e:                              # noqa: BLE001
            LOG.debug("could not read the fill log for the portal: %s", e)
        return out

    @staticmethod
    def _watchlist(trader) -> list[dict[str, Any]]:
        seen: dict[str, dict[str, Any]] = {}
        for st in getattr(trader, "states", {}).values():
            status = ("blocked" if getattr(st, "blocked", False)
                      else "retired" if getattr(st, "retired", False) else "active")
            # blocked beats retired beats active when two strategies disagree
            rank = {"blocked": 2, "retired": 1, "active": 0}
            if st.symbol not in seen or rank[status] > rank[seen[st.symbol]["status"]]:
                seen[st.symbol] = {"symbol": st.symbol, "status": status, "note": None}
        return sorted(seen.values(), key=lambda r: r["symbol"])

    @staticmethod
    def _settings(trader) -> list[dict[str, Any]]:
        """What the portal may offer to change. Anything absent is not editable,
        and anything here says which command applies it."""
        settings = [{
            "key": "max_concurrent_positions",
            "label": "Max concurrent positions",
            "group": "Risk",
            "type": "number",
            "value": int(getattr(trader, "max_positions", 0)),
            "min": 0, "max": 10, "step": 1,
            "editable_now": True,
            "applies_to": "new_positions",
            "set_command": "set_setting",
            "description": "0 takes no new entries and still records signals.",
        }]
        for adapter in getattr(trader, "strategies", []):
            settings.append({
                "key": f"trail_pct:{adapter.name}",
                "label": f"Trailing stop — {adapter.name}",
                "group": "Exits",
                "type": "number",
                "value": float(adapter.trail_pct),
                "min": 0.5, "max": 20, "step": 0.5, "unit": "%",
                "editable_now": True,
                "applies_to": "new_positions",
                "set_command": "set_setting",
                "description": "Open positions keep the trail they were opened with.",
            })
            settings.append({
                "key": f"price_band:{adapter.name}",
                "label": f"Entry price band — {adapter.name}",
                "group": "Universe",
                "type": "string",
                "value": f"${adapter.price_min:.2f}–${adapter.price_max:.2f}",
                "editable_now": False,
                "applies_to": "next_session",
                "set_command": None,
                "description": "Enforced at entry; changing it is a repo change.",
            })
        return settings

    def _commands(self, trader) -> list[dict[str, Any]]:
        """Nothing is offered on a live account, however the relay is configured."""
        if not self.is_paper:
            return []
        paused = bool(getattr(trader, "paused", False))
        names = [getattr(a, "name", "") for a in getattr(trader, "strategies", [])]
        return [
            {"type": "start", "label": "Start", "confirm": False, "args_schema": None}
            if paused else
            {"type": "stop", "label": "Stop new entries", "confirm": True,
             "args_schema": None},
            {"type": "set_strategy_enabled", "label": "Enable or disable a strategy",
             "confirm": False,
             "args_schema": {"type": "object", "required": ["strategy", "enabled"],
                             "properties": {"strategy": {"type": "string", "enum": names},
                                            "enabled": {"type": "boolean"}}}},
            {"type": "set_setting", "label": "Change a parameter", "confirm": False,
             "args_schema": {"type": "object", "required": ["key", "value"],
                             "properties": {"key": {"type": "string"}, "value": {}}}},
        ]

    # -- the CONFIG row ----------------------------------------------------
    @staticmethod
    def _adapter_names(trader) -> list[str]:
        return [getattr(a, "name", "") for a in getattr(trader, "strategies", [])
                if getattr(a, "name", "")]

    def _scope(self, trader, kind: str, args: dict[str, Any]) -> tuple[str, list[str]]:
        """(setting name, the adapters it applied to).

        A change that is genuinely global lists every adapter, because one row
        per adapter is the truthful record of it and a synthetic "ALL" would
        become a phantom strategy in every census that groups by the column.
        """
        every = self._adapter_names(trader)
        if kind in ("stop", "pause", "start", "resume"):
            return SETTING_PAUSED, every
        if kind == "set_strategy_enabled":
            named = args.get("strategy")
            return SETTING_ENABLED, [named] if named in every else every
        if kind == "set_setting":
            key = args.get("key") or ""
            if isinstance(key, str) and key.startswith("trail_pct:"):
                named = key.split(":", 1)[1]
                return SETTING_TRAIL, [named] if named in every else every
            if key == "max_concurrent_positions":
                return SETTING_CAP, every
        return SETTING_UNKNOWN, every

    def record_config(self, trader, *, now_et: datetime, setting: str,
                      status: str, reason: str, detail: str,
                      strategies: list[str], trail_pct: float | None = None) -> None:
        """Write one CONFIG row per adapter into the trader's OWN fill log.

        Never raises. This is called from inside the trading loop, and a log
        that cannot be written is not a reason to stop trading -- but it IS
        logged at exception level, because a silent recorder is the failure
        this row exists to make impossible.
        """
        log = getattr(trader, "log", None)
        if log is None:
            return
        for name in (strategies or [""]):
            try:
                log.write(ts_et=now_et.strftime("%Y-%m-%d %H:%M:%S"),
                          strategy=name,
                          symbol=setting,
                          action=CONFIG_ACTION,
                          status=status,
                          reason=_ascii(reason)[:32],
                          reject_reason=_ascii(detail)[:255],
                          trail_pct=trail_pct)
            except Exception:                               # noqa: BLE001
                LOG.exception("could not write the CONFIG row for %s/%s",
                              name, setting)

    def record_session_open(self, trader, now_et: datetime) -> None:
        """One row per adapter at startup, with the values in force.

        A journal that writes only on CHANGE cannot tell "nobody touched it"
        from "the recorder was broken" -- both are an empty file. This turns the
        absence of a change into a positive record, gives the first command of
        the day something to be a diff from, and means no reader has to fall
        back on "presumably the default" for the rows before it.
        """
        if self._session_open_written:
            return
        self._session_open_written = True
        cap = getattr(trader, "max_positions", None)
        paused = bool(getattr(trader, "paused", False))
        disabled = set(getattr(trader, "disabled_strategies", ()) or ())
        for adapter in getattr(trader, "strategies", []):
            name = getattr(adapter, "name", "")
            trail = getattr(adapter, "trail_pct", None)
            self.record_config(
                trader, now_et=now_et, setting=SETTING_TRAIL,
                status=CONFIG_APPLIED, reason="session_open",
                detail=(f"trail_pct={trail} paused={paused} "
                        f"max_positions={cap} enabled={name not in disabled} "
                        f"portal={self.base_url}"),
                strategies=[name], trail_pct=trail)

    # -- applying a command ------------------------------------------------
    def apply(self, trader, command: dict[str, Any],
              now_et: datetime | None = None) -> dict[str, Any]:
        """Answer every command, including the ones refused. Never raises.

        Every answer is also written to the fill log as a CONFIG row, applied
        and rejected alike. A rejected command that left no trace would read as
        a command nobody sent, which is the same ambiguity a declined entry
        writing no row would create.
        """
        kind = command.get("type")
        args = command.get("args") or {}
        answer = self._decide(trader, kind, args)

        try:
            setting, scope = self._scope(trader, kind or "", args)
            self.record_config(
                trader, now_et=now_et or datetime.now(ET), setting=setting,
                status=(CONFIG_APPLIED if answer["status"] == "applied"
                        else CONFIG_REJECTED),
                reason=str(kind or "unknown"),
                detail=answer.get("detail", ""),
                strategies=scope,
                trail_pct=self._new_trail(trader, kind, args, answer))
        except Exception:                                   # noqa: BLE001
            LOG.exception("could not record the CONFIG row for %s", kind)
        return answer

    @staticmethod
    def _new_trail(trader, kind, args, answer) -> float | None:
        """The trail column on a CONFIG row, populated only when the row IS a
        trail change that took effect. Reading it back off the adapter rather
        than off the request means the row records what the trader now has, not
        what was asked for."""
        if kind != "set_setting" or answer.get("status") != "applied":
            return None
        key = args.get("key") or ""
        if not (isinstance(key, str) and key.startswith("trail_pct:")):
            return None
        name = key.split(":", 1)[1]
        adapter = next((a for a in getattr(trader, "strategies", [])
                        if getattr(a, "name", "") == name), None)
        return getattr(adapter, "trail_pct", None)

    def _decide(self, trader, kind, args: dict[str, Any]) -> dict[str, Any]:
        """The answer itself. Split out so apply() can record every outcome in
        one place rather than at each return."""

        if not self.is_paper:
            return _ack("rejected", "this trader is not on a paper account",
                        "not_paper_account")

        try:
            if kind in ("stop", "pause"):
                trader.paused = True
                open_now = sum(1 for s in trader.states.values() if s.position is not None)
                detail = f"no new entries; {open_now} open position(s) still managed"
                self.record_event("warn", f"stopped from the portal: {detail}")
                return _ack("applied", detail)

            if kind in ("start", "resume"):
                trader.paused = False
                self.record_event("info", "started from the portal")
                return _ack("applied", "entries enabled")

            if kind == "set_strategy_enabled":
                name, on = args.get("strategy"), args.get("enabled")
                known = {a.name for a in trader.strategies}
                if name not in known:
                    return _ack("rejected", f"no strategy {name!r} is running",
                                "bad_args")
                if not isinstance(on, bool):
                    return _ack("rejected", "enabled must be true or false", "bad_args")
                if on:
                    trader.disabled_strategies.discard(name)
                else:
                    trader.disabled_strategies.add(name)
                self.record_event("info", f"{name} {'enabled' if on else 'disabled'} "
                                          f"from the portal")
                return _ack("applied", f"{name} {'enabled' if on else 'disabled'}")

            if kind == "set_setting":
                return self._set_setting(trader, args)

            return _ack("rejected", f"this trader does not accept {kind!r}",
                        "unknown_command")
        except Exception as e:                              # noqa: BLE001
            LOG.exception("portal command %s failed", kind)
            return _ack("rejected", f"the trader raised {e.__class__.__name__}: {e}",
                        "agent_busy")

    def _set_setting(self, trader, args: dict[str, Any]) -> dict[str, Any]:
        key, value = args.get("key"), args.get("value")

        if key == "max_concurrent_positions":
            number = _num(value)
            if number is None or number < 0 or number > 10 or number != int(number):
                return _ack("rejected", "a whole number between 0 and 10", "bad_args")
            was, trader.max_positions = trader.max_positions, int(number)
            self.record_event("info", f"max concurrent positions {was} -> {int(number)}")
            return _ack("applied", f"cap set to {int(number)}; open positions are kept")

        if isinstance(key, str) and key.startswith("trail_pct:"):
            name = key.split(":", 1)[1]
            adapter = next((a for a in trader.strategies if a.name == name), None)
            if adapter is None:
                return _ack("rejected", f"no strategy {name!r} is running", "bad_args")
            number = _num(value)
            if number is None or not (0.5 <= number <= 20):
                return _ack("rejected", "a percentage between 0.5 and 20", "bad_args")
            was = adapter.trail_pct
            _rebind_adapter(trader, adapter,
                            dataclasses.replace(adapter, trail_pct=float(number)))
            self.record_event("info", f"{name} trail {was}% -> {float(number)}%")
            return _ack("applied", f"{name} trail set to {number}% — new positions only")

        return _ack("rejected", f"{key!r} cannot be changed from the portal",
                    "not_applicable_now")

    # -- the loop ----------------------------------------------------------
    async def tick(self, trader, now_et: datetime | None = None) -> None:
        """Push, collect, answer. Called from the trading loop; never raises,
        and returns immediately when it is not yet time to push."""
        clock = now_et or datetime.now(ET)
        # BEFORE the throttle, and before anything touches the network: the
        # session-open record is about the TRADER's session, not the portal's
        # health, so a relay that never answers must not cost us the row.
        try:
            self.record_session_open(trader, clock)
        except Exception:                                   # noqa: BLE001
            LOG.exception("could not record the session-open rows")

        if time.monotonic() - self._last_push < self.push_every_s:
            return
        self._last_push = time.monotonic()

        try:
            state = self.build_state(trader, clock)
        except Exception:                                   # noqa: BLE001
            LOG.exception("could not build the portal state; skipping this push")
            return

        ok = await asyncio.to_thread(self._post, "/api/state", state)
        if not ok:
            return
        for command in await asyncio.to_thread(self._get, "/api/commands"):
            answer = self.apply(trader, command, clock)
            LOG.info("portal command %s (%s) -> %s: %s", command.get("type"),
                     command.get("id"), answer["status"], answer["detail"])
            await asyncio.to_thread(
                self._post, f"/api/commands/{command['id']}/ack",
                {"schema_version": CONTRACT_VERSION, "id": command["id"],
                 "acked_at": _utc_now(), **answer})

    # -- transport ---------------------------------------------------------
    def _request(self, path: str, data: dict[str, Any] | None) -> Any:
        body = None if data is None else json.dumps(data).encode()
        req = urllib.request.Request(
            f"{self.base_url}{path}", data=body,
            headers={"Authorization": f"Bearer {self.token}",
                     "Content-Type": "application/json"},
            method="POST" if data is not None else "GET")
        with urllib.request.urlopen(req, timeout=self.timeout_s) as res:
            return json.loads(res.read().decode() or "{}")

    def _post(self, path: str, data: dict[str, Any]) -> bool:
        try:
            self._request(path, data)
            self._recovered()
            return True
        except Exception as e:                              # noqa: BLE001
            self._failed(f"pushing to {path}", e)
            return False

    def _get(self, path: str) -> list[dict[str, Any]]:
        try:
            answer = self._request(path, None)
            self._recovered()
            return list(answer.get("commands") or [])
        except Exception as e:                              # noqa: BLE001
            self._failed(f"reading {path}", e)
            return []

    def _failed(self, what: str, error: Exception) -> None:
        self._failures += 1
        if self._failures <= QUIET_AFTER:
            LOG.warning("portal: %s failed (%s). The trader is unaffected.",
                        what, error)
            if self._failures == QUIET_AFTER:
                LOG.warning("portal: further failures will not be logged until "
                            "it answers again.")

    def _recovered(self) -> None:
        if self._failures > QUIET_AFTER:
            LOG.info("portal: reachable again after %d failures", self._failures)
        self._failures = 0


def _ack(status: str, detail: str, reason_code: str | None = None) -> dict[str, Any]:
    return {"status": status, "detail": detail, "reason_code": reason_code}


def _iso(value) -> str | None:
    if not isinstance(value, datetime):
        return None
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _num(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
