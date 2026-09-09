#!/usr/bin/env python3
"""Telegram notifications for watchlist changes and fills.

    python -m common.notify --test        # send one message, prove the setup

SETUP -- and the token never goes anywhere near a chat window or this repo
------------------------------------------------------------------------
Two values, resolved the same way as every other credential in this project
(common/secrets_util.py): an environment variable holding either the literal
secret or an `op://vault/item/field` reference.

    setx TELEGRAM_BOT_TOKEN "op://Trading/<item>/<field>"
    setx TELEGRAM_CHAT_ID   "op://Trading/<item>/<field>"

Open a NEW terminal afterwards; setx does not affect the current one. To get
the two values: message @BotFather to create a bot (it gives the token), then
send your new bot any message and read your chat id from
https://api.telegram.org/bot<TOKEN>/getUpdates.

THE DESIGN CONSTRAINT THAT SHAPES EVERYTHING HERE
-------------------------------------------------
**A notification must never be able to affect trading.** The trailing stop
lives inside the running process -- outside RTH there is no broker-side stop --
so anything that can block the event loop or raise into it can leave a
position unprotected. Telegram is a network call to a third party that can be
slow, rate-limited, or down.

So sends are fire-and-forget onto a bounded queue, drained by a daemon thread.
The trading loop never waits, never sees an exception, and never blocks on a
full queue -- it drops the message instead. A dropped notification is an
annoyance; a stalled trader is a loss. The counters exist so drops are visible
rather than silent.

Unconfigured is a normal state, not an error: with no token the notifier is a
no-op and everything downstream carries on.

RATE LIMITS AND DE-DUPLICATION, per claude/messaging_alert_channels.md:
"a screener bug that fires fifty alerts in a minute gets the channel muted,
which is worse than no alerts at all." Telegram allows roughly one message a
second to a single chat. Three defences, because coalescing at the call site
is not enough on its own -- a bug upstream is exactly the case where the call
site is not behaving:

  1. callers coalesce (tv_feed sends ONE message per poll that changed
     something, never one per symbol);
  2. this class enforces MIN_INTERVAL_S between sends and drops what arrives
     inside it;
  3. it drops a message identical to the previous one within DEDUPE_WINDOW_S,
     which is what a stuck loop produces.

HEARTBEAT. Also from that doc: "a dead alerter and a quiet market look
identical from the phone." Callers send a periodic heartbeat so silence is
unambiguous -- see tv_feed's --heartbeat.
"""
from __future__ import annotations

import argparse
import json
import logging
import queue
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

from common import secrets_util as S

LOG = logging.getLogger("notify")
ET = ZoneInfo("America/New_York")
# Ben's wall clock. Named as an IANA zone, never a fixed offset: Australia and
# the US change over on different weekends, so AEST/AEDT sits 14, 15 or 16
# hours from ET depending on the date, and a hard-coded offset is wrong for
# several weeks a year. Same rule the Flex parser learned the hard way.
LOCAL = ZoneInfo("Australia/Sydney")

TOKEN_VAR = "TELEGRAM_BOT_TOKEN"
CHAT_VAR = "TELEGRAM_CHAT_ID"

API = "https://api.telegram.org/bot{token}/sendMessage"

# A Telegram bot token is "<digits>:<35-ish url-safe chars>". Validating it
# matters more than it looks: BotFather presents it inside a sentence, so the
# value people actually paste is often "API: 1234:ABC..." -- label, space and
# all. That produced an InvalidURL whose message contained the WHOLE TOKEN.
TOKEN_RE = re.compile(r"^\d{5,}:[A-Za-z0-9_-]{20,}$")
TIMEOUT_S = 6.0
QUEUE_MAX = 200

# Telegram permits ~1 message/second to one chat. Sit well under it.
MIN_INTERVAL_S = 2.0
DEDUPE_WINDOW_S = 120.0


