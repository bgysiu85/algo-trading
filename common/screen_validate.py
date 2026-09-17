#!/usr/bin/env python3
"""Does the simulated screen surface the names the LIVE screen actually did?

    python -m common.screen_validate --pairs var/state/screen_pairs_pit_itch_ext.json \\
        --dataset XNAS.ITCH --capture-ladder var/reports/itch_capture.json --diagnose

THE CHECK THAT HAS NEVER BEEN RUN
----------------------------------
`screen_sim`'s only gate was its fast path against `screen_at` -- 11 ticks, 0
disagreements. That verifies the implementation against **itself**. It has never
been compared to what TradingView actually put on Ben's watchlist, and every
point-in-time figure this project produced on 2026-09-11 rests on that
unmeasured agreement. The live record already disagrees with the simulation
about the shape of MCL's deficit (47.1% win / R 0.72 against 21.7% / R 1.67),
which is what a different universe would look like.

`var/archive/watchlist_YYYYMMDD.txt` is the evidence: the actual list, archived
per session.

ONLY THE AUTOMATED WATCHLISTS COUNT, AND THIS REFUSES THE REST
---------------------------------------------------------------
The early watchlists were **hand-synced from TradingView under a different
screen**. Their own headers say so -- "RVOL(1D) >= 5x, float < 20m, top-2
pre-market gainer" -- and neither the float nor the RVOL clause exists in the
shipped `FILTERS` the simulation reproduces. Comparing against those measures
the difference between two screens and reads exactly like a simulation defect:
a first pass at this by hand scored 6 of 13, about a coin flip, on precisely
those files.

So provenance is read from the header. A list written by `tv_feed` is evidence;
anything else is excluded and counted, never silently included.

THE SESSION IS THE HEADER'S DATE, NOT THE FILE'S
-------------------------------------------------
`archive_watchlist` names the file by the machine's local date at 09:30 ET.
That is the ET date under AEST and the NEXT day under AEDT
(`prior_close_check_20260912.md`), so the pairing reads `# tv_feed YYYY-MM-DD`
and falls back to the filename only for a file with no such header.

THE 04:00 CARRY-OVER, AND WHY IT IS SET ASIDE BEFORE THE VERDICT
-----------------------------------------------------------------
The live file is ordered HOT, WARM, COLD and its header carries the counts, so
each name's tier at 09:29 is recoverable. On session after session the COLD
tail is exactly the previous session's list: `tv_feed`'s ranker was scoped to a
session on 2026-09-12, but the names kept arriving -- and the blocked files
stamp them at **04:00:05, 04:00:06, 04:00:08, 04:00:26**, the feed's first poll
of the day. TradingView's `premarket_*` fields still hold yesterday's values
until today's pre-market prints, so the first poll surfaces yesterday's screen.
That is a fact about the live feed (it arms those names), not about whether
the simulation reproduces the screen, and the simulation cannot reproduce it:
its session starts empty by construction.

So a name that is COLD at 09:29 **and** was on the previous automated list is
a *carry-over candidate*. The rule is sim-blind -- it never looks at whether
the simulation found the name -- and the verdict is read on the live names
that remain. Both bases are printed. A genuine repeat runner (on yesterday's
screen, on today's, faded by 09:29) is excluded by the same rule; the count of
candidates the simulation found anyway says how many of those there were.

THE EVIDENCE IS ASYMMETRIC, AND THE VERDICT USES ONLY THE SOUND HALF
---------------------------------------------------------------------
**A live name the simulation never surfaced is a definite miss.** It was on the
real screen; the simulation says it was not there.

**A simulated name absent from the live list is NOT a definite error.** The live
watchlist is capped at `MAX_SYMBOLS` and ordered by TradingView's own
`premarket_change`, so a name the simulation ranked 12th may simply have fallen
below the cut on a fuller tape. Both are reported; only the miss rate drives the
verdict.

**A name IBKR refused was still screened.** The blocked entries -- inline
`# SYM <-- BLOCKED` comments and the separate `watchlist_blocked_*.txt` -- are
part of the live list, because the screen surfaced them and the broker, not the
screen, declined.

TIMING, FROM THE ONLY CLOCK THE ARCHIVE KEEPS
----------------------------------------------
The archived list has no arrival times. The blocked entries do: the trader's
whatIf probe refuses a restricted name within seconds of arming it, so a
block stamp is an upper bound on when that name reached the live file --
and, per the runbook, close to it. Against the simulation's `first_seen` that
gives `live - sim` in minutes for the blocked names only. Positive means the
simulation saw the name first. It is a handful of names; it is reported as a
list with a median, never as a rate.

`--diagnose` reads the tape for every clean miss and says which clause the name
failed and by how much -- or that it passed all three at some tick, which would
point at the simulation rather than the tape -- and, for a name the live
record proves the feed had BEFORE the simulation's first_seen, what the three
clauses said at that moment. `common/screen_miss` is the fuller per-clause
diagnosis (per-clause bests, the capture the name would have needed); it
predates the capture ladder and reads every miss, carry-over included, so the
short form lives here beside the basis it belongs to.

PRE-REGISTERED, BEFORE THE FIRST RUN (2026-09-12)
--------------------------------------------------
Bands on the share of live names the simulation found, with a Wilson interval
because six sessions of eight names is a small sample and a point estimate would
be read as precise:

    >= 80%   the simulation reproduces the live screen well enough that the
             point-in-time figures can be read as describing live trading.
    50-80%   partially. Treat every point-in-time figure as indicative of a
             related universe, not a measurement of this one.
    <  50%   the simulation describes a DIFFERENT universe. Its figures are
             about that universe and may not be quoted as live expectations.

The verdict is taken from the LOWER bound of the interval, not the point
estimate: a small sample that happens to land at 81% is not evidence of 80%.
The carry-over rule and the clean basis were added 2026-09-17
(`REGISTERED_screen_validate_itch.md`) before the ITCH run.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from common.report_fmt import acct
from common.report_io import emit

ET = ZoneInfo("America/New_York")

# A list written by the live feed. Anything else was assembled by hand under a
# screen this simulation does not implement.
AUTOMATED_MARKER = "# tv_feed"
# `# tv_feed 2026-09-16 09:29:56 ET  hot=4 warm=0 cold=4`
HEADER = re.compile(r"^#\s*tv_feed\s+(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})\s+ET"
                    r"(?:\s+hot=(\d+)\s+warm=(\d+)\s+cold=(\d+))?")
# `# MIMI   <-- BLOCKED 2026-09-03 04:01:26: Error 201 ...`
BLOCKED_INLINE = re.compile(r"^#\s*([A-Za-z][A-Za-z.\-]{0,6})\s+<--\s*BLOCKED"
                            r"(?:\s+(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2}))?")
# `PCLA  # 2026-09-11 04:00:05 - Error 201 ...`
BLOCKED_FILE = re.compile(r"^([A-Za-z][A-Za-z.\-]{0,6})\s*#"
                          r"(?:\s*(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2}))?")

GOOD, PARTIAL = 0.80, 0.50
# A blocked stamp this early is the feed's first poll: the name was in the
# file before today's tape could have put it there.
FIRST_POLL_END = "04:01:00"


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% interval for a proportion.

    Wilson rather than the normal approximation because n here is dozens, not
    thousands, and the normal interval goes outside [0, 1] and misbehaves near
    the ends -- which is exactly where a good or a catastrophic result would
    land.
    """
    if not n:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    s = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (c - s) / d), min(1.0, (c + s) / d)


