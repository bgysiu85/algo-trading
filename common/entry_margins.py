#!/usr/bin/env python3
r"""By how much did each entry clause pass, and did clearing by a mile help?

    python -m common.entry_margins --jobs 8

THE QUESTION
------------
MCL's entry is five conditions and nothing records BY HOW MUCH each one passed.
Four of them are sign tests -- `macd > macd_sig`, `macd > 0`, `mfi > mfi[3]`,
`rsi > rsi[3]` -- true at any margin whatever. The fifth is a pair of ratios,
`volume >= prev_vol * 3` and `prev_vol >= trail_avg * 0.5`, whose every term is
a multiple of the tape's own recent volume rather than a number of shares.

So the rule cannot tell a liquid bar from a dead one, and cannot tell a trend
from a crossing. Whether that MATTERS is a different question from whether it is
true, and this measures it:

    how many entries cleared by a hair, and did the ones that cleared by a mile
    do any better?

PRE-REGISTERED, WRITTEN BEFORE THE FIRST RUN
---------------------------------------------
The claim: **a wider margin over the entry threshold predicts a better net per
trade.** The decision rule, the same one `entry_shares` carries so the two are
comparable:

    CLEARS      a bucket's net per trade is positive after $4.26 friction, in
                BOTH halves, and still positive after dropping its best five.
    SEPARATES   the buckets run monotonically the same way in both halves and
                the ends differ by more than friction, without any bucket
                clearing.
    NOTHING     everything else.

`entry_features` has already returned 0 CANDIDATE of 11 families over this kind
of question. The prior is not neutral, and three of the six columns here are
columns it already tested -- on a DIFFERENT population. That overlap is stated
in the multiplicity count rather than quietly claimed as independent evidence.

TWO SCALES, AND ONLY ONE OF THEM CAN ANSWER BEN'S QUESTION
-----------------------------------------------------------
The absolute section reports the raw figures against the rule's own thresholds:
dollars on the bar, ratio over 3.0, MACD margin in basis points of price. Those
are the numbers a person judges -- "$2,655 of stock traded on that bar" means
something on its own.

The RELATIVE section ranks each entry's margin WITHIN this population, which is
the only way six quantities in six different units can be compared on one row.
A percentile cannot say the population as a whole is marginal: if every entry
in the book cleared by a hair, the tightest of them would still rank at 0 and
the loosest at 100. Only the absolute section can answer that, and it is
printed first for that reason.

WHAT THIS IS NOT
----------------
Not a rule, and not a threshold search. The removal ladder at the end prints
EVERY level on a fixed list in both halves precisely so that reading the best
row off it is visibly a choice made after seeing the data, rather than a
finding.
"""
from __future__ import annotations

import argparse
import os
import time
from collections import defaultdict
from datetime import date as _date
from pathlib import Path
from zoneinfo import ZoneInfo

from common.entry_features import (FAMILIES, QUANTILES, buckets, monotone,
                                   why_not_bucketable)
from common.entry_shares import (DROP, MEASURED_FRICTION, PUBLISHED_TRADES,
                                 QTY, drop_top, per_trade, split, with_net)
from common.report_io import emit

ET = ZoneInfo("America/New_York")

# The six columns MCL's five clauses reduce to, each with the threshold the
# rule actually applies. The margin is computed against THIS number, so a
# change to the strategy that is not reflected here fails the test below rather
# than quietly measuring against a stale threshold.
CLAUSES_MCL = {
    "vol_multiple": ("volume / prev_vol", "VOL_MULTIPLE", 3.0),
    "floor_margin": ("prev_vol / trail_avg", "FLOOR_FRACTION", 0.5),
    "macd_margin": ("macd - macd_sig", None, 0.0),
    "macd_level": ("macd", None, 0.0),
    "rsi_slope": ("rsi - rsi[3]", None, 0.0),
    "mfi_slope": ("mfi - mfi[3]", None, 0.0),
}