class Notifier:
    """Fire-and-forget Telegram sender. Safe to construct unconfigured."""

    def __init__(self, token: str = "", chat_id: str = "", enabled: bool = True):
        # Strip first. A trailing newline or a stray space from a copy-paste
        # is otherwise carried into the URL and fails at request time, in an
        # exception that used to quote the token.
        self.token = (token or "").strip()
        self.chat_id = (chat_id or "").strip()
        self.problems = self._validate()
        self.enabled = bool(enabled and self.token and self.chat_id
                            and not self.problems)
        self.sent = 0
        self.failed = 0
        self.dropped = 0
        self.suppressed = 0
        self._last_send = 0.0
        self._last_text = ""
        self._last_text_at = 0.0
        self._lock = threading.Lock()
        self._q: queue.Queue[str] = queue.Queue(maxsize=QUEUE_MAX)
        self._thread: threading.Thread | None = None
        if self.enabled:
            self._thread = threading.Thread(target=self._drain, daemon=True,
                                            name="telegram")
            self._thread.start()

    def _validate(self) -> list[str]:
        """Catch a malformed token or chat id HERE, where it can be explained,
        rather than at request time where the failure is an opaque URL error.
        Refusing to start is deliberate: a notifier that cannot possibly work
        should say so at setup, not once a session is running."""
        out = []
        if self.token and not TOKEN_RE.match(self.token):
            hint = ""
            if ":" in self.token and self.token.split(":", 1)[0].strip().isdigit() is False:
                hint = (" It looks like a label was copied with it — BotFather "
                        "shows the token inside a sentence, and only the "
                        "'<digits>:<letters>' part is the token.")
            out.append(
                f"{TOKEN_VAR} is not a valid Telegram bot token "
                f"({len(self.token)} chars).{hint}")
        if self.chat_id:
            body = self.chat_id[1:] if self.chat_id.startswith("-") else self.chat_id
            if not body.isdigit():
                out.append(f"{CHAT_VAR} must be numeric, got {len(self.chat_id)} "
                           f"non-numeric chars.")
            elif self.chat_id.startswith("0"):
                out.append(
                    f"{CHAT_VAR} starts with 0, which no Telegram chat id does "
                    f"— this looks like a phone number. Get the real id by "
                    f"messaging your bot, then opening "
                    f"https://api.telegram.org/bot<TOKEN>/getUpdates and "
                    f"reading result[].message.chat.id")
        return out

    def _scrub(self, text: str) -> str:
        """Never let the token reach a log. urllib puts the full URL into its
        exception message, and the URL contains the token -- which is exactly
        how a live token ended up pasted into a chat window on 2026-09-05."""
        if self.token:
            text = text.replace(self.token, "<TOKEN>")
            # Also catch a mangled value that merely CONTAINS the real token.
            for part in self.token.split(":"):
                if len(part) >= 20:
                    text = text.replace(part, "<TOKEN>")
        return text

    # -- construction ---------------------------------------------------

    @classmethod
    def from_env(cls) -> "Notifier":
        """Resolve at startup, per the project's credential discipline. Absent
        configuration disables notifications rather than stopping the run."""
        got = S.preload_optional({TOKEN_VAR: "Telegram bot token",
                                  CHAT_VAR: "Telegram chat id"})
        if {TOKEN_VAR, CHAT_VAR} <= got:
            n = cls(S.get(TOKEN_VAR), S.get(CHAT_VAR))
            if n.problems:
                for p in n.problems:
                    LOG.error("Telegram not started: %s", p)
                return n
            LOG.info("Telegram notifications ON (chat %s)", S.mask(n.chat_id))
            return n
        LOG.info("Telegram notifications OFF — set %s and %s to enable",
                 TOKEN_VAR, CHAT_VAR)
        return cls()

    # -- sending --------------------------------------------------------

    def send(self, text: str, force: bool = False) -> bool:
        """Queue a message. Returns whether it was queued, never raises, and
        never blocks -- a full queue drops rather than waits.

        force bypasses the rate limit and the de-duplicator. Use it only for
        things that must not be swallowed: fills, and the heartbeat.
        """
        if not self.enabled:
            return False
        if not force and not self._allow(text):
            return False
        try:
            self._q.put_nowait(text)
            return True
        except queue.Full:
            self.dropped += 1
            LOG.warning("telegram queue full, dropped a message (%d total)",
                        self.dropped)
            return False

    def _allow(self, text: str) -> bool:
        """The rate limit and de-duplicator, per the guidance in
        claude/messaging_alert_channels.md. Counted, not silent."""
        now = time.monotonic()
        with self._lock:
            if text == self._last_text and now - self._last_text_at < DEDUPE_WINDOW_S:
                self.suppressed += 1
                return False
            if now - self._last_send < MIN_INTERVAL_S:
                self.suppressed += 1
                return False
            self._last_send = now
            self._last_text = text
            self._last_text_at = now
            return True

    def _drain(self) -> None:
        while True:
            text = self._q.get()
            try:
                self._post(text)
                self.sent += 1
            except BaseException as e:                  # noqa: BLE001
                # BaseException, not Exception, and deliberately so. If this
                # thread dies, every later notification is lost SILENTLY for
                # the rest of the session -- there is no error, just no more
                # messages, which is the worst failure mode an alerter has.
                # Catching this broadly is safe here specifically because it
                # is a daemon WORKER: KeyboardInterrupt and SystemExit are
                # delivered to the main thread, so nothing here can swallow a
                # Ctrl-C or an interpreter shutdown.
                self.failed += 1
                LOG.warning("telegram send failed (%s: %s)",
                            type(e).__name__, self._scrub(str(e)))
            finally:
                self._q.task_done()

    def _post(self, text: str) -> None:
        data = urllib.parse.urlencode({
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }).encode()
        req = urllib.request.Request(API.format(token=self.token), data=data)
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            body = json.load(r)
        if not body.get("ok"):
            raise RuntimeError(f"telegram refused: {body}")

    def flush(self, timeout: float = 5.0) -> None:
        """Best-effort drain, for shutdown. Never blocks forever."""
        if not self.enabled:
            return
        end = threading.Event()
        t = threading.Thread(target=lambda: (self._q.join(), end.set()),
                             daemon=True)
        t.start()
        end.wait(timeout)

    def stats(self) -> str:
        return (f"telegram sent={self.sent} failed={self.failed} "
                f"dropped={self.dropped} suppressed={self.suppressed}")


