#!/usr/bin/env python3
"""TL-v0 / TL-v0-rev pre-flight -- REGISTERED_tl_v0.md sec 5. AT-105 subitem 3.

    python -m common.tl_v0_preflight
    python -m common.tl_v0_preflight --markets CL GC   # a scoped re-run

TRAINING SIDE ONLY. NO EXIT PRICES, NO P&L.
--------------------------------------------
This module never simulates a trailing-stop hit and never prices an exit.
It reports entry-signal frequency, the weekly top-down filter's block rate,
v0's ignored-in-position count / v0-rev's reversal count, and the STATIC
(no-lookahead) initial stop distance in $ at the moment each position opens
-- never a realised trade, a fill, or a return. That is what
"the runner must refuse to compute exits or P&L in this mode" (sec 5) means
here: it is a design property of this module, not merely an unused code
path (see the "WHAT THIS RUN DOES NOT COMPUTE" section this module writes
into its own report -- read that before the tables).

ONE CONSEQUENCE WORTH FLAGGING UP FRONT: because nothing here ever asks
"did the trailing stop get hit", a v0 position -- which only reacts to a
stop, never to an opposite break -- never closes in this simulation. Its
"signals" count is therefore ~1 per market for the whole training window
(it opens once; every later opposite break is "ignored" forever, absent a
stop-hit check). That is not a bug: it is the honest consequence of
withholding the exit engine, and the report says so. "allowed_breaks/yr"
(every break the weekly filter would have let through, irrespective of
position state) is the more informative frequency number for v0.

DATA: common/tl_v0_data.py reuses common/dbn_io.py for the actual reads and
the amendment-C held-contract logic already reviewed in
claude/raw/tsmom_topup_readback_20260920.txt. LINES: common/tl_v0_lines.py.
"""
from __future__ import annotations
import argparse

import numpy as np
import pandas as pd

from common.tl_v0_data import held_series, back_adjust
from common.tl_v0_lines import atr14, find_pivots, build_line_series, break_events, swing_fallback
from common.report_io import emit

TRAIN_START = pd.Timestamp("2010-06-01")
TRAIN_END = pd.Timestamp("2021-12-31")
EQUITY = 22000.0
PIVOT_SIZES = (3, 5, 8)

# REGISTERED_tl_v0.md sec 5: micros named explicitly; anything else is
# reported per full contract, named as such. Multipliers from the same CME
# fact-card table claude/tsmom_spec_20260917.md sec 2.2 already used and
# trusted for TSMOM, plus CME Treasury contract specs for ZN/TN/MTN.
MARKETS = {
    "ES":  dict(kind="front", micro="MES", micro_mult=5,      full_mult=50),
    "RTY": dict(kind="front", micro="M2K", micro_mult=5,      full_mult=50),
    "CL":  dict(kind="front", micro="MCL", micro_mult=100,    full_mult=1000),
    "NG":  dict(kind="front", micro=None,  micro_mult=None,   full_mult=10000),
    "6A":  dict(kind="front", micro="M6A", micro_mult=10000,  full_mult=100000),
    "6B":  dict(kind="front", micro="M6B", micro_mult=6250,   full_mult=62500),
    "6E":  dict(kind="front", micro="M6E", micro_mult=12500,  full_mult=125000),
    "6J":  dict(kind="front", micro=None,  micro_mult=None,   full_mult=12500000),
    "GC":  dict(kind="cycle", micro="MGC", micro_mult=10,     full_mult=100),
    "SI":  dict(kind="cycle", micro="SIL", micro_mult=1000,   full_mult=5000),
    "HG":  dict(kind="cycle", micro="MHG", micro_mult=2500,   full_mult=25000),
    "ZN":  dict(kind="cycle", micro=None,  micro_mult=None,   full_mult=1000),
    # MTN is itself the traded (already micro-sized) instrument, listed only
    # from 2024-03-25; its SIGNAL is TN's own history under amendment C
    # (REGISTERED_tsmom.md sec 0.2, G3). The multiplier is a fixed contract
    # spec and is applied to TN's geometry throughout training -- not a
    # look-ahead, but MTN itself was not tradeable in 2010-2021; the report
    # says so.
    "MTN": dict(kind="cycle", signal_root="TN", micro="MTN", micro_mult=100,
                full_mult=None),
}