# MC5's ENTIRE entry, on 5-minute bars. Three clauses, and NONE OF THEM IS A
# VOLUME TEST: `mc5.signals()` reads only `close`, and `volume` appears once in
# the whole module, writing a field into a log row. So the "volume headroom"
# family that MCL carries has no member here at all -- which is the finding,
# not an omission in this table.
CLAUSES_MC5 = {
    "rsi_roc": ("rsi rate of change over 3 bars, %", "ENTRY_RSI_ROC_PCT", 5.0),
    "ema_gap": ("ema9 - ema21", None, 0.0),
    "macd_margin": ("macd - macd_sig", None, 0.0),
}

CLAUSES_BY_STRATEGY = {"mcl": CLAUSES_MCL, "mc5": CLAUSES_MC5}

# The bar the clauses are computed on. PRINTED IN EVERY REPORT, because a
# `dollar_vol_bar` measured over five minutes and one measured over one minute
# are two different quantities under one column name -- which is this project's
# most persistent defect, and putting both strategies in one module is exactly
# how it would arrive here.
BAR_MINUTES = {"mcl": 1, "mc5": 5}

# "Within a hair", stated in each column's own units and fixed in advance.
# A ratio clause is a hair over when it is within 10% of its multiplier; a
# sign clause when the margin is under one basis point of price (MACD) or a
# tenth of an index point (RSI, MFI, both on a 0-100 scale).
HAIR = {
    "vol_multiple": ("within 10% of 3.0x", lambda r: r["vol_multiple"] < 3.30),
    "floor_margin": ("within 10% of 0.50x", lambda r: r["floor_margin"] < 0.55),
    "macd_margin": ("under 1bp of price", lambda r: abs(r["macd_bps"]) < 1.0),
    "macd_level": ("under 1bp of price", lambda r: abs(r["macd_level_bps"]) < 1.0),
    "rsi_slope": ("under 0.1 RSI points", lambda r: r["rsi_slope"] < 0.1),
    "mfi_slope": ("under 0.1 MFI points", lambda r: r["mfi_slope"] < 0.1),
    "rsi_roc": ("within 10% of 5.0%", lambda r: r["rsi_roc"] < 5.5),
    "ema_gap": ("under 1bp of price", lambda r: abs(r["ema_gap_bps"]) < 1.0),
}

# Absolute liquidity levels, fixed before the run. EVERY row is printed.
DOLLAR_FLOORS = (5e3, 10e3, 25e3, 50e3, 100e3, 250e3, 500e3, 1e6)

PAIRS = "var/state/screen_pairs_pit.json"


# --- the tape ---------------------------------------------------------------

def run_day(args: tuple) -> tuple:
    """One session's entries with their clause margins. Picklable.

    `features_at` is imported, not reimplemented: `vol_multiple`,
    `floor_margin`, `macd_margin` and the rest already exist there and are
    already tested against a slow reference path. A second copy with its own
    idea of `trail_avg` would produce figures that look comparable with
    entry_features' and are not.
    """
    from common.dbn_io import read_dbn
    from common.entry_features import frame_ctx, features_at
    from common.pit_h0 import first_seen_time
    from common.pit_strategy import build_frame, engine

    import pandas as pd
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
        if strategy == "mc5":
            from strategy.mc5 import mc5 as MC5
            sig = MC5.signals(MC5.to_5m(df))
            for t in trades:
                out.append(mc5_row(sig, t, rec["symbol"], day))
        else:
            sig = MCL.signals(df)
            ctx = frame_ctx(sig)
            for t in trades:
                out.append(margin_row(sig, ctx, t, rec["symbol"], day,
                                      CLAUSES_MCL))
    return day, out, ""


