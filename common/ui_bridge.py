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
import hashlib
import json
import logging
import os
import re
import socket
import time
import urllib.error
import urllib.request
from datetime import datetime, time as dtime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any

from common import feed_state as FS

LOG = logging.getLogger("ui_bridge")

# Every module in this repo names the exchange clock for itself; this is a
# fact about the market, not a value anyone configures.
ET = ZoneInfo("America/New_York")

CONTRACT_VERSION = "1.8"
PUSH_EVERY_S = 5.0
HTTP_TIMEOUT_S = 3.0
MAX_FILLS = 500
MAX_NOTIFICATIONS = 100
MAX_EVENTS = 20

# The history upload wakes a free-tier Neon database that suspends after five
# idle minutes, so the first request after a session can take a few seconds.
# Two minutes is ample and still finite -- see
# claude/handover_session_end_upload_20260919.md sec 3, "it is bounded".
HISTORY_TIMEOUT_S = 120.0

# The live trader's own daily fill log -- var/fills/mcl_fills_YYYYMMDD.csv,
# named for MCL historically but shared by every strategy running in the
# session (FIELDS' own comment: "One file, not one per strategy"). NOT a
# rolled-aside `..._preHHMMSS.csv` from FillLog's stale-header guard, which is
# not a session and has no date a re-upload could trust.
_SESSION_FILE_RE = re.compile(r"^mcl_fills_(\d{8})\.csv$")

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


def _clock(stamp: str | None) -> str | None:
    """The time of day out of a fill-log timestamp, or None."""
    if not stamp:
        return None
    part = stamp.strip().split(" ")[-1]
    return part or None


def _minus_minutes(stamp: str | None, minutes: float | None) -> str | None:
    """Fallback entry time: the exit, less how long the position was held.

    Used only when no opening row is in today's log -- a position adopted from
    a previous session, or a log that was rolled aside mid-session. hold_minutes
    is stored to one decimal, so this lands within about three seconds, which
    is honest for a column read as a time of day and useless for anything
    finer. Pairing with the BUY row is exact and is tried first.
    """
    if not stamp or minutes is None:
        return None
    try:
        opened = datetime.strptime(stamp.strip(), "%Y-%m-%d %H:%M:%S") - \
            timedelta(minutes=float(minutes))
    except (TypeError, ValueError):
        return None
    return opened.strftime("%H:%M:%S")


