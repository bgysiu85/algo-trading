#!/usr/bin/env python3
"""H0 on the point-in-time universe — the measurement the whole thing is for.

    python -m common.pit_h0

THE QUESTION, AND IT IS THE ONE BLOCKING EVERYTHING
-----------------------------------------------------
`premarket_hypotheses_results_20260908.md` §3 measured H0 -- "buy the screen at
04:30 and hold" -- two ways and got two answers that bracket zero without
locating it:

    stage-2 survivors   +$4.72/trade    the universe chosen with the whole day known
    stage-2 rejects     -$9.81/trade    what buying the screen looks like without that

Land near +$4.72 and the screen was doing the work. Land near -$9.81 and the
+$4.72 was the leak -- and with it every P/L figure this project has produced,
because every backtest here was handed a universe selected on the session's own
daily bar.

`screen_sim` built the third universe: the names the live screen would actually
have surfaced, when it would have surfaced them. This runs H0 on it.

TWO VARIANTS, AND THE DIFFERENCE BETWEEN THEM IS ITSELF THE ANSWER
-------------------------------------------------------------------
The original H0 buys at 04:30. On a point-in-time universe most names are not
on the watchlist yet at 04:30, so "buy at 04:30" and "buy the screen" stop being
the same sentence. Both readings are run, because they answer different things:

  **KNOWABLE AT 04:30** -- only names with `first_seen <= 04:30`, bought at
  04:30. The ENTRY TIME IS HELD FIXED and only the universe changes, so this is
  the strict like-for-like against +$4.72. It is the comparison the scope asks
  for.

  **AS SCREENED** -- every name, bought at `max(04:30, first_seen)`. This is
  what could actually have been traded: the live feed surfaces a name at 06:10
  and you buy it at 06:10. It is not comparable to +$4.72 -- the entry time
  moved -- but it is the only one of the two that describes a tradeable rule.

The gap between them prices what the late qualifiers are worth. If KNOWABLE is
near +$4.72 and AS SCREENED is much worse, the screen's early names carry it and
the feed's re-ranking is destroying value; if the reverse, the 04:30 snapshot
was never the right moment to look.

WHAT WOULD MAKE THIS WRONG
--------------------------
**Entering before `first_seen`.** The floor is `max(ENTRY_FROM, first_seen)`
inside `hypotheses.signal_h0`, and `max` is what stops a floor from ever moving
an entry EARLIER than the registered 04:30. A test asserts no trade in either
variant starts before its symbol's own first_seen.

**Reading the wrong bars.** The universe came from the 04:00-09:30 window
slices and this reads the same files, so a name cannot be screened from one tape
and traded on another.

**Quoting one friction number.** Every figure is reported at $1.00, $4.26 and
$8.92 per round trip, per `friction_reconciliation_20260911.md` §5 item 3. The
$4.26 the project charges is an n=2 measurement of a superseded exit mechanic
and the live mean is roughly twice it.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from dataclasses import asdict
from datetime import date as _date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from common.harness import run_session
from common.report_io import emit
from strategy.premkt import hypotheses as H

ET = ZoneInfo("America/New_York")

# The two published brackets this is measured against.
BRACKET_SURVIVORS = 4.72
BRACKET_REJECTS = -9.81

# Per friction_reconciliation_20260911.md: the well-measured crossing cost, the
# figure every backtest charges, and the live end-to-end observation.
FRICTIONS = (("$1.00", 1.00), ("$4.26", 4.26), ("$8.92", 8.92))

DROP = 5


def load_pit(path: Path) -> dict[str, list[dict]]:
    rows = json.loads(Path(path).read_text())
    if not rows:
        sys.exit(f"{path} is empty -- run `python -m common.screen_sim` first")
    by_date: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_date[r["date"]].append(r)
    return dict(by_date)


def first_seen_time(rec: dict):
    """`first_seen` as an ET time-of-day, which is what the signal floor takes."""
    return pd.Timestamp(rec["first_seen"]).tz_convert(ET).time()


def run_day(bars: pd.DataFrame, day: str, universe: list[dict], *,
            as_screened: bool, trail: float) -> list[dict]:
    """H0 over one session's point-in-time universe."""
    rules = H.rules(trail)
    d = _date.fromisoformat(day)
    out: list[dict] = []
    for rec in universe:
        floor = first_seen_time(rec)
        if not as_screened and floor > H.ENTRY_FROM:
            # KNOWABLE AT 04:30: the name was not on the watchlist yet, so it
            # is not in this variant's universe at all. Skipped rather than
            # entered late, because the point of this variant is to hold the
            # ENTRY TIME fixed and vary only the universe.
            continue
        df = bars[bars["symbol"] == rec["symbol"]]
        if df.empty:
            continue
        sig = H.signal_h0(df, d, ET, not_before=floor if as_screened else None)
        for t in run_session(sig, d, ET, rules, symbol=rec["symbol"],
                             entry_shares=H.ENTRY_SHARES):
            row = asdict(t)
            row.update(symbol=rec["symbol"], date=day,
                       first_seen=rec["first_seen"],
                       first_rank=rec["first_rank"])
            out.append(row)
    return out


