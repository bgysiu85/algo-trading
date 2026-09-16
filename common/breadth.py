#!/usr/bin/env python3
"""Go/no-go criterion 2, replaced — and the measurement that retires the old one.

    python -m common.breadth --list-runs
    python -m common.breadth --run-id <RUN>
    python -m common.breadth --csv var/reports/backtest_trades_mc5.csv

REGISTERED FIRST
----------------
`docs/research/REGISTERED_breadth.md`, commit `4bfaa88`, written before this
file existed and before ORB produced any number. Read it before reading any
output here. Nothing in this module chooses a threshold; it applies the ones
registered there.

WHY THE OLD CRITERION COULD NOT BE RE-ESTIMATED
------------------------------------------------
`orb_strategy_spec.md` §11 criterion 2 was "a majority of symbols with >= 1
trade are profitable". §11.1 recorded that it moves with trades per symbol --
1.7 a symbol for VW9's Setup B against 4.1 for MC5.

The second confound is the one that decides the design. **With right-skewed
payoffs most symbols are negative at a genuinely positive expectancy.** A 27%
trade win rate and a long right tail leaves most symbols underwater because of
the payoff shape, not because the edge is narrow.

So the obvious repair does not work. "Median across symbols of per-symbol mean
net >= 0" reads like a sample-size-independent restatement and is THE SAME
TEST: a median is non-negative exactly when half the symbols are profitable.
It would have changed the wording and nothing else.

WHAT REPLACES IT
----------------
A SYMBOL-CLUSTER BOOTSTRAP. Symbols drawn with replacement, every trade
belonging to a drawn symbol coming with it. Two conditions, because a large
enough sample makes the first easy on its own:

    total net > 0 in at least 95% of resamples

ONE condition. A second was registered and withdrawn before ORB had a number:
a floor on the 2.5th percentile of per-trade net cannot fail independently,
because per_trade = total / count shares the sign of total in every resample.
The magnitude question belongs to criterion 3, at $1.00 a trade.

Symbols, not symbol-days and not trades: two sessions on the same ticker are
not independent draws.

AND RETIRING THE OLD ONE IS A MEASUREMENT
------------------------------------------
Trade nets are permuted across symbol labels with each symbol's trade COUNT
HELD FIXED. That is the distribution "share of symbols profitable" takes when
there is no symbol-specific effect at all -- only skew and trade count. If the
observed share sits inside it, the old criterion carried no information about
breadth on this sample and its retirement is evidenced rather than argued.

If it sits OUTSIDE, the registration says the old criterion was measuring
something real, the replacement is adopted in addition, and the original is
kept. This module prints that verdict rather than assuming the convenient one.
"""
from __future__ import annotations

import argparse
import csv
import random
import statistics
import sys
from pathlib import Path

from common.report_io import emit

# Every one of these is fixed in REGISTERED_breadth.md §3.1. They are here as
# constants so a reader can check the code against the registration, and they
# are not CLI flags: a threshold that can be passed in on the command line is a
# threshold that gets swept.
RESAMPLES = 2000
SEED = 20260916
BOOT_MIN_P = 0.95          # share of resamples with total net > 0
# There is no second pass condition. One was registered -- a floor on the
# 2.5th percentile of per-trade net -- and withdrawn before ORB had a number,
# because per_trade = total / count carries the SAME SIGN as total in every
# resample, so that floor was this bar at a stricter level rather than a
# magnitude check. The magnitude question is criterion 3's, at $1.00 a trade.
# See the amendment in REGISTERED_breadth.md.
# The old criterion, kept only so it can be printed beside its own null.
OLD_MAJORITY = 0.50
BUCKETS = ((1, 1, "1"), (2, 2, "2"), (3, 5, "3-5"), (6, 10, "6-10"),
           (11, 10 ** 9, "11+"))


# ------------------------------------------------------------------ loading
def load_csv(path: Path) -> list[dict]:
    rows = []
    for r in csv.DictReader(Path(path).open(encoding="utf-8-sig")):
        sym, net = r.get("symbol"), r.get("net")
        if not sym or net in (None, ""):
            continue
        rows.append({"symbol": sym.strip().upper(), "net": float(net)})
    return rows


def load_db(run_id: str) -> list[dict]:
    """The trades of one backtest run, from the database.

    The CSVs in var/reports hold a few hundred trades; the screened
    out-of-sample runs this criterion was written about hold thousands and
    live only in `backtest_trade`. A criterion that could only be applied to
    the small copy would be a criterion about the small copy.
    """
    from sqlalchemy import select

    from common import db as D

    eng = D.engine()
    t = D.backtest_trade
    with eng.connect() as c:
        got = c.execute(
            select(t.c.symbol, t.c.net).where(t.c.run_id == run_id)).all()
    return [{"symbol": str(s).strip().upper(), "net": float(n)}
            for s, n in got if s is not None and n is not None]


