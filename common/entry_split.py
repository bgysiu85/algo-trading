#!/usr/bin/env python3
"""Is the profitable kind of trade visible AT the entry bar?

    python -m common.entry_split --strategy mcl

THE QUESTION, AND WHY IT IS WORTH ONE MORE RUN
-----------------------------------------------
`entry_excursion_result_20260914.md` split MCL's 3,955 point-in-time trades by
which extreme arrived first, and the two halves are different businesses:

    dips then runs   1,156 (29.3%)   $44.00 available in 30 bars   +$19.13/trade
    pops then fades  2,794 (70.7%)   $15.30 available in 30 bars   (22.73)/trade

The difference is a property of the situation entered, not of how the position
was managed. So: **does anything observable at the entry bar say which one this
is going to be?**

If yes, it is an entry filter and MCL has a path to profitability. If no, the
entry is not identifiable from minute OHLCV and the question becomes what data
would make it so.

THE BAR, DERIVED RATHER THAN PICKED
------------------------------------
A filter has to lift the dip-then-run rate far enough that the book makes money,
and that number comes out of the two group means rather than out of the air:

    p * 19.13  =  (1 - p) * 22.73      ->    p = 22.73 / 41.86 = 54.3%

So **BREAK_EVEN_RATE** is 54.3% against a base rate of 29.3% -- a lift of 1.85x.
A feature whose top bucket does not reach it does not, on its own, produce a
profitable strategy, however pretty its progression looks. Both figures are
computed from THIS RUN's data, not pasted, so they cannot drift from the split
they came from.

    CLEARS      monotone the same way in both halves AND the top bucket
                reaches break-even in both. This is the bar that matters.
    SEPARATES   monotone the same way in both halves with a top-vs-bottom lift
                of at least 1.3x in both, but short of break-even. Not a filter
                on its own; evidence that something is there.
    NOTHING     everything else, printed anyway.

THE HONEST PRIOR, WRITTEN DOWN BEFORE THE RUN
----------------------------------------------
`entry_features` put these same 22 features across 11 families against MCL's
trade P/L and cleared **zero**. The expectation here is another null. What makes
it worth running anyway is that the target is different in two ways that matter:
it is BINARY and mechanically defined rather than a noisy dollar amount, and its
base rate is 29.3% where `run_signal` was fighting 0.108%.

A negative closes the entry question as firmly as a positive opens it. That is
the value of the run, and it is why the bar is registered before it.

WHAT WOULD MAKE THIS WRONG
--------------------------
**Reading the future.** Every feature comes from `entry_features.features_at`,
which may not touch `sig.iloc[i+1:]` and has a test that shuffles the future and
asserts the output is unchanged. The LABEL is deliberately post-entry -- that is
what it is -- but nothing on the feature side may be.

**A second bucketing implementation.** `buckets`, `monotone`,
`why_not_bucketable` and `FAMILIES` are imported from `entry_features`, not
reimplemented. A copy with its own quantile edges would make a result here
incomparable with the null recorded there, which is the only thing this run is
read against.

**Multiplicity counted by column.** 22 columns is 22 chances; 11 families is 11.
Tiers are counted by family, as they are there.

**A base rate that drifts.** The rate and the two group means are recomputed
here from the same trades the tiers are built on. Quoting the doc's 29.3% while
bucketing a different population is the defect this project keeps finding.
"""
from __future__ import annotations

import argparse
import os
import time
from datetime import date as _date
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from common.entry_features import (FAMILIES, QUANTILES, buckets, frame_ctx,
                                   features_at, monotone, split,
                                   why_not_bucketable)
from common.entry_excursion import QTY, measure
from common.pit_h0 import first_seen_time, load_pit
from common.pit_strategy import WARMUP_SESSIONS
from common.report_fmt import acct
from common.report_io import emit

ET = ZoneInfo("America/New_York")

LABEL = "dipped_first"
MEASURED_FRICTION = 4.26

# Registered above. SEPARATES is a lift on the base rate; CLEARS is break-even,
# which is computed from the run's own group means.
SEPARATES_LIFT = 1.30
MIN_ROWS = 200


def label_rows(rows: list[dict]) -> list[dict]:
    """Attach the 0/1 label. 1 means the drawdown arrived before the move."""
    for r in rows:
        r[LABEL] = 1.0 if r.get("adverse_first") else 0.0
    return rows


