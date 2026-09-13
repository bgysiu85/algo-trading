#!/usr/bin/env python3
"""Can anything tell a bar that is ABOUT to run from one that is not?

    python -m common.run_signal --source cache
    python -m common.run_signal --source archive --cell 8x15

THE QUESTION, AND WHY IT IS A DIFFERENT ONE
--------------------------------------------
`entry_features` asked what separates MCL's winning entries from its losing
ones and found nothing, across 22 features and 11 families. The most likely
reason is not that the tape is featureless: it is that MCL's five conditions
had already made all 482 entries ALIKE. A search for variation inside a
population built to be homogeneous comes back empty almost by construction.

`run_census` then counted the thing Ben actually wants to catch -- a TNON-shaped
move -- and found it is common: roughly one bar in fifty starts an 8%-in-15
run. So the problem was never detection. It is the other fifty.

This module asks the question that follows: over ALL bars, not MCL's, does any
feature separate the bars that start a run from the bars that do not?

PRECISION IS THE WHOLE ANSWER, AND IT IS EASY TO HIDE
------------------------------------------------------
A feature can look strong and be useless here. If 2% of bars start a run and a
condition doubles that to 4%, the condition is genuinely informative AND still
wrong 96% of the time. Any report that prints "2x lift" without printing 4%
has told the flattering half of one fact.

So every feature gets its RUN RATE per quartile, the LIFT over the base, and
the precision and recall a rule taking that quartile would actually have -- at
the TRUE base rate, restored through the sampling weight below.

CASE-CONTROL SAMPLING, AND THE WEIGHT THAT UNDOES IT
------------------------------------------------------
Computing 22 features on every bar in the archive is not affordable, so this
takes EVERY run start and a random sample of the rest. That inflates the
apparent run rate by exactly the sampling factor, and a report that forgot to
undo it would show a 40% run rate for a 2% phenomenon -- a twentyfold error in
the one number that decides everything.

The factor is therefore carried explicitly on every row, restored in every rate
this prints, and the report states the sample and the restored base rate side
by side so the correction is visible rather than promised.

WHAT THIS STILL CANNOT DO
--------------------------
It cannot tell you what a rule would MAKE. "Started a run" is not "made money":
that needs an exit, and the exit is a separate question with its own choices in
it. Precision and recall are as far as this goes, deliberately.
"""
from __future__ import annotations

import argparse
import os
import sys
import zlib
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from common.entry_features import (FAMILIES, FEATURES, features_at,
                                   frame_ctx, monotone, why_not_bucketable)
from common.report_io import emit
from common.run_census import (MAX_PRICE, MIN_BARS, MIN_PRICE, runs_in)

ET = ZoneInfo("America/New_York")
QUANTILES = 4
CONTROLS_PER_CASE = 6      # non-starts sampled per run start, before weighting
MIN_LIFT = 1.25            # below this a feature cannot pay for its own
                           # false positives at any threshold worth writing


def parse_cell(s: str) -> tuple[float, int]:
    """'8x15' -> (8.0, 15). One cell, named on the command line and printed in
    the report, so the cell is never chosen silently downstream."""
    try:
        r, n = s.lower().split("x")
        return float(r), int(n)
    except ValueError:
        sys.exit(f"--cell wants RxN, e.g. 8x15, got {s!r}")


def label_and_sample(sig: pd.DataFrame, cell: tuple[float, int], adverse: float,
                     rng: np.random.Generator, warm: int,
                     hi: int | None = None
                     ) -> tuple[list[int], list[int], int]:
    """(run-start indices, sampled control indices, eligible bar count).

    Only bars with enough history behind them are eligible, on both sides: a
    control drawn from the warm-up region would be compared against cases that
    all have full indicators, and the difference would be the warm-up.

    `hi` bounds where a bar may START, and it is NOT the end of the frame. The
    first version had no such bound, so on the cache source -- whose frames run
    to 20:00 -- it drew cases and controls from the regular session and after
    hours while the report's header said 04:00-09:30. The forward window may
    still read past `hi`: a run beginning at 09:28 finishes when it finishes.
    """
    close = sig["close"].to_numpy(dtype=float)
    low = sig["low"].to_numpy(dtype=float)
    r, n = cell
    last = len(close) - n if hi is None else min(hi, len(close) - n)
    found = runs_in(close, low, adverse, [r], [n])[(r, n)]
    starts = sorted(t for t, _, _ in found if warm <= t < last)
    eligible = [i for i in range(warm, last)]
    if not eligible:
        return [], [], 0
    case_set = set(starts)
    pool = [i for i in eligible if i not in case_set]
    k = min(len(pool), len(starts) * CONTROLS_PER_CASE)
    controls = ([] if k == 0
                else sorted(rng.choice(pool, size=k, replace=False).tolist()))
    return starts, controls, len(eligible)


