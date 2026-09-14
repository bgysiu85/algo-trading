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

import numpy as np
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
    "tape_density": "minutes that TRADED / minutes elapsed since the session's "
                    "first bar, in percent. A thin tape is a different market.",
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


def frame_ctx(sig: pd.DataFrame) -> dict:
    """Everything that can be computed ONCE per frame instead of once per bar.

    `features_at` was written per-bar and was O(i) in the bar index: it sliced
    `sig.iloc[:i+1]`, converted that whole slice's index to ET, and ran a Python
    comprehension over its dates -- for every bar. Fine for 482 entries, and
    2.5 hours for the archive, which is how it was found.

    Every quantity here is a PREFIX aggregate, so a bar still sees only itself
    and the bars before it. The session-to-date sums become differences of
    cumulative sums and the rolling means become one pandas pass. Nothing is
    approximated: `test_ctx_matches_the_slow_path_exactly` asserts the two
    paths agree bar for bar on a real frame.
    """
    local = sig.index.tz_convert(ET)
    dates = np.array([d.toordinal() for d in local.date])
    # First index of each bar's own ET day.
    newday = np.r_[True, dates[1:] != dates[:-1]]
    day_start = np.maximum.accumulate(np.where(newday, np.arange(len(dates)), 0))

    vol = sig["volume"].to_numpy(dtype=float)
    close = sig["close"].to_numpy(dtype=float)
    have_hl = {"high", "low"} <= set(sig.columns)
    high = sig["high"].to_numpy(dtype=float) if have_hl else close
    low = sig["low"].to_numpy(dtype=float) if have_hl else close
    typ = (high + low + close) / 3.0

    def pre(a):
        return np.r_[0.0, np.cumsum(a)]

    ctx = {
        "local": local,
        "day_start": day_start,
        "have_hl": have_hl,
        "close": close, "high": high, "low": low, "vol": vol,
        "open": (sig["open"].to_numpy(dtype=float) if "open" in sig.columns
                 else np.full(len(sig), np.nan)),
        "macd": sig["macd"].to_numpy(dtype=float),
        "macd_sig": sig["macd_sig"].to_numpy(dtype=float),
        "rsi": sig["rsi"].to_numpy(dtype=float),
        "mfi": sig["mfi"].to_numpy(dtype=float),
        "trail_avg": sig["trail_avg"].to_numpy(dtype=float),
        "prev_vol": sig["prev_vol"].to_numpy(dtype=float),
        "c_vol": pre(vol),
        "c_tv": pre(typ * vol),
        "c_traded": pre((vol > 0).astype(float)),
        # Minutes from the frame's first bar, via a Timedelta division
        # rather than raw integers: `.asi8` is whatever resolution the
        # index happens to carry, and on a datetime64[us] index the
        # nanosecond assumption was off by a thousand -- tape_density
        # came back as 16,680%.
        "epoch_min": ((sig.index - sig.index[0]) / pd.Timedelta(minutes=1)
                      ).to_numpy(dtype=float),
    }
    s = pd.Series(close)
    ctx["ma20"] = s.rolling(20).mean().to_numpy()
    if have_hl:
        rng = pd.Series((high - low) / close)
        ctx["rng14"] = rng.rolling(14, min_periods=1).mean().to_numpy() * 100.0
        ctx["mrange14"] = pd.Series(high - low).rolling(
            14, min_periods=1).mean().to_numpy()
    else:
        ctx["rng14"] = np.full(len(sig), np.nan)
        ctx["mrange14"] = np.full(len(sig), np.nan)
    return ctx