def list_runs() -> list[tuple]:
    from sqlalchemy import func, select

    from common import db as D

    eng = D.engine()
    t = D.backtest_trade
    with eng.connect() as c:
        return c.execute(
            select(t.c.run_id,
                   func.count().label("n"),
                   func.count(func.distinct(t.c.symbol)).label("syms"),
                   func.sum(t.c.net).label("net"))
            .group_by(t.c.run_id).order_by(func.count().desc())).all()


def by_symbol(rows: list[dict]) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}
    for r in rows:
        out.setdefault(r["symbol"], []).append(r["net"])
    return out


# --------------------------------------------------------------- the tests
def cluster_bootstrap(by_sym: dict[str, list[float]], resamples: int = RESAMPLES,
                      seed: int = SEED) -> dict:
    """Resample SYMBOLS with replacement; every trade of a drawn symbol comes
    with it.

    The convention `trail_study.paired_bootstrap` and
    `manual_vs_strategy._bootstrap` already use here. Those two resample paired
    DELTAS, which is a different object -- this one resamples a level and needs
    the trade counts to travel with the symbol, because the per-trade statistic
    divides by them.

    Resampling trades instead would understate the interval: two sessions on
    the same ticker are the same story, often the same setup, and treating them
    as independent draws is how a criterion passes something it should not.
    """
    syms = sorted(by_sym)
    n = len(syms)
    if not n:
        return {"totals": [], "per_trade": [], "n_syms": 0}
    rng = random.Random(seed)
    totals, per_trade = [], []
    for _ in range(resamples):
        tot, cnt = 0.0, 0
        for _ in range(n):
            nets = by_sym[syms[rng.randrange(n)]]
            tot += sum(nets)
            cnt += len(nets)
        totals.append(tot)
        per_trade.append(tot / cnt if cnt else 0.0)
    return {"totals": sorted(totals), "per_trade": sorted(per_trade),
            "n_syms": n}