def break_even_rate(rows: list[dict], friction: float) -> tuple[float, dict]:
    """The dip-then-run rate at which the book stops losing money.

    Derived from THIS run's two group means, not pasted from the doc that
    produced them: a bar quoted from elsewhere while bucketing a different
    population is the defect this project keeps finding, one level out.

    p * win  =  (1 - p) * |lose|   ->   p = |lose| / (win + |lose|)
    """
    win = [r["net"] - friction for r in rows if r[LABEL] > 0]
    lose = [r["net"] - friction for r in rows if r[LABEL] == 0]
    # Stats are ALWAYS complete, even when a group is empty. The first version
    # returned {} on that path and the renderer read st["n_win"] out of it -- a
    # crash on the one input the branch exists to handle.
    w = sum(win) / len(win) if win else float("nan")
    l = sum(lose) / len(lose) if lose else float("nan")
    stats = {"n_win": len(win), "n_lose": len(lose), "win_per": w,
             "lose_per": l,
             "base": (len(win) / len(rows)) if rows else float("nan")}
    if not win or not lose or w <= 0 or l >= 0:
        # No positive group, or no negative one: there is no rate that trades
        # one against the other, and returning a number here would invent one.
        return float("nan"), stats
    return abs(l) / (w + abs(l)), stats


def tier(ba: list[dict], bb: list[dict], base: float,
         breakeven: float) -> tuple[str, str]:
    """(tier, why) for one feature, from its two halves.

    Bucket means are RATES here, because the label is 0/1. The shape test is
    `entry_features.monotone`, unchanged -- what differs is only the size bar,
    which has to be a rate rather than a dollar amount.
    """
    if not ba or not bb:
        return "NOTHING", "a half could not be bucketed (reason above)"
    ma, mb = monotone(ba), monotone(bb)
    if not (ma and ma == mb):
        return "NOTHING", ("no single direction holds across the buckets in "
                           "both halves")
    # The END the feature points at, which is the bottom bucket when falling.
    ta = ba[-1]["mean"] if ma > 0 else ba[0]["mean"]
    tb = bb[-1]["mean"] if mb > 0 else bb[0]["mean"]
    oa = ba[0]["mean"] if ma > 0 else ba[-1]["mean"]
    ob = bb[0]["mean"] if mb > 0 else bb[-1]["mean"]
    if breakeven == breakeven and min(ta, tb) >= breakeven:
        return "CLEARS", (f"monotone both halves and the top bucket reaches "
                          f"{100 * breakeven:.1f}% in both")
    lift_a = ta / oa if oa > 0 else float("inf") if ta > 0 else 0.0
    lift_b = tb / ob if ob > 0 else float("inf") if tb > 0 else 0.0
    if min(lift_a, lift_b) >= SEPARATES_LIFT:
        return "SEPARATES", (f"monotone both halves, top-vs-bottom "
                             f"{min(lift_a, lift_b):.2f}x, short of the "
                             f"{100 * breakeven:.1f}% a filter needs")
    return "NOTHING", (f"monotone but the ends differ by only "
                       f"{min(lift_a, lift_b):.2f}x")