def rng_for(seed: int, day: str, symbol: str) -> np.random.Generator:
    """A generator fixed by (seed, day, symbol), not by processing order.

    The first version threaded ONE generator through every symbol-day in
    sequence, so which bars became controls depended on the order they were
    reached -- which means on the number of workers. Two runs of the same seed
    could then disagree, and the only way to reproduce a report would be to
    remember how many cores it was run on.

    zlib.crc32, not hash(): Python salts hash() per process, so a
    process-pool worker would seed differently from the parent.
    """
    key = zlib.crc32(f"{day}:{symbol}".encode()) & 0xFFFFFFFF
    return np.random.default_rng([int(seed), key])


def collect(sig: pd.DataFrame, idx: list[int], is_case: bool, symbol: str,
            date_str: str, weight: float, ctx: dict | None = None) -> list[dict]:
    out = []
    for i in idx:
        f = features_at(sig, i, ctx)
        f.update(case=1 if is_case else 0, weight=weight,
                 symbol=symbol, date=date_str)
        out.append(f)
    return out


MIN_PER_BUCKET = 25        # a quartile thinner than this is not a measurement


def wbuckets(rows: list[dict], name: str, q: int = QUANTILES,
             min_per_bucket: int = MIN_PER_BUCKET) -> list[dict]:
    """Quantile buckets with the WEIGHTED run rate in each.

    Edges come from the sampled population; the rate inside each bucket is
    restored to the true base rate by the case-control weights. Both halves of
    that are necessary: unweighted edges on a weighted rate would put the right
    number in the wrong bucket.
    """
    vals = [(r[name], r["case"], r["weight"]) for r in rows
            if r.get(name) is not None and r[name] == r[name]]
    if len(vals) < q * min_per_bucket or why_not_bucketable(
            [{name: v[0], "net": 0.0} for v in vals], name, q):
        return []
    vals.sort(key=lambda x: x[0])
    out, n = [], len(vals)
    for k in range(q):
        lo, hi = n * k // q, n * (k + 1) // q
        chunk = vals[lo:hi]
        if not chunk:
            continue
        wcase = sum(w for _, c, w in chunk if c)
        wall = sum(w for _, _, w in chunk)
        out.append({"lo": chunk[0][0], "hi": chunk[-1][0], "n": len(chunk),
                    "cases": sum(c for _, c, _ in chunk),
                    "rate": (wcase / wall * 100.0) if wall else float("nan"),
                    "wcase": wcase, "wall": wall})
    return out


VOL_PROXY = "range_pct"    # the yardstick for "is this just volatility?"


def spearman(rows: list[dict], a: str, b: str) -> float:
    """Rank correlation between two features over the sampled rows.

    Rank, not Pearson: these features are heavy-tailed (dollar volume spans
    four orders of magnitude) and a single outlier would otherwise set the
    number. Returns 0.0 when either side has no spread to rank.
    """
    pairs = [(r[a], r[b]) for r in rows
             if r.get(a) is not None and r[a] == r[a]
             and r.get(b) is not None and r[b] == r[b]]
    if len(pairs) < 25:
        return 0.0
    x = np.array([p[0] for p in pairs], dtype=float)
    y = np.array([p[1] for p in pairs], dtype=float)

    def rank(v):
        """Average ranks within ties.

        Handing tied values DISTINCT ranks (which plain argsort does) invents
        an ordering that is not in the data: a feature that is the same number
        on every row came back with a non-zero correlation to everything,
        because its 'ranks' were really its row order.
        """
        n_ = len(v)
        order = v.argsort()
        sv = v[order]
        grp = np.cumsum(np.r_[True, sv[1:] != sv[:-1]]) - 1
        avg = (np.bincount(grp, weights=np.arange(n_, dtype=float))
               / np.bincount(grp))
        rk = np.empty(n_, dtype=float)
        rk[order] = avg[grp]
        return rk

    rx, ry = rank(x), rank(y)
    if rx.std() == 0 or ry.std() == 0:
        return 0.0
    return float(np.corrcoef(rx, ry)[0, 1])


