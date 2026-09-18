#!/usr/bin/env python3
r"""The market-context gate: trade WITH the index's opening range, skip AGAINST.

    python -m strategy.orb.sip_context spy --jobs 8     # build the state cache
    python -m strategy.orb.sip_context score

`REGISTERED_orb_sip.md` amendment H. The gate is REGISTERED, not adopted, and
H.5 predicts it fails criterion 1.

THE RULE HAS NO PARAMETER, AND THAT IS THE POINT
------------------------------------------------
A trade is WITH when its side matches the sign of SPY's own 5-minute opening
range -- the same window, on the index, read at the same instant the strategy's
trigger arms (09:35 ET). AGAINST when it opposes it. The magnitude of SPY's
move is deliberately unused and will not be swept: a threshold makes this a
grid, a grid on a book carried by five symbols is a search rather than a test,
and all four failed regime precedents had one. H.5 retires the family on a
failure instead of allowing a knob.

WHY THE SHUFFLED-SIGN CONTROL IS MANDATORY HERE
-----------------------------------------------
Amendment G found that the sessions holding the biggest winners were better
sessions for the rest of the book. But G selected those days BECAUSE they held
a giant winner, so the lift is measured conditional on the outcome and a 50/50
session split can inherit the artifact. H.3(a) therefore requires the real
bucket to beat a 2,000-draw null in which SPY's signs are dealt at random
across the same sessions, on BOTH the mean and drop-top-5. A gate that cannot
beat a coin flip over the same days is a relabelling.
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
from strategy.orb import sip_report as P
from strategy.orb import sip_resolved as R
from strategy.orb.sip_summary import day_file

INDEX = "SPY"                 # H.1, named so a failure cannot become "try QQQ"
DATASET = "XNAS.ITCH"
OR_FROM, OR_TO = 570, 574     # 09:30-09:34 inclusive, the strategy's own window
WITH, AGAINST, FLAT = "WITH", "AGAINST", "FLAT"
DRAWS = 2000                  # H.3(a)
NULL_PCT = 95                 # H.3(a): "the 95th percentile of that null"
STATE_DEFAULT = Path("var/state/orb_sip_spy_or.csv")
REPORT_DEFAULT = Path("var/reports/orb_sip_context.txt")


# --------------------------------------------------------------- the variable

def or_sign(minute, open_, close, lo: int = OR_FROM, hi: int = OR_TO) -> int:
    """+1 / -1 / 0 for the index's opening-range move. 0 is FLAT, not an error."""
    m = np.asarray(minute)
    keep = (m >= lo) & (m <= hi)
    if not keep.any():
        raise ValueError("no index bars in the opening-range window")
    o = np.asarray(open_, float)[keep]
    c = np.asarray(close, float)[keep]
    move = float(c[-1] - o[0])
    return int(np.sign(move))


def _one(args):
    archive, day = args
    from common.dbn_io import read_dbn
    try:
        bars = read_dbn(day_file(Path(archive), DATASET, day))
    except Exception as e:  # noqa: BLE001
        return day, None, 0, f"{type(e).__name__}"
    et = bars.index.tz_convert("America/New_York")
    m = (et.hour * 60 + et.minute).to_numpy()
    s = bars[(bars["symbol"].to_numpy() == INDEX)]
    mm = m[(bars["symbol"].to_numpy() == INDEX)]
    inside = (mm >= OR_FROM) & (mm <= OR_TO)
    if not inside.any():
        return day, None, 0, "no index bars"
    order = np.argsort(mm[inside])
    o = s["open"].to_numpy(float)[inside][order]
    c = s["close"].to_numpy(float)[inside][order]
    return day, int(np.sign(c[-1] - o[0])), int(inside.sum()), ""


def build_state(days, archive: Path, jobs: int) -> pd.DataFrame:
    work = [(str(archive), d) for d in days]
    if jobs > 1:
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            rows = list(ex.map(_one, work))
    else:
        rows = [_one(w) for w in work]
    return pd.DataFrame(rows, columns=["date", "sign", "bars", "error"])


# ------------------------------------------------------------------ bucketing