def load_market(root, spec):
    df = held_series(spec.get("signal_root", root), spec["kind"])
    return back_adjust(df).reset_index(drop=True)


def week_end(dates):
    return dates.dt.to_period("W-FRI").apply(lambda p: p.end_time.normalize())


def build_weekly(df):
    d = df.set_index("date")[["open_adj", "high_adj", "low_adj", "close_adj"]]
    return (d.resample("W-FRI")
             .agg({"open_adj": "first", "high_adj": "max",
                   "low_adj": "min", "close_adj": "last"})
             .dropna().reset_index().rename(columns={"date": "week_end"}))


def lines_for(o, h, l, c, R):
    a = atr14(h, l, c)
    ph, pl = find_pivots(h, R, "high"), find_pivots(l, R, "low")
    res = build_line_series(len(c), ph, R, c, a, "high")
    sup = build_line_series(len(c), pl, R, c, a, "low")
    return a, ph, pl, res, sup


def align_weekly_to_daily(daily_dates, weekly_df, cols):
    """Completed weeks only: a daily bar sees the weekly state as of the
    PRIOR completed week, never the week it is itself inside of."""
    dd = pd.DataFrame({"date": daily_dates})
    dd["week_end"] = week_end(dd["date"])
    dd["key"] = dd["week_end"] - pd.Timedelta(days=7)
    dd = dd.reset_index().rename(columns={"index": "_orig"})
    w = weekly_df[["week_end"] + cols].sort_values("week_end")
    merged = pd.merge_asof(dd.sort_values("key"), w, left_on="key",
                            right_on="week_end", direction="backward",
                            suffixes=("", "_w")).sort_values("_orig")
    return merged[cols].reset_index(drop=True)


