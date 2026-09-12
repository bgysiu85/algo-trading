#!/usr/bin/env python3
"""What were the bars MCL refused actually worth?

    python -m common.refused_value
    python -m common.refused_value --population locked

THE QUESTION, AND WHY IT COMES BEFORE A RULE CHANGE
-----------------------------------------------------
`volume_interlock` counted the refusals: on 372 symbol-days, 2,102 bars where
every condition but `c_floor` approved, and 1,162 of those with the
follow-through locked out behind them -- 3.12 per session, on 76% of sessions.

That is a FREQUENCY. It says the interlock binds often; it says nothing about
whether the bars it refused were worth taking. The obvious next move is to
build a relaxed variant and sweep it, and that is the wrong order: a variant
changes the rule, and every mechanic change measured in this project has lost
money. **Price the refused bars first.** If they are worth less than nothing,
no variant needs writing and the line of enquiry ends here.

HOW IT IS PRICED, AND THE ONE THING THAT MAKES IT HONEST
----------------------------------------------------------
Each refused bar is entered at its close and exited by MCL'S OWN EXIT -- the
same trailing stop, the same forced flatten at the window, the same commission
model -- by handing `backtest_session` an `entry_bars` mask that REPLACES the
rule's entry signal. Nothing about the exit is re-implemented here. A second
implementation of the exit written next to the question is how the live path
and the backtest drifted apart for three days.

THE CONTROL
-----------
A number like "-$3.10 a trade" means nothing alone. The same machinery is run
over the SAME symbol-days with the rule's own entries, so the refused
population is read against what MCL actually takes rather than against zero.

PER TRADE FIRST, AND WHY THE CAP DOES NOT GET A VOTE YET
-----------------------------------------------------------
These trades did not happen, and the largest reason they could not all have
happened is the concurrency cap: live, 29% of buy attempts were refused by it,
and the book holds two or three names at once. So a TOTAL over 1,162 refused
entries is an upper bound on a quantity nobody could have collected.

Per-trade expectancy is not subject to that. If it is negative, adding these
bars loses money at ANY scale and the cap is irrelevant. Only if it is
positive does the cap decide how much of it was reachable -- and that is a
different measurement, stated as such rather than folded in.

So the report leads with per trade, at all three friction levels, with
drop-top-5 and a both-halves split, and refuses a verdict when the halves
disagree.
"""
from __future__ import annotations

import argparse
import statistics
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from common.report_fmt import acct
from common.report_io import emit

ET = ZoneInfo("America/New_York")

# The friction levels every P/L figure in this project is quoted at.
FRICTIONS = (1.00, 4.26, 8.92)
DROP = 5


def refused_mask(sig: pd.DataFrame, population: str) -> pd.Series:
    """Which bars to price, as a per-bar boolean over `sig`'s index.

    Both populations require the three NON-volume conditions to have approved
    the bar, so every one of them is a bar that would have entered but for a
    single volume rule. A population that did not require that would include
    bars MACD had already rejected -- bars no volume change could have saved.
    """
    others = sig["c_macd"] & sig["c_mfi"] & sig["c_rsi"]
    warm = sig["trail_avg"].notna() & (sig["trail_avg"] > 0)
    base = others & warm
    floor_sole = base & sig["c_vol"] & ~sig["c_floor"]
    if population == "floor_sole":
        return floor_sole
    if population == "locked":
        vol_sole = base & ~sig["c_vol"] & sig["c_floor"]
        return floor_sole & vol_sole.shift(-1, fill_value=False)
    raise ValueError(f"unknown population {population!r}")


def price(trades, friction: float) -> dict:
    """Net of the stated friction, per round trip."""
    nets = [t.net - friction for t in trades]
    if not nets:
        return {"n": 0, "net": 0.0, "per": float("nan"), "win": float("nan"),
                "drop": float("nan")}
    kept = sorted(nets)[:-DROP] if len(nets) > DROP else None
    return {
        "n": len(nets),
        "net": sum(nets),
        "per": sum(nets) / len(nets),
        "win": sum(1 for x in nets if x > 0) / len(nets) * 100.0,
        # n/a, never $0: with DROP or fewer trades there is nothing to drop
        # to, and printing 0 would read as "dropping the best five costs
        # nothing" instead of "this was not computed".
        "drop": (sum(kept) / len(kept)) if kept else float("nan"),
    }


