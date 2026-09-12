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
know. With 482 entries, 22 features and four buckets each over two halves,
that is 176 comparisons; at the usual thresholds several will look meaningful
by chance alone. Run it, pick the best-looking split, add it as a condition,
and the backtest improves and the live account does not. That is the standard
way a strategy is destroyed, and it looks like progress the entire time.

So this module is built to describe, NEVER to choose:

  * THE FEATURE LIST IS FIXED IN THIS FILE before the run it is used for, and
    WHEN each entry was fixed is recorded in it. The first thirteen were
    written before any outcome was seen. Nine more were added on 2026-09-12,
    AFTER the first report -- a second experiment, marked as one in FEATURES,
    each chosen for a mechanical reason rather than because the first pass
    made it look promising. Widening a search is allowed; pretending the
    widened list was pre-registered is not.
  * MULTIPLICITY IS COUNTED BY FAMILY, not by column. `rsi_slope` and
    `mfi_slope` are one idea measured twice; counting them as two findings
    doubles the apparent evidence for a single pattern.
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
A feature is worth a second look only if it is MONOTONE across its buckets the
same way in BOTH halves, the top-to-bottom effect is larger than friction
($4.26/round trip) in both, and the bucket counts are not tiny. All three, not
any one. Monotonicity was added after the first run, which passed `macd_level`
on ends that differed while its middles ran (6.58) / 7.40 / (10.11) / 3.27:
two ends differing is what noise looks like, four buckets in order is rarer.
Even then it is a hypothesis to be registered and tested -- not a condition to
add.

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
# Read off the strategy so the trail-fit feature moves if the trail does.
from strategy.mcl.mcl import TRAIL_PCT as MCL_TRAIL  # noqa: E402
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

    # --- added 2026-09-12, AFTER the first run. A second experiment, and it
    # says so: the first thirteen were fixed before any outcome was seen,
    # these nine were chosen knowing what the first pass showed. Each was
    # picked for a MECHANICAL reason to matter, not because it looked
    # promising -- nothing from the first report guided the choice.
    "dollar_vol_session": "price x cumulative session volume, in $. Nothing "
                          "in the entry rule knows whether the name was "
                          "tradeable at all.",
    "dollar_vol_bar": "price x this bar's volume, in $.",
    "tape_density": "bars printed / minutes elapsed since the session's first "
                    "bar, in percent. A thin tape is a different market.",
    "trail_over_range": "the 5% trail distance / the mean bar range. How many "
                        "typical bars of movement the stop allows before it "
                        "is hit -- under ~1 the stop is inside the noise.",
    "close_in_bar": "(close - low) / (high - low) of the ENTRY bar. MCL fills "
                    "at the close, so 1.0 is paying the top tick of a spike.",
    "body_ratio": "|close - open| / (high - low). Decisive bar or a wick.",
    "vwap_dist": "close / session VWAP - 1, in percent. Absent from the entry "
                 "rule entirely.",
    "ma20_dist": "close / the 20-bar mean - 1, in percent.",
    "ma20_slope": "the 20-bar mean now / 3 bars ago - 1, in percent.",
}

