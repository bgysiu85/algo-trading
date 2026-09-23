#!/usr/bin/env python3
r"""Volume confirmation on the break -- measured as a ceiling, not a strategy.

    python -m strategy.orb.sip_volume bars --jobs 4    # build the volume cache
    python -m strategy.orb.sip_volume score

`REGISTERED_orb_sip.md` amendment I. The last named ORB candidate.

WHAT "CEILING" MEANS HERE, AND WHY IT IS NOT A DEFECT
-----------------------------------------------------
A minute bar's volume is complete only at the END of that minute, and the entry
happens inside it. So the breakout bar's volume is NOT knowable when the rule
would have to fire, and I.1's primary reading uses information the trader does
not have. That is deliberate (I.2): if the filter cannot help even when handed
the future, the honest version cannot succeed, and one run settles the family.
A pass would earn the tradeable form a registration and nothing else -- the
primary reading is never adoptable on its own terms.

The tradeable form is computed and reported beside it FOR INFORMATION ONLY.
The decision rests on the ceiling alone: reporting two readings and then
choosing whichever looks better is the two-denominator failure this program
refuses.
"""
from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from common.breadth import BOOT_MIN_P, SEED
from strategy.orb import sip_context as C
from strategy.orb import sip_report as P
from strategy.orb import sip_resolved as R
from strategy.orb.sip_summary import day_file

DATASET = "XNAS.ITCH"
BASELINE = 5                  # I.1: the strategy's own opening-range length
CONFIRMED, WEAK, NO_DATA = "CONFIRMED", "WEAK", "NO_DATA"
DRAWS = 2000                  # I.4(a)
NULL_PCT = 95
CACHE_DEFAULT = Path("var/cache/orb_sip/break_volume.csv.gz")
REPORT_DEFAULT = Path("var/reports/orb_sip_volume.txt")
COLS = ["symbol", "date", "break_vol", "prior_med", "lag_vol", "lag_med"]


def volumes(minute, volume, entry_min: int, baseline: int = BASELINE) -> tuple | None:
    """Break-bar and lagged volumes against their own prior-median baselines.

    Returns (break_vol, prior_med, lag_vol, lag_med), any of which may be nan
    when the bars are not there. `break` is the entry minute -- the ceiling
    reading. `lag` is the last COMPLETED minute before it, measured the same
    way one minute earlier, which is what a trader could actually see.
    """
    m = np.asarray(minute)
    v = np.asarray(volume, float)
    # No sort: both helpers below select by MASK on the minute value, so bar
    # order is irrelevant here. A sort was written first and removed once a
    # mutation showed nothing depended on it -- dead code that looks like a
    # guarantee is worse than none.

    def at(x):
        hit = m == x
        return float(v[hit][0]) if hit.any() else float("nan")

    def med(lo, hi):
        w = (m >= lo) & (m <= hi)
        return float(np.median(v[w])) if w.any() else float("nan")

    return (at(entry_min), med(entry_min - baseline, entry_min - 1),
            at(entry_min - 1), med(entry_min - 1 - baseline, entry_min - 2))


def label(break_vol, prior_med) -> np.ndarray:
    """I.1. A tie is WEAK, and a missing reading is NO_DATA, never guessed."""
    b = np.asarray(break_vol, float)
    p = np.asarray(prior_med, float)
    bad = np.isnan(b) | np.isnan(p)
    return np.where(bad, NO_DATA, np.where(b > p, CONFIRMED, WEAK))


def _one(args):
    archive, day, rows_json = args
    from common.dbn_io import read_dbn
    rows = pd.read_json(rows_json, orient="records")
    try:
        bars = read_dbn(day_file(Path(archive), DATASET, day))
    except Exception:  # noqa: BLE001
        return []
    et = bars.index.tz_convert("America/New_York")
    mins = (et.hour * 60 + et.minute).to_numpy()
    sym = bars["symbol"].to_numpy()
    vol = bars["volume"].to_numpy(float)
    out = []
    for t in rows.itertuples():
        k = sym == t.symbol
        if not k.any():
            out.append((t.symbol, day, np.nan, np.nan, np.nan, np.nan))
            continue
        out.append((t.symbol, day, *volumes(mins[k], vol[k], int(t.entry_min))))
    return out