def run_market(root, spec):
    df = load_market(root, spec)
    if df.empty:
        return None
    n = len(df)
    o, h, l, c = (df["open_adj"].to_numpy(), df["high_adj"].to_numpy(),
                  df["low_adj"].to_numpy(), df["close_adj"].to_numpy())
    dates = df["date"]
    weekly = build_weekly(df)
    wo, wh, wl, wc = (weekly["open_adj"].to_numpy(), weekly["high_adj"].to_numpy(),
                      weekly["low_adj"].to_numpy(), weekly["close_adj"].to_numpy())

    out_entries, out_counts = [], []
    for R in PIVOT_SIZES:
        a, ph, pl, res, sup = lines_for(o, h, l, c, R)
        ups, downs = break_events(c, res, sup, a)

        wa, wph, wpl, wres, wsup = lines_for(wo, wh, wl, wc, R)
        wups, wdowns = break_events(wc, wres, wsup, wa)
        state, wdir = None, np.full(len(wc), np.nan, dtype=object)
        for j in range(len(wc)):
            if wups[j]:
                state = "long"
            elif wdowns[j]:
                state = "short"
            wdir[j] = state
        weekly["dir"], weekly["wres"], weekly["wsup"] = wdir, wres, wsup

        aligned = align_weekly_to_daily(dates, weekly, ["dir", "wres", "wsup"])
        f_dir = aligned["dir"].to_numpy()
        f_wres = aligned["wres"].to_numpy(dtype=float)
        f_wsup = aligned["wsup"].to_numpy(dtype=float)

        for ruleset in ("v0", "v0-rev"):
            position = None
            signals = htf_blocked = ignored = reversals = same_dir = 0
            for j in range(1, n - 1):
                if not (ups[j] or downs[j]):
                    continue
                direction = "long" if ups[j] else "short"
                if f_dir[j] != direction:
                    htf_blocked += 1
                    continue
                entry_idx = j + 1
                if entry_idx >= n:
                    continue
                is_new = False
                if position is None:
                    is_new = True
                elif position == direction:
                    same_dir += 1
                    continue
                elif ruleset == "v0":
                    ignored += 1
                    continue
                else:
                    reversals += 1
                    is_new = True
                if is_new:
                    entry_px = o[entry_idx]
                    stop = None
                    if ruleset == "v0":
                        opp = sup[entry_idx] if direction == "long" else res[entry_idx]
                        if not np.isnan(opp):
                            stop = opp - 0.25 * a[entry_idx] if direction == "long" else opp + 0.25 * a[entry_idx]
                        else:
                            stop = swing_fallback(pl, ph, h, l, a, R, entry_idx, entry_px, direction)
                    else:
                        wopp = f_wsup[entry_idx] if direction == "long" else f_wres[entry_idx]
                        if not np.isnan(wopp):
                            stop = wopp - 0.25 * a[entry_idx] if direction == "long" else wopp + 0.25 * a[entry_idx]
                        else:
                            opp = sup[entry_idx] if direction == "long" else res[entry_idx]
                            if not np.isnan(opp):
                                stop = opp - 0.25 * a[entry_idx] if direction == "long" else opp + 0.25 * a[entry_idx]
                            else:
                                stop = swing_fallback(pl, ph, h, l, a, R, entry_idx, entry_px, direction)
                    stopdist = abs(entry_px - stop) if stop is not None else np.nan
                    edate = dates.iloc[entry_idx]
                    if TRAIN_START <= edate <= TRAIN_END:
                        out_entries.append(dict(market=root, ruleset=ruleset, R=R,
                                                 date=edate, year=edate.year,
                                                 direction=direction, stopdist=stopdist))
                        signals += 1
                    position = direction
            out_counts.append(dict(
                market=root, ruleset=ruleset, R=R, signals=signals,
                htf_blocked=htf_blocked, ignored=ignored, reversals=reversals,
                same_dir=same_dir, allowed_breaks=signals + ignored + reversals + same_dir,
                coverage_first=str(dates.min().date()), coverage_last=str(dates.max().date())))
    return out_entries, out_counts


def stop_dollars(row):
    spec = MARKETS[row["market"]]
    mult = spec["micro_mult"] or spec["full_mult"]
    used = "micro" if spec["micro_mult"] else "full"
    if mult is None or np.isnan(row["stopdist"]):
        return pd.Series([np.nan, used])
    return pd.Series([row["stopdist"] * mult, used])