def margin_row(sig, ctx, t, symbol: str, day: str,
               clauses: dict | None = None) -> dict:
    """One trade's row, located or not. Split out so the NOT-located branch can
    be tested: it is the branch that would otherwise shorten the table in
    silence, and a population that changes without saying so is the failure
    this project keeps rediscovering."""
    import pandas as pd
    from common.entry_features import features_at

    row = {"symbol": symbol, "date": day,
           "gross": (t.exit_price - t.entry_price) * QTY}
    i = sig.index.searchsorted(pd.Timestamp(t.entry_time))
    if i >= len(sig) or sig.index[i] != pd.Timestamp(t.entry_time):
        row["located"] = False
        return row
    m = features_at(sig, int(i), ctx=ctx)
    row["located"] = True
    row["entry_price"] = float(t.entry_price)
    for col in (clauses or CLAUSES_MCL):
        row[col] = m.get(col)
    row["bar_volume"] = float(sig["volume"].iloc[i])
    row["dollar_vol_bar"] = m.get("dollar_vol_bar")
    row["dollar_vol_session"] = m.get("dollar_vol_session")
    return row


def mc5_row(sig, t, symbol: str, day: str) -> dict:
    """One MC5 trade's row, computed on the FIVE-MINUTE frame it entered on.

    `features_at` is not used and must not be: it is MCL's 1-minute feature
    set, and running it against a 5-minute frame would compute a table the
    features were not written for and print it as a measurement. The three
    columns here are MC5's own three clauses, read off its own signal frame.
    """
    import pandas as pd

    row = {"symbol": symbol, "date": day,
           "gross": (t.exit_price - t.entry_price) * QTY}
    i = sig.index.searchsorted(pd.Timestamp(t.entry_time))
    if i >= len(sig) or sig.index[i] != pd.Timestamp(t.entry_time):
        row["located"] = False
        return row
    r = sig.iloc[i]
    row["located"] = True
    row["entry_price"] = float(t.entry_price)
    row["rsi_roc"] = float(r["rsi_roc"])
    row["ema_gap"] = float(r["ema_fast"]) - float(r["ema_slow"])
    row["macd_margin"] = float(r["macd"]) - float(r["macd_sig"])
    row["bar_volume"] = float(r["volume"])
    row["dollar_vol_bar"] = float(r["close"]) * float(r["volume"])
    # Session to date, from this frame's own bars on this ET day. Computed
    # here rather than imported because `features_at`'s version is a
    # 1-minute prefix sum and this one is a 5-minute one.
    local = sig.index.tz_convert(ET)
    day_of = local[i].date()
    same = sig[[d == day_of for d in local.date]]
    upto = same[same.index <= sig.index[i]]
    row["dollar_vol_session"] = float((upto["close"] * upto["volume"]).sum())
    return row


def derive(rows: list[dict]) -> list[dict]:
    """The two columns that only make sense against a price.

    MACD is in price units, so a margin of 0.01 is a different thing on a $2
    stock and a $25 one. Basis points of the entry price is the comparison that
    holds across the price range the screen admits.
    """
    for r in rows:
        px = r.get("entry_price") or 0.0
        for src, dst in (("macd_margin", "macd_bps"),
                         ("macd_level", "macd_level_bps"),
                         ("ema_gap", "ema_gap_bps")):
            v = r.get(src)
            r[dst] = (v / px * 10_000.0) if (px and v is not None) else None
    return rows


# --- sections ---------------------------------------------------------------

def population(rows: list[dict], strategy: str, n_days: int) -> list[str]:
    n = len(rows)
    lost = sum(1 for r in rows if not r.get("located"))
    L = ["POPULATION", "",
         f"  trades              {n:,}",
         f"  sessions            {n_days:,}",
         f"  entry bar located   {n - lost:,}"
         + (f"   ({lost:,} NOT located)" if lost else "")]
    pub = PUBLISHED_TRADES.get(strategy)
    if pub is not None:
        L.append(f"  published count     {pub:,}   "
                 + ("matches" if n == pub else "*** DOES NOT MATCH ***"))
        if n != pub:
            L += ["",
                  "  A DIFFERENT BOOK UNDER THE SAME CAVEAT. Do not read the",
                  "  sections below until this reconciles."]
    return L + [""]