# --- reading the archive ----------------------------------------------------

def read_watchlist(path: Path) -> dict:
    """The archived list, with everything its text can still tell us.

    {names, automated, date (header's, or None), order (names in file order,
    inline-blocked ones in their place), tiers {name: hot|warm|cold} when the
    header's counts match the file, blocked {name: 'YYYY-MM-DD HH:MM:SS'}}.

    Blocked names are INCLUDED. The screen surfaced them; the broker declined
    them, and this module is measuring the screen.
    """
    order: list[str] = []
    blocked: dict[str, str] = {}
    automated, date, counts = False, None, None
    for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        if ln.startswith(AUTOMATED_MARKER):
            automated = True
            m = HEADER.match(ln)
            if m:
                date = m.group(1)
                if m.group(3) is not None:
                    counts = tuple(int(m.group(i)) for i in (3, 4, 5))
            continue
        if ln.startswith("#"):
            m = BLOCKED_INLINE.match(ln)
            if m:
                name = m.group(1).upper()
                order.append(name)
                if m.group(2):
                    blocked.setdefault(name, f"{m.group(2)} {m.group(3)}")
            continue
        order.append(ln.split()[0].upper())
    # keep first occurrence, in order
    seen: set[str] = set()
    order = [n for n in order if not (n in seen or seen.add(n))]
    tiers: dict[str, str] = {}
    if counts and sum(counts) == len(order):
        h, w, _c = counts
        for i, n in enumerate(order):
            tiers[n] = "hot" if i < h else "warm" if i < h + w else "cold"
    return {"names": set(order), "automated": automated, "date": date,
            "order": order, "tiers": tiers, "blocked": blocked}