# The session-open CONFIG row and the bridge state live on the TRADER
# (MCLPaperTrader.bridge_state / record_config), not here. I built a second
# copy of both in this file on 2026-09-16 without knowing the strategy side had
# already built them; theirs is better placed, because the row records what the
# TRADER was running with. Two writers would have put two rows per adapter in
# the ledger at every session start.


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
                 timeout_s: float = HTTP_TIMEOUT_S,
                 feed_state_path=FS.STATE_PATH):
        self.feed_state_path = feed_state_path
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
        # Process uptime, for the portal's health block. Monotonic so a
        # system clock change can never make this run backwards or negative.
        self._started_monotonic = time.monotonic()

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
                # The bar size this strategy DECIDES on, read off the adapter.
                # The portal uses it to pick a chart interval without holding a
                # table of strategy names -- so a new strategy, or one that
                # changes its bar size, needs no UI change and cannot silently
                # be charted at the wrong resolution.
                "bar_minutes": getattr(adapter, "bar_minutes", None),
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

        # ONE SOURCE FOR REALISED, and this file used to have two. The
        # per-strategy figures above sum the fill log; this total used to read
        # `trader.session_pnl`, the trader's own accumulator. Both are correct
        # and they do not agree: the log rounds each trade to 2dp as it is
        # written, the accumulator adds the unrounded values. On 2026-09-16
        # that put 25.71 on the curve, 25.71 across the strategy bars and 25.74
        # in the headline -- the same quantity, three times, on one screen,
        # disagreeing by three cents. A dashboard that contradicts itself by a
        # little teaches you to trust none of it.
        #
        # The log wins because it is the auditable record: every figure on the
        # page can now be checked against the CSV, and the parts sum to the
        # whole by construction.
        realized = round(sum(f["trade_pnl"] for f in fills
                             if f.get("trade_pnl") is not None), 2)

        # A FEW CENTS is rounding and expected. A LARGE gap is not: it means the
        # log is missing a round trip the trader counted, which is a real defect
        # and one that would otherwise show up as a slightly wrong number nobody
        # queries. Telegram and the trader's own log still quote session_pnl, so
        # the two are visible side by side and should stay close.
        session_pnl = getattr(trader, "session_pnl", None)
        if session_pnl is not None and abs(float(session_pnl) - realized) > 0.10:
            LOG.warning("realised P&L disagrees: fill log %.2f, trader %.2f "
                        "(%.2f apart) -- more than rounding; a round trip may be "
                        "missing from the log", realized, float(session_pnl),
                        abs(float(session_pnl) - realized))
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
                "realized": realized,
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
                "data_stale_seconds": self._data_stale_seconds(trader),
                "uptime_s": round(time.monotonic() - self._started_monotonic, 1),
                "last_error": None,
            },
            "events": list(self._events),
            "notifications": list(self._notifications),
            "links": [],
            # Contract 1.8, ADDITIVE AND OPTIONAL. `tv_feed` knows whether the
            # rows are real time; this process publishes the document. The
            # block is omitted entirely when the file is missing, unreadable or
            # malformed, and the portal renders an absent block exactly as it
            # renders `unknown` -- so a failure to learn the mode can never
            # come out the other end as `streaming`.
            **({"feed": feed} if (feed := FS.read(self.feed_state_path))
               else {}),
        }

    @staticmethod
    def _data_stale_seconds(trader) -> float | None:
        """Seconds since bar data was last fetched for any watched symbol.

        `bars_fetched_at` (`brokers/ibkr/trader.py`) is a per-symbol
        `time.monotonic()` stamp, set each time that symbol's 1-minute bars
        are (re)requested from IB. The freshest of those, across every
        symbol the trader is watching, is how current the trader's market
        data is. No symbols watched yet, or none ever fetched, reports
        `None` rather than a misleading `0`.
        """
        stamps = [
            ts for st in getattr(trader, "states", {}).values()
            if (ts := getattr(st, "bars_fetched_at", 0.0))
        ]
        if not stamps:
            return None
        return round(time.monotonic() - max(stamps), 1)

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
        # The opening time of each round trip. The closing row records the exit
        # and how long it was held, never when it opened -- so the entry is
        # taken from the BUY row that opened it, which is exact. The trader
        # allows one position per symbol per strategy at a time, so the most
        # recent unmatched BUY IS the one this SELL closes.
        opened_by: dict[tuple[str, str], str] = {}
        try:
            with Path(path).open(newline="", encoding="utf-8-sig") as fh:
                for i, row in enumerate(csv.DictReader(fh)):
                    status = (row.get("status") or "").upper()
                    key = (row.get("strategy") or "", row.get("symbol") or "")
                    action = (row.get("action") or "").upper()
                    entry_ts = None

                    # PAIRING FIRST, and over a wider set of rows than the fills
                    # list below. A partial fill opens a real position and is
                    # written as PARTIAL_FILL, so pairing on FILLED alone would
                    # leave its exit with no opening row.
                    if status in ("FILLED", "PARTIAL_FILL"):
                        if action in ("BUY", "COVER"):
                            # setdefault, not assignment: a second partial ADDS
                            # to the position the first one opened. The position
                            # opened at the FIRST fill, and that is the time the
                            # exit should carry -- overwriting would quietly
                            # shorten every partially-filled trade.
                            opened_by.setdefault(key, row.get("ts_et") or "")
                        elif action in ("SELL", "SHORT"):
                            # READ, and only forget once the position is flat.
                            # A partial exit leaves the rest held, so the SAME
                            # position produces a second exit row later -- and
                            # popping on the first one left that second row with
                            # no entry time at all ("--" in the Entered column,
                            # seen in the 2026-09-16 dry run). Both rows closed
                            # shares opened at the same moment and both should
                            # say so.
                            #
                            # This mirrors the trader exactly: it does
                            # `pos.qty -= sold` on a partial and
                            # `st.position = None` only when the position is
                            # fully closed -- and that final exit is always
                            # FILLED, because its order quantity IS the
                            # remaining position.
                            entry_ts = opened_by.get(key)
                            if status == "FILLED":
                                opened_by.pop(key, None)

                    # BOTH statuses, on the strategy side's ruling of
                    # 2026-09-16. A partial EXIT is a real close: the trader
                    # cancels the remainder, reduces pos.qty and keeps the
                    # position open (trader.py, "still holding %d after partial
                    # exit"), and the row's trade_pnl is
                    # (exit_px - entry_price) * filled - commission -- realised
                    # P&L on the shares that went, not a projection. A
                    # FILLED-only list therefore DROPPED realised money, and
                    # understated the P&L column by exactly the sum of those
                    # rows. No double counting: pos.qty falls with each partial
                    # so the quantities are disjoint, and entry_price is set
                    # once at position open and never reassigned.
                    #
                    # This also makes the portal agree with the rest of the
                    # codebase. common/friction.py has FILLED =
                    # ("FILLED", "PARTIAL_FILL") and the trader's own position
                    # reconstruction reads both. The portal was the only reader
                    # that did not.
                    if status not in ("FILLED", "PARTIAL_FILL"):
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
                        # A reader cannot infer this from qty alone: "40" is
                        # the same whether it closed a 40-share position or
                        # part of a 100-share one. Without it the only clue is
                        # the same symbol appearing twice, which is an
                        # inference, not a fact the row states.
                        "partial": status == "PARTIAL_FILL",
                        "entry_ts_et": _clock(entry_ts) or _minus_minutes(
                            row.get("ts_et"), _num(row.get("hold_minutes"))),
                        "entry_price": entry,
                        "price": price,
                        "commission": commission,
                        "reason": row.get("reason") or None,
                        "gross_pnl": gross,
                        "trade_pnl": net,
                        "friction_charged": False,
                    })
        except Exception:                                   # noqa: BLE001
            # LOUD. This catch exists because _fills_today runs in the trading
            # path and must not raise -- but at DEBUG it once hid a NameError
            # whose only symptom was an empty Closed today. A defect that
            # presents as "no trades" in a trading portal is the worst possible
            # disguise, so the trader's log says what happened even though the
            # dashboard carries on.
            LOG.exception("could not read the fill log for the portal (%s); "
                          "the dashboard will show no fills", path)
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

    # record_session_open used to live here. It now belongs to the trader --
    # MCLPaperTrader.record_config(reason="session_open"), called from the
    # trader's own startup -- because a session with no bridge needs the row
    # just as much, and arguably more.

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

    # -- shutdown ------------------------------------------------------------
    # Both of these are called ONCE, from the trader's own shutdown `finally`
    # (brokers/ibkr/trader.py main_async), after log.close() and ib.disconnect()
    # -- never from tick()'s loop. See
    # claude/handover_session_end_upload_20260919.md sec 1: final state push,
    # then history upload, then --sleep-on-exit, in that order, because the
    # push is what stops the portal showing a position the account no longer
    # holds and the upload is what makes "the trader stopped" a fact the
    # portal can state rather than infer from silence.
    def push_final_state(self, trader, now_et: datetime | None = None) -> bool:
        """The trader's last word: a synchronous, one-shot state push.

        Unlike `tick()` this ignores `push_every_s` and does not go through
        the asyncio loop, which may already be tearing down. The document
        gains `agent.stopped_at` -- the flag
        `claude/handover_portal_stale_position_20260918.md` item 2 asked for,
        so the portal can say the trader stopped rather than merely that it
        has been quiet. Never raises: a failed final push leaves the portal
        showing what it already had, which is the pre-existing behaviour.
        """
        clock = now_et or datetime.now(ET)
        try:
            state = self.build_state(trader, clock)
        except Exception:                                   # noqa: BLE001
            LOG.exception("could not build the final state; the portal keeps "
                          "whatever it last had")
            return False
        state["agent"]["stopped_at"] = _utc_now()
        return self._post("/api/state", state)

    def upload_history(self, trader, *, recent_days: int = 5) -> None:
        """Re-send the last `recent_days` sessions' closed trades, each as a
        whole-day replace to `POST /api/history`.

        Re-sending is harmless (each is a whole-day replace) and is what
        covers a shutdown that never ran -- a crash, a killed window, a power
        cut -- at the end of the *next* session, with nothing having to
        remember it was missed. See handover sec 3 for the properties this
        follows; `_trade_key` is pinned against its test vector.

        Never raises. A failed upload is a missing chart, not a reason to
        skip `--sleep-on-exit` -- the same rule `push_final_state` follows.
        """
        log = getattr(trader, "log", None)
        path = getattr(log, "path", None)
        if not path:
            return

        try:
            sessions = _session_files(Path(path).parent, recent_days)
        except Exception:                                   # noqa: BLE001
            LOG.exception("could not list session fill logs for the history "
                          "upload (%s)", path)
            return

        for date_digits, file_path in sessions:
            session_date = f"{date_digits[:4]}-{date_digits[4:6]}-{date_digits[6:]}"
            try:
                trades, order_outcomes = _read_session_csv(file_path, session_date)
            except Exception:                               # noqa: BLE001
                LOG.exception("could not read %s for the history upload",
                              file_path)
                continue

            doc = {
                "schema_version": CONTRACT_VERSION,
                "sent_at": _utc_now(),
                "agent": {"id": self.agent_id, "kind": "trader", "version": "1"},
                "session_date": session_date,
                "complete": True,
                "trades": trades,
                "order_outcomes": order_outcomes,
            }
            if self._post("/api/history", doc, timeout=HISTORY_TIMEOUT_S):
                LOG.info("portal: history uploaded for %s (%d trade(s))",
                         session_date, len(trades))
            else:
                LOG.warning("portal: history upload for %s did not go "
                           "through; it will be retried at the end of the "
                           "next session", session_date)

    # -- transport ---------------------------------------------------------
    def _request(self, path: str, data: dict[str, Any] | None,
                timeout: float | None = None) -> Any:
        body = None if data is None else json.dumps(data).encode()
        req = urllib.request.Request(
            f"{self.base_url}{path}", data=body,
            headers={"Authorization": f"Bearer {self.token}",
                     "Content-Type": "application/json"},
            method="POST" if data is not None else "GET")
        with urllib.request.urlopen(
                req, timeout=self.timeout_s if timeout is None else timeout) as res:
            return json.loads(res.read().decode() or "{}")

    def _post(self, path: str, data: dict[str, Any],
             timeout: float | None = None) -> bool:
        try:
            self._request(path, data, timeout=timeout)
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