def absolute_section(rows: list[dict], clauses: dict = CLAUSES_MCL,
                     strategy: str = "mcl") -> list[str]:
    """The raw figures, against the rule's own thresholds.

    THIS IS THE SECTION THAT ANSWERS "SHOULD THESE HAVE BEEN ENTERED AT ALL".
    The percentile work below cannot: a rank within the population says nothing
    about the population.
    """
    L = ["HOW FAR PAST ITS OWN THRESHOLD DID EACH CLAUSE GET?", "",
         "  Raw units, against the number the rule applies. `a hair` is fixed",
         "  in advance, per column, and printed beside its definition.", "",
         f"  {'clause':<14}{'rule':<26}{'p10':>12}{'p50':>12}{'p90':>12}"
         f"{'a hair':>9}", ""]
    for col, (expr, const, thr) in clauses.items():
        vals = sorted(r[col] for r in rows
                      if r.get(col) is not None and r[col] == r[col])
        if not vals:
            L.append(f"  {col:<14}{expr:<26}{'no values':>45}")
            continue

        def q(p):
            return vals[min(len(vals) - 1, int(p * len(vals)))]
        hair = hair_count(rows, col)
        rule = f"{expr} > {thr:g}" if const is None else f"{expr} >= {thr:g}"
        shown = ("  n/a" if hair is None
                 else f"{100.0 * hair / len(rows):7.1f}%")
        L.append(f"  {col:<14}{rule:<26}{q(.10):>12,.3f}{q(.50):>12,.3f}"
                 f"{q(.90):>12,.3f}{shown:>9}")
    if any(hair_count(rows, c) is None for c in clauses):
        L += ["",
              "  *** `n/a` MEANS THE HAIR TEST COULD NOT BE EVALUATED, not that",
              "      no entry was marginal. A column it needs was never",
              "      computed. Treat that row as absent, not as zero. ***"]
    L += [""]
    for col in clauses:
        L.append(f"    a hair, {col:<14} = {HAIR[col][0]}")
    L += [""]

    # THE BAR THAT DID NOT TRADE. MCL cannot enter on one by construction --
    # `c_vol` needs volume >= 3 x prev_vol AND prev_vol > 0, so a zero-volume
    # bar fails and a zero PREVIOUS bar fails too. MC5 has no such clause, and
    # the archive frames are gap-filled: a dead minute is PRESENT with volume 0
    # and the prior close repeated, so a 5-minute bucket of five dead minutes
    # survives resampling as O=H=L=C with volume 0. Its EMA, MACD and RSI are
    # then computed on repeated closes.
    #
    # A count of zero here is therefore two different facts depending on the
    # strategy, and the report says which it is rather than printing 0 twice.
    vols = [r["bar_volume"] for r in rows if r.get("bar_volume") is not None]
    if vols:
        L += ["  DID THE ENTRY BAR TRADE AT ALL?", ""]
        for lo, lab in ((0, "zero volume"), (1, "under 100 shares"),
                        (100, "under 1,000 shares"),
                        (1_000, "under 10,000 shares")):
            hi = {0: 1, 1: 100, 100: 1_000, 1_000: 10_000}[lo]
            n = sum(1 for v in vols if v < hi)
            L.append(f"    {lab:<22} {n:>7,}   {100.0*n/len(vols):5.1f}%")
        if strategy == "mcl":
            L += ["",
                  "    Zero is STRUCTURAL for MCL, not measured: `c_vol` needs",
                  "    volume >= 3 x prev_vol with prev_vol > 0, so neither a",
                  "    dead bar nor a dead previous bar can pass.", ""]
        else:
            L += ["",
                  "    MC5 HAS NO CLAUSE THAT COULD REFUSE THESE. `signals()`",
                  "    reads only `close`. A 5-minute bucket of five dead",
                  "    minutes arrives gap-filled as O=H=L=C with volume 0, and",
                  "    its EMA, MACD and RSI are computed on repeated closes.",
                  ""]

    # And the absolute liquidity, which no clause looks at at all.
    for col, name in (("dollar_vol_bar", "DOLLARS ON THE ENTRY BAR"),
                      ("dollar_vol_session", "DOLLARS IN THE SESSION SO FAR")):
        vals = sorted(r[col] for r in rows
                      if r.get(col) is not None and r[col] == r[col])
        if not vals:
            continue
        L += [f"  {name}   (no entry clause reads this)", ""]

        def q2(p):
            return vals[min(len(vals) - 1, int(p * len(vals)))]
        L += [f"    min {vals[0]:>14,.0f}   p10 {q2(.10):>14,.0f}"
              f"   p50 {q2(.50):>14,.0f}   p90 {q2(.90):>14,.0f}", ""]
        for lvl in DOLLAR_FLOORS:
            under = sum(1 for v in vals if v < lvl)
            L.append(f"    under ${lvl:>12,.0f}   {under:>7,}"
                     f"   {100.0*under/len(vals):5.1f}%")
        L += [""]
    return L