def build_cache(ledger: pd.DataFrame, archive: Path, jobs: int,
                tmp: Path) -> pd.DataFrame:
    tmp.mkdir(parents=True, exist_ok=True)
    work = []
    for day, g in ledger.groupby("date", sort=True):
        f = tmp / f"{day}.json"
        g[["symbol", "entry_min"]].to_json(f, orient="records")
        work.append((str(archive), day, str(f)))
    if jobs > 1:
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            parts = list(ex.map(_one, work))
    else:
        parts = [_one(w) for w in work]
    return pd.DataFrame([x for p in parts for x in p], columns=COLS)


# ------------------------------------------------------------------ controls

def shuffled_label_null(d: pd.DataFrame, col: str, keep_col: str,
                        draws: int = DRAWS, seed: int = SEED) -> dict:
    """I.4(a): the same labels dealt to the same TRADES at random.

    Per-trade, where H's null was per-session, because I is a per-trade filter.
    Permuting preserves the 60/40 proportion exactly; only which trades carry
    which label changes.
    """
    syms, si = np.unique(d["symbol"].to_numpy(), return_inverse=True)
    r = d[col].to_numpy(float)
    keep = d[keep_col].to_numpy(bool)
    n_sym = len(syms)
    obs_mean, obs_drop5 = C._mean_and_drop5(si, r, keep, n_sym)
    rng = np.random.default_rng(seed)
    perm = keep.copy()
    means = np.empty(draws)
    drops = np.empty(draws)
    for i in range(draws):
        rng.shuffle(perm)
        means[i], drops[i] = C._mean_and_drop5(si, r, perm, n_sym)
    valid = int(np.count_nonzero(~np.isnan(means)))
    return {"draws": draws, "valid_draws": valid,
            "obs_mean": obs_mean, "obs_drop5": obs_drop5,
            "mean_p95": float(np.nanpercentile(means, NULL_PCT)),
            "drop5_p95": float(np.nanpercentile(drops, NULL_PCT)),
            "mean_beats": bool(obs_mean > np.nanpercentile(means, NULL_PCT)),
            "drop5_beats": bool(obs_drop5 > np.nanpercentile(drops, NULL_PCT)),
            "mean_p": float(np.nanmean(means >= obs_mean)),
            "drop5_p": float(np.nanmean(drops >= obs_drop5))}


def composition(d: pd.DataFrame, bucket_col: str = "vol_label") -> pd.DataFrame:
    """I.4(b): is CONFIRMED really a time-of-day or an RVOL filter?"""
    t = d.copy()
    edge = [569, 575, 580, 600, 660, 780, 960]
    names = ["<=575", "576-580", "581-600", "601-660", "661-780", "781+"]
    t["when"] = pd.cut(t["entry_min"], bins=edge, labels=names)
    t["rank_decile"] = pd.cut(t["rank"], bins=[0, 5, 10, 15, 20],
                              labels=["1-5", "6-10", "11-15", "16-20"])
    rows = []
    for key in ("when", "rank_decile"):
        g = t.groupby(key, observed=True)[bucket_col]
        rows.append(pd.DataFrame({
            "group": [f"{key}={k}" for k in g.groups],
            "trades": [len(g.get_group(k)) for k in g.groups],
            "confirmed_share": [float((g.get_group(k) == CONFIRMED).mean())
                                for k in g.groups]}))
    return pd.concat(rows, ignore_index=True)


def delta_drop(d: pd.DataFrame, col: str, bucket_col: str = "vol_label") -> dict:
    t = d[d[bucket_col].isin([CONFIRMED, WEAK])]
    piv = (t.pivot_table(index="symbol", columns=bucket_col, values=col,
                         aggfunc="sum", fill_value=0.0)
             .reindex(columns=[CONFIRMED, WEAK], fill_value=0.0))
    delta = (piv[CONFIRMED] - piv[WEAK]).sort_values(ascending=False)
    return {"delta": float(delta.sum()),
            **{f"drop{k}": float(delta.iloc[k:].sum()) for k in (1, 3, 5)},
            "symbols": int(len(delta))}