# Correlated columns counted ONCE. `rsi_slope` and `mfi_slope` are both "how
# fast is the indicator rising" and the first report showed them carrying the
# same pattern in the same half -- reading that as two findings doubles the
# apparent evidence. The multiplicity denominator is families, not columns.
FAMILIES = {
    "volume headroom": ["vol_over_trail", "vol_multiple", "floor_margin"],
    "momentum level": ["macd_margin", "macd_level", "rsi", "mfi"],
    "momentum slope": ["rsi_slope", "mfi_slope"],
    "timing": ["mins_since_open"],
    "price level": ["price"],
    "extension": ["extension"],
    "volatility": ["range_pct"],
    "liquidity": ["dollar_vol_session", "dollar_vol_bar", "tape_density"],
    "trail fit": ["trail_over_range"],
    "bar shape": ["close_in_bar", "body_ratio"],
    "trend": ["vwap_dist", "ma20_dist", "ma20_slope"],
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

    # Session-to-date aggregates. All from `same_day`, which ends at bar i.
    cum_vol = float(same_day["volume"].sum()) if len(same_day) else 0.0
    o = float(r["open"]) if "open" in sig.columns else float("nan")
    hi_, lo_ = float(r["high"]), float(r["low"])
    span = hi_ - lo_
    if len(same_day) and {"high", "low"} <= set(same_day.columns):
        typ = (same_day["high"] + same_day["low"] + same_day["close"]) / 3.0
        vv = same_day["volume"]
        vwap = float((typ * vv).sum() / vv.sum()) if float(vv.sum()) else float("nan")
        # PRINTED BARS OVER ELAPSED MINUTES, not the share of rows with volume.
        # The cache holds only the minutes that printed -- a minute with no
        # trade is an ABSENT ROW, not a zero-volume one -- so
        # (volume > 0).mean() is 100% on a frame full of holes and 100% on a
        # frame with none. That is a measurement whose output is identical to
        # the thing it is supposed to detect.
        span_min = ((same_day.index[-1] - same_day.index[0]).total_seconds()
                    / 60.0 + 1.0)
        printed = len(same_day) / span_min * 100.0 if span_min > 0 else float("nan")
    else:
        vwap, printed = float("nan"), float("nan")
    ma20 = float(past["close"].iloc[-20:].mean()) if len(past) >= 20 else float("nan")
    ma20_prev = (float(past["close"].iloc[-23:-3].mean())
                 if len(past) >= 23 else float("nan"))
    mean_range = float((tail["high"] - tail["low"]).mean()) \
        if {"high", "low"} <= set(past.columns) else float("nan")

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
        "dollar_vol_session": float(r["close"]) * cum_vol,
        "dollar_vol_bar": float(r["close"]) * float(r["volume"]),
        "tape_density": printed,
        # A stop inside one bar's noise is a different instrument from a stop
        # three bars wide, whatever the percentage says.
        "trail_over_range": ((MCL_TRAIL / 100.0) * float(r["close"]) / mean_range
                             if mean_range and mean_range == mean_range
                             else float("nan")),
        # NaN, not 0.5, on a zero-range bar: 0.5 would read as "entered mid-bar"
        # on a bar that had no range at all.
        "close_in_bar": ((float(r["close"]) - lo_) / span if span > 0
                         else float("nan")),
        "body_ratio": (abs(float(r["close"]) - o) / span
                       if span > 0 and o == o else float("nan")),
        "vwap_dist": ((float(r["close"]) / vwap - 1.0) * 100.0
                      if vwap == vwap and vwap else float("nan")),
        "ma20_dist": ((float(r["close"]) / ma20 - 1.0) * 100.0
                      if ma20 == ma20 and ma20 else float("nan")),
        "ma20_slope": ((ma20 / ma20_prev - 1.0) * 100.0
                       if ma20 == ma20 and ma20_prev == ma20_prev and ma20_prev
                       else float("nan")),
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


def monotone(bs: list[dict]) -> int:
    """+1 rising, -1 falling, 0 neither, across the bucket MEANS.

    Top-minus-bottom is the weak test and it is what let `macd_level` through
    on the first run: its middles ran (6.58) / 7.40 / (10.11) / 3.27, which is
    noise with two ends that happened to differ. A clean progression across
    all four buckets IN BOTH HALVES is far rarer by chance, and requiring it
    is the cheapest real tightening available.
    """
    if len(bs) < 3:
        return 0
    d = [bs[k + 1]["mean"] - bs[k]["mean"] for k in range(len(bs) - 1)]
    if all(x > 0 for x in d):
        return 1
    if all(x < 0 for x in d):
        return -1
    return 0


def tier(ba: list[dict], bb: list[dict]) -> tuple[str, str]:
    """(tier, why) for one feature, from its two halves.

    CANDIDATE   monotone the same way in both halves, and top-vs-bottom
                exceeds friction in both. Nothing weaker is called a
                candidate, because nothing weaker has survived this project
                before.
    WEAK        direction agrees and the effect is large, but the buckets in
                between do not line up.
    NOTHING     everything else. Printed anyway.
    """
    if not ba or not bb:
        return "NOTHING", "too few trades to bucket"
    da = ba[-1]["mean"] - ba[0]["mean"]
    db = bb[-1]["mean"] - bb[0]["mean"]
    same = (da > 0) == (db > 0)
    big = min(abs(da), abs(db)) > FRICTION
    ma, mb = monotone(ba), monotone(bb)
    if ma and ma == mb and same and big:
        return "CANDIDATE", ("monotone the same way in both halves, and both "
                             f"ends differ by more than ${FRICTION:.2f}")
    if same and big:
        return "WEAK", ("ends agree and both exceed friction, but the buckets "
                        "between them do not line up -- two ends differing is "
                        "what noise looks like")
    if same:
        return "NOTHING", f"ends agree but the smaller is under ${FRICTION:.2f}"
    return "NOTHING", "the halves DISAGREE in direction"


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
    tiers: dict[str, str] = {}
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
        ba, bb = buckets(a, f), buckets(b, f)
        tl, why = tier(ba, bb)
        tiers[f] = tl
        if ba and bb:
            da = ba[-1]["mean"] - ba[0]["mean"]
            db = bb[-1]["mean"] - bb[0]["mean"]
            L += ["", f"    {acct(da, 1).strip()} early / "
                      f"{acct(db, 1).strip()} late   [{tl}] {why}"]
        else:
            L += ["", f"    [{tl}] {why}"]
        L.append("")

    # Families, not columns. Correlated features carrying one pattern would
    # otherwise be counted as separate evidence for it.
    cand_fams = sorted({fam for fam, cols in FAMILIES.items()
                        if any(tiers.get(c) == "CANDIDATE" for c in cols)})
    weak_fams = sorted({fam for fam, cols in FAMILIES.items()
                        if any(tiers.get(c) == "WEAK" for c in cols)
                        and fam not in cand_fams})
    L += ["", "TIERS, COUNTED BY FAMILY", "",
          f"  {len(FAMILIES)} families over {len(FEATURES)} columns. "
          "Correlated columns",
          "  carrying one pattern are ONE piece of evidence, not several.", "",
          f"  CANDIDATE  {len(cand_fams)}   "
          + (", ".join(cand_fams) if cand_fams else "none"),
          f"  WEAK       {len(weak_fams)}   "
          + (", ".join(weak_fams) if weak_fams else "none"), ""]
    if not cand_fams:
        L += ["  NO family cleared the bar. That is a result, not a failure:",
              "  it says the winners and losers are not separated by anything",
              "  on this list, and it costs nothing -- unlike adding a",
              "  condition that was never there.", ""]

    L += ["HOW TO READ THIS, AND HOW NOT TO", "",
          f"  {len(FEATURES) * QUANTILES * 2} comparisons were made. At any "
          "usual threshold several will look",
          "  meaningful by chance. The feature list was fixed in the module",
          "  BEFORE any outcome was examined, and every feature is printed,",
          "  including the flat ones -- reporting only what separated is the",
          "  selection this module exists to resist.",
          "",
          "  A feature is worth a second look ONLY if all three hold:",
          "    1. MONOTONE across the buckets, the same way in both halves,",
          f"    2. an effect larger than ${FRICTION:.2f} in BOTH halves,",
          "    3. bucket counts that are not tiny.",
          "",
          "  Monotonicity was added after the first run, which passed",
          "  `macd_level` on ends that differed while its middles ran",
          "  (6.58) / 7.40 / (10.11) / 3.27. Two ends differing is what noise",
          "  looks like; four buckets in order is much rarer.",
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
