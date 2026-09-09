#!/usr/bin/env python3
"""Does MCL enter in consolidation, and would a bandwidth gate help?

    python -m common.consolidation_study

THE OBSERVATION, Ben 2026-09-09, watching the MCL paper session
----------------------------------------------------------------
ACCL was bought at 06:31 during a period of consolidation -- the name barely
moved, so the position sat, took one of the two available slots, and left us
exposed for a long time to nothing. The proposed safeguard: while the Bollinger
bands are NARROWING, take no trades; take them only as the bands begin to
widen.

Three claims are bundled in there, and they are separable:

    (i)   consolidation entries deny other trades          -- MEASURABLE NOW
    (ii)  consolidation entries are worse in P/L           -- MEASURABLE NOW
    (iii) long holds are operational risk                  -- TRUE BY
          INSPECTION, because outside RTH the trailing stop is software-managed
          in this process, so a position held for hours is hours of process
          risk.

This module measures (i) and (ii) BEFORE anything is built, because the two
that are measurable decide whether (iii) is worth a rule.

WHAT IS PINNED, AND WHY IT IS PINNED HERE
------------------------------------------
Bandwidth has free parameters -- length, width, what "narrowing" means, over
how many bars -- and a filter tuned across those is a filter fitted to the
sample. So they are fixed at the conventional Bollinger defaults, written down
before the first run, and NOT swept:

    BB_LEN 20, BB_K 2.0, on 1-minute CLOSES
    level  = (upper - lower) / basis
    slope  = level[t] - level[t - SLOPE_BARS],  SLOPE_BARS = 5

WHAT THIS EVIDENCE IS NOT
-------------------------
holdout.json splits the SCREENED universe, not bar_cache, so the locked slice
protects nothing here -- and MCL was fitted over this whole period anyway.
Nothing this module prints is out of sample in any sense. The controls that DO
apply are the project's standing two: require the effect in both halves, split
once at the calendar midpoint and never moved; and drop-top-3, because P/L here
is concentrated enough that three trades routinely are the whole result.

Findings and the decision are in claude/consolidation_filter_test.md.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

import pandas as pd

from common import portfolio as P
from common.analysis import load_sessions
from common.report_io import emit
from strategy.mcl import mcl as MCL

BB_LEN, BB_K, SLOPE_BARS = 20, 2.0, 5

# The calendar midpoint of bar_cache's dates, taken once and hard-coded. NOT
# the median of the TRADES: that moves when the entry rule moves, which makes
# the split a function of the thing being tested.
SPLIT = "2026-03-20"

CAPITAL, PER_TRADE_PCT, MAX_POSITIONS, QTY = 5000.0, 60.0, 2, 100


def bbw(df: pd.DataFrame) -> pd.Series:
    """Bollinger bandwidth: band width as a fraction of the basis.

    Divided by the basis on purpose. A raw width in dollars is not comparable
    between a $2 name and a $9 one, and this universe spans that.
    """
    c = df["close"]
    basis = c.rolling(BB_LEN).mean()
    sd = c.rolling(BB_LEN).std(ddof=0)
    return (2 * BB_K * sd) / basis


def entry_rows(trades, frames) -> list[dict]:
    """One row per trade, carrying the bandwidth AS OF THE ENTRY BAR.

    Located by timestamp, never by counting minutes from the frame's start: a
    minute with no prints produces no row, so bar position and clock time come
    apart on exactly the thin names this is about.
    """
    out = []
    for t in trades:
        d = str(t["entry_ts"].tz_convert("America/New_York").date())
        df = frames.get((t["symbol"], d))
        if df is None or t["entry_ts"] not in df.index:
            continue
        w = bbw(df)
        i = w.index.get_loc(t["entry_ts"])
        if i < BB_LEN + SLOPE_BARS or pd.isna(w.iloc[i]):
            continue
        out.append(dict(
            symbol=t["symbol"], date=d, real=t["real"],
            level=float(w.iloc[i]),
            slope=float(w.iloc[i] - w.iloc[i - SLOPE_BARS]),
            hold=int((t["exit_ts"] - t["entry_ts"]).total_seconds() // 60)))
    return out


def stats(rows: list[dict], drop: int = 3) -> dict:
    """Net, per-trade, and net after removing this group's own best `drop`.

    Drop-top-N is computed WITHIN the group, never by removing the sample's
    overall winners: a bucket judged by whether someone else's best trades
    happened to land in it is not being judged at all.
    """
    net = sum(r["real"] for r in rows)
    top = sorted((r["real"] for r in rows), reverse=True)[:drop]
    holds = sorted(r["hold"] for r in rows)
    return {"n": len(rows), "net": net,
            "per_trade": net / len(rows) if rows else 0.0,
            "dropped": net - sum(top),
            "median_hold": holds[len(holds) // 2] if holds else 0}


def bucket(rows: list[dict], key: str, edges) -> list[tuple[str, dict]]:
    """Half-open buckets, [lo, hi). The boundary goes in the label so a reader
    can see which side a value falls on rather than inferring it."""
    out, lo = [], None
    for hi in list(edges) + [None]:
        sel = [r for r in rows if (lo is None or r[key] >= lo)
               and (hi is None or r[key] < hi)]
        name = (f"< {hi:g}" if lo is None
                else f">= {lo:g}" if hi is None else f"{lo:g} - {hi:g}")
        if sel:
            out.append((name, stats(sel)))
        lo = hi
    return out


def halves(rows: list[dict], split: str = SPLIT):
    return ([r for r in rows if r["date"] < split],
            [r for r in rows if r["date"] >= split])


def render(rows, capped, uncapped, rej_slot, rej_cap, n_sessions) -> list[str]:
    head = (f"      {'bucket':<18}{'n':>5}{'net':>10}{'per trade':>11}"
            f"{'drop top 3':>12}{'med hold':>10}")

    def line(name, s):
        return (f"      {name:<18}{s['n']:>5}${s['net']:>9,.0f}"
                f"${s['per_trade']:>10.2f}${s['dropped']:>11,.0f}"
                f"{s['median_hold']:>10}")

    L = ["CONSOLIDATION FILTER -- measured before anything was built", "",
         f"  {n_sessions} cached sessions, MCL live config, {QTY} shares flat, "
         f"cap {MAX_POSITIONS}",
         f"  Bollinger {BB_LEN}/{BB_K:g} on 1m closes, slope over "
         f"{SLOPE_BARS} bars. Pinned, not swept.",
         f"  Halves split at {SPLIT}, chosen once. Drop-top-3 within each "
         "bucket.",
         "",
         "  NOT out of sample: holdout.json splits the screened universe, not",
         "  this cache, and MCL was fitted over this whole period.", "",
         "A. IS A SLOT ACTUALLY SCARCE?", ""]

    net_c = sum(t["real"] for t in capped)
    net_u = sum(t["real"] for t in uncapped)
    holds = sorted(int((t["exit_ts"] - t["entry_ts"]).total_seconds() // 60)
                   for t in capped)

    def q(p):
        return holds[min(len(holds) - 1, int(p * len(holds)))]

    ex: dict = defaultdict(int)
    for t in capped:
        ex[t["reason"]] += 1
    L += [f"   trades {len(capped)}   denied by the cap {rej_slot}   "
          f"denied for capital {rej_cap}",
          f"   with NO cap at all: {len(uncapped)} trades",
          f"   net  capped ${net_c:>8,.0f}   uncapped ${net_u:>8,.0f}"
          + ("   <- lifting the cap is WORSE, so a freed slot is worth "
             "nothing" if net_u < net_c else ""),
          f"   hold minutes  p10 {q(.10)}  p50 {q(.50)}  p90 {q(.90)}  "
          f"p99 {q(.99)}  max {holds[-1]}",
          f"   exits {dict(ex)}", ""]

    L += [f"B. BANDWIDTH AT THE ENTRY BAR  ({len(rows)} of {len(capped)} "
          f"trades had {BB_LEN + SLOPE_BARS} prior bars)", ""]
    qs = sorted(r["level"] for r in rows)
    cuts = [round(qs[int(p * len(qs))], 4) for p in (0.2, 0.4, 0.6, 0.8)]
    L += [f"   by LEVEL, quintiles {cuts}", head]
    L += [line(n, s) for n, s in bucket(rows, "level", cuts)]
    L += ["", "   by SLOPE -- negative is NARROWING, which the proposal skips",
          head]
    L += [line(n, s) for n, s in bucket(rows, "slope", [-0.005, 0.0, 0.005])]

    L += ["", f"C. BOTH HALVES on the rule as proposed, split {SPLIT}", ""]
    for name, part in zip(("early", "late "), halves(rows)):
        for lbl, sel in (("narrowing (would SKIP)",
                          [r for r in part if r["slope"] < 0]),
                         ("widening  (would KEEP)",
                          [r for r in part if r["slope"] >= 0])):
            s = stats(sel)
            L.append(f"   {name} {lbl:<24} n={s['n']:>4} ${s['net']:>8,.0f} "
                     f"(${s['per_trade']:>7.2f}/trade, "
                     f"drop-top-3 ${s['dropped']:>8,.0f})")
    L += ["",
          "   A rule is supported only if it helps in BOTH halves AND survives",
          "   drop-top-3. Read those two columns before the headline number.",
          ""]

    L += ["D. WHAT THE HOLD TIMES ACTUALLY DID", "",
          head + f"{'early':>10}{'late':>10}"]
    lo = 0
    for hi in (5, 15, 30, 60, 120, None):
        sel = [r for r in rows if r["hold"] >= lo
               and (hi is None or r["hold"] < hi)]
        if sel:
            e, l = halves(sel)
            L.append(line(f"{lo}-{hi}m" if hi else f"{lo}m+", stats(sel))
                     + f"${sum(r['real'] for r in e):>9,.0f}"
                       f"${sum(r['real'] for r in l):>9,.0f}")
        lo = hi if hi else lo
    L += ["",
          "   Hold time is known only AFTER the trade, so this is a",
          "   description and not a filter. It says where to look, not what",
          "   to do.", ""]

    fast = [r for r in rows if r["hold"] < 5]
    slow = [r for r in rows if r["hold"] >= 5]
    L += ["E. ARE THE QUICK STOP-OUTS THE WIDENING ENTRIES?", ""]
    for lbl, g in (("held <5m ", fast), ("held >=5m", slow)):
        if not g:
            continue
        wid = sum(1 for r in g if r["slope"] >= 0.005)
        lv = sorted(r["level"] for r in g)
        L.append(f"   {lbl} n={len(g):>4}  widening at entry "
                 f"{100 * wid / len(g):>5.1f}%   median level "
                 f"{lv[len(lv) // 2]:.4f}")
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--cache", default="bar_cache",
                   help="IB bars are split-adjusted; see common/portfolio.py. "
                        "Sizing is flat here, so the adjustment does not reach "
                        "the share count, but the prices are still adjusted")
    p.add_argument("--out", default="var/reports/consolidation_study.txt")
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    sessions = load_sessions(Path(a.cache))
    capped, rej_cap, rej_slot, _ = P.simulate(
        sessions, MCL, CAPITAL, PER_TRADE_PCT, MAX_POSITIONS, fixed_qty=QTY)
    uncapped, _, _, _ = P.simulate(
        sessions, MCL, CAPITAL, PER_TRADE_PCT, 10_000, fixed_qty=QTY)
    frames = {(s, d): df for s, d, df in sessions}
    rows = entry_rows(capped, frames)

    emit("\n".join(render(rows, capped, uncapped, rej_slot, rej_cap,
                          len(sessions))),
         a.out, header=f"common.consolidation_study  cache={a.cache}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