# --- message formatting -----------------------------------------------------
#
# Kept as free functions so they can be tested without a network, a token, or
# a thread. Every number the message claims is passed in; nothing is recomputed
# here, so a message can never disagree with the fill log.

def _ts(now: datetime | None = None) -> str:
    return (now or datetime.now(ET)).strftime("%H:%M:%S ET")


def _tag(strategy: str) -> str:
    """Which strategy fired this. Empty when unknown rather than guessing a
    default -- a fill labelled with the wrong strategy is worse than one
    labelled with none, and there is more than one trader in this repo."""
    # "MCL BUY WYHG", not "MCL · BUY WYHG": Ben asked on 2026-09-09 for the
    # second line to be "Strategy BUY/SELL". The ticker stays on it -- his spec
    # did not mention it, and a fill notification without the symbol is not a
    # fill notification.
    return f"{strategy} " if strategy else ""


def header(now: datetime | None = None) -> str:
    """First line of every message: 'Monday 7 Sep 2026 18:30 AEDT (04:30 ET)'.

    BOTH CLOCKS, chosen by Ben on 2026-09-09 knowing the line is longer for it.
    Local is the clock he reads the phone in; ET is the one the fill CSV, the
    bar timestamps and the session window are all stamped in, so a message and
    a log line can be put side by side without arithmetic. Local alone would be
    ambiguous twice a year -- AEST and AEDT sit 14 and 16 hours from ET, and
    the gap changes on four separate dates because the two countries shift on
    different weekends.

    The day number carries no leading zero, and it is built from dt.day rather
    than a strftime code because the codes that do it are platform-specific --
    %-d on Linux, %#d on Windows -- and this runs on Windows.
    """
    dt = now or datetime.now(ET)
    local = dt.astimezone(LOCAL)
    et = dt.astimezone(ET)
    zone = local.strftime("%Z") or "local"
    return (f"{local:%A} {local.day} {local:%b %Y} {local:%H:%M} {zone} "
            f"({et:%H:%M} ET)")


def _kmb(x, dp_m: int = 1) -> str:
    """9,318,299 -> '9.3m'; 271,202 -> '271k'; 934 -> '934'.

    Share counts and volumes only. Never money: _money() stays exact, because
    a P/L rounded to '1.3k' on a phone is a number that cannot be reconciled
    against the fill log.
    """
    if not isinstance(x, (int, float)) or isinstance(x, bool):
        return "?"
    a = abs(x)
    if a >= 1e9:
        return f"{x / 1e9:.{dp_m}f}b"
    if a >= 1e6:
        return f"{x / 1e6:.{dp_m}f}m"
    if a >= 1e3:
        return f"{x / 1e3:.0f}k"
    return f"{x:,.0f}"