def bucket(ledger: pd.DataFrame, state: pd.DataFrame) -> pd.Series:
    """H.1. A session with no usable index reading is refused, never guessed."""
    s = state.set_index("date")["sign"]
    missing = set(ledger["date"]) - set(s.dropna().index)
    if missing:
        raise ValueError(f"{len(missing)} sessions have no index reading, "
                         f"e.g. {sorted(missing)[:3]}")
    sign = s.reindex(ledger["date"]).to_numpy()
    side = ledger["side"].to_numpy()
    out = np.where(sign == 0, FLAT, np.where(side == sign, WITH, AGAINST))
    return pd.Series(out, index=ledger.index, name="context")


# ------------------------------------------------------------------- controls

def _packed(d: pd.DataFrame, col: str):
    """Integer-coded arrays so 2,000 redraws stay cheap."""
    dates, di = np.unique(d["date"].to_numpy(), return_inverse=True)
    syms, si = np.unique(d["symbol"].to_numpy(), return_inverse=True)
    return (di, si, d["side"].to_numpy(int), d[col].to_numpy(float),
            len(dates), len(syms))


def _mean_and_drop5(si, r, keep, n_sym: int) -> tuple:
    if not keep.any():
        return float("nan"), float("nan")
    tot = np.bincount(si[keep], weights=r[keep], minlength=n_sym)
    ranked = np.sort(tot)[::-1]
    return float(r[keep].mean()), float(ranked[5:].sum())


def shuffled_sign_null(d: pd.DataFrame, signs: np.ndarray, col: str = "R_BASE",
                       draws: int = DRAWS, seed: int = SEED) -> dict:
    """H.3(a): deal the same signs to the same sessions at random.

    The observed up/down proportion is preserved by permuting the real sign
    vector, so the null differs from the truth in one respect only: WHICH
    sessions got which sign.
    """
    di, si, side, r, n_dates, n_sym = _packed(d, col)
    if len(signs) != n_dates:
        raise ValueError(f"{len(signs)} signs for {n_dates} sessions")
    obs_keep = side == signs[di]
    obs_mean, obs_drop5 = _mean_and_drop5(si, r, obs_keep, n_sym)

    rng = np.random.default_rng(seed)
    means = np.empty(draws)
    drops = np.empty(draws)
    perm = signs.copy()
    for i in range(draws):
        rng.shuffle(perm)
        means[i], drops[i] = _mean_and_drop5(si, r, side == perm[di], n_sym)
    # A permutation always leaves the same number of sessions on each sign, so
    # the retained bucket can never come back empty. Draws that did are the
    # signature of resampling with replacement, and are counted rather than
    # quietly dropped by nanpercentile.
    valid = int(np.count_nonzero(~np.isnan(means)))
    return {"draws": draws, "valid_draws": valid,
            "obs_mean": obs_mean, "obs_drop5": obs_drop5,
            "mean_p95": float(np.nanpercentile(means, NULL_PCT)),
            "drop5_p95": float(np.nanpercentile(drops, NULL_PCT)),
            "mean_beats": bool(obs_mean > np.nanpercentile(means, NULL_PCT)),
            "drop5_beats": bool(obs_drop5 > np.nanpercentile(drops, NULL_PCT)),
            "mean_p": float(np.nanmean(means >= obs_mean)),
            "drop5_p": float(np.nanmean(drops >= obs_drop5))}


def within_side(d: pd.DataFrame, col: str = "R_BASE") -> pd.DataFrame:
    """H.3(b): the long/short confound, read inside each bucket."""
    t = d.copy()
    t["dir"] = np.where(t["side"] == 1, "long", "short")
    g = t.groupby(["dir", "context"])[col].agg(trades="size", mean_R="mean")
    return g.unstack("context")