def score(trades: list[dict], split: str, friction: float) -> dict:
    real = [t["net"] - friction for t in trades]
    if not real:
        return {"n": 0, "net": 0.0, "per": 0.0, "win": 0.0, "dropped": 0.0,
                "early": 0.0, "late": 0.0, "ne": 0, "nl": 0, "syms": 0}
    e = [r for t, r in zip(trades, real) if t["date"] < split]
    l = [r for t, r in zip(trades, real) if t["date"] >= split]
    by_sym: dict[str, float] = defaultdict(float)
    for t, r in zip(trades, real):
        by_sym[t["symbol"]] += r
    worst_removed = sum(sorted(by_sym.values(), reverse=True)[:DROP])
    net = sum(real)
    # `syms` exists so a caller can tell a real drop-top-5 from a degenerate
    # one. With DROP or fewer distinct symbols the drop removes EVERYTHING and
    # the column prints exactly 0.00 -- which is indistinguishable from a
    # result whose top names happened to cancel out. Callers that render the
    # column must say "n/a" rather than print that zero.
    return {"n": len(real), "net": net, "per": net / len(real),
            "win": 100.0 * sum(1 for r in real if r > 0) / len(real),
            "dropped": net - worst_removed,
            "early": (sum(e) / len(e)) if e else 0.0,
            "late": (sum(l) / len(l)) if l else 0.0,
            "ne": len(e), "nl": len(l), "syms": len(by_sym)}