def read_blocked(path: Path) -> dict[str, str]:
    """{name: stamp or ''} from watchlist_blocked_<stem>.txt."""
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        m = BLOCKED_FILE.match(ln)
        if m:
            stamp = f"{m.group(2)} {m.group(3)}" if m.group(2) else ""
            out.setdefault(m.group(1).upper(), stamp)
        elif ln.split():
            out.setdefault(ln.split()[0].upper(), "")
    return out


def load_sim(path: Path) -> dict[str, dict[str, dict]]:
    """date -> {symbol: row}. The row carries first_seen and the ranks."""
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    if not rows:
        sys.exit(f"{path} is empty -- run `python -m common.screen_sim` first")
    out: dict[str, dict[str, dict]] = defaultdict(dict)
    for r in rows:
        out[r["date"]][r["symbol"]] = r
    return dict(out)


def _sim_names(sim, day) -> set[str]:
    v = sim.get(day)
    return set(v) if v is not None else set()


def _stamp_et(stamp: str):
    try:
        return datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ET)
    except ValueError:
        return None


def _first_seen_et(row) -> datetime | None:
    if not isinstance(row, dict) or not row.get("first_seen"):
        return None
    try:
        return datetime.fromisoformat(row["first_seen"]).astimezone(ET)
    except ValueError:
        return None


def read_fills(fills_dir: Path) -> dict[str, dict[str, str]]:
    """date -> {symbol: 'YYYY-MM-DD HH:MM:SS' of the FIRST entry signal}.

    The trader can only signal a name it has armed, so the first BUY line is
    a second upper bound on when the name reached the live file -- looser than
    a block stamp (the entry conditions must also fire) but available for
    every traded name, not just the refused ones.
    """
    out: dict[str, dict[str, str]] = defaultdict(dict)
    if not fills_dir or not Path(fills_dir).exists():
        return {}
    import csv
    for p in sorted(Path(fills_dir).glob("*_fills_2*.csv")):
        with open(p, encoding="utf-8", errors="replace", newline="") as f:
            for row in csv.DictReader(f):
                if row.get("action") != "BUY" or not row.get("symbol"):
                    continue
                ts = (row.get("ts_et") or "").strip()
                if len(ts) < 19:
                    continue
                day, sym = ts[:10], row["symbol"].strip().upper()
                if sym not in out[day] or ts < out[day][sym]:
                    out[day][sym] = ts[:19]
    return dict(out)


def collect(archive: Path, sim: dict, fills: dict | None = None
            ) -> tuple[list[dict], list[dict]]:
    """(comparable sessions, excluded sessions with the reason).

    `sim` is date -> {symbol: row} (from `load_sim`) or date -> set of symbols;
    the timing columns need the rows and are empty without them.
    """
    rows, skipped = [], []
    previous: dict | None = None            # the last AUTOMATED list read
    for p in sorted(archive.glob("watchlist_2*.txt")):
        if "blocked" in p.name:
            continue
        stem = p.name[len("watchlist_"):-len(".txt")]
        file_day = f"{stem[:4]}-{stem[4:6]}-{stem[6:8]}"
        wl = read_watchlist(p)
        blocked = read_blocked(p.with_name(f"watchlist_blocked_{stem}.txt"))
        for n, s in blocked.items():
            # the EARLIEST stamp: the arming probe, not a later order rejection
            cur = wl["blocked"].get(n)
            wl["blocked"][n] = min(cur, s) if cur and s else (cur or s)
        live = wl["names"] | set(blocked)
        if not wl["automated"]:
            skipped.append({"date": file_day, "n": len(live),
                            "why": "hand-synced under a different screen"})
            continue
        day = wl["date"] or file_day
        prev_names = previous["names"] if previous else set()
        prev_day = previous["day"] if previous else None
        previous = {"names": live, "day": day}
        if day not in sim:
            skipped.append({"date": day, "n": len(live),
                            "why": "outside the simulation's archive window"})
            continue
        got = _sim_names(sim, day)
        # carry-over candidates: cold at 09:29 AND on the previous automated
        # list. Sim-blind by construction.
        carry = sorted(n for n in live
                       if wl["tiers"].get(n) == "cold" and n in prev_names)
        stale = sorted(n for n, s in wl["blocked"].items()
                       if n in prev_names and s
                       and s[11:] <= FIRST_POLL_END and s[:10] == day)
        clean = sorted(live - set(carry))
        timing = []
        for n, s in sorted(wl["blocked"].items()):
            fs = _first_seen_et(sim[day].get(n) if isinstance(sim[day], dict)
                                else None)
            st = _stamp_et(s) if s else None
            # a stale 04:00 arrival's stamp is yesterday's screen, not today's
            if fs is None or st is None or n in carry or n in stale:
                continue
            timing.append({"symbol": n, "blocked_et": st.strftime("%H:%M:%S"),
                           "sim_first_seen_et": fs.strftime("%H:%M:%S"),
                           "live_minus_sim_min": round(
                               (st - fs).total_seconds() / 60, 1)})
        signals = []
        for n, ts in sorted((fills or {}).get(day, {}).items()):
            fs = _first_seen_et(sim[day].get(n) if isinstance(sim[day], dict)
                                else None)
            st = _stamp_et(ts)
            if fs is None or st is None:
                continue
            signals.append({"symbol": n, "signal_et": st.strftime("%H:%M:%S"),
                            "sim_first_seen_et": fs.strftime("%H:%M:%S"),
                            "live_minus_sim_min": round(
                                (st - fs).total_seconds() / 60, 1)})
        sim_only = sorted(got - live)
        ranks = {}
        if isinstance(sim[day], dict):
            ranks = {n: sim[day][n].get("best_rank") for n in sim_only}
        rows.append({"date": day, "file_date": file_day, "prev_date": prev_day,
                     "live": sorted(live), "sim": sorted(got),
                     "found": sorted(live & got),
                     "missed": sorted(live - got),
                     "sim_only": sim_only, "sim_only_rank": ranks,
                     "tiers_known": bool(wl["tiers"]),
                     "carry": carry,
                     "carry_found": sorted(set(carry) & got),
                     "stale_0400": stale,
                     "live_clean": clean,
                     "found_clean": sorted(set(clean) & got),
                     "missed_clean": sorted(set(clean) - got),
                     "timing": timing, "signals": signals})
    return rows, skipped