def hair_count(rows: list[dict], col: str) -> int | None:
    """How many rows are within a hair on `col`, or None if it cannot be asked.

    NONE IS NOT ZERO. The first version swallowed a KeyError and returned
    False, so a derived column that was never computed -- `macd_level_bps`, in
    the case that found this -- reported 0.0% marginal entries, which reads
    exactly like a book with no marginal entries in it.
    """
    _label, test = HAIR[col]
    n = 0
    for r in rows:
        try:
            v = test(r)
        except (TypeError, KeyError):
            return None
        if v is None:
            return None
        n += bool(v)
    return n


def pct_ranks(rows: list[dict], col: str) -> None:
    """Write `<col>_pct`: this entry's rank on that column, 0-100.

    Ties share the rank of their first occurrence, so a run of identical values
    cannot be split by list order -- the defect `why_not_bucketable` exists for,
    arriving here through a different door.
    """
    vals = sorted((r[col] for r in rows
                   if r.get(col) is not None and r[col] == r[col]))
    n = len(vals)
    if not n:
        for r in rows:
            r[f"{col}_pct"] = None
        return
    import bisect
    for r in rows:
        v = r.get(col)
        if v is None or v != v:
            r[f"{col}_pct"] = None
        else:
            r[f"{col}_pct"] = 100.0 * bisect.bisect_left(vals, v) / n


def add_slack(rows: list[dict], clauses: dict = CLAUSES_MCL) -> tuple[list[dict], list[str]]:
    """`min_slack` and `binding`: the tightest clause on each entry.

    Returns (rows, the columns excluded for having no spread).

    A COLUMN WITH ONE VALUE RANKS 0 ON EVERY ROW, and would therefore be named
    the binding clause on every entry in the book -- a constant presented as
    the thing that nearly stopped every trade. `why_not_bucketable` refuses
    such a column for the same reason one level up; this refuses it here, and
    names it rather than dropping it quietly.

    The percentile is a RANK WITHIN THIS POPULATION and nothing more. It cannot
    say the book as a whole is marginal -- if every entry cleared by a hair, the
    tightest would still rank 0 and the loosest 100.
    """
    usable, flat = [], []
    for col in clauses:
        pct_ranks(rows, col)
        seen = {r[col] for r in rows
                if r.get(col) is not None and r[col] == r[col]}
        (usable if len(seen) > 1 else flat).append(col)
    for r in rows:
        pairs = [(r[f"{c}_pct"], c) for c in usable
                 if r.get(f"{c}_pct") is not None]
        if pairs:
            r["min_slack"], r["binding"] = min(pairs)
        else:
            r["min_slack"], r["binding"] = None, "none"
    return rows, flat