def _trade_key(session_date: str, strategy: str, symbol: str, exit_ts: str,
               qty: float, exit_price: float) -> str:
    """The primary key the portal's backfill already computes for 194 trades.

    MUST NEVER DRIFT from `tools/fill_log.py` on the portal side: if the two
    sides compute this differently, every whole-day upload from one side
    deletes and re-inserts the other's rows for that date (harmless -- no
    duplicates, the replace removes unmentioned keys -- but it makes
    `ingested_at` meaningless and hides a real disagreement).

    Pinned against the fixed test vector in
    claude/handover_session_end_upload_20260919.md sec 3:
    `_trade_key("2026-09-18", "MCL", "BIAF", "2026-09-18 09:30:26", 100, 11.00)
    == "9ff0fe67a0f50bdd32e4cfb0e7d73596"`. `{qty:g}` and `{exit_price:g}`
    matter -- "100" not "100.0" -- that formatting is what the handover calls
    out as the part most likely to drift.
    """
    raw = (f"{session_date}|{strategy.upper()}|{symbol}|{exit_ts}|"
          f"{qty:g}|{exit_price:g}")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _session_files(fills_dir: Path, recent_days: int) -> list[tuple[str, Path]]:
    """(YYYYMMDD, path), oldest first, for the most recent `recent_days`
    session files in `fills_dir` -- or [] if the directory does not exist."""
    if recent_days <= 0 or not fills_dir.is_dir():
        return []
    found = [(m.group(1), p) for p in fills_dir.iterdir()
             if (m := _SESSION_FILE_RE.match(p.name))]
    found.sort(key=lambda t: t[0])
    return found[-recent_days:]


