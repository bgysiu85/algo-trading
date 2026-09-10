#!/usr/bin/env python3
"""Does the market's regime, known YESTERDAY, separate MCL's trades?

    python -m common.regime_study --archive databento --dataset EQUS.MINI

THE CLAIM BEING TESTED
----------------------
`warrior_census_20260910.md` §4 puts a 16x spread on his mean day between hot
and cold markets, from 234 recaps he labelled himself. `HANDOVER_TO_BUILD` §5
ranks a regime gate first on expected value for that reason: nothing else
measured in this project moves an outcome 16-fold.

His labels are his own, applied after the fact, to his own trading. This asks
the mechanical version: bucket MCL's trades by a regime computed from daily
bars, using only information that existed before the session opened, and see
whether the buckets separate.

THE THREE THINGS THAT WOULD MAKE THIS FAKE, AND WHAT STOPS EACH
----------------------------------------------------------------
**1. Measuring Ben instead of the market.** `bar_cache`'s universe is
`traded_pairs.json` -- the symbol-days he traded, a median of 3 a day. Breadth
computed over that is a measure of his trade count, which the census already
showed tracks his outcome. So this study reads the MARKET-WIDE daily archive
and REFUSES a universe too thin to be one (see MIN_UNIVERSE). The refusal is
the control: a regime table printed off a trade list would look exactly like a
regime table printed off a market.

**2. Knowing today.** A same-day label cannot be acted on at 04:00. The
headline is the LAGGED split -- yesterday's reading applied to today. The
same-day split is computed and reported as a CEILING, not a result.

**3. Three buckets and 90 sessions.** A spread appears by chance at that size,
and the eye is very willing to see a monotone ordering in three numbers. So the
verdict is gated on a PERMUTATION NULL: the labels are shuffled across dates
many times and the observed hot-minus-cold spread is placed in that
distribution. A spread that a shuffle reproduces one time in five is not an
effect, whatever it looks like in the table.

WHAT WOULD MAKE IT ADOPTABLE
----------------------------
The standard the apex sweeps had, plus one this needs and they did not:

  - the spread survives the permutation null at p < 0.05,
  - it holds in BOTH halves at the derived midpoint,
  - it survives drop-top-3 within each bucket, and
  - the ordering is MONOTONE across all three buckets.

The last one is not decoration. Cold-vs-hot alone is a two-point comparison and
two points always make a line; if mixed sits outside the pair, the feature is
picking out something other than a temperature.
"""
from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from common import holdout as HO
from common import regime as RG
from common.analysis import LIVE, MEASURED_FRICTION, load_sessions
from common.report_io import emit
from strategy.mcl import mcl as MCL

ET = ZoneInfo("America/New_York")
QTY = 100
DROP = 3
ORDER = ("cold", "mixed", "hot")

# Below this many distinct symbols on the median session, the daily frame is
# not a market. Set from what the thing has to be able to measure rather than
# from what any particular archive happens to hold: the headline feature is a
# count of names up over 100% on the day, which is 0 or 1 on most sessions even
# across all of US equities. A few hundred names cannot produce that count at
# all, so a "regime" computed from them would be a constant wearing a label.
MIN_UNIVERSE = 500

# Permutation resamples. 2,000 puts the resolution of the p-value at 0.0005,
# which is finer than the 0.05 the verdict is gated on, so the count is not
# itself a source of the answer.
N_PERM = 2000
SEED = 20260911


def bucket_stats(reals: list[float]) -> dict:
    if not reals:
        return {"n": 0, "net": 0.0, "per": 0.0, "win": 0.0, "dropped": 0.0}
    net = sum(reals)
    return {
        "n": len(reals), "net": net, "per": net / len(reals),
        "win": 100.0 * sum(1 for r in reals if r > 0) / len(reals),
        "dropped": net - sum(sorted(reals, reverse=True)[:DROP]),
    }