def _money(x: float) -> str:
    return f"${x:,.2f}"


def _trigger_line(r: dict) -> str:
    """The values that fired the screen, per claude/messaging_alert_channels.md:
    "'AAPL long' tells you nothing three hours later; the indicator readings
    let you reconstruct the decision." Read three hours later on a phone, the
    ticker alone is useless."""
    def num(key, fmt, suffix=""):
        v = r.get(key)
        return f"{v:{fmt}}{suffix}" if isinstance(v, (int, float)) else "?"
    px = (_money(r["premarket_close"])
          if isinstance(r.get("premarket_close"), (int, float)) else "?")
    # Volume in three readings, because they answer different questions and
    # only the first is what the screen actually filters on: how much has
    # traded pre-market (the clause), how that compares with a normal day
    # (relvol), and how much of the company can trade at all (float).
    return (f"    {r.get('ticker','?')}  "
            f"{num('premarket_change', '+.1f', '%')}  {px}  "
            f"pmvol {_kmb(r.get('premarket_volume'))}  "
            f"relvol {num('relative_volume_10d_calc', '.1f')}  "
            f"float {_kmb(r.get('float_shares_outstanding'))}")


def drop_reason(clauses: list[dict] | None, fallback: str = "") -> str:
    """'pm vol 62k < 100k' from tv_screener.failing_clauses() output.

    A name that stops screening returns NO ROW from the server, so the reason
    cannot be read off the poll that dropped it -- the caller has to go and ask
    for the name's current values. When that lookup fails or the clause list is
    empty, this returns the fallback rather than inventing a cause: "no longer
    screening" with no reason is honest, and a guessed reason is the kind of
    plausible-looking wrong number this project keeps finding weeks later.
    """
    if not clauses:
        return fallback
    parts = []
    for c in clauses:
        col, label, v, op, right = (c.get("column"), c.get("label"),
                                    c.get("value"), c.get("operation"),
                                    c.get("right"))
        shares = col in ("premarket_volume", "volume",
                         "float_shares_outstanding")
        if v is None:
            parts.append(f"{label} n/a")
            continue
        got = _kmb(v) if shares else (f"{v:,.1f}" if col != "premarket_close"
                                      else _money(v))
        if op == "in_range" and isinstance(right, (list, tuple)) and len(right) == 2:
            lo, hi = right
            want = (f"{_kmb(lo)}-{_kmb(hi)}" if shares
                    else f"{_money(lo)}-{_money(hi)}"
                    if col == "premarket_close" else f"{lo:g}-{hi:g}")
            parts.append(f"{label} {got} outside {want}")
        else:
            sym = {"egreater": "<", "greater": "<=",
                   "eless": ">", "less": ">="}.get(op, "fails")
            want = _kmb(right) if shares else (
                _money(right) if col == "premarket_close" else f"{right:g}")
            parts.append(f"{label} {got} {sym} {want}")
    return ", ".join(parts)


def watchlist_change(added: list[str], removed: list[str],
                     hot: list[str], warm: list[str], cold: list[str],
                     now: datetime | None = None,
                     rows: list[dict] | None = None,
                     reasons: dict[str, str] | None = None) -> str:
    """One message per poll that changed something -- not one per symbol.

    "removed" is a deliberate simplification of what the feed does. The feed
    never deletes a symbol mid-session (see common/tv_feed.py); a name that
    stops screening is demoted to COLD, and only the size cap evicts anything.
    So this reads as "no longer screening", and the tier list below it shows
    where the name actually went.

    `reasons` maps ticker -> why, already formatted by the caller (which is the
    only place that can look the values up). A ticker missing from it is
    reported without a reason rather than with a guessed one.
    """
    by_ticker = {r.get("ticker"): r for r in (rows or [])}
    reasons = reasons or {}
    lines = [header(now), f"<b>Watchlist</b>  {_ts(now)}"]
    if added:
        lines.append(f"➕ added: <b>{', '.join(added)}</b>")
        for t in added:
            if t in by_ticker:
                lines.append(_trigger_line(by_ticker[t]))
    if removed:
        lines.append("➖ no longer screening:")
        for t in removed:
            why = reasons.get(t)
            lines.append(f"    {t}" + (f"  —  {why}" if why else ""))
    lines.append("")
    lines.append(f"🔥 HOT ({len(hot)}): {', '.join(hot) if hot else '—'}")
    lines.append(f"🟡 WARM ({len(warm)}): {', '.join(warm) if warm else '—'}")
    lines.append(f"🧊 COLD ({len(cold)}): {', '.join(cold) if cold else '—'}")
    return "\n".join(lines)


