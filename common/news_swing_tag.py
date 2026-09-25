#!/usr/bin/env python3
r"""W07-0011 subitem 2 -- the NEWS / NO NEWS point-in-time tag on SWING-v0
picks, exactly per `docs/research/REGISTERED_swing_v0.md` §11.2-§11.3.

THIS IS A DIFFERENT, WIDER RULE THAN `common.news_events`'s Trigger A/B.
W03-0010's classifier (news_events.py) is narrow on purpose -- two specific
event types (a fresh dilution, a reverse split), each with its own short
window, built to veto entries on two already-losing intraday books without
refusing almost everything (its own probe found 7 of 8 names carried SOME
dilution/split filing in 90 days). W07-0011 asks a different, broader
question of a different, unrelated book (SWING-v0's multi-day cross-sectional
reversal candidate): "did ANYTHING company-specific happen before this stock
dropped, or did it drop on no news at all?" -- Chan (2003)'s distinction, not
a dilution/split-specific one. So this module classifies ANY 8-K/10-Q/10-K/
424B* filing and ANY (non-market-wide) headline as "there was news", rather
than reusing news_events.classify_filing/classify_headline's narrow label
sets. What IS reused: the timestamp parsing (EDGAR's acceptanceDateTime is
Eastern despite its 'Z' suffix; Alpaca's created_at is real UTC) -- both
`from common.news_events import parse_edgar_accepted, parse_alpaca_created_at`
-- and the per-symbol filings/headlines CSV cache format `common.news_pull`
already writes and `common.news_swing_pull` extends (this module's actual
sibling puller, reusing `news_pull.pull_edgar` and `.alpaca_symbol_history`
unchanged -- see that module's docstring).

THE RULE, EXACTLY (§11.2)
--------------------------
A pick is tagged NEWS if, strictly between the start of its K-day drop
(`drop_start`) and its entry timestamp (`entry_ts`), at least one of:

  * a Benzinga headline (via Alpaca) tagged to the symbol, EXCLUDING any
    headline tagged to more than `MARKET_WRAP_MAX_SYMBOLS` (5) symbols --
    the registration's own words, aimed at market wraps / "stocks moving"
    lists that would otherwise tag almost every name;
  * an SEC filing whose form is 8-K, 10-Q, 10-K, or starts with "424B",
    ACCEPTED before entry (EDGAR's acceptanceDateTime, Eastern).

Otherwise NO NEWS. "Every timestamp must be earlier than the entry time" --
the window is `drop_start <= ts < entry_ts`, entry itself excluded (a same-
timestamp event is not "before" it).

THIS MODULE DOES NOT COMPUTE P&L. It only classifies and joins; the picks
themselves -- symbol, drop_start, entry_ts, and the dollar figures §11.3
requires -- come from W07-0010's SWING-v0 engine, which has not landed yet
(no `strategy/swing/reversal_v0.py` in this repo as of this module's first
commit). `PICK_FIELDS` below is the documented, load-bearing contract this
module needs from that engine's output; `load_picks_csv` reads exactly that
shape. Everything here is built and unit/mutation-tested against synthetic
fixtures in that shape now, so subitem 3 (the real pull + tagged backtest)
can run the moment picks exist, per the board note on W07-0011: "Steps 2-5
unblocked to proceed in parallel except the NO-NEWS-only holdout spend."
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date as _date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from common.news_events import parse_alpaca_created_at, parse_edgar_accepted

ET = ZoneInfo("America/New_York")
REGISTERED = "docs/research/REGISTERED_swing_v0.md"

# --- §11.2, exactly ----------------------------------------------------------

# "an SEC filing of type 8-K, 10-Q, 10-K, or 424B* for that company" -- an
# exact match on the first three, a prefix match on 424B (424B1/3/4/5/...,
# any sub-form), deliberately wider than news_events.TRIGGER_A_FORMS, which
# is a *subset* of 424B forms (424B4/424B5 only) plus S-1/S-3/EFFECT that are
# NOT in this list at all -- the two modules score different questions.
SCORED_FILING_FORMS = frozenset({"8-K", "10-Q", "10-K"})


def is_scored_filing_form(form: str) -> bool:
    f = (form or "").strip().upper()
    return f in SCORED_FILING_FORMS or f.startswith("424B")


# "excluding any headline tagged to more than 5 symbols" -- Alpaca/Benzinga's
# own `symbols` field on each news item, the full tag list (not just the one
# symbol a per-symbol pull queried for). Count > 5 is excluded; count == 5 is
# not (the registration's own words: "more than 5").
MARKET_WRAP_MAX_SYMBOLS = 5


def is_scored_headline(symbol_count: int) -> bool:
    return symbol_count <= MARKET_WRAP_MAX_SYMBOLS


# --- events, timestamped, one symbol at a time --------------------------------

@dataclass(frozen=True)
class Event:
    ts: datetime   # tz-aware, America/New_York
    kind: str       # "FILING" or "HEADLINE" -- for the report only, never scored differently
    detail: str      # the form, or "N symbols" -- for sample-trade printouts


def filing_events(filings: list[dict]) -> list[Event]:
    """`filings`: rows shaped {form, accepted} -- exactly what
    `common.news_pull.load_filings_csv` hands back per symbol (the SAME
    cache `common.news_swing_pull` writes, reusing `news_pull.pull_edgar`
    unchanged). Every scored form (§11.2) becomes one Event; everything else
    is dropped here -- unlike news_events.py, this module does not keep
    descriptive-only labels, because §11 has none."""
    out = []
    for r in filings:
        form = r.get("form", "")
        if not is_scored_filing_form(form):
            continue
        accepted = r.get("accepted")
        if not accepted:
            continue
        out.append(Event(ts=parse_edgar_accepted(accepted), kind="FILING", detail=form))
    return out


def headline_events(headlines: list[dict]) -> list[Event]:
    """`headlines`: rows shaped {headline, created_at, symbol_count} --
    `symbol_count` is the field `common.news_swing_pull` adds that
    `common.news_pull`'s own cache does not carry (news_pull.py drops
    Alpaca's `symbols` list down to the single queried symbol; this rule
    needs the count, so the swing puller keeps it -- see that module's
    docstring). A row with no `symbol_count` is treated as count 1 (a
    single-name headline), the conservative default: it means "not
    excluded" rather than silently vetoing coverage that predates this
    field existing."""
    out = []
    for r in headlines:
        count = int(r["symbol_count"]) if r.get("symbol_count") not in (None, "") else 1
        if not is_scored_headline(count):
            continue
        created_at = r.get("created_at")
        if not created_at:
            continue
        out.append(Event(ts=parse_alpaca_created_at(created_at), kind="HEADLINE",
                         detail=f"{count} symbol(s)"))
    return out


# --- the tag, point-in-time, one pick at a time -------------------------------

NEWS = "NEWS"
NO_NEWS = "NO NEWS"


def tag_pick(drop_start: datetime, entry_ts: datetime, events: list[Event]) -> str:
    """NEWS if any event's timestamp falls in [drop_start, entry_ts) --
    entry itself excluded ("every timestamp must be earlier than the entry
    time", §11.2) -- else NO NEWS. `events` need not be pre-sorted or
    pre-filtered; pass one symbol's own filing_events + headline_events in.
    Both `drop_start` and `entry_ts` must be tz-aware (ET, matching the
    events); a naive datetime is a caller bug, not a rule this function
    should guess at."""
    if drop_start.tzinfo is None or entry_ts.tzinfo is None:
        raise ValueError("drop_start and entry_ts must be tz-aware (ET)")
    for e in events:
        if drop_start <= e.ts < entry_ts:
            return NEWS
    return NO_NEWS


def first_trigger(drop_start: datetime, entry_ts: datetime,
                  events: list[Event]) -> Event | None:
    """The earliest event that makes a pick NEWS, or None -- for sample-
    trade printouts (§11.3 item 3), not the verdict itself."""
    hits = [e for e in events if drop_start <= e.ts < entry_ts]
    return min(hits, key=lambda e: e.ts) if hits else None


# --- the picks contract, documented, and the join -----------------------------

# What W07-0010's SWING-v0 engine must emit for this module to tag it.
# `entry_date` + `entry_et` together are the entry timestamp; `drop_start_date`
# is the calendar date the K-day trailing-return window begins (the engine's
# own trading-calendar arithmetic -- this module does not re-derive a K-day
# lookback from a date alone, since that needs the trading calendar
# `strategy/swing/pit_universe.py`'s price files carry, not duplicated here).
# `net` / `net_2x_stress` are cash-funded, market-relative, at the bucket-
# specific friction and its 2x stress respectively (§2.6, §3 item 1) -- this
# module trusts the engine's own P&L, it does not recompute it.
PICK_FIELDS = ("symbol", "entry_date", "entry_et", "drop_start_date", "k",
              "bucket", "gross", "cost", "net", "net_2x_stress", "mkt_rel_net")


def _dt(date_s: str, hhmm: str) -> datetime:
    h, m = hhmm.split(":")
    d = _date.fromisoformat(date_s)
    return datetime(d.year, d.month, d.day, int(h), int(m), tzinfo=ET)


def _entry_of_day(date_s: str) -> datetime:
    """Midnight ET on `date_s` -- `drop_start` has no clock time of its own
    (it is a calendar date the K-day window begins), so it is compared as
    the start of that day, the most conservative reading (widest window,
    catching an event any time on the drop-start day itself)."""
    d = _date.fromisoformat(date_s)
    return datetime(d.year, d.month, d.day, 0, 0, tzinfo=ET)


def load_picks_csv(path: str) -> list[dict]:
    """Reads a picks CSV in `PICK_FIELDS` shape, adding tz-aware `entry_ts`
    / `drop_start` datetimes for the join. Numeric fields are cast; a picks
    file missing a required column fails loudly (a KeyError from csv's own
    DictReader), not silently, since a wrong-shaped picks file would
    otherwise tag every pick NO NEWS by construction (§0's own convention:
    absence of evidence must never look like a clean result)."""
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"{p} does not exist -- this is W07-0010's SWING-v0 "
                         f"picks output; run the backtest first (board W07-0010).")
    out = []
    with p.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            row = dict(r)
            row["k"] = int(r["k"])
            for money_field in ("gross", "cost", "net", "net_2x_stress", "mkt_rel_net"):
                row[money_field] = float(r[money_field])
            row["entry_ts"] = _dt(r["entry_date"], r["entry_et"])
            row["drop_start"] = _entry_of_day(r["drop_start_date"])
            out.append(row)
    return out


def population_from_picks(picks: list[dict]) -> dict[str, str]:
    """symbol -> its EARLIEST pick's `drop_start_date` -- the swing analogue
    of `common.news_pull.population_symbols`, feeding
    `common.news_swing_pull`'s per-symbol pull so the pull only ever covers
    symbols SWING-v0 actually picked, not the full ~1,600-name point-in-time
    universe (most of which is never picked on any given day)."""
    earliest: dict[str, str] = {}
    for r in picks:
        s, d = r["symbol"], r["drop_start_date"]
        if s not in earliest or d < earliest[s]:
            earliest[s] = d
    return earliest


def tag_picks(picks: list[dict], filings_by_symbol: dict[str, list[dict]],
              headlines_by_symbol: dict[str, list[dict]]) -> list[dict]:
    """Every pick, with `news_tag` (NEWS/NO NEWS) and `news_trigger` (the
    first Event that fired, or None) added. A symbol absent from both caches
    (nothing pulled or nothing found) tags NO NEWS -- absence of evidence is
    not evidence of news, the same convention `news_study.gate_book` uses
    for an un-pulled symbol on the W03-0010 line."""
    events_cache: dict[str, list[Event]] = {}
    out = []
    for r in picks:
        sym = r["symbol"]
        if sym not in events_cache:
            events_cache[sym] = (filing_events(filings_by_symbol.get(sym, []))
                                 + headline_events(headlines_by_symbol.get(sym, [])))
        ev = events_cache[sym]
        tag = tag_pick(r["drop_start"], r["entry_ts"], ev)
        trig = first_trigger(r["drop_start"], r["entry_ts"], ev)
        out.append({**r, "news_tag": tag,
                   "news_trigger": (f"{trig.kind}:{trig.detail}@{trig.ts.isoformat()}"
                                    if trig else "")})
    return out