def pct(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    i = int(q * (len(sorted_vals) - 1))
    return sorted_vals[i]


def share_above_zero(sorted_vals: list[float]) -> float:
    if not sorted_vals:
        return 0.0
    return sum(1 for v in sorted_vals if v > 0) / len(sorted_vals)


def share_profitable(by_sym: dict[str, list[float]],
                     lo: int = 1, hi: int = 10 ** 9) -> tuple[int, int, float]:
    """The OLD criterion, over symbols whose trade count is in [lo, hi].

    Kept only so it can be printed beside the null below. Its value is not a
    verdict in this module.
    """
    sel = [s for s, v in by_sym.items() if lo <= len(v) <= hi]
    good = sum(1 for s in sel if sum(by_sym[s]) > 0)
    return good, len(sel), (good / len(sel) if sel else 0.0)


def shuffled_shares(by_sym: dict[str, list[float]], resamples: int = RESAMPLES,
                    seed: int = SEED) -> list[float]:
    """The null for the old criterion: trade nets permuted across symbol
    labels with each symbol's trade COUNT HELD FIXED.

    Holding the count fixed is the whole point. Shuffled without it, the
    control would differ from the observation in two ways at once and could
    not say which one mattered.
    """
    counts = [len(v) for _, v in sorted(by_sym.items())]
    pool = [x for _, v in sorted(by_sym.items()) for x in v]
    rng = random.Random(seed)
    out = []
    for _ in range(resamples):
        rng.shuffle(pool)
        i, good = 0, 0
        for c in counts:
            if sum(pool[i:i + c]) > 0:
                good += 1
            i += c
        out.append(good / len(counts) if counts else 0.0)
    return sorted(out)


def verdict(boot: dict) -> tuple[bool, float, float]:
    """(passes, share of resamples above zero, 2.5th percentile per-trade).

    The per-trade figure is returned for REPORTING and takes no part in the
    verdict -- see the module docstring for why it cannot.
    """
    p = share_above_zero(boot["totals"])
    return p >= BOOT_MIN_P, p, pct(boot["per_trade"], 0.025)


# ---------------------------------------------------------------- the report
def render(label, rows, by_sym, boot, shuf, elapsed) -> list[str]:
    n_tr = len(rows)
    net = sum(r["net"] for r in rows)
    ok, p, lo_pt = verdict(boot)
    good, n_sy, old = share_profitable(by_sym)

    L = [f"BREADTH — GO/NO-GO CRITERION 2, AS REPLACED   [{label}]", "",
         "  Registered in docs/research/REGISTERED_breadth.md, commit 4bfaa88,",
         "  BEFORE this module was written and before ORB had a number.", "",
         f"  {n_tr:,} trades across {n_sy:,} symbols",
         f"  net {net:,.0f}   per trade {net / n_tr if n_tr else 0:.2f}",
         f"  {n_tr / n_sy if n_sy else 0:.1f} trades per symbol",
         f"  elapsed {elapsed:.1f}s", ""]

    L += ["1. THE REPLACEMENT — does this survive a different draw of symbols?",
          "",
          "  Symbols resampled with replacement, every trade of a drawn symbol",
          "  coming with it. Two conditions, because a large enough sample",
          "  makes the first easy on its own.", ""]
    if not boot["totals"]:
        L += ["  REFUSED: no symbols to resample.", ""]
    else:
        L += [f"  total net > 0 in   {p:.1%}   of {len(boot['totals']):,} "
              f"resamples   (bar {BOOT_MIN_P:.0%})",
              f"  95% interval on total   {pct(boot['totals'], 0.025):,.0f}"
              f"  to  {pct(boot['totals'], 0.975):,.0f}", ""]
        L += ["  *** PASSES criterion 2 as replaced. ***" if ok
              else f"  DOES NOT pass criterion 2 as replaced: {p:.1%} is "
                   f"under {BOOT_MIN_P:.0%}.", ""]
        L += [f"  per trade over the same resamples   {lo_pt:.2f}  to  "
              f"{pct(boot['per_trade'], 0.975):.2f}",
              "  CONTEXT, NOT A CONDITION. A floor here was registered and",
              "  withdrawn before ORB had a number: per_trade = total / count,",
              "  so it carries the sign of total in every resample and a floor",
              "  at zero is this same bar at a stricter level rather than a",
              "  magnitude check. The dollar bar is criterion 3's, at $1.00.",
              ""]

    L += ["2. THE OLD CRITERION, AND ITS OWN NULL", "",
          "  'A majority of symbols with >= 1 trade are profitable.' Printed",
          "  here beside the distribution it takes when NOTHING but skew and",
          "  trade count are at work — nets permuted across symbol labels with",
          "  each symbol's trade count held fixed.", ""]
    if not shuf:
        L += ["  REFUSED: nothing to permute.", ""]
    else:
        s_lo, s_hi = pct(shuf, 0.05), pct(shuf, 0.95)
        inside = s_lo <= old <= s_hi
        L += [f"  observed   {good:,} of {n_sy:,} profitable = {old:.1%}"
              f"   (the old bar was {OLD_MAJORITY:.0%})",
              f"  shuffled   {statistics.mean(shuf):.1%} mean, "
              f"middle 90% {s_lo:.1%} to {s_hi:.1%}", ""]
        if inside:
            L += ["  *** The observed share sits INSIDE its own null. On this",
                  "  sample the old criterion carries no information about",
                  "  breadth beyond skew and trade count, and its retirement is",
                  "  evidenced rather than argued. ***", ""]
        else:
            L += ["  *** The observed share sits OUTSIDE its own null, so the",
                  "  old criterion WAS measuring something real here. Per the",
                  "  registration it is KEPT, and section 1 is adopted in",
                  "  addition rather than instead. ***", ""]

    L += ["3. THE TRADE-COUNT CONFOUND, BUCKET BY BUCKET", "",
          "  §11.1's original objection. If the share climbs with trade count,",
          "  the old statistic was reading sample size.", "",
          f"  {'trades/symbol':<16}{'symbols':>9}{'profitable':>12}{'share':>9}",
          ""]
    for lo_b, hi_b, name in BUCKETS:
        g, n, s = share_profitable(by_sym, lo_b, hi_b)
        if n:
            L.append(f"  {name:<16}{n:>9,}{g:>12,}{s:>8.1%}")
    L.append("")

    L += ["WHAT THIS DOES NOT SETTLE", "",
          "  Not whether the edge is real out of sample — criterion 5's",
          "  temporal holdout is a separate question, and var/state/holdout.json",
          "  is untouched by any of this and remains unspent.",
          "",
          "  Criterion 1 (drop-top-3 and drop-top-5) is unchanged and is not",
          "  implied by anything here: drop-top-N asks what happens when the",
          "  best names are removed, this asks what happens when the draw",
          "  changes. Both are required."]
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--run-id", help="score one backtest_trade run")
    p.add_argument("--csv", help="score a trades CSV instead (symbol, net)")
    p.add_argument("--label", default=None, help="what to call it in the report")
    p.add_argument("--list-runs", action="store_true",
                   help="show the runs in backtest_trade and stop")
    p.add_argument("--out", default="var/reports/breadth.txt")
    return p


def main(argv=None) -> int:
    import time

    a = build_parser().parse_args(argv)
    if a.list_runs:
        for run, n, syms, net in list_runs():
            print(f"  {run:<48}{n:>8,} trades{syms:>8,} syms{net:>12,.0f}")
        return 0
    if bool(a.run_id) == bool(a.csv):
        sys.exit("give exactly one of --run-id or --csv (or --list-runs).")

    t0 = time.time()
    rows = load_csv(Path(a.csv)) if a.csv else load_db(a.run_id)
    if not rows:
        sys.exit("no trades with both a symbol and a net. Nothing to score, "
                 "and an empty sample must not render as a clean result.")
    bs = by_symbol(rows)
    boot = cluster_bootstrap(bs)
    shuf = shuffled_shares(bs)
    label = a.label or (Path(a.csv).name if a.csv else a.run_id)
    text = render(label, rows, bs, boot, shuf, time.time() - t0)
    emit("\n".join(text), a.out,
         header=f"common.breadth  {label}  resamples={RESAMPLES} seed={SEED}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