def heartbeat(scanned: int, hot: int, warm: int, cold: int,
              stats: str = "", now: datetime | None = None) -> str:
    """So silence is unambiguous. From claude/messaging_alert_channels.md:
    "a dead alerter and a quiet market look identical from the phone." A quiet
    pre-market produces no watchlist changes at all, which is exactly when a
    crashed feed is invisible."""
    line = (f"{header(now)}\n💓 <b>feed alive</b> — screened {scanned}, "
            f"hot {hot} / warm {warm} / cold {cold}")
    return line + (f"\n<i>{stats}</i>" if stats else "")


def buy_filled(ticker: str, price: float, qty: int, commission: float,
               now: datetime | None = None, strategy: str = "") -> str:
    cost = price * qty
    return "\n".join([
        header(now),
        f"<b>{_tag(strategy)}BUY {ticker}</b>",
        f"price      {_money(price)}",
        f"shares     {qty:,}",
        f"cost       {_money(cost)}",
        f"commission {_money(commission)}",
        f"<b>total     {_money(cost + commission)}</b>",
    ])


def sell_filled(ticker: str, price: float, qty: int, commission: float,
                net_profit: float, now: datetime | None = None,
                strategy: str = "") -> str:
    """net_profit is the ROUND TRIP net -- both legs' commission already taken
    out -- because that is the number worth seeing on a phone. `commission`
    here is the sell leg only, so the two are not double counted."""
    proceeds = price * qty
    sign = "🟢" if net_profit >= 0 else "🔴"
    return "\n".join([
        header(now),
        f"<b>{_tag(strategy)}SELL {ticker}</b>",
        f"price      {_money(price)}",
        f"shares     {qty:,}",
        f"proceeds   {_money(proceeds)}",
        f"commission {_money(commission)}  (this leg)",
        f"{sign} <b>net P/L  {_money(net_profit)}</b>  (round trip, both legs)",
    ])


def main() -> int:
    ap = argparse.ArgumentParser(description="Telegram notifier")
    ap.add_argument("--test", action="store_true",
                    help="send one message and report the result")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    problems = S.check()
    if problems:
        print("credential setup problems:")
        for pr in problems:
            print(f"  * {pr}")
        print()

    n = Notifier.from_env()
    if n.problems:
        print("Telegram configuration problems:")
        for pr in n.problems:
            print(f"  * {pr}")
        return 1
    if not n.enabled:
        print(f"Not configured. Set {TOKEN_VAR} and {CHAT_VAR} "
              f"(literal value or op:// reference), then open a new terminal.")
        return 1
    if a.test:
        # force=True and spaced. Without both, the rate limiter does exactly
        # its job and swallows two of the three -- which is correct behaviour
        # and a useless test, since the point here is to SEE all three
        # formats arrive. Live callers already force fills and heartbeats.
        for msg in (watchlist_change(["AOUT"], ["OLDNAME"], ["AOUT"],
                                     ["EXPENSIVE"], ["OLDNAME"],
                                     rows=[{"ticker": "AOUT",
                                            "premarket_change": 27.47,
                                            "premarket_close": 12.76,
                                            "premarket_volume": 271_202.0,
                                            "relative_volume_10d_calc": 65.46,
                                            "float_shares_outstanding": 10_589_237.0}],
                                     reasons={"OLDNAME": "pm vol 62k < 100k"}),
                    buy_filled("AOUT", 12.76, 100, 0.35, strategy="MCL"),
                    sell_filled("AOUT", 13.40, 100, 0.35, 63.30,
                                strategy="MCL")):
            n.send(msg, force=True)
            time.sleep(MIN_INTERVAL_S / 2)
        n.flush()
        print(n.stats())
        if n.suppressed:
            print(f"NOTE {n.suppressed} suppressed — that should be 0 here; "
                  f"the rate limiter is only meant to catch runaway callers.")
        return 0 if n.failed == 0 else 1
    print(n.stats())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