def delta_drop(d: pd.DataFrame, col: str = "R_BASE") -> dict:
    """H.3(d): drop-top-N on the DELTA, not only on the level.

    Per symbol, its WITH total minus its AGAINST total. If dropping a handful
    of symbols erases the gate's advantage, the advantage is those symbols.
    """
    t = d[d["context"] != FLAT]
    piv = (t.pivot_table(index="symbol", columns="context", values=col,
                         aggfunc="sum", fill_value=0.0)
             .reindex(columns=[WITH, AGAINST], fill_value=0.0))
    delta = (piv[WITH] - piv[AGAINST]).sort_values(ascending=False)
    return {"delta": float(delta.sum()),
            **{f"drop{k}": float(delta.iloc[k:].sum()) for k in (1, 3, 5)},
            "symbols": int(len(delta))}


def per_session(d: pd.DataFrame, col: str = "R_BASE") -> dict:
    """H.3(c): the second denominator. A disagreement is a refusal."""
    out = {}
    for b in (WITH, AGAINST):
        g = d[d["context"] == b]
        by_day = g.groupby("date")[col].sum()
        out[b] = {"sessions": int(len(by_day)),
                  "mean_per_session": float(by_day.mean()) if len(by_day) else float("nan"),
                  "share_positive": float((by_day > 0).mean()) if len(by_day) else float("nan")}
    a, b = out[WITH]["mean_per_session"], out[AGAINST]["mean_per_session"]
    out["agrees_with_per_trade"] = None   # filled by the caller, which has both
    out["session_delta"] = a - b
    return out


def criteria_pass(arm: dict) -> dict:
    """H.2: criteria 1-6 unrelaxed. 7 stays unscored (E.2's scope)."""
    if not arm.get("trades"):
        return {n: False for n in range(1, 7)} | {"met": 0, "all": False}
    got = {
        1: arm["drop3_R"] > 0 and arm["drop5_R"] > 0,
        2: arm["boot_p"] >= BOOT_MIN_P,
        3: arm["mean_R"] >= P.MIN_R_PER_TRADE,
        4: arm["trades"] >= P.MIN_TRADES,
        5: arm["early_R"] > 0 and arm["late_R"] > 0,
        6: arm["long_mean_R"] > 0 and arm["short_mean_R"] > 0,
    }
    return got | {"met": sum(got.values()), "all": all(got.values())}


# --------------------------------------------------------------- the report

