#!/usr/bin/env python3
r"""The classifier: dilution/reverse-split filings and press headlines, as
Trigger A / Trigger B / two descriptive-only labels -- exactly per
`docs/research/REGISTERED_news_events.md` \xa73. No network here and no P&L;
this module turns rows a puller already fetched into point-in-time labels.
`common.news_pull` fetches; `common.news_study` scores. This module only
classifies and windows.

THE TWO GATES THIS MODULE CLEARS (\xa70 G2-G3)
-------------------------------------------
G2(a) two named false positives, both from the probe's own 30-day sample,
checked BEFORE the headline rules that would otherwise fire on them:
  * "PG&E And GM Energy Announce Bundle Offering ..." -- a product bundle,
    not a securities offering. Would otherwise match OFFERING_PRICED.
  * "IM Cannabis Says It Received Nasdaq Notice Of Regained Compliance ..."
    -- the OPPOSITE of a new deficiency. Would otherwise match DELIST_NOTICE.
G2(b) normalization before any match: HTML entities (`&#39;` -> `'`) and every
non-ASCII hyphen/dash variant (probe sample: DCOY's headline used U+2011,
"1‑For‑12") folded to a plain '-'.
G2(c) 424B3 and proxy-only filings (DEF 14A / PRE 14A / DEFA14A) are held OUT
of Trigger A/B and returned as their own descriptive labels.
G2(d) EDGAR's `acceptanceDateTime` is Eastern time despite the raw JSON's
trailing 'Z' -- see `parse_edgar_accepted`'s docstring for the evidence.
G3 is `tests/common/test_news_events.py::test_g3_probe_sample`, which
reproduces the probe's hand-read sample (`claude/raw/w03_0010_news_probe_20260924.txt`)
row for row and asserts this module's label matches the human one.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
REGISTERED = "docs/research/REGISTERED_news_events.md"

# --- G2(b): normalization, applied before any keyword match -----------------

# Every Unicode hyphen/dash variant seen or plausible in wire headlines,
# folded to the plain ASCII '-' the regexes below are written against.
_HYPHENS = {
    "‐": "-", "‑": "-", "‒": "-", "–": "-",
    "—": "-", "−": "-",
}


def normalize_headline(text: str | None) -> str:
    """HTML-entity unescape, then every non-standard hyphen/dash folded to
    '-'. Applied before any keyword match (\xa70 G2b) -- the probe's DCOY
    headline ("1‑For‑12", U+2011) and the live-websocket sample
    ("&#39;A...", an HTML entity) are the two cases this exists for."""
    if not text:
        return ""
    t = html.unescape(text)
    for h, plain in _HYPHENS.items():
        t = t.replace(h, plain)
    return t


# --- headline classifier ------------------------------------------------------------

# G2(a): checked BEFORE the rules below, on the normalized text. A hit here
# means NOT FLAGGED, full stop, whatever else the headline would otherwise
# match -- the registration's own words ("both classify as NOT FLAGGED").
_EXCLUDE_BEFORE: list[re.Pattern] = [
    re.compile(r"\bbundle offering\b", re.I),           # GM/PCG, probe sample
    re.compile(r"regained compliance", re.I),            # IMCC, probe sample
]

# Order matters: the first rule that matches wins, most specific first --
# unchanged from the probe's first draft (w03_0010_news_probe.py), which this
# module supersedes as the STUDY's registered classifier (\xa73's own words:
# "the study registers its own").
HEADLINE_RULES: list[tuple[str, re.Pattern]] = [
    ("REVERSE_SPLIT", re.compile(
        r"reverse (stock |share )?split|\b1[- ]for[- ]\d{1,3}\b|share consolidation", re.I)),
    # "priced at-the-market under Nasdaq rules" is a registered direct
    # offering's pricing language, not an ATM program, so it is excluded here
    # and falls through to OFFERING_PRICED.
    ("ATM", re.compile(r"(?<!priced )at[- ]the[- ]market(?! under)|"
                       r"\bATM (offering|program|facility)", re.I)),
    ("OFFERING_PROPOSED", re.compile(
        r"(proposed|intends? to offer|launch(es)?).{0,60}(offering|private placement)", re.I)),
    ("OFFERING_PRICED", re.compile(
        r"(announces?|prices?|priced|pricing of|closes?|closing of).{0,80}"
        r"(offering|registered direct|private placement|PIPE\b)", re.I)),
    ("WARRANT", re.compile(r"warrant (inducement|exercise|amendment|repricing)|"
                           r"inducement (letter|agreement)", re.I)),
    ("DELIST_NOTICE", re.compile(r"(nasdaq|nyse).{0,60}(deficiency|non-?compliance|"
                                 r"delist|minimum bid)", re.I)),
]


def classify_headline(headline: str | None) -> str | None:
    """The label a headline matches, after G2(b) normalization and G2(a)'s
    two exclusions, or None. One of REVERSE_SPLIT / ATM / OFFERING_PROPOSED /
    OFFERING_PRICED / WARRANT / DELIST_NOTICE / None."""
    t = normalize_headline(headline)
    if not t:
        return None
    for rx in _EXCLUDE_BEFORE:
        if rx.search(t):
            return None
    for label, rx in HEADLINE_RULES:
        if rx.search(t):
            return label
    return None


# --- EDGAR filing classification, exactly per REGISTERED_news_events.md \xa73 ------

# Trigger A -- a fresh dilution EVENT, trailing 2 calendar days.
TRIGGER_A_FORMS = frozenset({"S-1", "S-1/A", "S-3", "424B4", "424B5", "EFFECT"})
TRIGGER_A_8K_ITEMS = frozenset({"1.01", "3.02"})
TRIGGER_A_WINDOW_DAYS = 2

# Trigger B -- a reverse split FILED (takes effect), trailing 30 calendar days.
TRIGGER_B_8K_ITEM = "5.03"
TRIGGER_B_WINDOW_DAYS = 30

# 424B3 is explicitly EXCLUDED from Trigger A (\xa73): a routine prospectus
# supplement under an ALREADY-EFFECTIVE shelf is a continuous state, not a
# discrete event. Tracked as its own descriptive label instead.
ACTIVE_SHELF_FORM = "424B3"
ACTIVE_SHELF_WINDOW_DAYS = 90
ACTIVE_SHELF_MIN_COUNT = 3

# A proxy alone is not Trigger B (\xa73) -- descriptive only.
PROPOSED_RS_FORMS = frozenset({"DEF 14A", "PRE 14A", "DEFA14A"})

# Descriptive-only headline labels that are never a trigger (\xa73): reported
# beside the scored buckets, folded into neither A nor B.
DESCRIPTIVE_HEADLINE_LABELS = frozenset({"DELIST_NOTICE", "ATM"})


def _8k_items(items_field: str | None) -> frozenset[str]:
    return frozenset(x.strip() for x in (items_field or "").split(",") if x.strip())


def classify_filing(form: str, items_field: str | None = "") -> frozenset[str]:
    """The set of labels one filing row earns -- zero, one, or two of
    TRIGGER_A / TRIGGER_B / ACTIVE_SHELF_CANDIDATE / PROPOSED_RS_CANDIDATE.

    TWO AT ONCE IS REAL, NOT A BUG: an 8-K can carry both a dilution item and
    5.03 in the same filing (the probe sample's GRML row, items "1.01,3.02,5.03"
    -- items 1.01/3.02 are Trigger A, 5.03 is Trigger B, in the SAME filing),
    so this returns a set rather than the first match. A form outside every
    list here -- an 8-K whose only item is 3.01 or 3.03, e.g. -- returns the
    empty set: those items bear on listing/holder mechanics the registration
    does not score (\xa73 only names 1.01, 3.02, 5.03)."""
    items = _8k_items(items_field)
    out: set[str] = set()
    if form == ACTIVE_SHELF_FORM:
        out.add("ACTIVE_SHELF_CANDIDATE")
    if form in PROPOSED_RS_FORMS:
        out.add("PROPOSED_RS_CANDIDATE")
    if form in TRIGGER_A_FORMS:
        out.add("TRIGGER_A")
    if form.startswith("8-K"):
        if items & TRIGGER_A_8K_ITEMS:
            out.add("TRIGGER_A")
        if TRIGGER_B_8K_ITEM in items:
            out.add("TRIGGER_B")
    return frozenset(out)


# --- G2(d): EDGAR's acceptanceDateTime is Eastern, not UTC ------------------

def parse_edgar_accepted(raw: str) -> datetime:
    """EDGAR's `acceptanceDateTime`, localized to America/New_York.

    THE RAW JSON'S TRAILING 'Z' IS MISLEADING. SEC's own field is Eastern
    wall-clock time despite the ISO-8601 UTC marker -- the evidence is the
    probe's own hand-pulled sample (\xa70 G2d, `w03_0010_news_probe_20260924.txt`):
    WHLR's four same-day 424B3 filings land at 20:07-20:18, IPDN/GRML/KIDZ's
    filings cluster 20:30-21:23. EDGAR accepts filings up to 22:00 ET for
    same-day filing status; a cluster in the twenty minutes before 22:00 is
    the expected shape of last-minute filing behaviour in EASTERN time and
    an unexplained coincidence in UTC (which would put it mid-afternoon on
    the US west coast, evening in the UK -- no comparable market-close or
    deadline sits there). This is a documented interpretation, not a network
    re-check (this session cannot reach sec.gov); `common.news_pull`'s own
    docstring repeats the same claim and its report prints the raw
    acceptanceDateTime beside the parsed one so Ben can eyeball the same
    clustering against a live pull before subitem 5 is scored (\xa70 G2d says
    "confirmed", not "assumed", and this is the puller's job to confirm).

    Localized DST-aware via zoneinfo, never converted from UTC -- converting
    would shift every timestamp by 4 or 5 hours in the wrong direction.
    """
    s = raw.strip()
    if s.endswith("Z"):
        s = s[:-1]
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt.replace(tzinfo=ET)


def parse_alpaca_created_at(raw: str) -> datetime:
    """Alpaca/Benzinga's `created_at` -- genuine RFC3339 UTC, converted to ET.
    Unlike EDGAR's acceptanceDateTime, Alpaca's timestamp is real UTC; the
    distinction is the point of having two functions instead of one."""
    s = raw.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s).astimezone(ET)


# --- events, merged across both sources -------------------------------------

@dataclass(frozen=True)
class Event:
    """One classified, timestamped, point-in-time fact about a symbol."""
    ts: datetime          # tz-aware, America/New_York
    kind: str              # TRIGGER_A / TRIGGER_B / ACTIVE_SHELF_CANDIDATE /
                            # PROPOSED_RS_CANDIDATE / DELIST_NOTICE / ATM
    source: str             # "EDGAR" / "ALPACA"
    symbol: str
    detail: str              # the form, or the headline label -- for the report


def events_from_filings(symbol: str, filings: list[dict]) -> list[Event]:
    """`filings`: rows shaped {form, items (comma string), accepted (EDGAR's
    raw acceptanceDateTime string)} -- what `common.news_pull` writes to its
    per-symbol cache. One filing can yield two Events (the GRML case)."""
    out: list[Event] = []
    for r in filings:
        kinds = classify_filing(r["form"], r.get("items", ""))
        if not kinds:
            continue
        ts = parse_edgar_accepted(r["accepted"])
        out.extend(Event(ts=ts, kind=k, source="EDGAR", symbol=symbol,
                         detail=r["form"]) for k in sorted(kinds))
    return out


def events_from_headlines(symbol: str, headlines: list[dict]) -> list[Event]:
    """`headlines`: rows shaped {headline, created_at (Alpaca's raw UTC
    string)}. REVERSE_SPLIT -> TRIGGER_B; OFFERING_PRICED/OFFERING_PROPOSED
    -> TRIGGER_A; ATM/WARRANT/DELIST_NOTICE are kept as their own descriptive
    kind, never folded into a trigger (\xa73)."""
    label_to_trigger = {"REVERSE_SPLIT": "TRIGGER_B",
                        "OFFERING_PRICED": "TRIGGER_A",
                        "OFFERING_PROPOSED": "TRIGGER_A"}
    out: list[Event] = []
    for r in headlines:
        label = classify_headline(r.get("headline"))
        if label is None:
            continue
        ts = parse_alpaca_created_at(r["created_at"])
        kind = label_to_trigger.get(label, label)  # WARRANT stays "WARRANT" etc.
        out.append(Event(ts=ts, kind=kind, source="ALPACA", symbol=symbol, detail=label))
    return out


# --- point-in-time evaluation, one symbol at a time -------------------------

EDGAR_ONLY = frozenset({"EDGAR"})
EDGAR_PLUS_HEADLINES = frozenset({"EDGAR", "ALPACA"})


def _within(events: list[Event], kind: str, at: datetime, days: int) -> list[Event]:
    """Events of `kind`, at or before `at`, strictly within the trailing
    `days` (i.e. `at - days*24h < ts <= at`) -- a rolling window, the same
    convention `common.edgar_shares.STALE_DAYS` uses (elapsed time, not
    calendar-date boundaries)."""
    cut = at - timedelta(days=days)
    return [e for e in events if e.kind == kind and cut < e.ts <= at]


def label_at(events: list[Event], at: datetime, *,
            sources: frozenset[str] = EDGAR_PLUS_HEADLINES) -> dict:
    """Everything true of a symbol AT `at`, from `events` filtered to
    `sources`. `events` need not be pre-sorted or pre-filtered to the symbol
    -- pass one symbol's own events in."""
    ev = [e for e in events if e.source in sources]
    trig_a = _within(ev, "TRIGGER_A", at, TRIGGER_A_WINDOW_DAYS)
    trig_b = _within(ev, "TRIGGER_B", at, TRIGGER_B_WINDOW_DAYS)
    shelf = _within(ev, "ACTIVE_SHELF_CANDIDATE", at, ACTIVE_SHELF_WINDOW_DAYS)
    proposed = _within(ev, "PROPOSED_RS_CANDIDATE", at, ACTIVE_SHELF_WINDOW_DAYS)
    delist = _within(ev, "DELIST_NOTICE", at, ACTIVE_SHELF_WINDOW_DAYS)
    atm = _within(ev, "ATM", at, ACTIVE_SHELF_WINDOW_DAYS)
    return {
        "trigger_a": bool(trig_a), "trigger_b": bool(trig_b),
        "veto": bool(trig_a or trig_b),
        "active_shelf": len(shelf) >= ACTIVE_SHELF_MIN_COUNT,
        "proposed_rs": bool(proposed),
        "delist_notice_recent": bool(delist),
        "atm_recent": bool(atm),
        "trigger_a_events": trig_a, "trigger_b_events": trig_b,
    }


# --- \xa73's recency table, descriptive only ------------------------------------

RECENCY_BUCKETS = ((0.0, 1.0, "0-1 day"), (1.0, 7.0, "2-7"),
                   (7.0, 30.0, "8-30"), (30.0, 90.0, "31-90"))


def recency_bucket(events: list[Event], kind: str, at: datetime) -> str:
    """Which \xa73 recency bucket the MOST RECENT `kind` event before `at`
    falls in, or 'none' / '90+'. Descriptive only -- never read by a verdict."""
    cand = [e for e in events if e.kind == kind and e.ts <= at]
    if not cand:
        return "none"
    days = (at - max(e.ts for e in cand)).total_seconds() / 86400.0
    for lo, hi, label in RECENCY_BUCKETS:
        if lo <= days <= hi:
            return label
    return "90+"