def binding_section(rows: list[dict], flat: list[str] | None = None) -> list[str]:
    c: dict[str, int] = defaultdict(int)
    for r in rows:
        c[r.get("binding", "none")] += 1
    n = len(rows)
    L = ["WHICH CLAUSE WAS THE BINDING ONE?", "",
         "  The clause this entry was closest to failing, by rank within the",
         "  population. A clause that is almost never binding is not doing work",
         "  -- it is being carried by the others.", ""]
    for k in sorted(c, key=lambda k: -c[k]):
        L.append(f"    {k:<16} {c[k]:>7,}   {100.0*c[k]/n:5.1f}%")
    if flat:
        L += ["",
              f"    EXCLUDED, one value across the book: {', '.join(flat)}.",
              "    A constant ranks 0 on every row and would be named binding",
              "    on every entry -- a column that measures nothing, presented",
              "    as the thing that nearly stopped every trade."]
    return L + [""]


def one_column(rows: list[dict], col: str) -> tuple[list[str], str]:
    """Quartiles of one margin against outcome, both halves, drop-top-N."""
    usable = [r for r in rows if r.get(col) is not None and r[col] == r[col]]
    L = [f"  {col}   n={len(usable):,}"]
    why = why_not_bucketable(usable, col, QUANTILES) if usable else "no values"
    if why:
        return L + [f"    not bucketable: {why}", ""], "NOTHING"
    whole = buckets(usable, col, QUANTILES)
    a, b = split(usable)
    ba = buckets(a, col, QUANTILES) if a else []
    bb = buckets(b, col, QUANTILES) if b else []

    vals = sorted(usable, key=lambda r: r[col])
    robust = []
    for k in range(QUANTILES):
        lo, hi = len(vals) * k // QUANTILES, len(vals) * (k + 1) // QUANTILES
        kept = drop_top(vals[lo:hi])
        robust.append({"lo": vals[lo][col], "hi": vals[hi - 1][col],
                       "n": len(kept),
                       "mean": (sum(r["net"] for r in kept) / len(kept))
                       if kept else 0.0})
    for bs, name in ((whole, "all"), (ba, "1st half"), (bb, "2nd half"),
                     (robust, f"less top{DROP}")):
        if not bs:
            L.append(f"    {name:<10} could not be bucketed")
            continue
        L.append(f"    {name:<10} " + "  ".join(
            f"[{x['lo']:,.2f}-{x['hi']:,.2f}] {x['mean']:>8,.2f} (n={x['n']:,})"
            for x in bs))

    verdict, why_v = "NOTHING", "no bucket is positive in both halves"
    if ba and bb:
        for k in range(min(len(whole), len(ba), len(bb), len(robust))):
            if (whole[k]["mean"] > 0 and ba[k]["mean"] > 0
                    and bb[k]["mean"] > 0 and robust[k]["mean"] > 0):
                verdict, why_v = "CLEARS", (
                    f"bucket {k+1} positive in both halves and after dropping "
                    f"its top {DROP}")
                break
        else:
            ma, mb = monotone(ba), monotone(bb)
            da = ba[-1]["mean"] - ba[0]["mean"]
            db = bb[-1]["mean"] - bb[0]["mean"]
            if (ma and ma == mb and (da > 0) == (db > 0)
                    and min(abs(da), abs(db)) > MEASURED_FRICTION):
                verdict, why_v = "SEPARATES", (
                    "monotone the same way in both halves, ends more than "
                    "friction apart -- and nothing profitable")
    L += [f"    verdict: {verdict} -- {why_v}", ""]
    return L, verdict