def render(rows: list[dict], name: str, n_days: int, elapsed: float,
           jobs: int) -> list[str]:
    L = [f"{name.upper()}: IS THE PROFITABLE KIND OF TRADE VISIBLE AT ENTRY?",
         "",
         f"  {n_days} sessions, {len(rows):,} trades, {QUANTILES} buckets "
         f"per feature",
         f"  label: 1 = the drawdown arrived BEFORE the move (dips then runs)",
         f"  elapsed {elapsed:.1f}s on {jobs} worker(s)", ""]
    if len(rows) < MIN_ROWS:
        return L + [f"TOO FEW TRADES. {len(rows)} is under the {MIN_ROWS} this",
                    "  refuses to bucket below.", ""]

    be, st = break_even_rate(rows, MEASURED_FRICTION)
    L += ["THE BAR, COMPUTED FROM THIS RUN", "",
          f"  dips then runs   {st['n_win']:>6,} trades  "
          f"{acct(st['win_per'], 9)}/trade",
          f"  pops then fades  {st['n_lose']:>6,} trades  "
          f"{acct(st['lose_per'], 9)}/trade",
          f"  base rate        {100 * st['base']:>5.1f}%", ""]
    if be != be:
        L += ["  NO BREAK-EVEN RATE EXISTS. One group is not positive or the",
              "  other is not negative, so there is no mix of them that trades",
              "  one against the other. Nothing below is read as a filter.", ""]
    else:
        L += [f"  break-even rate  {100 * be:>5.1f}%   "
              f"(a lift of {be / st['base']:.2f}x on the base rate)", "",
              "  Derived from the two means above, not pasted: p * win ="
              " (1 - p) * |lose|.",
              "  A feature whose top bucket does not reach it does not produce",
              "  a profitable book on its own, however clean its shape.", ""]

    a, b = split(rows)
    L += ["EVERY FEATURE, PRINTED", "",
          "  Nothing is ranked and nothing is omitted. A list sorted by effect",
          "  invites reading the top of it as a finding.", ""]
    tiers: dict[str, str] = {}
    for fam in sorted(FAMILIES):
        L.append(f"  {fam.upper()}")
        for col in FAMILIES[fam]:
            why = why_not_bucketable(rows, col, QUANTILES)
            if why:
                tiers[col] = "NOTHING"
                L += [f"    {col:<22} NOT BUCKETABLE -- {why}"]
                continue
            bs = buckets(rows, col, QUANTILES, outcome=LABEL)
            ba = buckets(a, col, QUANTILES, outcome=LABEL)
            bb = buckets(b, col, QUANTILES, outcome=LABEL)
            t, note = tier(ba, bb, st["base"], be)
            tiers[col] = t
            cells = "  ".join(f"{100 * x['mean']:>5.1f}%" for x in bs)
            L += [f"    {col:<22} {cells}   {t}",
                  f"      {note}"]
        L.append("")

    clears = sorted({f for f, cols in FAMILIES.items()
                     if any(tiers.get(c) == "CLEARS" for c in cols)})
    seps = sorted({f for f, cols in FAMILIES.items()
                   if any(tiers.get(c) == "SEPARATES" for c in cols)
                   and f not in clears})
    L += ["TIERS, COUNTED BY FAMILY", "",
          "  22 columns is 22 chances; 11 families is 11. Counted the way",
          "  `entry_features` counts them, so the two runs are comparable.", "",
          f"  CLEARS     {len(clears)}   "
          + (", ".join(clears) if clears else "-"),
          f"  SEPARATES  {len(seps)}   "
          + (", ".join(seps) if seps else "-"),
          f"  of {len(FAMILIES)} families", ""]

    if not clears and not seps:
        L += ["NOTHING AT THE ENTRY BAR SEES IT", "",
              "  No family separates the two populations in both halves. On",
              "  this data the profitable kind of trade is not identifiable",
              "  when the decision has to be made -- which is the same answer",
              "  `entry_features` gave against trade P/L and `run_signal` gave",
              "  against the whole tape.",
              "",
              "  That closes the entry question for minute OHLCV. It does not",
              "  close it for other data: float, short interest, halt state,",
              "  news and order-book depth are all absent here and all",
              "  plausibly carry it.", ""]
    elif not clears:
        L += ["SOMETHING IS THERE, AND IT IS NOT ENOUGH ALONE", "",
              f"  {len(seps)} family(ies) separate the two populations without",
              "  reaching the rate a filter needs. That is evidence rather",
              "  than a rule: a combination might reach it, and testing a",
              "  combination is a new registration, not a reading of this",
              "  report.", ""]
    else:
        L += ["A FILTER IS POSSIBLE, AND IS NOT YET A RESULT", "",
              f"  {len(clears)} family(ies) reach break-even in both halves.",
              "  Nothing has been traded on it. The next step is a registered",
              "  rule and a `pit_delta` run, not a figure quoted from here.",
              ""]

    L += ["WHAT THIS IS NOT", "",
          "  Not a claim the label is causal. It says the two populations",
          "  differ on a feature, not that the feature makes them differ.",
          "",
          "  Not out of sample. `holdout.json` has not been spent here.",
          "",
          "  Not a measurement of a rule. No filter was applied; the trades",
          "  are exactly the ones MCL took."]
    return L