def split(rows: list[dict]) -> tuple[list, list]:
    dates = sorted({r["date"] for r in rows})
    if len(dates) < 2:
        return rows, []
    cut = dates[len(dates) // 2]
    return ([r for r in rows if r["date"] < cut],
            [r for r in rows if r["date"] >= cut])


def tier(ba: list[dict], bb: list[dict], base_a: float, base_b: float
         ) -> tuple[str, str]:
    """CANDIDATE / WEAK / NOTHING, on LIFT rather than on dollars.

    Same shape test as the feature study -- monotone the same way in both
    halves -- because two ends differing is what noise looks like there too.
    """
    if not ba or not bb:
        return "NOTHING", "a half could not be bucketed (reason above)"
    la = [b["rate"] for b in ba]
    lb = [b["rate"] for b in bb]
    ea = (la[-1] / la[0]) if la[0] else float("inf")
    eb = (lb[-1] / lb[0]) if lb[0] else float("inf")
    # Direction agrees if both ends move the same way relative to their own base.
    same = (la[-1] > la[0]) == (lb[-1] > lb[0])
    big = min(max(ea, 1 / ea if ea else 0),
              max(eb, 1 / eb if eb else 0)) >= MIN_LIFT
    ma = monotone([{"mean": x} for x in la])
    mb = monotone([{"mean": x} for x in lb])
    if ma and ma == mb and same and big:
        return "CANDIDATE", (f"monotone both halves, top/bottom lift "
                             f"{ea:.2f}x and {eb:.2f}x")
    if same and big:
        return "WEAK", (f"ends agree ({ea:.2f}x, {eb:.2f}x) but the buckets "
                        "between them do not line up")
    if same:
        return "NOTHING", (f"ends agree but the smaller lift is {min(ea, eb):.2f}x, "
                           f"under {MIN_LIFT:.2f}x")
    return "NOTHING", "the halves DISAGREE in direction"



def _usable(df, warm: int) -> str:
    if len(df) < MIN_BARS + warm:
        return "short"
    c = df["close"].to_numpy(dtype=float)
    if not np.isfinite(c).all():
        return "nan"
    if c.min() < MIN_PRICE:
        return "under $1"
    if c.max() > MAX_PRICE:
        return "reverse-split price"
    return ""


def process_slice(args: tuple) -> dict:
    """One archive day, start to finish. Module-level and picklable so a
    process pool can run it; the sequential path calls it too, so there is one
    implementation rather than two that can drift.

    The previous day is RE-READ here rather than carried in from the caller.
    That costs one extra decode per day and is what makes the days independent
    -- without it the warm-up is a chain and nothing can be parallel.
    """
    from common.dbn_io import read_dbn
    from strategy.mcl import mcl as MCL

    (path, prev_path, cell, adverse, warm, seed) = args
    day = Path(path).name[:10]
    frame = read_dbn(path)
    rows: list[dict] = []
    skips: dict[str, int] = {}
    bars = sym_days = 0
    if frame.empty:
        return {"day": day, "rows": rows, "skips": skips, "bars": 0,
                "sym_days": 0, "used": False}

    back: dict[str, pd.DataFrame] = {}
    if prev_path:
        pf = read_dbn(prev_path)
        if not pf.empty:
            for sym, d in pf.groupby("symbol"):
                back[str(sym)] = d.sort_index()

    used = False
    for sym, df in frame.groupby("symbol"):
        sym = str(sym)
        df = df.sort_index()
        sym_days += 1
        b = back.get(sym)
        full = pd.concat([b, df]) if b is not None else df
        why = _usable(full, warm)
        if why:
            skips[why] = skips.get(why, 0) + 1
            continue
        first = len(full) - len(df)
        base = max(0, first - warm)
        raw = full.iloc[base:]
        hi = len(full) - base
        starts, controls, elig = label_and_sample(
            raw, cell, adverse, rng_for(seed, day, sym), warm, hi)
        if not elig:
            skips["no eligible bars"] = skips.get("no eligible bars", 0) + 1
            continue
        bars += elig
        if not starts:
            skips["no run start"] = skips.get("no run start", 0) + 1
            continue
        sig = MCL.signals(full).iloc[base:]
        ctx = frame_ctx(sig)
        n_ctrl = len(controls)
        w = ((elig - len(starts)) / n_ctrl) if n_ctrl else 1.0
        rows.extend(collect(sig, starts, True, sym, day, 1.0, ctx))
        rows.extend(collect(sig, controls, False, sym, day, w, ctx))
        used = True
    return {"day": day, "rows": rows, "skips": skips, "bars": bars,
            "sym_days": sym_days, "used": used}


def render(rows: list[dict], cell: tuple[float, int], adverse: float,
           bars: int, sessions: int, sym_days: int, skips: dict,
           source: str, elapsed: float) -> list[str]:
    r, n = cell
    n_case = sum(x["case"] for x in rows)
    n_ctrl = len(rows) - n_case
    wcase = sum(x["weight"] for x in rows if x["case"])
    wall = sum(x["weight"] for x in rows)
    base = (wcase / wall * 100.0) if wall else float("nan")

    L = [f"WHAT PRECEDES A RUN, IF ANYTHING?", "",
         f"  a run = close rises {r:.0f}% within {n} bars, never having dipped "
         f"{adverse:.1f}% first",
         f"  source: {source}   window 04:00-09:30 ET",
         f"  {sym_days:,} symbol-day(s) over {sessions:,} session(s)",
         f"  {bars:,} eligible bars", ""]
    if skips:
        L += [f"  {sum(skips.values()):,} symbol-day(s) NOT used, by reason:"]
        for why, k in sorted(skips.items(), key=lambda x: -x[1]):
            L.append(f"      {k:>6,}  {why}")
        L.append("")
    if not rows or not n_case:
        return L + ["NOTHING TO SEPARATE", "",
                    "  No run starts in this population.", ""]

    L += ["THE SAMPLE, AND THE WEIGHT THAT UNDOES IT", "",
          f"  {'run starts (all of them)':<34}{n_case:>12,}",
          f"  {'non-starts (sampled)':<34}{n_ctrl:>12,}",
          f"  {'mean weight on a non-start':<34}"
          f"{(sum(x['weight'] for x in rows if not x['case']) / n_ctrl):>12.2f}"
          if n_ctrl else "  (no non-starts sampled)",
          f"  {'run rate IN THE SAMPLE':<34}"
          f"{n_case / len(rows) * 100.0:>11.2f}%",
          f"  {'run rate RESTORED (the real one)':<34}{base:>11.2f}%", "",
          "  The sample rate is the one that flatters and it is printed only",
          "  so the correction is visible. Every rate below is the restored",
          "  one.", ""]

    a, b = split(rows)

    def base_of(part):
        wc = sum(x["weight"] for x in part if x["case"])
        wa = sum(x["weight"] for x in part)
        return (wc / wa * 100.0) if wa else float("nan")

    base_a, base_b = base_of(a), base_of(b)
    L += [f"  early half base {base_a:.2f}%     late half base {base_b:.2f}%", ""]

    tiers: dict[str, str] = {}
    L += ["EVERY FEATURE, BOTH HALVES  (nothing ranked, nothing omitted)", "",
          "  each cell: the restored % of bars in that quartile that started a "
          "run", ""]
    for f, desc in FEATURES.items():
        L += [f"  {f}", f"    {desc}", ""]
        ba, bb = wbuckets(a, f), wbuckets(b, f)
        for label, bs, bse in (("early", ba, base_a), ("late", bb, base_b)):
            if not bs:
                L.append(f"    {label:<6} too few bars to bucket")
                continue
            cells = "  ".join(
                f"{x['rate']:.2f}% ({x['rate'] / bse:.2f}x)" for x in bs)
            L.append(f"    {label:<6} {cells}")
        tl, why = tier(ba, bb, base_a, base_b)
        tiers[f] = tl
        L += ["", f"    [{tl}] {why}", ""]

    cand = sorted({fam for fam, cols in FAMILIES.items()
                   if any(tiers.get(c) == "CANDIDATE" for c in cols)})
    weak = sorted({fam for fam, cols in FAMILIES.items()
                   if any(tiers.get(c) == "WEAK" for c in cols)
                   and fam not in cand})
    L += ["", "TIERS, COUNTED BY FAMILY", "",
          f"  {len(FAMILIES)} families over {len(FEATURES)} columns.", "",
          f"  CANDIDATE  {len(cand)}   " + (", ".join(cand) if cand else "none"),
          f"  WEAK       {len(weak)}   " + (", ".join(weak) if weak else "none"),
          ""]

    L += ["", "WHAT A RULE ON THE BEST-LOOKING QUARTILE WOULD ACTUALLY DO", "",
          "  for every feature, taking its TOP quartile as an entry condition.",
          "  precision = of the bars it fires on, the share that start a run.",
          "  recall = of all the runs, the share it would be present for.",
          "  A quartile is a quarter of all bars, so recall near 25% means the",
          "  feature is telling you nothing at all.", ""]
    L += ["  " + "feature".ljust(20) + "precision".rjust(11)
          + "recall".rjust(9) + "lift".rjust(8) + "  |r| vol".rjust(10)
          + "   tier"]
    L += ["  " + "-" * 68]
    for f in FEATURES:
        bs = wbuckets(rows, f)
        if not bs:
            continue
        top = bs[-1]
        prec = top["rate"]
        rec = (top["wcase"] / wcase * 100.0) if wcase else float("nan")
        rv = abs(spearman(rows, f, VOL_PROXY))
        L.append("  " + f.ljust(20) + f"{prec:>10.2f}%" + f"{rec:>8.1f}%"
                 + f"{prec / base:>7.2f}x" + f"{rv:>10.2f}"
                 + f"   {tiers.get(f, '')}")

    L += ["", "  |r| vol is |Spearman| against " + VOL_PROXY + ", and it is the",
          "  column to read first. A run is DEFINED as a percentage move, and",
          "  volatility is the propensity to make percentage moves -- so a",
          "  feature that is mostly a volatility proxy predicts runs almost by",
          "  construction, and finding that it does is not a discovery. A high",
          "  lift next to a high |r| vol is the definition looking at itself.",
          "",
          "  The families below were inherited from `entry_features`, where the",
          "  question was different. They do NOT collapse volatility proxies,",
          "  so a count of candidate families OVERSTATES the number of",
          "  independent findings here. Read the correlation column, not the",
          "  count."]

    L += ["", "", "HOW TO READ THIS", "",
          f"  The base rate is {base:.2f}%. A feature whose top quartile shows",
          f"  {base * 2:.2f}% has doubled your odds and is still wrong",
          f"  {100 - base * 2:.1f}% of the time. Lift is the interesting number",
          "  and precision is the one you trade.",
          "",
          f"  A lift under {MIN_LIFT:.2f}x is treated as nothing here. That is a",
          "  judgement, stated so it can be argued with: below it, a condition",
          "  cannot pay for the false positives it admits at any threshold.",
          "",
          "  Both halves, always. A feature that separates in one half and not",
          "  the other is noise, and pooling them would hide exactly that.",
          "",
          "WHAT THIS IS NOT", "",
          "  Not a P&L. `started a run` is not `made money` -- that needs an",
          "  exit, and the exit is a separate question with its own choices in",
          "  it. Nothing here should be turned into a backtest without one.",
          "",
          "  Not out of sample. `var/state/holdout.json` is NOT touched.",
          "",
          "  Not a chosen cell. This is the "
          f"{r:.0f}%-in-{n} definition, named on the",
          "  command line. Running every cell and keeping the best-looking one",
          "  is the selection these reports exist to resist.",
          "",
          "  Not free of the universe. These are the symbols the screen already",
          "  surfaced; a run in a name it never showed is invisible here."]
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--source", default="cache", choices=["archive", "cache"])
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default="XNAS.BASIC")
    p.add_argument("--cache", default="bar_cache")
    p.add_argument("--pairs", default="var/state/traded_pairs.json")
    p.add_argument("--cell", default="8x15",
                   help="the run definition, RxN. Named here and printed in "
                        "the report so it is never chosen silently.")
    p.add_argument("--adverse", type=float, default=None)
    p.add_argument("--seed", type=int, default=0,
                   help="the control sample is random; the seed is recorded "
                        "so the run reproduces.")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--jobs", type=int, default=1,
                   help="worker processes for --source archive. Each day is "
                        "independent once its warm-up day is re-read, and the "
                        "control sample is seeded per symbol-day, so the "
                        "answer does not depend on how many are used. 0 means "
                        "one per core.")
    p.add_argument("--out", default=None)
    return p