def _read_session_csv(path: Path, session_date: str
                      ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(closed trades, order outcomes) for one day's fill log.

    Mirrors UIBridge._fills_today's BUY/SELL pairing (see its comments for
    why: partial fills, the most-recent-unmatched-BUY rule), but keeps the
    FULL timestamp on both sides rather than truncating to a clock, because
    the history document's trade_key and entry_ts_et need the date that
    _fills_today deliberately drops for the live dashboard. CONFIG rows carry
    no real symbol and are skipped entirely, as they are not orders.

    order_outcomes counts every other row -- SKIPPED_*, REJECTED and the
    like -- by (strategy, status), which never became a trade.
    """
    trades: list[dict[str, Any]] = []
    outcome_counts: dict[tuple[str, str], int] = {}
    opened_by: dict[tuple[str, str], str] = {}

    with path.open(newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            action = (row.get("action") or "").upper()
            if action == CONFIG_ACTION:
                continue
            status = (row.get("status") or "").upper()
            key = (row.get("strategy") or "", row.get("symbol") or "")

            entry_ts = None
            if status in ("FILLED", "PARTIAL_FILL"):
                if action in ("BUY", "COVER"):
                    opened_by.setdefault(key, row.get("ts_et") or "")
                elif action in ("SELL", "SHORT"):
                    entry_ts = opened_by.get(key)
                    if status == "FILLED":
                        opened_by.pop(key, None)

            if status not in ("FILLED", "PARTIAL_FILL"):
                strategy = row.get("strategy") or ""
                outcome_key = (strategy, status or "UNKNOWN")
                outcome_counts[outcome_key] = outcome_counts.get(outcome_key, 0) + 1
                continue

            if action not in ("SELL", "SHORT"):
                # The opening leg of a round trip, not a closed trade -- and
                # not an "outcome" either, since it filled. Its close (this
                # session or, for a position cut off by shutdown, a later
                # one) is the trade row.
                continue

            qty = _num(row.get("filled_qty")) or _num(row.get("qty")) or 0
            price = _num(row.get("fill_price")) or 0.0
            entry = _num(row.get("entry_price"))
            net = _num(row.get("trade_pnl"))
            gross, commission = _round_trip_costs(entry, price, qty, net)
            strategy = row.get("strategy") or ""
            symbol = row.get("symbol") or ""
            exit_ts = row.get("ts_et") or ""
            trades.append({
                "trade_key": _trade_key(session_date, strategy, symbol,
                                        exit_ts, qty, price),
                "session_date": session_date,
                "strategy": strategy,
                "symbol": symbol,
                "entry_ts_et": entry_ts,
                "exit_ts_et": exit_ts,
                "qty": qty,
                "partial": status == "PARTIAL_FILL",
                "entry_price": entry,
                "exit_price": price,
                "gross_pnl": gross,
                "commission": commission,
                "net_pnl": net,
                "reason": row.get("reason") or None,
                "hold_minutes": _num(row.get("hold_minutes")),
                "contract_version": CONTRACT_VERSION,
                "source": "trader",
            })

    order_outcomes = [{"strategy": s, "status": st, "count": n}
                      for (s, st), n in sorted(outcome_counts.items())]
    return trades, order_outcomes


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