def run_day(args: tuple) -> tuple:
    """One session's trades, labelled and featurised. Module-level, picklable."""
    from common.dbn_io import read_dbn
    from common.pit_strategy import build_frame, engine

    from strategy.mcl import mcl as MCL

    paths, day, universe, strategy = args
    mod, extra = engine(strategy)
    parts = []
    for pth in paths:
        try:
            f = read_dbn(Path(pth))
        except Exception as e:                              # noqa: BLE001
            return day, [], f"unreadable ({type(e).__name__}: {e})"
        if not f.empty:
            parts.append((Path(pth).name[:10], f))
    if not parts or parts[-1][0] != day:
        return day, [], ""
    frame = build_frame(parts, day)
    d = _date.fromisoformat(day)
    out: list[dict] = []
    for rec in universe:
        df = frame[frame["symbol"] == rec["symbol"]]
        if df.empty or not rec.get("first_seen"):
            continue
        df = df.sort_index(kind="mergesort")
        try:
            trades = mod.backtest_session(df, d, ET, entry_shares=QTY,
                                          not_before=first_seen_time(rec),
                                          **extra)
        except Exception:                                   # noqa: BLE001
            continue
        if not trades:
            continue
        # `features_at` reads INDICATOR columns -- macd, rsi, mfi and the rest --
        # so it needs the signal frame, not the raw OHLCV one. Handing it `df`
        # raised KeyError('macd') on the first real session; every unit test
        # here passed, because they all fed the renderer dictionaries and never
        # ran this function against a frame.
        sig = MCL.signals(df)
        ctx = frame_ctx(sig)
        for t in trades:
            m = measure(df, t)
            if m is None:
                continue
            i = sig.index.searchsorted(pd.Timestamp(t.entry_time))
            if i >= len(sig) or sig.index[i] != pd.Timestamp(t.entry_time):
                continue
            # features from bar i and the bars BEFORE it; the label is the only
            # thing here that knows what happened afterwards.
            m.update(features_at(sig, int(i), ctx=ctx))
            out.append(m)
    return day, out, ""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    # MCL ONLY, on purpose. `entry_features` computes MCL's 1-minute indicator
    # set, and MC5's `signals()` wants 5-minute bars -- so an mc5 run would
    # either raise or, worse, compute a feature table against a frame those
    # features were not written for and print it as a measurement.
    p.add_argument("--strategy", default="mcl", choices=["mcl"],
                   help="mcl only: the feature set is MCL's 1-minute one")
    p.add_argument("--pairs", default="var/state/screen_pairs_pit.json")
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default="XNAS.BASIC")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--jobs", type=int, default=0)
    p.add_argument("--out", default=None)
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    from common.databento_fetch import default_archive
    from common.screen_sim import window_slices, date_of

    archive = Path(a.archive) if a.archive else default_archive()
    by_date = load_pit(Path(a.pairs))
    slices = {date_of(p): p for p in window_slices(archive, a.dataset)}
    days = sorted(by_date)
    if a.limit:
        days = days[:a.limit]
    have = [d for d in days if d in slices]
    tasks = [([str(slices[x]) for x in have[max(0, i - WARMUP_SESSIONS):i + 1]],
              d, by_date[d], a.strategy)
             for i, d in enumerate(have)]
    jobs = (os.cpu_count() or 1) if a.jobs == 0 else max(1, a.jobs)
    print(f"  {a.strategy} features + label over {len(tasks):,} session(s) on "
          f"{jobs} worker(s)", flush=True)

    t0 = time.time()
    got: dict[str, list[dict]] = {}

    def take(res, k):
        day, rows, err = res
        if err:
            print(f"  {day}: {err}", flush=True)
        else:
            got[day] = rows
        if k % 25 == 0 or k == len(tasks):
            el = time.time() - t0
            eta = (len(tasks) - k) / (k / el) / 60.0 if el and k else 0.0
            n = sum(len(v) for v in got.values())
            print(f"    [{k:>4}/{len(tasks)}] {day}  {n:>7,} trades  "
                  f"{el / 60:>5.1f} min  ~{eta:>5.1f} min left", flush=True)

    if jobs == 1:
        for k, t in enumerate(tasks, 1):
            take(run_day(t), k)
    else:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            for k, r in enumerate(ex.map(run_day, tasks, chunksize=4), 1):
                take(r, k)

    rows: list[dict] = []
    for day in sorted(got):
        rows += got[day]
    label_rows(rows)

    out = a.out or f"var/reports/entry_split_{a.strategy}.txt"
    emit("\n".join(render(rows, a.strategy, len(days), time.time() - t0, jobs)),
         out, header=f"common.entry_split  strategy={a.strategy}  "
                     f"pairs={a.pairs}"
                     + (f"  LIMIT {a.limit}" if a.limit else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