def _features_fast(sig: pd.DataFrame, i: int, c: dict) -> dict:
    """features_at via the precomputed context. Same numbers, O(1)."""
    d0 = int(c["day_start"][i])
    cum_vol = c["c_vol"][i + 1] - c["c_vol"][d0]
    tv = c["c_tv"][i + 1] - c["c_tv"][d0]
    traded = c["c_traded"][i + 1] - c["c_traded"][d0]
    vwap = (tv / cum_vol) if cum_vol else float("nan")
    span_min = c["epoch_min"][i] - c["epoch_min"][d0] + 1.0
    printed = (traded / span_min * 100.0) if span_min > 0 else float("nan")
    if not c["have_hl"]:
        vwap = printed = float("nan")
    first_close = c["close"][d0]
    rng = c["rng14"][i]
    mean_range = c["mrange14"][i]
    ma20 = c["ma20"][i] if i >= 19 else float("nan")
    ma20_prev = c["ma20"][i - 3] if i >= 22 else float("nan")
    cl, o = c["close"][i], c["open"][i]
    hi_, lo_ = c["high"][i], c["low"][i]
    span = hi_ - lo_
    ta, pv = c["trail_avg"][i], c["prev_vol"][i]
    lt = c["local"][i]
    return _assemble(cl, o, hi_, lo_, span, ta, pv, c["vol"][i],
                     c["macd"][i], c["macd_sig"][i], c["rsi"][i], c["mfi"][i],
                     (c["rsi"][i] - c["rsi"][i - 3]) if i >= 3 else float("nan"),
                     (c["mfi"][i] - c["mfi"][i - 3]) if i >= 3 else float("nan"),
                     lt.hour * 60 + lt.minute - 240, first_close, rng,
                     cum_vol, printed, mean_range, vwap, ma20, ma20_prev)


def features_at(sig: pd.DataFrame, i: int, ctx: dict | None = None) -> dict:
    """Every feature at bar `i`, from that bar and the ones BEFORE it.

    Nothing here may read sig.iloc[i+1:]. A test shuffles the future and
    asserts the output is identical.

    Pass `ctx` from `frame_ctx(sig)` when looping over many bars of one frame:
    same numbers, without the per-bar reslice. Omit it and this takes the
    original path, which the equivalence test uses as the reference.
    """
    if ctx is not None:
        return _features_fast(sig, i, ctx)
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
        # MINUTES THAT TRADED over minutes ELAPSED. Both halves matter, and I
        # got this wrong once in each direction:
        #
        #   (volume > 0).mean()          misses absent rows
        #   len(same_day) / elapsed      misses zero-volume rows
        #
        # I shipped the second on the theory that a dead minute is an absent
        # row. It is not, in this cache: the archive frames are gap-filled and
        # a dead minute is present with volume 0 -- LGHL 2026-05-21 has 1,999
        # of 2,770 bars at zero. So the second form read 100.00 for all 482
        # entries, which is how it got caught. Counting TRADED minutes against
        # ELAPSED ones is right whichever way a frame is stored, so it does not
        # depend on my being right about the storage.
        span_min = ((same_day.index[-1] - same_day.index[0]).total_seconds()
                    / 60.0 + 1.0)
        traded = float((same_day["volume"] > 0).sum())
        printed = traded / span_min * 100.0 if span_min > 0 else float("nan")
    else:
        vwap, printed = float("nan"), float("nan")
    ma20 = float(past["close"].iloc[-20:].mean()) if len(past) >= 20 else float("nan")
    ma20_prev = (float(past["close"].iloc[-23:-3].mean())
                 if len(past) >= 23 else float("nan"))
    mean_range = float((tail["high"] - tail["low"]).mean()) \
        if {"high", "low"} <= set(past.columns) else float("nan")

    return _assemble(
        float(r["close"]), o, hi_, lo_, span, ta, pv, float(r["volume"]),
        float(r["macd"]), float(r["macd_sig"]), float(r["rsi"]), float(r["mfi"]),
        (float(r["rsi"]) - float(sig["rsi"].iloc[i - 3])) if i >= 3
        else float("nan"),
        (float(r["mfi"]) - float(sig["mfi"].iloc[i - 3])) if i >= 3
        else float("nan"),
        local[-1].hour * 60 + local[-1].minute - 240,
        first_close, float(rng), cum_vol, printed, mean_range, vwap,
        ma20, ma20_prev)