def main(argv=None) -> int:
    import time
    from common.run_census import A_PCT
    from strategy.mcl import mcl as MCL

    a = build_parser().parse_args(argv)
    cell = parse_cell(a.cell)
    adverse = A_PCT if a.adverse is None else a.adverse
    warm = MCL.MIN_BARS_REQUIRED

    rows: list[dict] = []
    skips: dict[str, int] = {}
    bars = sym_days = 0
    days: set[str] = set()
    t0 = time.time()

    def one(raw: pd.DataFrame, make_sig, symbol: str, date_str: str,
            hi: int | None = None) -> None:
        """Label first, build indicators only if there is something to label.

        LABELLING NEEDS ONLY close AND low -- no indicators at all -- while
        MCL.signals costs ~12 ms whatever the frame size, because the cost is
        pandas per-call overhead rather than bars. The first version computed
        signals for every symbol-day and then threw ~85% of them away, since
        most symbol-days have no run start: 79 minutes of the archive run was
        indicator maths for bars that were never going to be used.

        `make_sig` is therefore a thunk, called only past the no-starts gate.
        Eligible bars are still counted for every symbol-day -- that is the
        denominator, and skipping it would inflate every rate on the page.
        """
        nonlocal bars
        starts, controls, elig = label_and_sample(
            raw, cell, adverse, rng_for(a.seed, date_str, symbol), warm, hi)
        if not elig:
            skips["no eligible bars"] = skips.get("no eligible bars", 0) + 1
            return
        bars += elig
        if not starts:
            # A symbol-day with no run contributes no cases, and its controls
            # would carry a weight derived from a case count of zero. Skipped,
            # and counted, rather than folded in with an invented weight.
            skips["no run start"] = skips.get("no run start", 0) + 1
            return
        sig = make_sig()
        n_ctrl = len(controls)
        pool = elig - len(starts)
        w = (pool / n_ctrl) if n_ctrl else 1.0
        ctx = frame_ctx(sig)
        rows.extend(collect(sig, starts, True, symbol, date_str, 1.0, ctx))
        rows.extend(collect(sig, controls, False, symbol, date_str, w, ctx))
        days.add(date_str)

    def usable(df: pd.DataFrame) -> str:
        if len(df) < MIN_BARS + warm:
            return "short"
        c = df["close"].to_numpy(dtype=float)
        if not np.isfinite(c).all():
            return "nan"
        if c.min() < MIN_PRICE:
            return "under $1"
        if c.max() > MAX_PRICE:
            return "reverse-split price"
        return ""

    if a.source == "cache":
        from common.cache_io import (SHARED_DURATION, SHARED_END_HHMM,
                                     load_cached_bars, load_pairs, window_dir)
        pairs = load_pairs(Path(a.pairs))
        if a.limit:
            pairs = pairs[:a.limit]
        cache = window_dir(Path(a.cache), SHARED_DURATION, SHARED_END_HHMM)
        for k_pair, p in enumerate(pairs, 1):
            if k_pair % 50 == 0 or k_pair == len(pairs):
                print(f"  [{k_pair:>5}/{len(pairs)}] {len(rows):>9,} rows  "
                      f"{(time.time() - t0) / 60:.1f} min", flush=True)
            df = load_cached_bars(cache, p["symbol"], p["date"])
            sym_days += 1
            if df is None or df.empty:
                skips["no bars"] = skips.get("no bars", 0) + 1
                continue
            df.index = (df.index.tz_localize("UTC") if df.index.tz is None
                        else df.index.tz_convert("UTC"))
            df = df.sort_index()
            why = usable(df)
            if why:
                skips[why] = skips.get(why, 0) + 1
                continue
            # Label only this session's premarket bars; the prior session is
            # present for warm-up and must not contribute cases or controls.
            local = df.index.tz_convert(ET)
            day = datetime.strptime(p["date"], "%Y-%m-%d").date()
            keep = np.array([(t.date() == day and 240 <= t.hour * 60 + t.minute
                              < 570) for t in local])
            if keep.sum() < MIN_BARS:
                skips["short"] = skips.get("short", 0) + 1
                continue
            first = int(np.argmax(keep))
            last = len(keep) - 1 - int(np.argmax(keep[::-1]))
            base = max(0, first - warm)
            # The frame runs to 20:00; a case or control may only START inside
            # 04:00-09:30, which is what the header claims.
            one(df.iloc[base:], lambda d=df, b=base: MCL.signals(d).iloc[b:],
                p["symbol"], p["date"], hi=last - base + 1)
    else:
        from common.databento_fetch import default_archive
        from common.dbn_io import read_dbn
        from common.screen_sim import date_of, window_slices
        archive = Path(a.archive) if a.archive else default_archive()
        slices = window_slices(archive, a.dataset)
        if not slices:
            sys.exit(f"no 04:00-09:30 window slices under "
                     f"{archive}/{a.dataset}/ohlcv-1m.")
        if a.limit:
            slices = slices[-a.limit:]
        tasks = [(str(path), str(slices[k - 1]) if k else "",
                  cell, adverse, warm, a.seed)
                 for k, path in enumerate(slices)]
        jobs = (os.cpu_count() or 1) if a.jobs == 0 else max(1, a.jobs)

        def absorb(res: dict, k: int) -> None:
            nonlocal bars, sym_days
            rows.extend(res["rows"])
            bars += res["bars"]
            sym_days += res["sym_days"]
            for why, n_ in res["skips"].items():
                skips[why] = skips.get(why, 0) + n_
            if res["used"]:
                days.add(res["day"])
            el = time.time() - t0
            eta = (len(tasks) - k) / (k / el) / 60.0 if el and k else 0.0
            print(f"  [{k:>4}/{len(tasks)}] {res['day']}  {len(rows):>9,} rows"
                  f"  {el / 60:>5.1f} min elapsed  ~{eta:>5.1f} min left",
                  flush=True)

        if jobs == 1:
            for k, t in enumerate(tasks, 1):
                absorb(process_slice(t), k)
        else:
            # Days are independent because each worker re-reads its own warm-up
            # day, and the control sample is seeded per symbol-day rather than
            # by arrival order -- so the answer is the same at any --jobs.
            print(f"  {jobs} worker process(es) over {len(tasks)} slice(s)",
                  flush=True)
            from concurrent.futures import ProcessPoolExecutor
            with ProcessPoolExecutor(max_workers=jobs) as ex:
                for k, res in enumerate(ex.map(process_slice, tasks,
                                               chunksize=1), 1):
                    absorb(res, k)

    if not rows:
        sys.exit(f"no run starts found in {sym_days:,} symbol-day(s).")

    out = a.out or f"var/reports/run_signal_{a.cell}.txt"
    emit("\n".join(render(rows, cell, adverse, bars, len(days), sym_days,
                          skips, a.source, time.time() - t0)),
         out, header=f"common.run_signal  cell={a.cell} source={a.source} "
                     f"seed={a.seed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