def group(trades, labels: dict[str, str]) -> dict[str, list[float]]:
    """Trades bucketed by their session's label.

    A trade on a date the labelling does not cover is DROPPED, not defaulted
    into a bucket. The lagged labelling has no entry for the first session by
    construction, and quietly filing that day under "cold" would put a real
    trading day in a bucket on the strength of an absent predecessor.
    """
    out: dict[str, list[float]] = {k: [] for k in ORDER}
    for _, d, t in trades:
        lab = labels.get(d)
        if lab in out:
            out[lab].append(t.net - MEASURED_FRICTION)
    return out


def spread(by: dict[str, list[float]]) -> float:
    """Hot per-trade minus cold per-trade. The statistic under test."""
    h, c = bucket_stats(by["hot"]), bucket_stats(by["cold"])
    if not h["n"] or not c["n"]:
        return 0.0
    return h["per"] - c["per"]


def permutation_p(trades, labels: dict[str, str], observed: float,
                  n: int = N_PERM, seed: int = SEED) -> float:
    """How often a shuffle of the labels ACROSS DATES beats the observed spread.

    The shuffle is over dates and not over trades, which matters: trades on one
    session share a market and are not independent draws. Shuffling trades
    would break that clustering and produce a null far too tight, turning noise
    into significance. Permuting the date labels preserves how many trades each
    session contributed and asks only whether the LABELS are attached to the
    right days.
    """
    dates = sorted(labels)
    vals = [labels[d] for d in dates]
    rng = random.Random(seed)
    hits = 0
    for _ in range(n):
        rng.shuffle(vals)
        s = spread(group(trades, dict(zip(dates, vals))))
        if abs(s) >= abs(observed):
            hits += 1
    # +1 on both sides: with no resample beating it the honest statement is
    # "below 1/(n+1)", not "zero".
    return (hits + 1) / (n + 1)