def _assemble(cl, o, hi_, lo_, span, ta, pv, vol, macd, macd_sig, rsi, mfi,
              rsi_slope, mfi_slope, mins, first_close, rng, cum_vol, printed,
              mean_range, vwap, ma20, ma20_prev) -> dict:
    """The feature dictionary itself, shared by both paths.

    Factored out so the fast path cannot drift from the slow one in the
    ARITHMETIC. What the equivalence test then has to check is only that the
    two paths derive the same INPUTS, which is the part that could differ.
    """
    return {
        "vol_over_trail": vol / ta if ta else float("nan"),
        "vol_multiple": vol / pv if pv else float("nan"),
        "floor_margin": pv / ta if ta else float("nan"),
        "macd_margin": macd - macd_sig,
        "macd_level": macd,
        "rsi": rsi,
        "rsi_slope": rsi_slope,
        "mfi": mfi,
        "mfi_slope": mfi_slope,
        "mins_since_open": mins,
        "price": cl,
        "extension": (cl / first_close - 1.0) * 100.0
        if first_close == first_close and first_close else float("nan"),
        "range_pct": float(rng),
        "dollar_vol_session": cl * cum_vol,
        "dollar_vol_bar": cl * vol,
        "tape_density": printed,
        # A stop inside one bar's noise is a different instrument from a stop
        # three bars wide, whatever the percentage says.
        "trail_over_range": ((MCL_TRAIL / 100.0) * cl / mean_range
                             if mean_range and mean_range == mean_range
                             else float("nan")),
        # NaN, not 0.5, on a zero-range bar: 0.5 would read as "entered mid-bar"
        # on a bar that had no range at all.
        "close_in_bar": ((cl - lo_) / span if span > 0 else float("nan")),
        "body_ratio": (abs(cl - o) / span
                       if span > 0 and o == o else float("nan")),
        "vwap_dist": ((cl / vwap - 1.0) * 100.0
                      if vwap == vwap and vwap else float("nan")),
        "ma20_dist": ((cl / ma20 - 1.0) * 100.0
                      if ma20 == ma20 and ma20 else float("nan")),
        "ma20_slope": ((ma20 / ma20_prev - 1.0) * 100.0
                       if ma20 == ma20 and ma20_prev == ma20_prev and ma20_prev
                       else float("nan")),
    }


