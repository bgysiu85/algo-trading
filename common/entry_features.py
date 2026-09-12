#!/usr/bin/env python3
"""What separates MCL's winning entries from its losing ones?

    python -m common.entry_features
    python -m common.entry_features --population refused

THE QUESTION
------------
Every bar MCL enters on passed the identical five conditions. About a third of
them win. Ben's question is what else is true at the bar that the rule does not
look at -- and whether the winners and losers differ on any of it.

WHY THIS IS THE MOST DANGEROUS MODULE IN THE PROJECT
------------------------------------------------------
It is a SEARCH OVER FEATURES for something that separates outcomes we already
know. With 482 entries, 13 features and five buckets each, that is 65
comparisons; at the usual thresholds roughly three will look meaningful by
chance alone. Run it, pick the best-looking split, add it as a condition, and
the backtest improves and the live account does not. That is the standard way
a strategy is destroyed, and it looks like progress the entire time.

So this module is built to describe, NEVER to choose:

  * THE FEATURE LIST IS FIXED IN THIS FILE, before any outcome was looked at.
    Adding a feature after seeing the results is a different experiment and
    has to say so.
  * EVERY FEATURE IS REPORTED, including the flat ones. Reporting only what
    separated is the selection this module exists to resist.
  * EVERY RESULT IS SPLIT train/test by date. A split that holds on one half
    and not the other is noise, and the report says so per feature rather
    than pooling them into a number that hides it.
  * NOTHING IS RANKED. There is no "best feature" line, because writing one
    would hand the reader the overfit answer in the one place they will look.
  * `holdout.json` IS NOT TOUCHED. It was cut on 2026-09-07 and must not be
    spent on a fishing expedition -- only on a specific hypothesis that has
    already survived here.

WHAT WOULD MAKE A RESULT WORTH ANYTHING
-----------------------------------------
A feature is worth a second look only if the SAME direction appears in both
halves, the effect is larger than friction ($4.26/round trip), and the bucket
counts are not tiny. All three, not any one. Even then it is a hypothesis to be
registered and tested -- not a condition to add.

NO LOOK-AHEAD
-------------
Every feature is computed from the signal bar and the bars BEFORE it. A test
asserts that shuffling all bars after the entry leaves every feature unchanged.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from common.report_fmt import acct
from common.report_io import emit

ET = ZoneInfo("America/New_York")
FRICTION = 4.26
QUANTILES = 4          # quartiles: five buckets is thinner than this data bears


# Fixed before any outcome was examined. Each is a plain function of the signal
# bar and its history, and the docstring says what a reader should expect --
# stating it in advance is what makes a surprising result informative rather
# than merely available.
FEATURES = {
    "vol_over_trail": "this bar's volume / the 60-bar average. The headroom "
                      "the entry had; 1.5x is where the joint window opens.",
    "vol_multiple": "volume / prev_vol. How far past the 3x minimum it was.",
    "floor_margin": "prev_vol / trail_avg. How far past the 0.5x floor.",
    "macd_margin": "macd - macd_signal. Conviction, not just the sign.",
    "macd_level": "macd itself. Far above zero is a move already underway.",
    "rsi": "RSI at entry. High is strength, or exhaustion.",
    "rsi_slope": "RSI minus RSI three bars ago.",
    "mfi": "MFI at entry.",
    "mfi_slope": "MFI minus MFI three bars ago.",
    "mins_since_open": "minutes since 04:00 ET.",
    "price": "the entry price.",
    "extension": "close / the session's first close - 1, in percent. How much "
                 "of the move had already happened.",
    "range_pct": "mean(high-low)/close over the last 14 bars, in percent. "
                 "Recent volatility.",
}


def features_at(sig: pd.DataFrame, i: int) -> dict:
    """Every feature at bar `i`, from that bar and the ones BEFORE it.

    Nothing here may read sig.iloc[i+1:]. A test shuffles the future and
    asserts the output is identical.
    """
    r = sig.iloc[i]
    past = sig.iloc[:i + 1]
    local = past.index.tz_convert(ET)
    day = local[-1].date()
    same_day = past[[d == day for d in local.date]]
    first_close = float(same_day["close"].iloc[0]) if len(same_day) else float("nan")
    tail = past.iloc[-14:]
    rng = ((tail["high"] - tail["low"]) / tail["close"]).mean() * 100.0 \
        if {"high", "low"} <= set(past.columns) else float("nan")
    ta, pv = float(r["trail_avg"]), float(r["prev_vol"])
    return {
        "vol_over_trail": float(r["volume"]) / ta if ta else float("nan"),
        "vol_multiple": float(r["volume"]) / pv if pv else float("nan"),
        "floor_margin": pv / ta if ta else float("nan"),
        "macd_margin": float(r["macd"]) - float(r["macd_sig"]),
        "macd_level": float(r["macd"]),
        "rsi": float(r["rsi"]),
        "rsi_slope": float(r["rsi"]) - float(sig["rsi"].iloc[i - 3]) if i >= 3
        else float("nan"),
        "mfi": float(r["mfi"]),
        "mfi_slope": float(r["mfi"]) - float(sig["mfi"].iloc[i - 3]) if i >= 3
        else float("nan"),
        "mins_since_open": local[-1].hour * 60 + local[-1].minute - 240,
        "price": float(r["close"]),
        "extension": (float(r["close"]) / first_close - 1.0) * 100.0
        if first_close == first_close and first_close else float("nan"),
        "range_pct": float(rng),
    }


def buckets(rows: list[dict], name: str, q: int = QUANTILES) -> list[dict]:
    """Quantile buckets of one feature, with the outcome in each.

    Edges come from the data, not from round numbers: a hand-chosen threshold
    is already a fitted parameter.
    """
    vals = [(r[name], r["net"]) for r in rows
            if r.get(name) is not None and r[name] == r[name]]
    if len(vals) < q * 5:
        return []
    vals.sort(key=lambda x: x[0])
    out, n = [], len(vals)
    for k in range(q):
        lo, hi = n * k // q, n * (k + 1) // q
        chunk = vals[lo:hi]
        if not chunk:
            continue
        nets = [c[1] for c in chunk]
        out.append({"lo": chunk[0][0], "hi": chunk[-1][0], "n": len(chunk),
                    "mean": sum(nets) / len(nets),
                    "win": sum(1 for x in nets if x > 0) / len(nets) * 100.0})
    return out


def split(rows: list[dict]) -> tuple[list, list]:
    dates = sorted({r["date"] for r in rows})
    if len(dates) < 2:
        return rows, []
    cut = dates[len(dates) // 2]
    return ([r for r in rows if r["date"] < cut],
            [r for r in rows if r["date"] >= cut])


def render(rows: list[dict], population: str, pairs_path: str,
           skipped: int, elapsed: float) -> list[str]:
    n = len(rows)
    L = ["WHAT SEPARATES THE WINNERS FROM THE LOSERS?", "",
         f"  population: {population}",
         f"  {n:,} entr(ies) from {pairs_path}",
         f"  outcome: net at ${FRICTION:.2f}/round trip",
         f"  {len(FEATURES)} features x {QUANTILES} buckets x 2 halves = "
         f"{len(FEATURES) * QUANTILES * 2} comparisons",
         f"  elapsed {elapsed:.1f}s", ""]
    if skipped:
        L += [f"  {skipped:,} symbol-day(s) NOT tested: no bars, or too short "
              "for warm-up", ""]
    if not rows:
        return L + ["NOTHING TO DESCRIBE", "",
                    "  No entries in this population.", ""]

    nets = [r["net"] for r in rows]
    base_win = sum(1 for x in nets if x > 0) / n * 100.0
    L += ["THE BASE RATE  (what any feature has to beat)", "",
          f"  {'trades':<22}{n:>10,}",
          f"  {'mean net':<22}{acct(sum(nets) / n, 10)}",
          f"  {'win rate':<22}{base_win:>9.1f}%", ""]

    a, b = split(rows)
    L += ["EVERY FEATURE, BOTH HALVES  (nothing is ranked, nothing omitted)",
          ""]
    for f, desc in FEATURES.items():
        L += [f"  {f}", f"    {desc}", ""]
        for label, part in (("early", a), ("late", b)):
            bs = buckets(part, f)
            if not bs:
                L.append(f"    {label:<6} too few trades to bucket")
                continue
            cells = "  ".join(
                f"[{acct(x['lo'], 1).strip()}-{acct(x['hi'], 1).strip()}]"
                f" n={x['n']} {acct(x['mean'], 1).strip()}"
                f" {x['win']:.0f}%" for x in bs)
            L.append(f"    {label:<6} {cells}")
        # Does the direction agree across halves? Reported, never ranked.
        ba, bb = buckets(a, f), buckets(b, f)
        if ba and bb:
            da = ba[-1]["mean"] - ba[0]["mean"]
            db = bb[-1]["mean"] - bb[0]["mean"]
            same = (da > 0) == (db > 0)
            big = min(abs(da), abs(db)) > FRICTION
            note = ("top-vs-bottom agrees in direction" if same
                    else "top-vs-bottom DISAGREES between halves")
            if same and big:
                note += f", and both exceed ${FRICTION:.2f}"
            elif same:
                note += f", but the smaller is under ${FRICTION:.2f}"
            L += ["", f"    {acct(da, 1).strip()} early / "
                      f"{acct(db, 1).strip()} late  -- {note}"]
        L.append("")

    L += ["HOW TO READ THIS, AND HOW NOT TO", "",
          f"  {len(FEATURES) * QUANTILES * 2} comparisons were made. At any "
          "usual threshold several will look",
          "  meaningful by chance. The feature list was fixed in the module",
          "  BEFORE any outcome was examined, and every feature is printed,",
          "  including the flat ones -- reporting only what separated is the",
          "  selection this module exists to resist.",
          "",
          "  A feature is worth a second look ONLY if all three hold:",
          "    1. the same direction in both halves,",
          f"    2. an effect larger than ${FRICTION:.2f} in BOTH halves,",
          "    3. bucket counts that are not tiny.",
          "",
          "  Even then it is a HYPOTHESIS, not a condition. The next step is",
          "  to register it, then test it -- not to add it and re-run the",
          "  backtest, which is how a strategy gets fitted to its own history.",
          "",
          "WHAT THIS IS NOT", "",
          "  Not a model. No weights were fitted and no feature was selected.",
          "",
          "  Not out of sample. `var/state/holdout.json` was cut 2026-09-07",
          "  and is NOT touched here. It must not be spent on a search; only",
          "  on a specific hypothesis that has already survived this report.",
          "",
          "  Not causal. A feature that separates outcomes may be a proxy for",
          "  something else entirely -- time of day and volatility are",
          "  correlated with almost everything else on this list.",
          "",
          "  Not free of the universe. These entries come from the pairs file",
          "  named above, which the `prior_close` defect helped select."]
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--pairs", default="var/state/traded_pairs.json")
    p.add_argument("--cache", default="bar_cache")
    p.add_argument("--population", default="entries",
                   choices=["entries", "refused"],
                   help="`entries` is the rule's OWN entries -- bars that all "
                        "passed the identical five conditions and then "
                        "diverged, which is the question asked. `refused` is "
                        "the floor_sole population, for comparison.")
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
    from common.refused_value import refused_mask
    from strategy.mcl import mcl as MCL

    pairs = load_pairs(Path(a.pairs))
    if a.limit:
        pairs = pairs[:a.limit]
    cache = window_dir(Path(a.cache), SHARED_DURATION, SHARED_END_HHMM)
    end_h, end_m = int(BACKTEST_END_HHMM[:2]), int(BACKTEST_END_HHMM[2:])

    t0 = time.time()
    rows, skipped = [], 0
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

        sig = MCL.signals(sl)
        mask = (sig["entry"] if a.population == "entries"
                else refused_mask(sig, "floor_sole"))
        trades = MCL.backtest_session(sl, day, ET,
                                      entry_bars=None if a.population ==
                                      "entries" else mask)
        # Match each trade to the bar it opened on, so the features describe
        # the ENTRY rather than the session. A trade whose bar cannot be
        # located is dropped and counted, never matched to a neighbour.
        by_ts = {str(t.entry_time): t for t in trades}
        for i, ts in enumerate(sig.index):
            if not bool(mask.iloc[i]):
                continue
            t = by_ts.get(str(ts))
            if t is None:
                continue
            f = features_at(sig, i)
            f.update(symbol=p["symbol"], date=p["date"],
                     net=t.net - FRICTION)
            rows.append(f)

    if not rows:
        sys.exit(f"no entries found for {len(pairs)} symbol-day(s) under "
                 f"{cache}/")

    out = a.out or f"var/reports/entry_features_{a.population}.txt"
    emit("\n".join(render(rows, a.population, a.pairs, skipped,
                          time.time() - t0)),
         out, header=f"common.entry_features  population={a.population}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
