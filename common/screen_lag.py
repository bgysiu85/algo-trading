#!/usr/bin/env python3
"""Is the live watchlist compared against the wrong SESSION?

    python -m common.screen_lag

WHAT `prior_close_check` TURNED UP INSTEAD OF WHAT IT WENT LOOKING FOR
-----------------------------------------------------------------------
The hypothesis was an off-by-one in `prior_close`. It is dead: every name's
`prior_close` was the previous daily row, correctly. But the consistent
baselines were not one row back, they were two to five, and the same shape
appeared on every name -- the 20% move had ALREADY HAPPENED, one session before
the watchlist that carries the name:

    file 2026-09-11  ACVA   moved 7.37 -> 10.38 on 09-10, flat on 09-11
    file 2026-09-10  IRD    moved 4.48 ->  6.07 on 09-09, flat on 09-10
    file 2026-09-10  BIAF   moved 8.86 -> 10.91 on 09-09, flat on 09-10
    file 2026-09-09  WYHG   moved 4.06 ->  5.61 on 09-08, flat on 09-09

That is not a threshold and not a baseline. It is the comparison being made
against the wrong SESSION -- `archive_watchlist` stamps with `datetime.now(ET)`
at the moment of archiving, so a list left unarchived by an interrupted session
and cleared at the start of the next one lands under the NEXT day's date.

WHY THOSE FOUR NAMES ARE NOT THE EVIDENCE
------------------------------------------
I chose them. Four rows that fit a shape I had just described are worth a
hypothesis and nothing more, and a module written to re-display them would be
the same mistake with more code around it.

So this measures the shape on ALL the evidence: every automated watchlist,
every name on it, against the simulation's universe for a RANGE of session
offsets. If the live list for date D really describes session D-1, then scoring
it against the simulation's D-1 universe must beat scoring it against D.

PRE-REGISTERED, BEFORE THE FIRST RUN (2026-09-12)
--------------------------------------------------
Testing several offsets and reporting the best one is fitting. So the claim is
constrained in advance:

    A lag is CLAIMED only if a single non-zero offset
      (a) beats offset 0 by at least MATERIAL on the pooled found-rate, AND
      (b) beats offset 0 on EVERY session individually, not just pooled.

    Anything else is reported as NOT ESTABLISHED, including the case where
    several offsets improve on 0 -- that pattern says the watchlists carry
    persistent names, not that the dates are shifted.

(b) is what makes this falsifiable on four sessions. A pooled number can be
carried by one session; a rule that must hold four times out of four cannot.

WHAT THIS CANNOT DO
--------------------
Shifting the comparison shrinks the overlap: a watchlist dated on the first
session of the archive has no D-1 universe to score against, so offsets are
compared only over the sessions where BOTH are defined, and the count is
printed for every offset. An offset scored on fewer sessions than offset 0 is
not comparable to it and the report says so rather than ranking them together.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from common.report_fmt import acct
from common.report_io import emit
from common.screen_validate import load_sim, read_blocked, read_watchlist

MATERIAL = 0.10          # pooled found-rate improvement that counts
OFFSETS = (-2, -1, 0, 1, 2)


def parse_day(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def sessions_of(sim: dict[str, set[str]]) -> list[date]:
    """The simulation's session dates, in order. These ARE the trading days --
    a weekend or a holiday has no window slice and so no universe, which is why
    an offset is counted in SESSIONS and never in calendar days."""
    return sorted(parse_day(d) for d in sim)


def shift(day: date, off: int, sessions: list[date]) -> date | None:
    """`off` trading sessions from `day`, or None if that falls off the archive.

    Calendar arithmetic would step a Monday-dated list onto a Sunday with no
    universe at all and score it as a total miss -- an artefact that would look
    exactly like a real lag.
    """
    if day not in sessions:
        return None
    i = sessions.index(day) + off
    return sessions[i] if 0 <= i < len(sessions) else None


def live_lists(archive: Path) -> tuple[dict[date, set[str]], list[dict]]:
    """Automated watchlists only, keyed by the date in the FILENAME."""
    out: dict[date, set[str]] = {}
    skipped: list[dict] = []
    for p in sorted(archive.glob("watchlist_2*.txt")):
        if "blocked" in p.name:
            continue
        stem = p.name[len("watchlist_"):-len(".txt")]
        # `_unique_path` appends _2 when a date is archived twice. A second
        # archive on one date is itself a symptom of the mechanism under test,
        # so it is named rather than merged in or dropped in silence.
        suffix = ""
        if len(stem) > 8:
            suffix, stem = stem[8:], stem[:8]
        try:
            day = parse_day(f"{stem[:4]}-{stem[4:6]}-{stem[6:8]}")
        except ValueError:
            skipped.append({"file": p.name, "why": "unparseable date"})
            continue
        live, automated = read_watchlist(p)
        live |= read_blocked(p.with_name(f"watchlist_blocked_{stem}{suffix}.txt"))
        if not automated:
            skipped.append({"file": p.name, "n": len(live),
                            "why": "hand-synced under a different screen"})
            continue
        if suffix:
            skipped.append({"file": p.name, "n": len(live),
                            "why": f"second archive on {day} -- not merged"})
            continue
        if not live:
            skipped.append({"file": p.name, "n": 0, "why": "empty"})
            continue
        out[day] = live
    return out, skipped


def score(live: dict[date, set[str]], sim: dict[str, set[str]],
          sessions: list[date], off: int) -> dict:
    """Found-rate for one offset, pooled and per session."""
    per, k, n = [], 0, 0
    for day in sorted(live):
        target = shift(day, off, sessions)
        if target is None:
            continue
        got = sim.get(target.isoformat())
        if got is None:
            continue
        names = live[day]
        found = names & got
        per.append({"file_date": day, "scored_against": target,
                    "k": len(found), "n": len(names),
                    "rate": len(found) / len(names)})
        k += len(found)
        n += len(names)
    return {"offset": off, "k": k, "n": n, "sessions": len(per),
            "rate": (k / n) if n else 0.0, "per": per}


def verdict(rows: list[dict]) -> tuple[str, list[str]]:
    """NOT ESTABLISHED unless exactly one offset clears both pre-registered
    conditions. The tie case is a refusal, not a tie-break."""
    base = next((r for r in rows if r["offset"] == 0), None)
    if base is None or not base["sessions"]:
        return "NO BASELINE", ["Offset 0 scored no session -- nothing to "
                               "compare against."]

    # Only offsets scored over the SAME sessions as offset 0 are comparable.
    base_days = {p["file_date"] for p in base["per"]}
    winners = []
    for r in rows:
        if r["offset"] == 0 or not r["sessions"]:
            continue
        if {p["file_date"] for p in r["per"]} != base_days:
            continue
        if r["rate"] - base["rate"] < MATERIAL:
            continue
        bys = {p["file_date"]: p["rate"] for p in base["per"]}
        if all(p["rate"] > bys[p["file_date"]] for p in r["per"]):
            winners.append(r)

    if len(winners) == 1:
        w = winners[0]
        return "LAG OF %+d SESSION(S)" % w["offset"], [
            f"The live list dated D matches the simulation's universe for "
            f"session D{w['offset']:+d}",
            f"on every one of {w['sessions']} session(s), and pools "
            f"{w['rate']:.0%} against offset 0's {base['rate']:.0%}.",
            "",
            "This is a DATE defect, not a screen defect. The simulated screen",
            "was being asked to reproduce a different session's list."]
    if len(winners) > 1:
        return "NOT ESTABLISHED", [
            f"{len(winners)} offsets clear both conditions "
            f"({', '.join('%+d' % w['offset'] for w in winners)}).",
            "More than one shift cannot be the right one. This is the",
            "signature of watchlists carrying names across sessions, which",
            "makes several offsets score well and none of them explanatory."]
    return "NOT ESTABLISHED", [
        "No offset beats offset 0 by the pre-registered margin on every",
        "session. The date is not the defect, and the CHANGE failures",
        f"`screen_miss` found have another cause. Offset 0 pools "
        f"{base['rate']:.0%}."]


def render(rows: list[dict], skipped: list[dict], live: dict[date, set[str]],
           elapsed: float) -> list[str]:
    L = ["IS THE LIVE WATCHLIST ONE SESSION OUT?", "",
         f"  {len(live)} automated watchlist(s), "
         f"{sum(len(v) for v in live.values())} live name(s)",
         f"  offsets tested: {', '.join('%+d' % o for o in OFFSETS)} "
         "(trading sessions, never calendar days)",
         f"  a lag is claimed only on a pooled gain of >= {MATERIAL:.0%} AND a "
         "gain on EVERY session",
         f"  elapsed {elapsed:.1f}s", ""]

    L += ["POOLED", "",
          f"  {'offset':>8}{'found':>8}{'of':>7}{'rate':>9}{'sessions':>11}   "]
    base = next((r for r in rows if r["offset"] == 0), None)
    base_days = {p["file_date"] for p in base["per"]} if base else set()
    for r in rows:
        same = ({p["file_date"] for p in r["per"]} == base_days)
        note = "" if same else "   NOT the same sessions as offset 0"
        mark = "  <- as shipped" if r["offset"] == 0 else ""
        L.append(f"  {r['offset']:>+8}{r['k']:>8}{r['n']:>7}"
                 f"{acct(r['rate'] * 100, 8)}%{r['sessions']:>11}{mark}{note}")

    L += ["", "PER SESSION", "",
          f"  {'file date':<13}" + "".join(f"{'%+d' % o:>10}" for o in OFFSETS)]
    for day in sorted(live):
        cells = []
        for o in OFFSETS:
            r = next(x for x in rows if x["offset"] == o)
            p = next((p for p in r["per"] if p["file_date"] == day), None)
            cells.append(f"{p['k']}/{p['n']:<4}".rjust(10) if p
                         else f"{'-':>10}")
        L.append(f"  {day.isoformat():<13}" + "".join(cells))
    L += ["", "  A dash is an offset with no universe on that side of the",
          "  archive, NOT a zero. Scoring it as 0 would manufacture a lag."]

    v, why = verdict(rows)
    L += ["", "VERDICT", "", f"  {v}", ""]
    L += [f"  {w}" for w in why]

    if skipped:
        L += ["", "EXCLUDED", ""]
        for s in skipped:
            n = f" ({s['n']} names)" if "n" in s else ""
            L.append(f"  {s['file']}{n}: {s['why']}")

    L += ["", "WHAT THIS IS NOT", "",
          "  Not a claim about which file is wrong. A lag here says the list",
          "  and the universe disagree by a session; whether the archiving",
          "  stamp or the simulation's session date is the wrong one is a",
          "  separate question this cannot answer.",
          "",
          "  Not a re-validation. If a lag is found, `screen_validate` must be",
          "  re-run against the corrected pairing before its 58% -- or any",
          "  replacement for it -- means anything.",
          "",
          "  Not a licence to shift and re-score until agreement improves. The",
          "  conditions above were registered before the first run; a later",
          "  run that widens them is a different measurement and must say so."]
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--watchlists", default="var/archive")
    p.add_argument("--pairs", default="var/state/screen_pairs_pit.json")
    p.add_argument("--out", default="var/reports/screen_lag.txt")
    return p


def main(argv=None) -> int:
    import time
    a = build_parser().parse_args(argv)
    t0 = time.time()

    sim = load_sim(Path(a.pairs))
    sessions = sessions_of(sim)
    live, skipped = live_lists(Path(a.watchlists))
    if not live:
        sys.exit("no automated watchlist to score -- run "
                 "`python -m common.screen_validate` and read the EXCLUDED "
                 "section.")

    rows = [score(live, sim, sessions, o) for o in OFFSETS]
    emit("\n".join(render(rows, skipped, live, time.time() - t0)), a.out,
         header="common.screen_lag")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