def per_symbol_day(d: pd.DataFrame, col: str, bucket_col: str = "vol_label") -> dict:
    """I.4(c): the second denominator."""
    out = {}
    for b in (CONFIRMED, WEAK):
        g = d[d[bucket_col] == b]
        by = g.groupby(["symbol", "date"])[col].sum()
        out[b] = float(by.mean()) if len(by) else float("nan")
    out["delta"] = out[CONFIRMED] - out[WEAK]
    return out


def render(d: pd.DataFrame, arms: dict, crit: dict, null: dict, comp,
           delta: dict, sd: dict, lag_arms: dict, level: str) -> list[str]:
    L = ["ORB, STOCKS IN PLAY -- VOLUME CONFIRMATION ON THE BREAK (amendment I)",
         "",
         "  registration   docs/research/REGISTERED_orb_sip.md amendment I,",
         "                 committed before this ran",
         "  rule           CONFIRMED when the breakout bar's volume exceeds the",
         f"                 median of the {BASELINE} minutes before it. No multiplier.",
         "  data           XNAS.ITCH minute bars already on disk; nothing bought",
         f"  criteria at    {level}, unrelaxed; criterion 7 unscored (E.2)", "",
         "  *** THIS PRIMARY READING IS A CEILING, NOT A STRATEGY (I.2) ***",
         "  A minute bar's volume is complete only at the end of the minute the",
         "  entry happens inside, so the rule below uses information the trader",
         "  does not have. If it fails, the honest version cannot succeed. If it",
         "  passes, it earns the tradeable form a registration and nothing more.",
         "",
         f"  trades         {len(d):,}", "",
         "BOTH BUCKETS, IN FULL", "",
         "  bucket        trades   mean_R  gross_R  fric_R    total_R    drop5_R"
         "    win  boot_p",
         "  " + "-" * 92]
    for b in (CONFIRMED, WEAK, NO_DATA):
        if b in arms and arms[b].get("trades"):
            L.append(P._arm_line(b, arms[b]))

    L += ["", "THE BAR: CRITERIA 1-6 ON THE CONFIRMED BUCKET (I.3)", ""]
    w = crit
    a = arms[CONFIRMED]
    names = {1: "drop-top-3 and drop-top-5 > 0",
             2: f"bootstrap P(total>0) >= {BOOT_MIN_P:.2f}",
             3: f"mean net >= +{P.MIN_R_PER_TRADE:.2f}R",
             4: f"trades >= {P.MIN_TRADES}", 5: "both halves > 0",
             6: "both sides > 0"}
    vals = {1: f"{a['drop3_R']:+.1f}R / {a['drop5_R']:+.1f}R",
            2: f"{a['boot_p']:.3f}", 3: f"{a['mean_R']:+.3f}R",
            4: f"{a['trades']:,}", 5: f"{a['early_R']:+.1f}R / {a['late_R']:+.1f}R",
            6: f"{a['long_mean_R']:+.3f}R / {a['short_mean_R']:+.3f}R"}
    for n in range(1, 7):
        L.append(f"  {n}. {names[n]:<36} {vals[n]:>28}   "
                 f"{'pass' if w[n] else 'FAIL'}")
    L += ["", f"  {w['met']} of 6 met, ON THE CEILING READING.", ""]

    L += [f"I.4(a) THE SHUFFLED-LABEL NULL -- {null['draws']:,} draws, seed {SEED}", "",
          "  The same labels dealt to the same TRADES at random, the 60/40",
          "  proportion preserved. Per-trade, where H's null was per-session.", "",
          f"    mean_R    observed {null['obs_mean']:>+8.3f}   null p95 "
          f"{null['mean_p95']:>+8.3f}   p {null['mean_p']:.3f}   "
          f"{'BEATS' if null['mean_beats'] else 'does not beat'}",
          f"    drop5_R   observed {null['obs_drop5']:>+8.1f}   null p95 "
          f"{null['drop5_p95']:>+8.1f}   p {null['drop5_p']:.3f}   "
          f"{'BEATS' if null['drop5_beats'] else 'does not beat'}",
          f"    valid draws {null['valid_draws']:,} of {null['draws']:,}", ""]

    L += ["I.4(b) THE COMPOSITION CONTROL", "",
          "  Volume is mechanically higher early and on heavy names. If",
          "  CONFIRMED is concentrated there, it is a time or an RVOL filter.", "",
          "  " + comp.to_string(index=False).replace("\n", "\n  "), ""]

    L += ["I.4(c) THE SECOND DENOMINATOR", "",
          f"    per trade        CONFIRMED {arms[CONFIRMED]['mean_R']:>+7.3f}R   "
          f"WEAK {arms[WEAK]['mean_R']:>+7.3f}R   "
          f"delta {arms[CONFIRMED]['mean_R'] - arms[WEAK]['mean_R']:>+7.3f}R",
          f"    per symbol-day   CONFIRMED {sd[CONFIRMED]:>+7.3f}R   "
          f"WEAK {sd[WEAK]:>+7.3f}R   delta {sd['delta']:>+7.3f}R",
          "",
          f"    the two denominators "
          f"{'AGREE' if sd['agrees'] else 'DISAGREE -- refusal (PROGRAM_INDEX 4)'}",
          ""]

    L += ["I.4(d) DROP-TOP-N ON THE DELTA", "",
          f"    delta            {delta['delta']:>+9.1f}R over {delta['symbols']:,} symbols",
          f"    less top 1       {delta['drop1']:>+9.1f}R",
          f"    less top 3       {delta['drop3']:>+9.1f}R",
          f"    less top 5       {delta['drop5']:>+9.1f}R", ""]

    L += ["THE TRADEABLE READING -- FOR INFORMATION ONLY (I.2)", "",
          "  The same rule one minute earlier, on the last COMPLETED bar, which",
          "  is what a trader could actually see. The decision does NOT rest on",
          "  this line; it is here so the gap between the two is visible.", ""]
    for b in (CONFIRMED, WEAK):
        if b in lag_arms and lag_arms[b].get("trades"):
            L.append(P._arm_line(b, lag_arms[b]))

    ok = (w["all"] and null["mean_beats"] and null["drop5_beats"]
          and sd["agrees"] and delta["drop5"] > 0)
    L += ["", "VERDICT, AS REGISTERED", ""]
    if ok:
        L += ["  The CONFIRMED bucket clears criteria 1-6 unrelaxed, beats the",
              "  shuffled-label null on both readings, agrees across both",
              "  denominators, and its delta survives drop-top-5 -- ON A READING",
              "  THAT USES THE FUTURE. It is NOT adoptable (I.2). What it earns",
              "  is a registration for the tradeable form, and nothing else.", ""]
    else:
        why = []
        if not w["all"]:
            why.append(f"criteria {sorted(n for n in range(1,7) if not w[n])} fail")
        if not null["mean_beats"]:
            why.append("the mean does not beat a random relabelling")
        if not null["drop5_beats"]:
            why.append("drop-top-5 does not beat a random relabelling")
        if not sd["agrees"]:
            why.append("the two denominators disagree")
        if delta["drop5"] <= 0:
            why.append("the delta does not survive drop-top-5")
        L += ["  NOT ADOPTABLE: " + "; ".join(why) + ".", "",
              "  And this was the CEILING. A filter that cannot help while being",
              "  handed the future cannot help without it, so the tradeable form",
              "  is dead with it.", "",
              "  I.6 retires the volume-confirmation family for ORB: no",
              "  multiplier sweep, no alternative baseline window, no dollar",
              "  volume, no confirmation-on-the-retest.", "",
              "  ORB NOW HAS NO NAMED CANDIDATE REMAINING.", ""]
    L += [f"  I.5 predicted NOT ADOPTABLE: {'WRONG' if ok else 'correct'}.",
          f"  I.5's secondary predicted CONFIRMED's mean beats WEAK while",
          f"  drop-top-5 stays negative: mean "
          f"{'higher' if arms[CONFIRMED]['mean_R'] > arms[WEAK]['mean_R'] else 'NOT higher'}"
          f", drop5 {arms[CONFIRMED]['drop5_R']:+.1f}R -> "
          f"{'correct' if (arms[CONFIRMED]['mean_R'] > arms[WEAK]['mean_R'] and arms[CONFIRMED]['drop5_R'] < 0) else 'WRONG'}.",
          "  (The same secondary was WRONG in amendment H.)", ""]
    return L


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("action", choices=("bars", "score"))
    p.add_argument("--trades", default=str(P.TRADES_DEFAULT))
    p.add_argument("--verdicts", default=str(R.RESOLVED_DEFAULT))
    p.add_argument("--cache", default=str(CACHE_DEFAULT))
    p.add_argument("--archive", default=None)
    p.add_argument("--report", default=str(REPORT_DEFAULT))
    p.add_argument("--level", default="BASE")
    p.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    p.add_argument("--slice", type=int, nargs=2, default=None)
    a = p.parse_args(argv)

    raw = P.load_ledger(Path(a.trades))
    res = P.add_net(R.apply_verdicts(raw, pd.read_csv(a.verdicts, encoding="utf-8")))
    d = P.arm(res, P.PRIMARY_RANGE, "top", P.PRIMARY_TOP_N).copy()

    if a.action == "bars":
        archive = Path(a.archive) if a.archive else None
        if archive is None:
            from common.databento_fetch import default_archive
            archive = default_archive()
        done = pd.DataFrame(columns=COLS)
        if Path(a.cache).exists():
            done = pd.read_csv(a.cache, encoding="utf-8")
        days = sorted(d["date"].unique())
        todo = [x for x in days if x not in set(done["date"])]
        if a.slice:
            todo = todo[a.slice[0]:a.slice[1]]
        if todo:
            got = build_cache(d[d["date"].isin(todo)], archive, a.jobs,
                              Path(a.cache).parent / "_volume")
            done = pd.concat([done, got], ignore_index=True)
            Path(a.cache).parent.mkdir(parents=True, exist_ok=True)
            done.to_csv(a.cache, index=False, encoding="utf-8", compression="gzip")
        print(f"{done['date'].nunique():,} of {len(days):,} sessions cached "
              f"({len(done):,} trades)")
        return 0

    v = pd.read_csv(a.cache, encoding="utf-8")
    d = d.merge(v, on=["symbol", "date"], how="left")
    d["vol_label"] = label(d["break_vol"], d["prior_med"])
    d["lag_label"] = label(d["lag_vol"], d["lag_med"])
    col = f"R_{a.level}"
    split = sorted(d["date"].unique())[d["date"].nunique() // 2]

    arms = {b: P.read_arm(d[d["vol_label"] == b], a.level, split)
            for b in (CONFIRMED, WEAK, NO_DATA)}
    lag_arms = {b: P.read_arm(d[d["lag_label"] == b], a.level, split)
                for b in (CONFIRMED, WEAK)}
    crit = C.criteria_pass(arms[CONFIRMED])
    scored = d[d["vol_label"].isin([CONFIRMED, WEAK])].copy()
    scored["keep"] = scored["vol_label"] == CONFIRMED
    null = shuffled_label_null(scored, col, "keep")
    comp = composition(d[d["vol_label"] != NO_DATA])
    delta = delta_drop(d, col)
    sd = per_symbol_day(d, col)
    sd["agrees"] = bool(np.sign(arms[CONFIRMED]["mean_R"] - arms[WEAK]["mean_R"])
                        == np.sign(sd["delta"]))

    L = render(d, arms, crit, null, comp, delta, sd, lag_arms, a.level)
    Path(a.report).parent.mkdir(parents=True, exist_ok=True)
    Path(a.report).write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    print(f"\nwrote {a.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