def halves_split(dates) -> str:
    ds = sorted(set(dates))
    return ds[len(ds) // 2] if ds else ""


def check_universe(daily) -> tuple[int, str | None]:
    """The median distinct-symbol count per session, and why it is refused."""
    if daily.empty:
        return 0, "the daily archive is empty"
    per = daily.groupby("date")["symbol"].nunique()
    med = int(per.median())
    if med < MIN_UNIVERSE:
        return med, (
            f"the median session carries {med:,} symbols, under the "
            f"{MIN_UNIVERSE:,} this needs to be a market")
    return med, None


def render(*, trades, lab_same, lab_lag, feats, n_sessions, med_universe,
           side) -> list[str]:
    L = ["MARKET REGIME as a GATE on MCL", "",
         f"  {n_sessions} cached sessions, {QTY} shares flat, {side}",
         f"  regime from the daily archive: median {med_universe:,} symbols "
         f"per session, ${RG.BAND[0]:.0f}-${RG.BAND[1]:.0f} on the PRIOR close",
         f"  net after tiered commission and ${MEASURED_FRICTION}/RT friction",
         ""]

    rated = [f for f in feats.values() if f.usable]
    L += ["WHAT THE MARKET DID, over the archive's sessions", "",
          f"  sessions with >= {RG.MIN_NAMES} movers   "
          f"{len(rated)} of {len(feats)}",
          f"  median movers (>= {RG.MOVER_MIN:.0%})      "
          f"{sorted(f.n_movers for f in rated)[len(rated) // 2] if rated else 0}",
          f"  sessions with a >= {RG.BIG_MIN:.0%} gainer  "
          f"{sum(1 for f in feats.values() if f.n_big)}",
          f"  median leading gainer            "
          f"{(sorted(f.lead for f in rated)[len(rated) // 2] if rated else 0):.0%}",
          ""]

    ac = RG.autocorr(lab_same)
    L += ["PERSISTENCE — the ceiling on any lagged gate", "",
          f"  P(today's label == yesterday's) = {ac:.1%}   "
          f"(1/3 = no information)", ""]
    if ac < 0.40:
        L += ["  THE LABEL BARELY PERSISTS. Whatever the same-day table shows,",
              "  yesterday's reading is close to a coin toss about today, and a",
              "  gate cannot use what it cannot see coming. Read the lagged",
              "  block as the result and the same-day block as a description.",
              ""]

    for title, labels, note in (
        ("THE GATE — yesterday's regime, applied to today", lab_lag,
         "This is the only actionable form."),
        ("THE CEILING — today's regime, which you cannot know at 04:00",
         lab_same,
         "NOT a result. The most this feature set could be worth with "
         "tomorrow's paper."),
    ):
        by = group(trades, labels)
        L += [title, "", f"  {note}", "",
              f"  {'bucket':<10}{'sessions':>10}{'trades':>8}{'net':>10}"
              f"{'per':>8}{'win%':>7}{'drop top 3':>12}"]
        for k in ORDER:
            s = bucket_stats(by[k])
            ns = sum(1 for v in labels.values() if v == k)
            L.append(f"  {k:<10}{ns:>10}{s['n']:>8}${s['net']:>9,.0f}"
                     f"${s['per']:>7.2f}{s['win']:>6.1f}%${s['dropped']:>11,.0f}")
        L.append("")

    by = group(trades, lab_lag)
    counts = {k: bucket_stats(by[k])["n"] for k in ORDER}
    if min(counts.values()) == 0:
        empty = [k for k, v in counts.items() if not v]
        return L + ["NO VERDICT", "",
                    f"  {', '.join(empty)} has no trades under the lagged",
                    "  labelling, so there is nothing to compare. A bucket",
                    "  with no trades reads exactly like a bucket that lost",
                    "  nothing.", ""]

    per = {k: bucket_stats(by[k])["per"] for k in ORDER}
    obs = per["hot"] - per["cold"]
    p = permutation_p(trades, lab_lag, obs)
    mono = per["cold"] <= per["mixed"] <= per["hot"]

    dates = sorted({d for _, d, _ in trades if d in lab_lag})
    mid = halves_split(dates)
    early = [(s, d, t) for s, d, t in trades if d in lab_lag and d < mid]
    late = [(s, d, t) for s, d, t in trades if d in lab_lag and d >= mid]
    se, sl = spread(group(early, lab_lag)), spread(group(late, lab_lag))
    dropped_ok = (bucket_stats(by["hot"])["dropped"] / max(counts["hot"], 1)
                  > bucket_stats(by["cold"])["dropped"] / max(counts["cold"], 1))

    L += ["CONTROLS on the lagged split", "",
          f"  hot - cold, per trade        {obs:+.2f}",
          f"  permutation p                {p:.4f}   "
          f"({N_PERM:,} shuffles of the labels across dates)",
          f"  monotone cold<=mixed<=hot    {'yes' if mono else 'NO'}   "
          f"({per['cold']:+.2f} / {per['mixed']:+.2f} / {per['hot']:+.2f})",
          f"  both halves (split {mid})  early {se:+.2f}   late {sl:+.2f}",
          f"  survives drop-top-3          {'yes' if dropped_ok else 'NO'}",
          ""]

    ok = p < 0.05 and mono and se * sl > 0 and dropped_ok and obs > 0
    if ok:
        L += ["VERDICT — the gate separates", "",
              "  Every control holds. This is still IN-SAMPLE: MCL's parameters",
              "  were fitted on these sessions, and holdout.json was cut over",
              "  the SCREENED universe so it does not cover bar_cache. Re-run",
              "  on bar_cache_xnas with --spend-holdout before sizing to it.", ""]
    else:
        why = []
        if obs <= 0:
            why.append("hot does not beat cold")
        if p >= 0.05:
            why.append(f"a shuffle reproduces the spread {p:.1%} of the time")
        if not mono:
            why.append("the ordering is not monotone, so mixed is not between "
                       "the two and the feature is not a temperature")
        if se * sl <= 0:
            why.append("the sign flips between halves")
        if not dropped_ok:
            why.append("it does not survive drop-top-3")
        L += ["VERDICT — not adoptable as measured", ""]
        L += [f"  - {w}" for w in why]
        L += ["",
              "  Note what this does NOT say. The census's 16x is over HIS",
              "  trading, and his gate is discretionary: in a cold market he",
              "  cuts size ~5x, drops to A-only setups and stops by 10:00",
              "  (`execution_gap_20260910.md` §5). A null here says the daily",
              "  breadth features do not reproduce that decision -- not that",
              "  the regime is imaginary. The next move is the SIZE response,",
              "  which is what he actually changes, rather than a go/no-go.", ""]

    L += ["WHAT IS NOT IN HERE", "",
          "  FLOAT of the leaders, which he names as a cold tell (a 160M-float",
          "  leader). The daily archive does not carry it and a proxy invented",
          "  here would be a fourth feature whose only property is existing.",
          "",
          "  THE ASYMMETRIC SMOOTHER. He says the shift hot->cold is subtler",
          "  than cold->hot, which argues for entering cold slowly and leaving",
          "  it fast. That is two fitted constants and the base case has to be",
          "  measured before there is anything for them to improve.",
          "",
          "  HIS THRESHOLDS. 58% = cold and 300-500% = hot are labels on his",
          "  market in his years. The buckets here are terciles of OUR sample,",
          "  so 'hot' means our top third and not his."]
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--cache", default="bar_cache")
    p.add_argument("--archive", default=None,
                   help="the Databento archive holding ohlcv-1d")
    p.add_argument("--dataset", default="EQUS.MINI")
    p.add_argument("--spend-holdout", action="store_true",
                   help="read the LOCKED sessions instead of the training "
                        "ones. One-way: a holdout read casually is not one.")
    p.add_argument("--out", default="var/reports/regime.txt")
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    from common.databento_fetch import default_archive
    from common.dbn_io import daily_frame

    archive = Path(a.archive) if a.archive else default_archive()
    daily = daily_frame(archive, a.dataset)
    med, refusal = check_universe(daily)
    if refusal:
        sys.exit(
            "REFUSING TO RUN\n\n"
            f"  {refusal}.\n\n"
            "  A regime is a property of the market. Computed over a handful\n"
            "  of names -- and bar_cache's universe is traded_pairs.json, the\n"
            "  symbol-days Ben traded, a median of 3 a day -- the breadth\n"
            "  features measure HIS TRADE COUNT, which the census already\n"
            "  showed tracks his outcome. The table would look identical and\n"
            "  mean the opposite.\n\n"
            "  Point --archive at a daily archive covering the market. That\n"
            "  is the same archive prior_spike reads, and its default schema\n"
            "  is already ohlcv-1d:\n"
            "    python -m common.databento_universe --confirm\n")

    feats = RG.series(daily)
    lab_same = RG.classify(feats)
    lab_lag = RG.lagged(lab_same)

    sessions = load_sessions(Path(a.cache))
    sessions, set_aside, side = HO.split_sessions(sessions, a.spend_holdout)
    if not sessions:
        sys.exit(f"no sessions on the {side} side of {a.cache}")

    trades = []
    for sym, d, df in sessions:
        try:
            trades += [(sym, d, t) for t in MCL.backtest_session(
                df, datetime.strptime(d, "%Y-%m-%d").date(), ET,
                entry_shares=QTY, **LIVE)]
        except Exception:                                   # noqa: BLE001
            pass

    emit("\n".join(render(trades=trades, lab_same=lab_same, lab_lag=lab_lag,
                          feats=feats, n_sessions=len(sessions),
                          med_universe=med, side=side)),
         a.out, header=f"common.regime_study  cache={a.cache} "
                       f"archive={archive}/{a.dataset}  side={side}"
                       + (f"  ({set_aside} set aside)" if set_aside else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