# --- the diagnosis -----------------------------------------------------------

def diagnose_symbol(bars, prior_close: float | None, date_et, cfg,
                    cadence_s: int = 60) -> dict:
    """Why a live name was not in the simulated universe, read off the tape.

    Walks the ticks with the same visibility rule as `screen_sim` (a bar counts
    once it has CLOSED) and reports the best the name ever looked: the tick
    of maximum change, the price and cumulative volume there against the
    clause thresholds at that tick, and whether it ever cleared all three.
    """
    from common.screen_sim import accumulate, ticks
    from common.screen_at import session_open_utc

    out = {"on_tape": bars is not None and not bars.empty,
           "prior_close": prior_close, "bars": 0 if bars is None else int(len(bars))}
    if not out["on_tape"]:
        out["verdict"] = "not on the tape"
        return out
    if prior_close is None or not prior_close > 0:
        out["verdict"] = "no prior close"
        return out
    acc = accumulate(bars, cfg)
    lo, hi = cfg.price_range
    best = None
    passed_at = None
    vol_when_qualifying = None
    for t in ticks(date_et, cfg, cadence_s):
        vis = acc[(acc["visible_at"] <= t) & (acc.index >= session_open_utc(t, cfg))]
        if vis.empty:
            continue
        px = float(vis["close"].iloc[-1])
        vol = float(vis["cum_volume"].iloc[-1])
        chg = (px / prior_close - 1.0) * 100.0
        vmin = cfg.volume_min_at(t)
        et = t.tz_convert(ET).strftime("%H:%M")
        if best is None or chg > best["change"]:
            best = {"at_et": et, "change": chg, "price": px, "volume": vol,
                    "volume_min": vmin}
        if chg >= cfg.change_min and lo <= px <= hi:
            if vol_when_qualifying is None or vol > vol_when_qualifying["volume"]:
                vol_when_qualifying = {"at_et": et, "volume": vol,
                                       "volume_min": vmin, "change": chg,
                                       "price": px}
            if vol >= vmin and passed_at is None:
                passed_at = et
    out["best"] = best
    out["qualifying"] = vol_when_qualifying
    if best is None:
        out["verdict"] = "no closed bar in the window"
    elif passed_at:
        out["verdict"] = f"PASSED all three at {passed_at} -- look at the simulation"
        out["passed_at"] = passed_at
    elif best["change"] < cfg.change_min:
        out["verdict"] = (f"change never reached {cfg.change_min:g}% "
                          f"(max {best['change']:+.1f}% at {best['at_et']})")
    elif vol_when_qualifying is None:
        out["verdict"] = (f"price outside ${lo:g}-{hi:g} whenever the change "
                          f"qualified (max change {best['change']:+.1f}% at "
                          f"${best['price']:.2f})")
    else:
        q = vol_when_qualifying
        out["verdict"] = (f"volume {q['volume']:,.0f} < {q['volume_min']:,} on "
                          f"the tape at {q['at_et']} while change and price "
                          f"qualified")
    return out