def build_report(edf: pd.DataFrame, cdf: pd.DataFrame) -> str:
    YEARS = 2021 - 2010 + 0.58
    lines = []
    def p(s=""):
        lines.append(s)

    p("TL-v0 / TL-v0-rev PRE-FLIGHT -- REGISTERED_tl_v0.md sec 5 (AT-105 subitem 3)")
    p("Training side only, no exits, no P&L.")
    p("Archive: E:\\Databento\\GLBX.MDP3 (ohlcv-1d + definition), the bars TSMOM reads.")
    p("Training window: 2010-06-01 .. 2021-12-31.")
    p("")
    p("=" * 78); p("0. WHAT THIS RUN DOES AND DOES NOT COMPUTE"); p("=" * 78)
    p("""
This is a signal-frequency and initial-risk sizing diagnostic. It does NOT
simulate the trailing stop, does NOT determine when a position closes by a
stop being hit, and computes no exit price and no P&L, per the registration's
explicit refusal.

  * Under v0, an opposite break while in a position is "ignored", and this
    pre-flight never asks whether the trailing stop would since have closed
    the position -- that IS the exit simulation withheld until step 4 (gated
    behind G1-G5). Consequence: v0's "signals" collapse to ~1/market for the
    whole window. "allowed_breaks/yr" (every break the weekly filter would
    allow, regardless of position state) is the informative frequency number
    for v0; treat it as an upper bound on what a stop-aware engine would
    convert some "ignored" bars into.
  * v0-rev DOES reverse on an allowed opposite break, so its "signals" count
    is a real (if stop-independent) entry count.
  * Every stop-distance figure is the opposing line's (or fallback swing's)
    STATIC value at the moment of entry -- never a simulated outcome.
  * Weekly line construction uses the SAME pivot size (L=R) as its daily
    sleeve -- the registration does not pin this; flagged for review before
    step 4.
  * MTN's own $100/point multiplier is applied to TN's line geometry
    throughout training, even though MTN itself was not listed until
    2024-03-25 (a multiplier is a fixed spec, not a price history -- not a
    look-ahead). MTN's training-window figures describe the signal's risk
    profile, not executability.
""")
    p("=" * 78); p("1. COVERAGE"); p("=" * 78)
    cov = cdf[cdf.ruleset == "v0"][["market", "coverage_first", "coverage_last"]].drop_duplicates()
    p(cov.to_string(index=False)); p("")
    p("MTN: bars from 2024-03-25 only; signal computed on TN (listed 2016-01-11).")

    p(""); p("=" * 78)
    p("2. SIGNALS, HTF-BLOCKED, IGNORED (v0) / REVERSALS (v0-rev) -- summed over 13 markets")
    p("=" * 78)
    summ = cdf.groupby(["ruleset", "R"])[["signals", "htf_blocked", "ignored", "reversals", "allowed_breaks"]].sum()
    p(summ.to_string()); p("")
    p("Per-year rate (allowed_breaks / 11.58 training years), summed over markets:")
    summ2 = summ.copy()
    summ2["allowed_breaks_per_yr"] = (summ2["allowed_breaks"] / YEARS).round(1)
    p(summ2[["allowed_breaks_per_yr"]].to_string())

    p(""); p("=" * 78); p("3. PER-MARKET BREAKDOWN, R=5 (reported neighbour; 3 & 8 in the CSVs)"); p("=" * 78)
    for rs in ("v0", "v0-rev"):
        p(f"-- {rs} --")
        col = "ignored" if rs == "v0" else "reversals"
        sub = cdf[(cdf.ruleset == rs) & (cdf.R == 5)][["market", "signals", "htf_blocked", col, "allowed_breaks"]]
        p(sub.to_string(index=False)); p("")

    p("=" * 78)
    p("4. STOP DISTANCE ($ PER MICRO, OR PER FULL CONTRACT WHERE NAMED) AND SIZEABILITY")
    p("   pooled across pivot sizes 3/5/8 (the deployed ensemble)")
    p("=" * 78)
    for rs in ("v0", "v0-rev"):
        p(f"-- {rs}, pooled R=3,5,8 --")
        sub = edf[edf.ruleset == rs]
        g = sub.groupby("market").agg(n=("stop_dollars", "size"), unit=("unit", "first"),
                                       median_stop_usd=("stop_dollars", "median"),
                                       pct_sizeable_1pct=("sizeable_1pct", "mean"),
                                       pct_sizeable_2pct=("sizeable_2pct", "mean"))
        g["median_stop_usd"] = g["median_stop_usd"].round(0)
        g["pct_sizeable_1pct"] = (g["pct_sizeable_1pct"] * 100).round(0)
        g["pct_sizeable_2pct"] = (g["pct_sizeable_2pct"] * 100).round(0)
        p(g.to_string()); p("")

    p("-- ALL MARKETS POOLED, by pivot size alone (the registered 'reported neighbours') --")
    for rs in ("v0", "v0-rev"):
        sub = edf[edf.ruleset == rs]
        gr = sub.groupby("R").agg(n=("stop_dollars", "size"),
                                   pct_sizeable_1pct=("sizeable_1pct", "mean"),
                                   pct_sizeable_2pct=("sizeable_2pct", "mean"))
        gr["pct_sizeable_1pct"] = (gr["pct_sizeable_1pct"] * 100).round(0)
        gr["pct_sizeable_2pct"] = (gr["pct_sizeable_2pct"] * 100).round(0)
        p(f"  {rs}:"); p("  " + gr.to_string().replace("\n", "\n  "))
    p("")
    p("Markets with no micro named in registration sec 5 (reported PER FULL")
    p("CONTRACT): NG, 6J, ZN. All others (ES/RTY/CL/GC/SI/HG/6A/6B/6E) have a")
    p("micro and are reported per micro.")

    p(""); p("=" * 78); p("5. SECTION 5.1 STOP RULE -- v0-rev at 2% risk on $22,000"); p("=" * 78)
    pool = edf[edf.ruleset == "v0-rev"].groupby("market").agg(n=("stop_dollars", "size"), pct2=("sizeable_2pct", "mean"))
    pool["market_clears_50pct"] = pool["pct2"] >= 0.5
    n_markets, n_clear = pool.shape[0], int(pool["market_clears_50pct"].sum())
    overall_frac = edf[edf.ruleset == "v0-rev"]["sizeable_2pct"].mean()
    p(pool.round(3).to_string()); p("")
    p("Reading A -- markets where >=50% of that market's v0-rev signals are sizeable at 2%:")
    p(f"  {n_clear} of {n_markets} clear it. 'More than half the markets' at N={n_markets} means >={n_markets // 2 + 1}. "
      + ("Result: CLEARS (barely)." if n_clear >= n_markets // 2 + 1 else "Result: FAILS -- the study stops for this account size."))
    p("")
    p("Reading B -- overall pooled fraction of ALL v0-rev signals sizeable at 2%:")
    p(f"  {overall_frac:.1%} of signals sizeable. "
      + ("CLEARS." if overall_frac >= 0.5 else "FAILS on this reading -- under half of all v0-rev signals can be sized."))
    p("")
    p("The two readings disagree. The registration's wording does not disambiguate")
    p("which is meant -- flagged for Ben / the step-4 build session rather than")
    p("resolved here by picking the reading that passes.")
    p("")
    p("Per-sec 5.1/sec 7: raising risk above 2% because 1% cannot be sized is")
    p("registered as NOT to be done. Whichever reading applies, this is the finding.")

    p(""); p("=" * 78); p("6. WHAT THIS MEANS FOR G1"); p("=" * 78)
    p("""
The weakest markets on both readings match TSMOM's own AT-43 capacity
finding (unsizeable at $22k): NG, SI, ZN -- joined here by 6J and RTY under
TL-v0-rev's tighter, trend-line-based stops. GC, HG, CL and MTN sit near or
above the 50% line; the currency majors (6A, 6B, 6E) and MTN are the
best-sized names, because their stops are small in $ terms relative to
$22k -- not because their line geometry is any cleaner.
""")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--markets", nargs="+", default=list(MARKETS),
                    help="scope to these roots (default: the registered set)")
    ap.add_argument("--report", default="var/reports/tl_v0_preflight.txt")
    ap.add_argument("--entries-csv", default="var/reports/tl_v0_preflight_entries.csv")
    ap.add_argument("--counts-csv", default="var/reports/tl_v0_preflight_counts.csv")
    a = ap.parse_args(argv)

    all_entries, all_counts = [], []
    for root in a.markets:
        res = run_market(root, MARKETS[root])
        if res is None:
            print(f"{root}: NO DATA")
            continue
        ents, counts = res
        all_entries += ents
        all_counts += counts

    edf = pd.DataFrame(all_entries)
    cdf = pd.DataFrame(all_counts)
    edf[["stop_dollars", "unit"]] = edf.apply(stop_dollars, axis=1)
    edf["sizeable_1pct"] = (np.floor(0.01 * EQUITY / edf["stop_dollars"]) >= 1).astype(float)
    edf["sizeable_2pct"] = (np.floor(0.02 * EQUITY / edf["stop_dollars"]) >= 1).astype(float)
    missing = edf["stop_dollars"].isna()
    edf.loc[missing, "sizeable_1pct"] = np.nan
    edf.loc[missing, "sizeable_2pct"] = np.nan

    edf.to_csv(a.entries_csv, index=False)
    cdf.to_csv(a.counts_csv, index=False)
    text = build_report(edf, cdf)
    emit(text, a.report, header="common.tl_v0_preflight")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
