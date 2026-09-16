#!/usr/bin/env python3
"""Does the simulated screen surface the names the LIVE screen actually did?

    python -m common.screen_validate

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
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

from common.report_fmt import acct
from common.report_io import emit

# A list written by the live feed. Anything else was assembled by hand under a
# screen this simulation does not implement.
AUTOMATED_MARKER = "# tv_feed"

# `# MIMI   <-- BLOCKED 2026-09-03 04:01:26: Error 201 ...`
BLOCKED_INLINE = re.compile(r"^#\s*([A-Za-z][A-Za-z.\-]{0,6})\s+<--\s*BLOCKED")
# `PCLA  # 2026-09-11 04:00:05 - Error 201 ...`
BLOCKED_FILE = re.compile(r"^([A-Za-z][A-Za-z.\-]{0,6})\s*#")

GOOD, PARTIAL = 0.80, 0.50


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


def read_watchlist(path: Path) -> tuple[set[str], bool]:
    """(names, was it written by tv_feed).

    Blocked names are INCLUDED. The screen surfaced them; the broker declined
    them, and this module is measuring the screen.
    """
    names: set[str] = set()
    automated = False
    for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        if ln.startswith(AUTOMATED_MARKER):
            automated = True
            continue
        if ln.startswith("#"):
            m = BLOCKED_INLINE.match(ln)
            if m:
                names.add(m.group(1).upper())
            continue
        names.add(ln.split()[0].upper())
    return names, automated


def read_blocked(path: Path) -> set[str]:
    if not path.exists():
        return set()
    out: set[str] = set()
    for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        m = BLOCKED_FILE.match(ln)
        if m:
            out.add(m.group(1).upper())
        elif ln.split():
            out.add(ln.split()[0].upper())
    return out


def load_sim(path: Path) -> dict[str, set[str]]:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    if not rows:
        sys.exit(f"{path} is empty -- run `python -m common.screen_sim` first")
    out: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        out[r["date"]].add(r["symbol"])
    return dict(out)


def collect(archive: Path, sim: dict[str, set[str]]) -> tuple[list[dict],
                                                              list[dict]]:
    """(comparable sessions, excluded sessions with the reason)."""
    rows, skipped = [], []
    for p in sorted(archive.glob("watchlist_2*.txt")):
        if "blocked" in p.name:
            continue
        stem = p.name[len("watchlist_"):-len(".txt")]
        day = f"{stem[:4]}-{stem[4:6]}-{stem[6:8]}"
        live, automated = read_watchlist(p)
        live |= read_blocked(p.with_name(f"watchlist_blocked_{stem}.txt"))
        if not automated:
            skipped.append({"date": day, "n": len(live),
                            "why": "hand-synced under a different screen"})
            continue
        if day not in sim:
            skipped.append({"date": day, "n": len(live),
                            "why": "outside the simulation's archive window"})
            continue
        got = sim[day]
        rows.append({"date": day, "live": sorted(live), "sim": sorted(got),
                     "found": sorted(live & got),
                     "missed": sorted(live - got),
                     "sim_only": sorted(got - live)})
    return rows, skipped


def render(rows: list[dict], skipped: list[dict], sim_days: int) -> list[str]:
    L = ["DOES THE SIMULATED SCREEN MATCH THE LIVE ONE?", "",
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

    L += ["PER SESSION", "",
          f"  {'date':<12}{'live':>6}{'sim':>6}{'found':>7}{'missed':>8}"
          f"{'sim-only':>10}   the misses"]
    k = n = 0
    for r in rows:
        k += len(r["found"])
        n += len(r["live"])
        L.append(f"  {r['date']:<12}{len(r['live']):>6}{len(r['sim']):>6}"
                 f"{len(r['found']):>7}{len(r['missed']):>8}"
                 f"{len(r['sim_only']):>10}   "
                 + (", ".join(r["missed"]) if r["missed"] else "-"))

    lo, hi = wilson(k, n)
    L += ["", "THE AGREEMENT", "",
          f"  {k} of {n} live names were surfaced by the simulation "
          f"= {k / n:.0%}",
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

    # what the simulation surfaced that the live screen did not
    extra = sum(len(r["sim_only"]) for r in rows)
    L += ["THE OTHER DIRECTION, WHICH IS WEAKER EVIDENCE", "",
          f"  {extra} simulated name(s) were not on the live list.", "",
          "  This is NOT a symmetric count. The live watchlist is capped and",
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


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--archive", default="var/archive")
    p.add_argument("--pairs", default="var/state/screen_pairs_pit.json")
    p.add_argument("--out", default="var/reports/screen_validate.txt")
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    sim = load_sim(Path(a.pairs))
    rows, skipped = collect(Path(a.archive), sim)
    emit("\n".join(render(rows, skipped, len(sim))), a.out,
         header=f"common.screen_validate  archive={a.archive}  "
                f"pairs={a.pairs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