def clauses_at(bars, prior_close: float | None, when_et: datetime, cfg) -> dict:
    """The three clauses for one name at one moment, as the simulation would
    have read them: bars closed by `when_et`, cumulative volume since 04:00.
    For a name the live feed had BEFORE the simulation did."""
    from common.screen_sim import accumulate
    from common.screen_at import session_open_utc
    import pandas as pd

    t = pd.Timestamp(when_et).tz_convert("UTC")
    out = {"at_et": when_et.strftime("%H:%M:%S"), "prior_close": prior_close}
    if bars is None or bars.empty:
        out["verdict"] = "not on the tape"
        return out
    if prior_close is None or not prior_close > 0:
        out["verdict"] = "no prior close"
        return out
    acc = accumulate(bars, cfg)
    vis = acc[(acc["visible_at"] <= t) & (acc.index >= session_open_utc(t, cfg))]
    if vis.empty:
        out["verdict"] = "no closed bar yet on this tape"
        return out
    px = float(vis["close"].iloc[-1])
    vol = float(vis["cum_volume"].iloc[-1])
    chg = (px / prior_close - 1.0) * 100.0
    vmin = cfg.volume_min_at(t)
    lo, hi = cfg.price_range
    failing = []
    if chg < cfg.change_min:
        failing.append(f"change {chg:+.1f}% < {cfg.change_min:g}%")
    if not lo <= px <= hi:
        failing.append(f"price {px:.2f} outside {lo:g}-{hi:g}")
    if vol < vmin:
        failing.append(f"volume {vol:,.0f} < {vmin:,}")
    out.update(change=chg, price=px, volume=vol, volume_min=vmin)
    out["verdict"] = ("; ".join(failing) if failing
                      else "PASSED all three -- look at the simulation")
    return out