def ladder_section(rows: list[dict]) -> list[str]:
    """What an absolute dollar floor would have removed, at every fixed level.

    EVERY ROW IS PRINTED, IN BOTH HALVES, and no row is recommended. Reading
    the best one off this table is choosing a threshold after seeing its
    outcome, which is the definition of the thing this project refuses to do --
    and a floor that helps in one half and not the other is noise wearing a
    rule's clothes.
    """
    L = ["IF AN ABSOLUTE DOLLAR FLOOR HAD BEEN APPLIED", "",
         "  Removing every entry whose bar traded under the level. Both halves,",
         "  every level, nothing recommended. A level that helps in one half",
         "  and not the other is not a rule.", "",
         f"  {'floor':>12}{'removed':>10}{'removed $/t':>14}"
         f"{'kept $/t 1st':>15}{'kept $/t 2nd':>15}", ""]
    a, b = split(rows)
    for lvl in DOLLAR_FLOORS:
        gone = [r for r in rows if (r.get("dollar_vol_bar") or 0.0) < lvl]
        ka = [r for r in a if (r.get("dollar_vol_bar") or 0.0) >= lvl]
        kb = [r for r in b if (r.get("dollar_vol_bar") or 0.0) >= lvl]
        L.append(f"  ${lvl:>11,.0f}{len(gone):>10,}"
                 f"{per_trade(gone, MEASURED_FRICTION):>14,.2f}"
                 f"{per_trade(ka, MEASURED_FRICTION):>15,.2f}"
                 f"{per_trade(kb, MEASURED_FRICTION):>15,.2f}")
    L += ["",
          f"  baseline, no floor: 1st half "
          f"{per_trade(a, MEASURED_FRICTION):,.2f}, 2nd half "
          f"{per_trade(b, MEASURED_FRICTION):,.2f} per trade", ""]
    return L


def render(rows: list[dict], strategy: str, n_days: int, elapsed: float,
           jobs: int) -> list[str]:
    clauses = CLAUSES_BY_STRATEGY[strategy]
    mins = BAR_MINUTES[strategy]
    L = ["BY HOW MUCH DID EACH ENTRY CLAUSE PASS?", "",
         f"  strategy {strategy.upper()}   outcome: net at "
         f"${MEASURED_FRICTION:.2f}/round trip   {QUANTILES} buckets",
         f"  every column below is computed on {mins}-MINUTE BARS",
         f"  elapsed {elapsed:.1f}s on {jobs} worker(s)", "",
         "  PRE-REGISTERED: a wider margin over the threshold predicts a better",
         "  net per trade. CLEARS requires a bucket positive after friction in",
         f"  both halves AND after dropping its best {DROP} trades.", ""]
    L += population(rows, strategy, n_days)
    located = [r for r in rows if r.get("located")]
    if not located:
        return L + ["NO ENTRY BAR WAS LOCATED. Nothing below can be computed.",
                    ""]

    L += absolute_section(located, clauses, strategy)
    _rows, flat = add_slack(located, clauses)
    L += binding_section(located, flat)

    # add_slack FIRST, then with_net: `with_net` copies each row whole, so the
    # slack columns come across with everything else. Reversing these two lines
    # would score rows that do not have them yet and leave min_slack unbucketed
    # with n=0 -- which renders as "not bucketable" rather than as an error.
    scored = with_net(located, MEASURED_FRICTION)

    L += ["EACH MARGIN AGAINST OUTCOME", "",
          "  Every column printed, nothing ranked, nothing omitted.", ""]
    verdicts: dict[str, str] = {}
    for col in list(clauses) + ["min_slack"]:
        sec, v = one_column(scored, col)
        L += sec
        verdicts[col] = v

    fams = {f for f, cols in FAMILIES.items()
            if any(c in clauses for c in cols)}
    L += ["MULTIPLICITY", "",
          f"  {len(clauses) + 1} columns x {QUANTILES} buckets x 2 halves = "
          f"{(len(clauses)+1) * QUANTILES * 2} comparisons.",
          f"  Counted by family, the clause columns are {len(fams)} "
          f"famil(ies): {', '.join(sorted(fams)) or 'none that entry_features names'}.",
          "  Columns entry_features already tested on a DIFFERENT population",
          "  are a second look at the same idea, not independent evidence.", ""]

    L += ladder_section(scored)

    L += ["THE VERDICT", ""]
    clears = [c for c, v in verdicts.items() if v == "CLEARS"]
    seps = [c for c, v in verdicts.items() if v == "SEPARATES"]
    if clears:
        L += [f"  CLEARS: {', '.join(clears)}", "",
              "  One bucket profitable after friction in both halves and after",
              f"  dropping its best {DROP}. That is a candidate to test out of",
              "  sample, not a rule to ship.", ""]
    elif seps:
        L += [f"  SEPARATES, nothing clears: {', '.join(seps)}", "",
              "  A gradient with no profitable end is a description of the",
              "  losses, not a filter: removing the worst bucket leaves the",
              "  rest still losing.", ""]
    else:
        L += ["  NOTHING. No clause's margin separates the winners from the",
              "  losers, in either direction.", "",
              "  Read with the absolute section above, that is the answer to",
              "  the question this was built for: the entries ARE thin, and",
              "  the thin ones are not what is losing the money.", ""]

    L += ["WHAT THIS IS NOT", "",
          "  NOT A RULE. No filter was applied; the trades are exactly the ones",
          f"  {strategy.upper()} took.",
          "  NOT A THRESHOLD SEARCH. The ladder prints every level so that",
          "  choosing one is visibly a choice made after seeing the outcome.",
          "  NOT OUT OF SAMPLE. holdout.json has not been spent here.",
          "  NOT AN ABSOLUTE SCALE, in the percentile sections. A rank within",
          "  this population cannot say the population is marginal.", ""]
    return L