def render(d: pd.DataFrame, arms: dict, crit: dict, null: dict, sides,
           delta: dict, sess: dict, state: pd.DataFrame, level: str) -> list[str]:
    n_up = int((state["sign"] == 1).sum())
    n_dn = int((state["sign"] == -1).sum())
    n_fl = int((state["sign"] == 0).sum())
    L = ["ORB, STOCKS IN PLAY -- THE MARKET-CONTEXT GATE (amendment H)", "",
         "  registration   docs/research/REGISTERED_orb_sip.md amendment H,",
         "                 committed before this ran",
         f"  rule           trade WITH the sign of {INDEX}'s 09:30-09:34 move,",
         "                 skip AGAINST. No threshold; nothing to tune (H.1).",
         "  data           XNAS.ITCH minute bars already on disk; nothing bought",
         f"  criteria at    {level}, unrelaxed; criterion 7 stays unscored (E.2)",
         "",
         f"  sessions       {len(state):,}   up {n_up:,} / down {n_dn:,} / flat {n_fl:,}",
         f"  trades         {len(d):,}", "",
         "BOTH BUCKETS, IN FULL (H.4 -- a gate is a claim about what it discards)",
         "",
         "  bucket        trades   mean_R  gross_R  fric_R    total_R    drop5_R"
         "    win  boot_p",
         "  " + "-" * 92]
    for b in (WITH, AGAINST, FLAT):
        if b in arms and arms[b].get("trades"):
            L.append(P._arm_line(b, arms[b]))
    L += ["", "THE BAR: CRITERIA 1-6 ON THE RETAINED BUCKET (H.2)", ""]
    w = crit[WITH]
    names = {1: "drop-top-3 and drop-top-5 > 0",
             2: f"bootstrap P(total>0) >= {BOOT_MIN_P:.2f}",
             3: f"mean net >= +{P.MIN_R_PER_TRADE:.2f}R",
             4: f"trades >= {P.MIN_TRADES}", 5: "both halves > 0",
             6: "both sides > 0"}
    a = arms[WITH]
    vals = {1: f"{a['drop3_R']:+.1f}R / {a['drop5_R']:+.1f}R",
            2: f"{a['boot_p']:.3f}", 3: f"{a['mean_R']:+.3f}R",
            4: f"{a['trades']:,}", 5: f"{a['early_R']:+.1f}R / {a['late_R']:+.1f}R",
            6: f"{a['long_mean_R']:+.3f}R / {a['short_mean_R']:+.3f}R"}
    for n in range(1, 7):
        L.append(f"  {n}. {names[n]:<36} {vals[n]:>28}   "
                 f"{'pass' if w[n] else 'FAIL'}")
    L += ["", f"  {w['met']} of 6 met.  (7 unscored, so H cannot ship anything.)", ""]

    L += [f"H.3(a) THE SHUFFLED-SIGN CONTROL -- {null['draws']:,} draws, seed {SEED}", "",
          "  The same signs dealt to the same sessions at random. G's lift was",
          "  measured conditional on the outcome, so a 50/50 split can inherit",
          "  that artifact; this is what separates a rule from a relabelling.", "",
          f"    mean_R    observed {null['obs_mean']:>+8.3f}   null p95 "
          f"{null['mean_p95']:>+8.3f}   p {null['mean_p']:.3f}   "
          f"{'BEATS' if null['mean_beats'] else 'does not beat'}",
          f"    drop5_R   observed {null['obs_drop5']:>+8.1f}   null p95 "
          f"{null['drop5_p95']:>+8.1f}   p {null['drop5_p']:.3f}   "
          f"{'BEATS' if null['drop5_beats'] else 'does not beat'}", ""]

    L += ["H.3(b) THE SIDE-COMPOSITION CONTROL", "",
          "  On an up day more names break up, so WITH correlates with long.",
          "  The advantage must hold inside each side or it is the side split.", "",
          "  " + sides.to_string().replace("\n", "\n  "), ""]

    L += ["H.3(c) THE SECOND DENOMINATOR", "",
          f"    per trade      WITH {arms[WITH]['mean_R']:>+7.3f}R   "
          f"AGAINST {arms[AGAINST]['mean_R']:>+7.3f}R   "
          f"delta {arms[WITH]['mean_R'] - arms[AGAINST]['mean_R']:>+7.3f}R",
          f"    per session    WITH {sess[WITH]['mean_per_session']:>+7.3f}R   "
          f"AGAINST {sess[AGAINST]['mean_per_session']:>+7.3f}R   "
          f"delta {sess['session_delta']:>+7.3f}R",
          "",
          f"    the two denominators "
          f"{'AGREE' if sess['agrees_with_per_trade'] else 'DISAGREE -- refusal (PROGRAM_INDEX 4)'}",
          ""]

    L += ["H.3(d) DROP-TOP-N ON THE DELTA", "",
          "  Per symbol, its WITH total less its AGAINST total.", "",
          f"    delta            {delta['delta']:>+9.1f}R over {delta['symbols']:,} symbols",
          f"    less top 1       {delta['drop1']:>+9.1f}R",
          f"    less top 3       {delta['drop3']:>+9.1f}R",
          f"    less top 5       {delta['drop5']:>+9.1f}R", ""]

    ok = (w["all"] and null["mean_beats"] and null["drop5_beats"]
          and sess["agrees_with_per_trade"] and delta["drop5"] > 0)
    L += ["VERDICT, AS REGISTERED", ""]
    if ok:
        L += ["  The WITH bucket clears criteria 1-6 unrelaxed, beats the",
              "  shuffled-sign null on both readings, agrees across both",
              "  denominators, and its delta survives drop-top-5.",
              "",
              "  Criterion 7 remains unscored, so this is NOT a ship decision.",
              "  H.2's ceiling is reached: a holdout spend is now a question to",
              "  put to Ben, and is not taken by this amendment.", ""]
    else:
        why = []
        if not w["all"]:
            why.append(f"criteria {sorted(n for n in range(1,7) if not w[n])} fail")
        if not null["mean_beats"]:
            why.append("the mean does not beat a random sign split")
        if not null["drop5_beats"]:
            why.append("drop-top-5 does not beat a random sign split")
        if not sess["agrees_with_per_trade"]:
            why.append("the two denominators disagree")
        if delta["drop5"] <= 0:
            why.append("the delta does not survive drop-top-5")
        L += ["  NOT ADOPTABLE: " + "; ".join(why) + ".", "",
              "  H.5 retires the market-context family for ORB. No threshold",
              "  sweep, no second index, no second window -- those are the same",
              "  hypothesis with a knob, which is what H exists to refuse.", ""]
    L += [f"  H.5 predicted NOT ADOPTABLE: "
          f"{'WRONG' if ok else 'correct'}.",
          f"  H.5's secondary predicted the WITH mean beats AGAINST while",
          f"  drop-top-5 stays negative: mean "
          f"{'higher' if arms[WITH]['mean_R'] > arms[AGAINST]['mean_R'] else 'NOT higher'}"
          f", drop5 {arms[WITH]['drop5_R']:+.1f}R -> "
          f"{'correct' if (arms[WITH]['mean_R'] > arms[AGAINST]['mean_R'] and arms[WITH]['drop5_R'] < 0) else 'WRONG'}.",
          ""]
    return L


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("action", choices=("spy", "score"))
    p.add_argument("--trades", default=str(P.TRADES_DEFAULT))
    p.add_argument("--verdicts", default=str(R.RESOLVED_DEFAULT))
    p.add_argument("--state", default=str(STATE_DEFAULT))
    p.add_argument("--archive", default=None)
    p.add_argument("--report", default=str(REPORT_DEFAULT))
    p.add_argument("--level", default="BASE")
    p.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    p.add_argument("--slice", type=int, nargs=2, default=None)
    a = p.parse_args(argv)

    raw = P.load_ledger(Path(a.trades))
    res = P.add_net(R.apply_verdicts(raw, pd.read_csv(a.verdicts, encoding="utf-8")))
    d = P.arm(res, P.PRIMARY_RANGE, "top", P.PRIMARY_TOP_N).copy()
    days = sorted(d["date"].unique())

    if a.action == "spy":
        archive = Path(a.archive) if a.archive else None
        if archive is None:
            from common.databento_fetch import default_archive
            archive = default_archive()
        done = pd.DataFrame(columns=["date", "sign", "bars", "error"])
        if Path(a.state).exists():
            done = pd.read_csv(a.state, encoding="utf-8")
        todo = [x for x in days if x not in set(done["date"])]
        if a.slice:
            todo = todo[a.slice[0]:a.slice[1]]
        if todo:
            got = build_state(todo, archive, a.jobs)
            done = pd.concat([done, got], ignore_index=True).sort_values("date")
            Path(a.state).parent.mkdir(parents=True, exist_ok=True)
            done.to_csv(a.state, index=False, encoding="utf-8")
        print(f"{len(done):,} of {len(days):,} sessions have an index reading; "
              f"{int(done['sign'].isna().sum())} unreadable")
        return 0

    state = pd.read_csv(a.state, encoding="utf-8")
    d["context"] = bucket(d, state)
    split = sorted(d["date"].unique())[len(days) // 2]
    arms = {b: P.read_arm(d[d["context"] == b], a.level, split)
            for b in (WITH, AGAINST, FLAT)}
    crit = {WITH: criteria_pass(arms[WITH])}
    signs = (state.set_index("date")["sign"]
             .reindex(sorted(d["date"].unique())).to_numpy(float))
    null = shuffled_sign_null(d, signs, f"R_{a.level}")
    sides = within_side(d, f"R_{a.level}")
    delta = delta_drop(d, f"R_{a.level}")
    sess = per_session(d, f"R_{a.level}")
    sess["agrees_with_per_trade"] = bool(
        np.sign(arms[WITH]["mean_R"] - arms[AGAINST]["mean_R"])
        == np.sign(sess["session_delta"]))

    L = render(d, arms, crit, null, sides, delta, sess, state, a.level)
    Path(a.report).parent.mkdir(parents=True, exist_ok=True)
    Path(a.report).write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    print(f"\nwrote {a.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