def why_not_bucketable(rows: list[dict], name: str, q: int = QUANTILES) -> str:
    """"" if this feature can be bucketed, else the reason it cannot.

    The second reason is the one that bit. `tape_density` came back 100.00 for
    all 482 entries -- every archive frame is gap-free, so the feature measures
    nothing on this data. It was bucketed anyway, and printed

        [100.00-100.00] (3.33)  [100.00-100.00] (5.39)
        [100.00-100.00] 17.71   [100.00-100.00] (14.30)

    with a top-vs-bottom of (10.97). Those four means are real, but which
    trade landed in which bucket was decided by LIST ORDER, because sorting a
    run of identical values does not reorder it. That is not a measurement of
    anything; it is the entry order of the pairs file wearing a feature's name,
    and it was large enough to have been read as a finding.

    A boundary that falls INSIDE a run of identical values has the same defect
    in miniature, so the check is on the boundaries, not just on the extremes.
    """
    vals = sorted(r[name] for r in rows
                  if r.get(name) is not None and r[name] == r[name])
    if len(vals) < q * 5:
        return "too few trades to bucket"
    n = len(vals)
    edges = [vals[n * k // q] for k in range(q)]
    if edges[0] == vals[-1]:
        return f"NO VARIATION -- every entry is {edges[0]:,.2f}"
    if any(a == b for a, b in zip(edges, edges[1:])):
        return ("too few distinct values: a bucket boundary falls inside a run "
                "of identical values, so membership would be decided by list "
                "order")
    return ""


def buckets(rows: list[dict], name: str, q: int = QUANTILES,
            outcome: str = "net") -> list[dict]:
    """Quantile buckets of one feature, with the outcome in each.

    Edges come from the data, not from round numbers: a hand-chosen threshold
    is already a fitted parameter. Returns [] when the data cannot carry the
    split -- see why_not_bucketable.

    `outcome` names the column being averaged. It defaults to `net` so every
    published figure from this module is unchanged; `entry_split` passes a 0/1
    label, for which the bucket mean IS the rate. The bucketing discipline has
    to be ONE implementation -- a second copy with its own quantile edges and
    its own tie handling would make a result here incomparable with the 0-of-11
    null this module already recorded.
    """
    if why_not_bucketable(rows, name, q):
        return []
    vals = [(r[name], r[outcome]) for r in rows
            if r.get(name) is not None and r[name] == r[name]]
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
        # Not necessarily "too few trades" -- the half may have been refused
        # for having no spread. The per-half line above says which.
        return "NOTHING", "a half could not be bucketed (reason above)"
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
                # The REASON, not a generic line. "too few trades" and "this
                # feature is a constant" are different facts about the study
                # and only one of them is fixable by collecting more data.
                L.append(f"    {label:<6} {why_not_bucketable(part, f)}")
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


def locate(rows: list[dict], name: str, v: float,
           q: int = QUANTILES) -> dict | None:
    """Which bucket of the POOLED population `v` falls in, and what that
    bucket did. None if the feature cannot be bucketed or v is absent."""
    if v is None or v != v or why_not_bucketable(rows, name, q):
        return None
    bs = buckets(rows, name, q)
    if not bs:
        return None
    for k, b in enumerate(bs):
        if v <= b["hi"] or k == len(bs) - 1:
            return {**b, "k": k, "of": len(bs)}
    return None


def render_where(rows: list[dict], got: dict, label: str,
                 population: str) -> list[str]:
    """One bar, placed against the population on every feature.

    THIS CAN ONLY DISCONFIRM. The bar was chosen because its outcome was
    already known, so a feature that happens to flag it is one of 22 tried on
    a sample of one -- no evidence at all. A feature that does NOT flag it is
    worth something: it rules that feature out as the thing that would have
    caught this bar.
    """
    L = [f"WHERE DOES {label} SIT?", "",
         f"  measured against the {len(rows):,} {population} in the report, "
         "pooled.",
         "  Quartile 1 is the lowest quarter of the population on that "
         "feature.", ""]
    base = sum(r["net"] for r in rows) / len(rows)
    L += [f"  population mean net {acct(base, 1).strip()}", ""]
    flagged, ruled_out, unusable = [], [], []
    for f in FEATURES:
        v = got.get(f)
        b = locate(rows, f, v)
        if b is None:
            unusable.append(f)
            L.append(f"  {f:<20} {'n/a':>14}   not bucketable, or no value")
            continue
        tag = f"Q{b['k'] + 1}/{b['of']}"
        L.append(f"  {f:<20} {v:>14,.2f}   {tag}  that quartile: "
                 f"{acct(b['mean'], 1).strip()} mean, {b['win']:.0f}% win")
        # "Extreme" = the top or bottom quartile. Anything in the middle two
        # is, by construction, unremarkable.
        if b["k"] in (0, b["of"] - 1):
            flagged.append(f)
        else:
            ruled_out.append(f)
    L += ["", "WHAT THIS DOES AND DOES NOT SHOW", "",
          f"  {len(ruled_out)} of {len(FEATURES)} features put this bar in a "
          "MIDDLE quartile.",
          "  On those, it is indistinguishable from the population -- they",
          "  could not have separated it however they were thresholded.",
          ""]
    if flagged:
        L += [f"  {len(flagged)} put it in an outer quartile: "
              + ", ".join(flagged), "",
              "  That is NOT evidence. This bar was chosen because its outcome",
              "  was known, 22 features were tried on it, and a sample of one",
              "  has no halves to disagree. Roughly half of any bar's features",
              "  land in an outer quartile by construction.", ""]
    if unusable:
        L += ["  not bucketable here: " + ", ".join(unusable), ""]
    L += ["  The usable direction is the negative one. If the features that",
          "  would have to fire are the ones sitting in the middle, then",
          "  nothing on this list is the missing condition, and the search",
          "  has to widen or stop -- which is worth knowing either way."]
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
    p.add_argument("--where", default=None, metavar="SYM:DATE@HHMM",
                   help="also place ONE bar against the population, e.g. "
                        "TNON:2026-09-11@07:35. HHMM is ET. The bar need not "
                        "be an entry.")
    p.add_argument("--source", default="cache", choices=["cache", "archive"],
                   help="where the --where bar comes from. `archive` reaches "
                        "sessions the bar cache has not got.")
    p.add_argument("--archive", default=None)
    # XNAS.BASIC, not the EQUS.MINI default in databento_universe: the archive
    # was pulled as XNAS.BASIC and the two are different tapes.
    p.add_argument("--dataset", default="XNAS.BASIC")
    return p


def where_bar(spec: str, source: str, archive, dataset, cache_dir):
    """(features, label) for one SYM:DATE@HHMM bar, or exit with why not."""
    from common.cache_io import (BACKTEST_END_HHMM, BACKTEST_SESSIONS,
                                 check_sessions, load_cached_bars,
                                 slice_sessions)
    from strategy.mcl import mcl as MCL

    try:
        sym_date, hhmm = spec.split("@")
        sym, date_str = sym_date.split(":")
        hh, mm = int(hhmm[:2]), int(hhmm[-2:])
    except ValueError:
        sys.exit(f"--where wants SYM:DATE@HHMM, got {spec!r}")
    sym, day = sym.upper(), datetime.strptime(date_str, "%Y-%m-%d").date()

    if source == "archive":
        from common.why_no_entry import from_archive
        bars = from_archive(sym, date_str, archive, dataset)
        if bars is None or bars.empty:
            sys.exit(f"no archive bars for {sym} {date_str} under {archive}/")
        sl = bars
    else:
        bars = load_cached_bars(cache_dir, sym, date_str)
        if bars is None or bars.empty:
            sys.exit(f"no cached bars for {sym} {date_str} under {cache_dir}/")
        bars.index = (bars.index.tz_localize("UTC") if bars.index.tz is None
                      else bars.index.tz_convert("UTC"))
        bars = bars.sort_index()
        end_h, end_m = int(BACKTEST_END_HHMM[:2]), int(BACKTEST_END_HHMM[2:])
        want_end = datetime.combine(day, datetime.min.time()).replace(
            hour=end_h, minute=end_m, tzinfo=ET)
        if check_sessions(bars, want_end, BACKTEST_SESSIONS) < BACKTEST_SESSIONS:
            sys.exit(f"{sym} {date_str}: fewer than {BACKTEST_SESSIONS} "
                     "sessions cached -- try --source archive")
        sl = slice_sessions(bars, want_end, BACKTEST_SESSIONS)

    sig = MCL.signals(sl)
    local = sig.index.tz_convert(ET)
    hits = [k for k, t in enumerate(local)
            if t.date() == day and t.hour == hh and t.minute == mm]
    if not hits:
        sys.exit(f"{sym} {date_str}: no bar at {hh:02d}:{mm:02d} ET")
    i = hits[0]
    return features_at(sig, i), f"{sym} {date_str} {hh:02d}:{mm:02d} ET"


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
        ctx = frame_ctx(sig)
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
            f = features_at(sig, i, ctx)
            f.update(symbol=p["symbol"], date=p["date"],
                     net=t.net - FRICTION)
            rows.append(f)

    if not rows:
        sys.exit(f"no entries found for {len(pairs)} symbol-day(s) under "
                 f"{cache}/")

    text = render(rows, a.population, a.pairs, skipped, time.time() - t0)
    head = f"common.entry_features  population={a.population}"
    if a.where:
        archive = None
        if a.source == "archive":
            from common.databento_fetch import default_archive
            archive = Path(a.archive) if a.archive else default_archive()
        got, label = where_bar(a.where, a.source, archive, a.dataset, cache)
        text = render_where(rows, got, label, a.population) + ["", ""] + text
        head += f"  where={a.where}"

    out = a.out or f"var/reports/entry_features_{a.population}.txt"
    emit("\n".join(text), out, header=head)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