def diagnose(rows: list[dict], archive_root: Path, dataset: str,
             daily_dataset: str, cfg, ladders, ladder_cut: str) -> None:
    """Fill `row['diagnosis']` for every clean miss. Reads the archive."""
    from dataclasses import replace
    from common.dbn_io import daily_frame, read_dbn
    from common.screen_sim import (load_repaired, prior_closes, window_slices,
                                   date_of)

    def late(r):
        return [t for t in r.get("timing", []) + r.get("signals", [])
                if t["live_minus_sim_min"] < 0]

    todo = {r["date"]: r["missed_clean"] + [t["symbol"] for t in late(r)]
            for r in rows if r["missed_clean"] or late(r)}
    if not todo:
        return
    slices = {date_of(p): p for p in window_slices(archive_root, dataset)}
    daily = daily_frame(archive_root, daily_dataset)
    pc = prior_closes(daily, load_repaired())
    by_date = {d: g.set_index("symbol")["prior_close"]
               for d, g in pc.groupby("date") if d in todo}
    for r in rows:
        if not r["missed_clean"] and not late(r):
            continue
        day = r["date"]
        p = slices.get(day)
        c = cfg
        if ladders is not None:
            c = replace(cfg, ladder=ladders["before" if day < ladder_cut else "after"])
        prior = by_date.get(day)
        bars = read_dbn(p) if p is not None else None
        d_et = datetime.strptime(day, "%Y-%m-%d").date()
        r["diagnosis"] = {}
        for n in r["missed_clean"]:
            b = bars[bars["symbol"] == n] if bars is not None else None
            pcv = float(prior[n]) if prior is not None and n in prior.index else None
            r["diagnosis"][n] = diagnose_symbol(b, pcv, d_et, c)
        r["late"] = {}
        for t in late(r):
            n = t["symbol"]
            b = bars[bars["symbol"] == n] if bars is not None else None
            pcv = float(prior[n]) if prior is not None and n in prior.index else None
            when = t.get("blocked_et") or t.get("signal_et")
            when_et = datetime.strptime(f"{day} {when}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=ET)
            r["late"][n] = clauses_at(b, pcv, when_et, c)


# --- the report --------------------------------------------------------------

def _totals(rows, live_key, found_key):
    k = sum(len(r.get(found_key, r["found"])) for r in rows)
    n = sum(len(r.get(live_key, r["live"])) for r in rows)
    return k, n


def render(rows: list[dict], skipped: list[dict], sim_days: int,
           label: str = "") -> list[str]:
    L = ["DOES THE SIMULATED SCREEN MATCH THE LIVE ONE?"
         + (f"   [{label}]" if label else ""), "",
         "  The check `screen_sim` never had. Its own gate was its fast path",
         "  against `screen_at` -- which verifies the implementation against",
         "  itself, not against what TradingView actually surfaced.", "",
         f"  PRE-REGISTERED bands on the share of live names found, read from",
         f"  the LOWER bound of a 95% Wilson interval:",
         f"    >= {GOOD:.0%}   the point-in-time figures describe live trading",
         f"    {PARTIAL:.0%}-{GOOD:.0%}   indicative of a related universe only",
         f"    <  {PARTIAL:.0%}   a DIFFERENT universe; do not quote its figures",
         "           as live expectations", ""]

    if skipped:
        L += ["SESSIONS EXCLUDED, AND WHY", ""]
        for s in skipped:
            L.append(f"  {s['date']}  {s['n']:>3} names   {s['why']}")
        L += ["",
              "  A hand-synced list was built under `RVOL(1D) >= 5x, float <",
              "  20m` -- clauses the shipped FILTERS do not have. Scoring",
              "  against it measures the gap between two screens and reads as",
              "  a simulation defect.", ""]

    if not rows:
        return L + ["NO VERDICT", "",
                    "  No session has both an automated watchlist and "
                    "simulated",
                    f"  coverage. The simulation spans {sim_days} session(s);",
                    "  extend the Databento archive so the two overlap.", ""]

    has_carry = any("carry" in r for r in rows)

    L += ["PER SESSION, EVERY LIVE NAME", "",
          f"  {'date':<12}{'live':>6}{'sim':>6}{'found':>7}{'missed':>8}"
          f"{'sim-only':>10}   the misses"]
    for r in rows:
        L.append(f"  {r['date']:<12}{len(r['live']):>6}{len(r['sim']):>6}"
                 f"{len(r['found']):>7}{len(r['missed']):>8}"
                 f"{len(r['sim_only']):>10}   "
                 + (", ".join(r["missed"]) if r["missed"] else "-"))
    k_all, n_all = _totals(rows, "live", "found")
    lo_a, hi_a = wilson(k_all, n_all)
    L += ["", f"  {k_all} of {n_all} live names surfaced by the simulation = "
              f"{k_all / n_all:.0%}   95% interval {lo_a:.0%} to {hi_a:.0%}", ""]

    if has_carry:
        L += ["THE 04:00 CARRY-OVER, SET ASIDE", "",
              "  A name COLD at 09:29 that was on the previous automated list.",
              "  TradingView's premarket fields hold yesterday's values until",
              "  today's prints, so the feed's first poll surfaces yesterday's",
              "  screen; the blocked files stamp those names at 04:00:0x. The",
              "  rule never looks at the simulation. `sim found` counts the",
              "  candidates the simulation surfaced anyway -- repeat runners.", "",
              f"  {'date':<12}{'prev':<12}{'carry':>6}{'sim found':>10}"
              f"{'04:00 stamp':>12}   the names"]
        for r in rows:
            if not r.get("tiers_known", True):
                L.append(f"  {r['date']:<12}{'':<12}{'?':>6}{'':>10}{'':>12}   "
                         "header counts do not match the file; nothing set aside")
                continue
            L.append(f"  {r['date']:<12}{str(r.get('prev_date') or '-'):<12}"
                     f"{len(r['carry']):>6}{len(r['carry_found']):>10}"
                     f"{len(r['stale_0400']):>12}   "
                     + (", ".join(r["carry"]) if r["carry"] else "-"))
        L += ["", "PER SESSION, CARRY-OVER SET ASIDE  (the verdict's basis)", "",
              f"  {'date':<12}{'live':>6}{'sim':>6}{'found':>7}{'missed':>8}"
              f"{'sim-only':>10}   the misses"]
        for r in rows:
            L.append(f"  {r['date']:<12}{len(r['live_clean']):>6}{len(r['sim']):>6}"
                     f"{len(r['found_clean']):>7}{len(r['missed_clean']):>8}"
                     f"{len(r['sim_only']):>10}   "
                     + (", ".join(r["missed_clean"]) if r["missed_clean"] else "-"))
        L.append("")

    k, n = _totals(rows, "live_clean", "found_clean")
    lo, hi = wilson(k, n)
    L += ["THE AGREEMENT", "",
          f"  {k} of {n} live names were surfaced by the simulation "
          f"= {k / n:.0%}" if n else "  no live names remain",
          f"  95% interval  {lo:.0%} to {hi:.0%}   over {len(rows)} session(s)",
          ""]

    if lo >= GOOD:
        L += ["  THE SIMULATION REPRODUCES THE LIVE SCREEN. The point-in-time",
              "  figures can be read as describing live trading, and the",
              "  disagreement between them and the live record is about sample",
              "  size rather than about the universe.", ""]
    elif lo >= PARTIAL:
        L += ["  PARTIAL. The simulation finds most of the live screen and",
              "  misses a material share of it, so every point-in-time figure",
              "  is indicative of a related universe rather than a measurement",
              "  of the one actually traded. Quote them with this number.", ""]
    else:
        L += ["  A DIFFERENT UNIVERSE. The simulation does not reproduce the",
              "  live screen, so its figures are about the universe it built",
              "  and may not be quoted as live expectations. Every conclusion",
              "  drawn on the point-in-time universe needs this caveat --",
              "  including that MCL beats its control.", ""]

    if hi - lo > 0.30:
        L += [f"  The interval is {hi - lo:.0%} wide on {n} names. This is a",
              "  small sample and the band above was read from its lower edge",
              "  for that reason; more sessions will move it.", ""]

    # the misses, diagnosed
    diag = [(r["date"], n, d) for r in rows
            for n, d in (r.get("diagnosis") or {}).items()]
    if diag:
        L += ["THE MISSES, READ OFF THE TAPE", "",
              "  The best each name ever looked at a tick, and the clause it",
              "  failed there. `PASSED` would mean the tape agrees with the live",
              "  screen and the simulation does not.", ""]
        for day, n, d in diag:
            b = d.get("best") or {}
            L.append(f"  {day}  {n:<7} {d['verdict']}")
            if b:
                L.append(f"  {'':<12}{'':<7} prior {acct(d['prior_close'], 8)}  "
                         f"best {b['change']:+.1f}% at {b['at_et']}  "
                         f"px {b['price']:.2f}  vol {b['volume']:,.0f} "
                         f"(min {b['volume_min']:,})")
        L.append("")

    late = [(r["date"], n, d) for r in rows
            for n, d in (r.get("late") or {}).items()]
    if late:
        L += ["THE NAMES THE LIVE FEED HAD FIRST, READ OFF THE TAPE", "",
              "  What the simulation's three clauses said about the name at",
              "  the moment the live record proves the feed already had it.", ""]
        for day, n, d in late:
            L.append(f"  {day}  {n:<7} at {d['at_et']}  {d['verdict']}")
        L.append("")

    # timing from the blocked stamps
    timing = [(r["date"], t) for r in rows for t in r.get("timing", [])]
    if timing:
        deltas = sorted(t["live_minus_sim_min"] for _, t in timing)
        med = deltas[len(deltas) // 2] if len(deltas) % 2 else (
            deltas[len(deltas) // 2 - 1] + deltas[len(deltas) // 2]) / 2
        L += ["WHEN, FROM THE BLOCKED STAMPS", "",
              "  The trader refuses a restricted name within seconds of arming",
              "  it, so a block stamp is an upper bound on when the name reached",
              "  the live file. Against the simulation's first_seen (ET):", "",
              f"  {'date':<12}{'name':<7}{'blocked':>9}{'sim first':>11}"
              f"{'live-sim':>10}"]
        for day, t in timing:
            L.append(f"  {day:<12}{t['symbol']:<7}{t['blocked_et']:>9}"
                     f"{t['sim_first_seen_et']:>11}{t['live_minus_sim_min']:>+9.1f}m")
        L += ["", f"  {len(deltas)} name(s), median live-sim {med:+.1f} min, "
                  f"range {deltas[0]:+.1f} to {deltas[-1]:+.1f}.",
              "  Positive: the simulation saw the name before the live feed",
              "  can be shown to have had it. A list, not a rate.", ""]

    signals = [(r["date"], t) for r in rows for t in r.get("signals", [])]
    if signals:
        deltas = sorted(t["live_minus_sim_min"] for _, t in signals)
        med = deltas[len(deltas) // 2] if len(deltas) % 2 else (
            deltas[len(deltas) // 2 - 1] + deltas[len(deltas) // 2]) / 2
        early = sum(1 for d in deltas if d < 10)
        L += ["WHEN, FROM THE FIRST ENTRY SIGNAL", "",
              "  The trader signals only a name it has armed, so the first BUY",
              "  line is another upper bound on arrival -- looser (the entry",
              "  conditions must fire too) but for every traded name. What",
              "  matters is the SMALLEST delta: one name signalled under ten",
              "  minutes after the tape first qualified it rules out a fixed",
              "  feed delay of that size.", "",
              f"  {'date':<12}{'name':<7}{'1st BUY':>9}{'sim first':>11}"
              f"{'live-sim':>10}"]
        for day, t in signals:
            L.append(f"  {day:<12}{t['symbol']:<7}{t['signal_et']:>9}"
                     f"{t['sim_first_seen_et']:>11}{t['live_minus_sim_min']:>+9.1f}m")
        L += ["", f"  {len(deltas)} name(s), median {med:+.1f} min, smallest "
                  f"{deltas[0]:+.1f}, {early} under +10 min.", ""]

    # what the simulation surfaced that the live screen did not
    extra = sum(len(r["sim_only"]) for r in rows)
    L += ["THE OTHER DIRECTION, WHICH IS WEAKER EVIDENCE", "",
          f"  {extra} simulated name(s) were not on the live list.", ""]
    ranked = [(r["date"], n, r.get("sim_only_rank", {}).get(n))
              for r in rows for n in r["sim_only"]]
    if any(rk is not None for _, _, rk in ranked):
        L.append(f"  {'date':<12}{'name':<7}{'best rank':>10}")
        for day, n, rk in ranked:
            L.append(f"  {day:<12}{n:<7}{(rk if rk is not None else '?'):>10}")
        L.append("")
    L += ["  This is NOT a symmetric count. The live watchlist is capped and",
          "  ordered by TradingView's own premarket_change, so a name the",
          "  simulation ranked twelfth may simply have fallen below the cut on",
          "  a fuller tape. It is reported because a large number would point",
          "  at the volume threshold or the capture ratio, and it is kept out",
          "  of the verdict because it cannot distinguish those from a",
          "  ranking difference.", ""]

    L += ["WHAT THIS IS NOT", "",
          "  Not a test of the screen's RULES. Both sides apply the same three",
          "  clauses; what differs is the tape underneath them and",
          "  TradingView's own consolidation.",
          "",
          "  Not a measure of what was tradeable. Names IBKR refused are",
          "  counted as screened, because the screen surfaced them and the",
          "  broker declined -- a different failure with a different fix."]
    return L


def summary(rows: list[dict], skipped: list[dict], label: str) -> dict:
    k_all, n_all = _totals(rows, "live", "found")
    k, n = _totals(rows, "live_clean", "found_clean")
    return {"label": label, "sessions": len(rows), "skipped": skipped,
            "all": {"found": k_all, "live": n_all, "wilson": wilson(k_all, n_all)},
            "clean": {"found": k, "live": n, "wilson": wilson(k, n)},
            "carry": sum(len(r.get("carry", [])) for r in rows),
            "carry_found": sum(len(r.get("carry_found", [])) for r in rows),
            "stale_0400": sum(len(r.get("stale_0400", [])) for r in rows),
            "sim_only": sum(len(r["sim_only"]) for r in rows),
            "rows": rows}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--archive", default="var/archive",
                   help="the watchlist archive (var/archive)")
    p.add_argument("--pairs", default="var/state/screen_pairs_pit.json")
    p.add_argument("--out", default="var/reports/screen_validate.txt")
    p.add_argument("--label", default="", help="printed in the title, e.g. the tape")
    p.add_argument("--fills", default="var/fills",
                   help="the trader's fill logs, for the first-signal clock "
                        "(pass '' to skip)")
    p.add_argument("--diagnose", action="store_true",
                   help="read the Databento archive for every clean miss")
    p.add_argument("--databento", default=None,
                   help="Databento archive root (default: as databento_fetch resolves it)")
    p.add_argument("--dataset", default="XNAS.BASIC")
    p.add_argument("--daily-dataset", default="XNAS.BASIC")
    p.add_argument("--capture", type=float, default=None)
    p.add_argument("--capture-ladder", default=None)
    p.add_argument("--ladder-cut", default="2026-03-30")
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    sim = load_sim(Path(a.pairs))
    rows, skipped = collect(Path(a.archive), sim,
                            read_fills(Path(a.fills)) if a.fills else None)
    if a.diagnose and rows:
        from dataclasses import replace
        from common.databento_fetch import default_archive
        from common.screen_at import ScreenConfig, ladder_from_json
        cfg = ScreenConfig()
        if a.capture is not None:
            cfg = replace(cfg, capture=a.capture)
        ladders = None
        if a.capture_ladder:
            ladders = {reg: ladder_from_json(a.capture_ladder, reg)
                       for reg in ("before", "after")}
        root = Path(a.databento) if a.databento else default_archive()
        diagnose(rows, root, a.dataset, a.daily_dataset, cfg, ladders, a.ladder_cut)
    label = a.label or a.dataset
    emit("\n".join(render(rows, skipped, len(sim), label)), a.out,
         header=f"common.screen_validate  archive={a.archive}  "
                f"pairs={a.pairs}  dataset={a.dataset}"
                + (f"  capture_ladder={a.capture_ladder}" if a.capture_ladder else "")
                + ("  diagnose" if a.diagnose else ""))
    out = Path(a.out)
    if a.out:
        js = out.with_suffix(".json")
        js.write_text(json.dumps(summary(rows, skipped, label), indent=1,
                                 default=str), encoding="utf-8")
        print(f"summary written to {js}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
