#!/usr/bin/env python3
"""Fixed-cent stops against percentage stops, on our own tape.

    python -m common.cent_stop_study

THE DECISION, from claude/warrior_0_universe_and_risk.md §5.1
-------------------------------------------------------------
Every stop in this project is a percentage: MCL trails 5% from the peak. Every
stop Ross Cameron states is in cents:

    "I set a tight stop. I don't stop at the low of this pullback, that's too
     far. I use an arbitrary stop generally of 10 to 15 cents, because I don't
     want my average losers to be bigger than that."   -- V-SCALP 34:03

And he is explicit that the cap is calibrated to his own average loser rather
than to the chart -- he asserts a maximum loss and rejects setups whose
structure is wider, instead of deriving a stop from the market and accepting
what it costs.

Across a $2-20 band, 15c is 7.5% at $2 and 0.75% at $20. **A factor of ten.**
These are not two tunings of one rule; they are different rules, and Ben's own
handover names this the single largest decision in the Warrior set -- every
other parameter, targets and share count and the 2:1 ratio, scales from
whichever answer wins.

PINNED BEFORE RUNNING
---------------------
15c is the primary. It is what he says he uses most often, and it is chosen for
that reason rather than because it wins. 10c and 20c are reported as a BOUNDARY
CHECK -- the ends of his stated range -- and not as a menu: if the best cell
sits at an edge the range is in the wrong place and none of the three should be
adopted.

WHERE THE ANSWER LIVES, AND IT IS NOT THE HEADLINE
---------------------------------------------------
Because the cent stop is a fixed distance and the percentage stop is not, the
two diverge across the price band by construction. A single total hides that
completely: a cent stop can be near-identical at $3 and murderous at $18, and
the average of those two is a number describing nothing. So every figure here
is also broken out by entry price, and that table is the finding.

Controls: both halves at bar_cache's calendar midpoint, chosen once; and
drop-top-3 within each variant.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from common.analysis import LIVE, MEASURED_FRICTION, load_sessions
from common.report_io import emit
from strategy.mcl import mcl as MCL

ET = ZoneInfo("America/New_York")
SPLIT = "2026-03-20"
QTY = 100

PRIMARY_CENTS = 0.15                       # his stated most-used
BOUNDARY_CENTS = (0.10, 0.20)              # the ends of his stated range
PRICE_BUCKETS = (2.0, 4.0, 7.0, 12.0, 20.0)


def run(sessions, *, cents: float | None) -> list:
    """One variant over the whole cache. cents=None is MCL as it stands."""
    out = []
    for sym, d, df in sessions:
        try:
            out += [(sym, d, t) for t in MCL.backtest_session(
                df, datetime.strptime(d, "%Y-%m-%d").date(), ET,
                trail_cents=cents, entry_shares=QTY, **LIVE)]
        except Exception:                                   # noqa: BLE001
            # A session too short for the warm-up raises. Skipping it keeps
            # every variant over the SAME sessions, which is the only way the
            # differences mean anything.
            pass
    return out


def stats(trades, drop: int = 3) -> dict:
    real = [t.net - MEASURED_FRICTION for _, _, t in trades]
    if not real:
        return {"n": 0, "net": 0.0, "per": 0.0, "dropped": 0.0,
                "early": 0.0, "late": 0.0, "win": 0.0}
    net = sum(real)
    top = sorted(real, reverse=True)[:drop]
    return {
        "n": len(real), "net": net, "per": net / len(real),
        "dropped": net - sum(top),
        "win": 100.0 * sum(1 for r in real if r > 0) / len(real),
        "early": sum(r for (_, d, _), r in zip(trades, real) if d < SPLIT),
        "late": sum(r for (_, d, _), r in zip(trades, real) if d >= SPLIT),
    }


def by_price(trades) -> list[tuple[str, dict]]:
    """THE TABLE THAT MATTERS. A fixed distance and a percentage of price
    diverge across the band by construction, so a single total describes
    nothing."""
    out, lo = [], PRICE_BUCKETS[0]
    for hi in PRICE_BUCKETS[1:]:
        sel = [x for x in trades if lo <= x[2].entry_price < hi]
        if sel:
            out.append((f"${lo:g}-{hi:g}", stats(sel)))
        lo = hi
    return out


def equivalent_pct(cents: float) -> list[str]:
    """What the cent stop IS, as a percentage, at each end of the band. The
    whole argument in two numbers."""
    return [f"  {cents * 100:.0f}c is "
            + "   ".join(f"{100 * cents / p:.2f}% at ${p:g}"
                         for p in (2, 5, 10, 20))]


def render(variants: list[tuple[str, list]], n_sessions: int) -> list[str]:
    L = ["FIXED-CENT STOPS vs THE 5% TRAIL", "",
         f"  {n_sessions} cached sessions, MCL live config, {QTY} shares flat",
         f"  net after tiered commission and ${MEASURED_FRICTION}/RT friction",
         f"  halves split at {SPLIT}. Drop-top-3 within each variant.", "",
         f"  {PRIMARY_CENTS * 100:.0f}c is PINNED as the primary — his stated "
         "most-used value, chosen",
         "  before running and not because it won. 10c and 20c are a boundary",
         "  check on the ends of his range, not a menu.", ""]
    L += equivalent_pct(PRIMARY_CENTS) + [""]

    head = (f"  {'variant':<16}{'trades':>7}{'net':>10}{'per':>8}{'win%':>7}"
            f"{'drop top 3':>12}{'early':>10}{'late':>10}")
    L += [head]
    rows = [(name, stats(tr)) for name, tr in variants]
    for name, s in rows:
        L.append(f"  {name:<16}{s['n']:>7}${s['net']:>9,.0f}${s['per']:>7.2f}"
                 f"{s['win']:>6.1f}%${s['dropped']:>11,.0f}"
                 f"${s['early']:>9,.0f}${s['late']:>9,.0f}")
    L.append("")

    base = dict(rows).get("5% trail")
    prim = dict(rows).get(f"{PRIMARY_CENTS * 100:.0f}c stop")

    L += ["BY ENTRY PRICE — where a fixed distance and a percentage diverge", ""]
    for name, tr in variants:
        buckets = by_price(tr)
        if not buckets:
            continue
        L.append(f"  {name}")
        L.append(f"      {'band':<12}{'n':>6}{'net':>10}{'per':>9}{'win%':>7}")
        for label, s in buckets:
            L.append(f"      {label:<12}{s['n']:>6}${s['net']:>9,.0f}"
                     f"${s['per']:>8.2f}{s['win']:>6.1f}%")
        L.append("")

    if base and prim and base["n"] and prim["n"]:
        d = prim["net"] - base["net"]
        de = prim["early"] - base["early"]
        dl = prim["late"] - base["late"]
        L += [f"VERDICT on {PRIMARY_CENTS * 100:.0f}c against the 5% trail", "",
              f"  net {d:+,.0f}   early {de:+,.0f}   late {dl:+,.0f}",
              f"  win rate {prim['win']:.1f}% vs {base['win']:.1f}%",
              f"  trades   {prim['n']} vs {base['n']}", ""]
        if de * dl < 0:
            L += ["  THE SIGN FLIPS BETWEEN HALVES. Not a stable effect,",
                  "  whatever the total says.", ""]
        elif d > 0 and prim["dropped"] > base["dropped"]:
            L += ["  The cent stop wins on the total AND on drop-top-3, in",
                  "  both halves. That is the strongest form this project's",
                  "  standards allow from an in-sample run — and it is still",
                  "  in-sample: MCL was fitted on these very sessions.", ""]
        elif d > 0:
            L += ["  Better on the total but NOT after drop-top-3, so a",
                  "  handful of trades are the result. Not adoptable.", ""]
        else:
            L += ["  The cent stop is WORSE. The percentage trail stays, and",
                  "  the rest of the Warrior set — targets, share count, the",
                  "  2:1 ratio, all of which scale from the stop — has to be",
                  "  read against a percentage stop rather than his.", ""]

    edges = [(n, s) for n, s in rows if n != "5% trail"]
    if len(edges) >= 3:
        best = max(edges, key=lambda kv: kv[1]["net"])
        if best[0] in (f"{BOUNDARY_CENTS[0] * 100:.0f}c stop",
                       f"{BOUNDARY_CENTS[1] * 100:.0f}c stop"):
            L += [f"  BOUNDARY CHECK FAILED: {best[0]} is the best cell and it",
                  "  sits at an edge of his stated range, so the range is in",
                  "  the wrong place and none of the three should be adopted.",
                  ""]

    L += ["WHAT THIS IS NOT", "",
          "  It is not his stop. His is min(pullback low, 10-20c) — a",
          "  structure stop with a cents CAP, and it does not trail. This",
          "  swaps one variable in MCL's trailing stop and holds everything",
          "  else, which is the only way to attribute the difference to",
          "  cents-versus-percent rather than to four changes at once.",
          "",
          "  Nothing here is out of sample. MCL's parameters were fitted on",
          "  these sessions, so a cent stop that wins has not been shown to",
          "  generalise — only to beat a rule that was tuned here."]
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--cache", default="bar_cache")
    p.add_argument("--out", default="var/reports/cent_stop.txt")
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    sessions = load_sessions(Path(a.cache))
    variants = [("5% trail", run(sessions, cents=None))]
    for c in sorted({PRIMARY_CENTS, *BOUNDARY_CENTS}):
        variants.append((f"{c * 100:.0f}c stop", run(sessions, cents=c)))
    emit("\n".join(render(variants, len(sessions))), a.out,
         header=f"common.cent_stop_study  cache={a.cache}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