def halves_split(dates) -> str:
    ds = sorted(set(dates))
    return ds[len(ds) // 2] if ds else ""


def render(res: dict, n_sessions: int, n_universe: int, split: str,
           trail: float, elapsed: float) -> list[str]:
    L = ["H0 ON THE POINT-IN-TIME UNIVERSE", "",
         f"  {n_sessions} sessions, {n_universe:,} screened symbol-days",
         f"  H0 as registered: one entry per symbol-session, {trail:g}% trail "
         f"from the peak, flat at 09:30, {H.ENTRY_SHARES} shares",
         f"  halves split at {split} (derived)",
         f"  elapsed {elapsed:.1f}s", "",
         "  THE BRACKETS THIS IS MEASURED AGAINST, at $4.26 friction:",
         f"    stage-2 survivors (whole day known)   {BRACKET_SURVIVORS:+.2f}/trade",
         f"    stage-2 rejects                       {BRACKET_REJECTS:+.2f}/trade",
         ""]

    for label, trades in (("KNOWABLE AT 04:30", res["knowable"]),
                          ("AS SCREENED", res["as_screened"])):
        note = ("entry time held FIXED at 04:30, only the universe changes -- "
                "the like-for-like"
                if label.startswith("KNOWABLE")
                else "bought at max(04:30, first_seen) -- the tradeable rule, "
                     "NOT comparable to the brackets")
        L += [f"{label}", "", f"  {note}", "",
              f"  {'friction':<10}{'trades':>8}{'net':>12}{'per':>9}"
              f"{'win%':>7}{'drop-top-5':>12}{'early':>9}{'late':>9}"]
        for fl, fv in FRICTIONS:
            s = score(trades, split, fv)
            drop = (f"${s['dropped']:>11,.0f}" if s["syms"] > DROP
                    else f"{'n/a':>12}")
            L.append(f"  {fl:<10}{s['n']:>8}${s['net']:>11,.0f}"
                     f"${s['per']:>8.2f}{s['win']:>6.1f}%{drop}"
                     f"${s['early']:>8.2f}${s['late']:>8.2f}")
        L.append("")

    k = score(res["knowable"], split, 4.26)
    a = score(res["as_screened"], split, 4.26)
    if not k["n"]:
        return L + ["NO VERDICT", "",
                    "  No name was on the watchlist by 04:30 in any session.",
                    "  That is itself the finding: the live screen does not",
                    "  surface this universe at the time every backtest here",
                    "  assumed it did. Read the first_seen histogram in",
                    "  var/reports/screen_sim.txt before anything else.", ""]

    L += ["WHERE THE LIKE-FOR-LIKE LANDS", "",
          f"  KNOWABLE AT 04:30, at $4.26   {k['per']:+.2f}/trade over "
          f"{k['n']:,} trades",
          f"  survivors  {BRACKET_SURVIVORS:+.2f}   rejects "
          f"{BRACKET_REJECTS:+.2f}", ""]
    span = BRACKET_SURVIVORS - BRACKET_REJECTS
    pos = (k["per"] - BRACKET_REJECTS) / span if span else 0.0
    L.append(f"  It sits {pos:.0%} of the way from the rejects to the survivors.")
    L.append("")
    if k["per"] >= BRACKET_SURVIVORS - 1.0:
        L += ["  THE SCREEN WAS DOING THE WORK. The +$4.72 survives a universe",
              "  built from what was knowable at 04:30, so stage 2's look-ahead",
              "  was not what produced it.", ""]
    elif k["per"] <= BRACKET_REJECTS + 1.0:
        L += ["  THE +$4.72 WAS THE LEAK. On the honest universe H0 lands with",
              "  the rejects, which means the universe -- not the rule -- was",
              "  the edge, and every P/L figure in this project that was",
              "  measured on a stage-2 universe is overstated by about the",
              "  width of that bracket.", ""]
    else:
        L += ["  BETWEEN THE BRACKETS. Part of the +$4.72 was the screen and",
              "  part was the look-ahead, and the split is the number above.",
              "  Neither published figure should be quoted alone again.", ""]

    if k["n"] and a["n"]:
        L += ["WHAT THE LATE QUALIFIERS ARE WORTH", "",
              f"  AS SCREENED  {a['per']:+.2f}/trade over {a['n']:,}",
              f"  KNOWABLE     {k['per']:+.2f}/trade over {k['n']:,}",
              f"  difference   {a['per'] - k['per']:+.2f}", "",
              "  A name the feed surfaces at 06:10 is bought at 06:10. If AS",
              "  SCREENED is much worse, the early names carry the result and",
              "  the re-ranking through the session is destroying value; if it",
              "  is better, 04:30 was never the right moment to look.", ""]

    L += ["SIGN STABILITY ACROSS THE FRICTION RANGE", ""]
    for label, trades in (("KNOWABLE", res["knowable"]),
                          ("AS SCREENED", res["as_screened"])):
        signs = {(" + " if score(trades, split, fv)["net"] > 0 else " - ")
                 for _, fv in FRICTIONS}
        L.append(f"  {label:<14}{'STABLE' if len(signs) == 1 else 'FLIPS'} "
                 f"across $1.00-$8.92")
    L += ["",
          "  A figure quoted at $4.26 without this note is quoting an n=2",
          "  measurement of a superseded exit mechanic as though it were a",
          "  constant (`friction_reconciliation_20260911.md` §6).", ""]

    L += ["WHAT THIS IS NOT", "",
          "  Not out of sample. `holdout.json` was cut over the SCREENED",
          "  universe on 2026-09-07 and is clean for a screen built after it --",
          "  `screener_simulation_scope.md` §5 says so and says it should not",
          "  be spent on anything else first. It has NOT been spent here.",
          "",
          "  Not TradingView's data. The universe reproduces their columns from",
          "  one Databento dataset at a measured 55.2% capture.",
          "",
          "  Not a strategy result. H0 is the control every entry rule is read",
          "  against, and on the old universe every one of them made it worse."]
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--pairs", default="var/state/screen_pairs_pit.json")
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default="XNAS.BASIC")
    p.add_argument("--trail", type=float, default=H.TRAIL_PRIMARY)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--out", default="var/reports/pit_h0.txt")
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    from common.databento_fetch import default_archive
    from common.dbn_io import read_dbn
    from common.screen_sim import window_slices, date_of

    archive = Path(a.archive) if a.archive else default_archive()
    by_date = load_pit(Path(a.pairs))
    slices = {date_of(p): p for p in window_slices(archive, a.dataset)}

    t0 = time.time()
    res = {"knowable": [], "as_screened": []}
    days = sorted(by_date)
    if a.limit:
        days = days[:a.limit]
    n_universe = 0
    for i, day in enumerate(days, 1):
        path = slices.get(day)
        if path is None:
            continue
        try:
            bars = read_dbn(path)
        except Exception as e:                              # noqa: BLE001
            print(f"  {day}: unreadable ({type(e).__name__}: {e})")
            continue
        if bars.empty:
            continue
        uni = by_date[day]
        n_universe += len(uni)
        res["knowable"] += run_day(bars, day, uni, as_screened=False,
                                   trail=a.trail)
        res["as_screened"] += run_day(bars, day, uni, as_screened=True,
                                      trail=a.trail)
        if i % 25 == 0:
            print(f"  {i}/{len(days)}  {day}  "
                  f"{len(res['as_screened']):,} trades")

    split = halves_split([t["date"] for t in res["as_screened"]])
    emit("\n".join(render(res, len(days), n_universe, split, a.trail,
                          time.time() - t0)),
         a.out, header=f"common.pit_h0  pairs={a.pairs}  trail={a.trail:g}"
                       + (f"  LIMIT {a.limit}" if a.limit else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