def halves(rows: list[dict]) -> tuple[list, list]:
    """Split by DATE at the median, derived from the data rather than chosen."""
    dates = sorted({r["date"] for r in rows})
    if len(dates) < 2:
        return rows, []
    cut = dates[len(dates) // 2]
    return ([r for r in rows if r["date"] < cut],
            [r for r in rows if r["date"] >= cut])


def render(refused: list[dict], control: list[dict], population: str,
           pairs_path: str, n_sd: int, skipped: int, elapsed: float) -> list[str]:
    L = ["WHAT WERE THE REFUSED BARS WORTH?", "",
         f"  population: {population}",
         f"  {n_sd:,} symbol-day(s) from {pairs_path}",
         "  entered at the refused bar's close, exited by MCL's OWN exit",
         "  (same trail, same forced flatten, same commission model)",
         f"  elapsed {elapsed:.1f}s", ""]
    if skipped:
        L += [f"  {skipped:,} symbol-day(s) NOT tested: no cached bars, or "
              "too short for full warm-up", ""]

    if not refused:
        return L + [
            "NO REFUSED BAR PRICED", "",
            "  The population is empty on these symbol-days. That is a",
            "  statement about this pairs file, not about the interlock.", ""]

    L += ["PER TRADE  (the cap does not affect this figure)", "",
          f"  {'friction':>10}{'n':>8}{'net':>12}{'per trade':>12}"
          f"{'win%':>8}{'drop-top-5':>12}   "]
    for f in FRICTIONS:
        r = price([t for row in refused for t in row["trades"]], f)
        c = price([t for row in control for t in row["trades"]], f)
        d = r["drop"]
        L.append(f"  REFUSED{f:>7.2f}{r['n']:>8,}{acct(r['net'], 12)}"
                 f"{acct(r['per'], 12)}{r['win']:>7.1f}%"
                 + (acct(d, 12) if d == d else f"{'n/a':>12}"))
        L.append(f"  control{f:>7.2f}{c['n']:>8,}{acct(c['net'], 12)}"
                 f"{acct(c['per'], 12)}{c['win']:>7.1f}%"
                 + (acct(c['drop'], 12) if c['drop'] == c['drop']
                    else f"{'n/a':>12}") + "   <- MCL's own entries")
        L.append("")

    # The decision is made at the measured friction, on the per-trade figure.
    r = price([t for row in refused for t in row["trades"]], 4.26)
    c = price([t for row in control for t in row["trades"]], 4.26)

    a, b = halves(refused)
    ha = price([t for row in a for t in row["trades"]], 4.26)
    hb = price([t for row in b for t in row["trades"]], 4.26)
    L += ["BOTH HALVES, at $4.26  (split by date at the median)", "",
          f"  {'early':<10}{ha['n']:>8,}{acct(ha['per'], 12)} per trade",
          f"  {'late':<10}{hb['n']:>8,}{acct(hb['per'], 12)} per trade", ""]
    agree = (ha["per"] > 0) == (hb["per"] > 0) if hb["n"] else None

    L += ["VERDICT", ""]
    # THE HALVES ARE CHECKED FIRST, WHATEVER THE SIGN.
    #
    # The first version tested `per < 0` before the split, so any pooled
    # negative short-circuited into "settled" -- and `locked` pooled at
    # (0.06) with halves of (3.39) and +2.70. A figure that small, with the
    # halves disagreeing in sign, is not a settled loss; it is an unstable
    # measurement that happened to land a few cents below zero. The standing
    # evidence rule says a split disagreement refuses a verdict, and putting
    # the sign test first quietly exempted every negative result from it.
    if agree is False:
        L += ["  NO VERDICT. The two halves disagree in sign "
              f"({acct(ha['per'], 1).strip()} early, "
              f"{acct(hb['per'], 1).strip()} late), so the per-trade figure is",
              "  not stable over the period. The pooled number "
              f"({acct(r['per'], 1).strip()}) is an",
              "  artefact of when the sample was drawn, in either direction.",
              "",
              "  This is a REFUSAL, not a negative result. It does not clear",
              "  the mechanic and it does not condemn it.", ""]
    elif r["per"] < 0:
        L += [f"  The refused bars LOSE {acct(r['per'], 1).strip()} a trade at "
              "$4.26.", "",
              "  That settles it without the concurrency cap being consulted:",
              "  a population with negative expectancy loses money at any",
              "  scale, so how many of them could have been taken does not",
              "  matter. No variant needs writing, and `c_floor` is doing a",
              "  job rather than costing one.", ""]
        if r["per"] < c["per"]:
            L += ["  They are also WORSE than MCL's own entries "
                  f"({acct(c['per'], 1).strip()}), so the rule is not merely",
                  "  declining average bars -- it is declining bad ones.", ""]
    else:
        L += [f"  The refused bars make {acct(r['per'], 1).strip()} a trade at "
              f"$4.26, against MCL's {acct(c['per'], 1).strip()}.", "",
              "  This is the ONLY branch where the concurrency cap matters,",
              "  and it now decides everything: the book holds two or three",
              "  names, live it refused 29% of buy attempts, and these",
              "  entries would have competed with the rule's own. The total",
              "  above is an upper bound on a quantity nobody could have",
              "  collected. Measuring the reachable share is a separate",
              "  question and must not be folded into this one.", ""]

    L += ["WHAT THIS IS NOT", "",
          "  Not a backtest of a strategy. It prices bars the rule refused,",
          "  using the rule's exit. No rule was changed and no variant exists.",
          "",
          "  Not free of the cap. Every TOTAL here assumes each refused bar",
          "  could be taken independently. Per trade is the figure that",
          "  survives that assumption; the totals do not.",
          "",
          "  Not a claim about the market. Taking 1,162 more positions would",
          "  have moved fills, changed which names were held, and changed",
          "  what the cap refused next. None of that is modelled.",
          "",
          "  Not out of sample. These are the same symbol-days the interlock",
          "  census ran on, chosen because MCL traded them."]
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--pairs", default="var/state/traded_pairs.json")
    p.add_argument("--cache", default="bar_cache")
    p.add_argument("--population", default="floor_sole",
                   choices=["floor_sole", "locked"])
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--out", default=None)
    return p


def main(argv=None) -> int:
    import time
    a = build_parser().parse_args(argv)
    from common.cache_io import (BACKTEST_END_HHMM, BACKTEST_SESSIONS,
                                 SHARED_DURATION, SHARED_END_HHMM,
                                 check_sessions, load_cached_bars, load_pairs,
                                 slice_sessions, window_dir)
    from strategy.mcl import mcl as MCL

    pairs = load_pairs(Path(a.pairs))
    if a.limit:
        pairs = pairs[:a.limit]
    cache = window_dir(Path(a.cache), SHARED_DURATION, SHARED_END_HHMM)
    end_h, end_m = int(BACKTEST_END_HHMM[:2]), int(BACKTEST_END_HHMM[2:])

    t0 = time.time()
    refused, control, skipped = [], [], 0
    for p in pairs:
        bars = load_cached_bars(cache, p["symbol"], p["date"])
        if bars is None or bars.empty:
            skipped += 1
            continue
        bars.index = (bars.index.tz_localize("UTC") if bars.index.tz is None
                      else bars.index.tz_convert("UTC"))
        bars = bars.sort_index()
        day = datetime.strptime(p["date"], "%Y-%m-%d").date()
        want_end = datetime.combine(day, datetime.min.time()).replace(
            hour=end_h, minute=end_m, tzinfo=ET)
        if check_sessions(bars, want_end, BACKTEST_SESSIONS) < BACKTEST_SESSIONS:
            skipped += 1
            continue
        sl = slice_sessions(bars, want_end, BACKTEST_SESSIONS)
        if len(sl) < MCL.MIN_BARS_REQUIRED:
            skipped += 1
            continue

        mask = refused_mask(MCL.signals(sl), a.population)
        if mask.any():
            t = MCL.backtest_session(sl, day, ET, entry_bars=mask)
            if t:
                refused.append({"symbol": p["symbol"], "date": p["date"],
                                "trades": t})
        ct = MCL.backtest_session(sl, day, ET)
        if ct:
            control.append({"symbol": p["symbol"], "date": p["date"],
                            "trades": ct})

    if not refused and not control:
        sys.exit(f"no usable bars for any of {len(pairs)} symbol-day(s) under "
                 f"{cache}/")

    out = a.out or f"var/reports/refused_value_{a.population}.txt"
    emit("\n".join(render(refused, control, a.population, a.pairs,
                          len(refused), skipped, time.time() - t0)),
         out, header=f"common.refused_value  population={a.population}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