# --- cli --------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    # MC5 is measured on ITS OWN three clauses, off its own 5-minute signal
    # frame. `features_at` is never run against it: that is MCL's 1-minute
    # feature set, and pointing it at a 5-minute frame would compute a table
    # the features were not written for and print it as a measurement.
    p.add_argument("--strategy", default="mcl", choices=["mcl", "mc5"])
    p.add_argument("--pairs", default=PAIRS)
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default="XNAS.BASIC")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--jobs", type=int, default=0)
    p.add_argument("--out", default=None)
    return p


def main(argv=None) -> int:
    from common.databento_fetch import default_archive
    from common.pit_h0 import load_pit
    from common.pit_strategy import WARMUP_SESSIONS
    from common.screen_sim import date_of, window_slices

    a = build_parser().parse_args(argv)
    by_date = load_pit(Path(a.pairs))
    archive = Path(a.archive) if a.archive else default_archive()
    slices = {date_of(p): p for p in window_slices(archive, a.dataset)}
    days = sorted(by_date)
    if a.limit:
        days = days[:a.limit]
    have = [d for d in days if d in slices]

    tasks = []
    for k, day in enumerate(have):
        first = max(0, k - WARMUP_SESSIONS)
        tasks.append(([str(slices[d]) for d in have[first:k + 1]], day,
                      by_date[day], a.strategy))

    jobs = (os.cpu_count() or 1) if a.jobs == 0 else max(1, a.jobs)
    print(f"entry_margins: {len(tasks):,} session(s) on {jobs} worker(s)",
          flush=True)
    t0 = time.time()
    got: dict[str, list] = {}
    if jobs == 1:
        for day, rows, err in map(run_day, tasks):
            got[day] = rows
            if err:
                print(f"  ! {day}: {err}", flush=True)
    else:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            for k, (day, rows, err) in enumerate(
                    ex.map(run_day, tasks, chunksize=4), 1):
                got[day] = rows
                if err:
                    print(f"  ! {day}: {err}", flush=True)
                if k % 50 == 0:
                    print(f"  ... {k:,} of {len(tasks):,}", flush=True)

    # DAY ORDER, not completion order -- float addition is not associative and
    # a net that moves with --jobs is not a constant.
    rows: list[dict] = []
    for day in sorted(got):
        rows.extend(got[day])
    derive(rows)
    emit("\n".join(render(rows, a.strategy, len(have), time.time() - t0, jobs)),
         a.out or f"var/reports/entry_margins_{a.strategy}.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
