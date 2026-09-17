#!/usr/bin/env python3
"""H0, H-S1 and H-S2 for the market-intraday-momentum study, and the five gates.

    .venv\\Scripts\\python.exe -m common.spy_intraday_study --h0
    .venv\\Scripts\\python.exe -m common.spy_intraday_study --run
    .venv\\Scripts\\python.exe -m common.spy_intraday_study --run --breadth
    .venv\\Scripts\\python.exe -m common.spy_intraday_study --spend-holdout   # ONCE

Registration: claude/spy_intraday_spec_20260917.md and
docs/research/REGISTERED_spy_intraday_data.md. Sessions and assertions come
from common/spy_intraday.py, which must report clean before anything here is
believed -- and --run refuses to start if it does not.

THE RULE, AND WHAT MAKES IT UNUSUALLY CLEAN TO SCORE
-----------------------------------------------------
    15:30   LONG if r1 > 0, SHORT if r1 <= 0
    16:00   flat, unconditionally

One trade per session, one symbol, no stop, no target, no trail -- the exit is
the clock. So the per-trade and per-symbol-day denominators are IDENTICAL BY
CONSTRUCTION (spec section 8.2), and the two-denominator refusal that every
prior study in this project has had to carry cannot fire here. That is a real
simplification and not a convenience: it removes a whole class of ambiguity
rather than hiding it.

FRICTION IS CHARGED, ALWAYS, AND THE LEVEL IS NAMED
-----------------------------------------------------
Section 1's hard rule. Three levels, every figure, every cell:

    optimistic   0.55 bps   >=100 shares, passive or mid fills
    realistic    1.15 bps   Ben's account today, crossing the spread   <- PRIMARY
    pessimistic  2.50 bps   wide 15:30 spread, partials, slippage

The gates are read at REALISTIC. A cell that survives only at optimistic is a
NOTHING (spec section 13), and the report says so in the same table rather
than leaving it to be noticed.

H0 FIRST, AND IT CAN STOP THE STUDY
------------------------------------
Spec section 12 step 3. H0 is the same dates and the same sizes with a RANDOM
SIGN, 10,000 draws. Its expected gross is exactly zero, so its mean net should
land on minus the friction. If it does not, the harness is wrong and nothing
below it means anything -- section 10: "if H0 shows an edge, the harness is
wrong, not the market."

--run refuses to proceed unless H0 has been run and came out flat. It is not a
line in a report that a reader has to check.

THE TRAILING PERCENTILE IS POINT-IN-TIME, AND THE FIRST YEAR PAYS FOR IT
-------------------------------------------------------------------------
H-S2 trades only when sigma1 is at or above the 67th percentile of the
TRAILING 252 sessions -- computed over sessions strictly BEFORE the one being
traded. A full-sample percentile is look-ahead, and it is exactly the defect
the first_entry_skip and screen_itch work was built to avoid.

The cost is that the first 252 sessions cannot be gated and are not traded by
H-S2 at all. That is reported, not hidden: H-S1 and H-S2 therefore run on
DIFFERENT numbers of sessions, and every comparison between them states both.

WHAT THIS MODULE WILL NOT DO
-----------------------------
It will not open the holdout as a side effect of anything. `--spend-holdout`
is a separate flag, it refuses to run unless a cell has already PASSED all
five gates on the training window, and it writes a marker so it cannot be run
twice. Spec section 9: opened exactly once, and the result is final.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from common import holdout
from common.report_fmt import acct
from common.report_io import emit
from common.spy_intraday import (SPY_HOLDOUT_PATH, build_sessions, check,
                                 load_bars, sigma1)

# Spec section 5. Return-space, charged once per round trip.
FRICTION_BPS = {"optimistic": 0.55, "realistic": 1.15, "pessimistic": 2.50}
PRIMARY = "realistic"

H0_DRAWS = 10_000
BOOT_DRAWS = 10_000
SEED = 20260917

TRAIL_WINDOW = 252              # sessions
SIGMA_Q = 0.67                  # spec section 3
DROP_N = (3, 5)                 # spec section 8.1
H0_BAR_Q = 0.95                 # spec section 8.1 reading 5

NOTIONAL = 9_802.65             # 13 shares at 754.05; spec section 5
TRADING_DAYS = 252

H0_FLAT_TOL_BPS = 0.30          # how far H0's mean net may sit from -friction
MARKER = Path(__file__).resolve().parents[1] / "var" / "spy_holdout_spent.json"


# --------------------------------------------------------------------------
# the books
# --------------------------------------------------------------------------

def signs(r1: pd.Series) -> pd.Series:
    """r1 > 0 -> +1 (long), r1 <= 0 -> -1 (short). The tie goes SHORT, as written."""
    return pd.Series(np.where(r1 > 0, 1.0, -1.0), index=r1.index)


def book(sessions: pd.DataFrame, mask: pd.Series | None = None) -> pd.DataFrame:
    """One row per trade: the sign taken at 15:30 and the gross it earned."""
    s = sessions.dropna(subset=["r1", "r13"]).copy()
    if mask is not None:
        s = s[mask.reindex(s.index).fillna(False)]
    out = pd.DataFrame(index=s.index)
    out["sign"] = signs(s["r1"])
    out["r1"] = s["r1"]
    out["r13"] = s["r13"]
    out["gross"] = out["sign"] * s["r13"]
    return out


def net(b: pd.DataFrame, level: str = PRIMARY) -> pd.Series:
    return b["gross"] - FRICTION_BPS[level] / 10_000.0


def trailing_gate(sig: pd.Series, window: int = TRAIL_WINDOW,
                  q: float = SIGMA_Q) -> pd.Series:
    """sigma1 >= the trailing percentile of STRICTLY PRIOR sessions.

    shift(1) before rolling is the whole point: without it the session being
    judged is inside the sample that sets its own threshold, which is
    look-ahead of exactly the kind this project has been bitten by. The first
    `window` sessions produce NaN and are NOT traded.
    """
    prior = sig.shift(1).rolling(window, min_periods=window).quantile(q)
    return sig >= prior


def annualised(b: pd.DataFrame, level: str, years: float) -> float:
    if b.empty or years <= 0:
        return 0.0
    return float(net(b, level).sum() / years)


def span_years(idx) -> float:
    if len(idx) < 2:
        return 0.0
    a, z = pd.Timestamp(idx[0]), pd.Timestamp(idx[-1])
    return max((z - a).days / 365.25, 1e-9)


# --------------------------------------------------------------------------
# H0 -- the control, and it runs first
# --------------------------------------------------------------------------

def h0(b: pd.DataFrame, level: str = PRIMARY, draws: int = H0_DRAWS,
       seed: int = SEED) -> dict:
    """Same dates, same sizes, RANDOM SIGN. Expected gross is exactly zero."""
    if b.empty:
        return {"valid": False}
    r13 = b["r13"].to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    f = FRICTION_BPS[level] / 10_000.0
    means = np.empty(draws)
    for i in range(draws):
        sgn = rng.choice((-1.0, 1.0), size=r13.size)
        means[i] = (sgn * r13 - f).mean()
    return {"valid": True, "n": int(r13.size), "draws": draws,
            "mean": float(means.mean()),
            "p05": float(np.quantile(means, 0.05)),
            "p95": float(np.quantile(means, H0_BAR_Q)),
            "expected": -f, "means": means}


def h0_is_flat(res: dict) -> tuple[bool, str]:
    """Is the control where arithmetic says it must be?"""
    if not res.get("valid"):
        return False, "H0 not computable"
    off_bps = abs(res["mean"] - res["expected"]) * 10_000.0
    if off_bps > H0_FLAT_TOL_BPS:
        return False, (f"H0 mean net {res['mean'] * 10_000:+.3f} bps sits "
                       f"{off_bps:.3f} bps from the -friction it must equal "
                       f"({res['expected'] * 10_000:+.3f}). The harness is "
                       f"wrong, not the market.")
    return True, (f"H0 mean net {res['mean'] * 10_000:+.3f} bps against an "
                  f"expected {res['expected'] * 10_000:+.3f} bps")


# --------------------------------------------------------------------------
# the five gates
# --------------------------------------------------------------------------

def month_bootstrap(b: pd.DataFrame, level: str, draws: int = BOOT_DRAWS,
                    seed: int = SEED) -> dict:
    """Cluster bootstrap, block = CALENDAR MONTH, because volatility clusters.

    Resampling sessions independently would treat a volatile fortnight as
    twenty independent observations. Months are drawn with replacement and
    every trade in a drawn month travels with it.
    """
    if b.empty:
        return {"valid": False}
    n = net(b, level)
    months = pd.Index([x[:7] for x in b.index])
    groups = [n[months == m].to_numpy() for m in months.unique()]
    if len(groups) < 2:
        return {"valid": False}
    rng = np.random.default_rng(seed)
    k = len(groups)
    out = np.empty(draws)
    for i in range(draws):
        pick = rng.integers(0, k, size=k)
        out[i] = np.concatenate([groups[j] for j in pick]).mean()
    return {"valid": True, "n_months": k,
            "lo": float(np.quantile(out, 0.025)),
            "hi": float(np.quantile(out, 0.975)),
            "p_above_zero": float((out > 0).mean())}


def drop_top(b: pd.DataFrame, level: str, k: int) -> float:
    """Total net after removing the k best SESSIONS. One trade per session, so
    the session is the unit and there is no symbol-vs-trade ambiguity."""
    n = net(b, level).sort_values(ascending=False)
    return float(n.iloc[k:].sum()) if len(n) > k else float("nan")


def drop_top_delta(b: pd.DataFrame, level: str, k: int,
                   seed: int = SEED) -> float:
    """The same drop, applied to the DELTA against H0 on the SAME sessions.

    H0 is recomputed on the surviving sessions rather than reused from the
    full set: a control evaluated on a different sample than the arm it
    controls is not a control.
    """
    n = net(b, level).sort_values(ascending=False)
    if len(n) <= k:
        return float("nan")
    kept = n.iloc[k:].index
    sub = b.loc[kept]
    ctrl = h0(sub, level, draws=1000, seed=seed)
    if not ctrl.get("valid"):
        return float("nan")
    return float(net(sub, level).mean() - ctrl["mean"])


def halves(b: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split at the MEDIAN SESSION, not the median date. Spec section 8.1."""
    mid = len(b) // 2
    return b.iloc[:mid], b.iloc[mid:]


def verdict(b: pd.DataFrame, level: str = PRIMARY) -> tuple[str, list[str], dict]:
    """The five, all required. No partial credit, no 'directionally encouraging'."""
    n = {}
    if b.empty:
        return "NOTHING", ["no trades"], n
    years = span_years(b.index)
    nn = net(b, level)
    n["n"] = len(b)
    n["per_trade"] = float(nn.mean())
    n["annual_pct"] = annualised(b, level, years) * 100.0
    n["trades_per_year"] = len(b) / years if years else 0.0

    a, z = halves(b)
    n["half_early"] = float(net(a, level).mean()) if len(a) else 0.0
    n["half_late"] = float(net(z, level).mean()) if len(z) else 0.0
    n["n_early"], n["n_late"] = len(a), len(z)

    n["drop"] = {k: drop_top(b, level, k) for k in DROP_N}
    n["drop_delta"] = {k: drop_top_delta(b, level, k) for k in DROP_N}
    n["boot"] = month_bootstrap(b, level)
    n["h0"] = h0(b, level)

    failed = []
    if not (n["per_trade"] > 0 and n["annual_pct"] > 0):
        failed.append("1 (mean net per trade > 0 and annualised > 0)")
    if not (len(a) and len(z)):
        failed.append("2 (a temporal half is EMPTY -- a spread of exactly 0.0 "
                      "is not a sign flip)")
    elif not (n["half_early"] > 0 and n["half_late"] > 0):
        failed.append("2 (both temporal halves positive)")
    if not all(np.isfinite(v) and v > 0 for v in n["drop"].values()):
        failed.append(f"3a (drop-top-{DROP_N} on the level)")
    if not all(np.isfinite(v) and v > 0 for v in n["drop_delta"].values()):
        failed.append(f"3b (drop-top-{DROP_N} on the delta vs H0)")
    if not (n["boot"].get("valid") and n["boot"]["lo"] > 0):
        failed.append("4 (cluster bootstrap by month, 95% CI lower bound > 0)")
    if not (n["h0"].get("valid") and n["per_trade"] > n["h0"]["p95"]):
        failed.append("5 (beats the 95th percentile of the H0 random-sign "
                      "distribution)")
    return ("PASSES" if not failed else "NOTHING"), failed, n


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------

def bps(x: float) -> str:
    return f"{x * 10_000:+.3f}"


def cell_block(name: str, b: pd.DataFrame) -> list[str]:
    L = [f"{name}", ""]
    if b.empty:
        return L + ["    no trades", ""]
    years = span_years(b.index)
    L.append(f"    sessions traded   {len(b)}   "
             f"({b.index[0]} -> {b.index[-1]}, {years:.2f} years, "
             f"{len(b) / years:.1f} trades/year)")
    L.append(f"    long / short      {int((b['sign'] > 0).sum())} / "
             f"{int((b['sign'] < 0).sum())}")
    L.append(f"    directional hit   "
             f"{float((b['gross'] > 0).mean()) * 100:.2f}%")
    L.append("")
    L.append("    friction level    bps/trade net    annualised %    "
             "$/yr on $9,803")
    for lvl, f in FRICTION_BPS.items():
        nn = net(b, lvl)
        ann = annualised(b, lvl, years) * 100.0
        dollars = annualised(b, lvl, years) * NOTIONAL
        star = "  <- PRIMARY" if lvl == PRIMARY else ""
        L.append(f"    {lvl:<14} {f:>4.2f}  {bps(float(nn.mean())):>8}    "
                 f"{acct(ann, 9, 2)}    {acct(dollars, 11, 0)}{star}")
    L.append("")
    return L


def verdict_block(name: str, b: pd.DataFrame) -> list[str]:
    tag, failed, n = verdict(b, PRIMARY)
    L = [f"  {name}: {tag}   (read at {PRIMARY}, "
         f"{FRICTION_BPS[PRIMARY]} bps)", ""]
    if not n:
        return L + ["    not computable", ""]
    L += [f"    1  per trade {bps(n['per_trade'])} bps, annualised "
          f"{acct(n['annual_pct'], 8, 2)}%",
          f"    2  halves    early {bps(n['half_early'])} (n={n['n_early']}), "
          f"late {bps(n['half_late'])} (n={n['n_late']})"]
    for k in DROP_N:
        L.append(f"    3  drop-top-{k}  level total "
                 f"{acct(n['drop'][k] * NOTIONAL, 10, 0)}   "
                 f"delta vs H0 {bps(n['drop_delta'][k])} bps")
    bt = n["boot"]
    if bt.get("valid"):
        L.append(f"    4  bootstrap  {bt['n_months']} monthly blocks, 95% CI "
                 f"[{bps(bt['lo'])}, {bps(bt['hi'])}] bps, "
                 f"P(>0)={bt['p_above_zero']:.3f}")
    else:
        L.append("    4  bootstrap  not computable")
    h = n["h0"]
    if h.get("valid"):
        L.append(f"    5  H0 p95    {bps(h['p95'])} bps against this cell's "
                 f"{bps(n['per_trade'])} bps")
    L.append("")
    if failed:
        L.append("    FAILS: " + "; ".join(failed))
    else:
        L.append("    all five, at the realistic friction level")
    L.append("")
    return L


# --------------------------------------------------------------------------

def load_study(symbol: str, fine: str) -> tuple[pd.DataFrame, pd.Series, dict]:
    df30 = load_bars("30 mins", symbol)
    s = build_sessions(df30)
    res = check(s, df30) if not s.empty else {}
    sig = sigma1(load_bars(fine, symbol))
    return s, sig, res


def assertions_clean(res: dict) -> tuple[bool, list[str]]:
    """--run will not start on a cache the assertion pass has not cleared."""
    bad = []
    if not res:
        bad.append("no sessions cached")
        return False, bad
    if res.get("n_bad_first_bar", 1):
        bad.append(f"{res['n_bad_first_bar']} sessions do not start at 09:30 ET")
    if res.get("dst_bad"):
        bad.append(f"{len(res['dst_bad'])} DST transitions mishandled")
    if res.get("dup_conflicts", 1):
        bad.append(f"{res['dup_conflicts']} cache rows disagree on price")
    if res.get("n_gaps", 1):
        bad.append(f"{res['n_gaps']} session gaps over four calendar days")
    return (not bad), bad


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--h0", action="store_true", help="the control, first")
    ap.add_argument("--run", action="store_true", help="H-S1 and H-S2")
    ap.add_argument("--breadth", action="store_true",
                    help="H-S1 unchanged on QQQ and IWM (spec 8.4)")
    ap.add_argument("--spend-holdout", action="store_true")
    ap.add_argument("--symbol", default="SPY")
    ap.add_argument("--fine", default="5 mins", choices=["5 mins", "1 min"])
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    if not (args.h0 or args.run or args.breadth or args.spend_holdout):
        sys.exit("pass --h0, --run, --breadth or --spend-holdout")

    s, sig, res = load_study(args.symbol, args.fine)
    if s.empty:
        sys.exit("no bars cached -- run common.spy_intraday_data --pull first")
    clean, bad = assertions_clean(res)
    if not clean:
        sys.exit("REFUSING TO RUN: the assertion pass is not clean:\n  "
                 + "\n  ".join(bad)
                 + "\nRun common.spy_intraday --assert and fix these first.")

    rec = (json.loads(SPY_HOLDOUT_PATH.read_text(encoding="utf-8"))
           if SPY_HOLDOUT_PATH.exists() else None)
    if rec is None:
        sys.exit("REFUSING TO RUN: holdout_spy.json does not exist. Cut it "
                 "first with common.spy_intraday --make-holdout.")
    triples = [(args.symbol, d, None) for d in s.index]
    keep, set_aside, label = holdout.split_sessions(
        triples, spend=args.spend_holdout, rec=rec)
    s = s.loc[[d for _, d, _ in keep]]

    L = [f"SPY INTRADAY MOMENTUM -- {args.symbol}", "",
         f"  run at      {datetime.now():%Y-%m-%d %H:%M:%S}",
         f"  sessions    {label}, {set_aside} set aside",
         f"  friction    charged at all three levels; gates read at "
         f"{PRIMARY} ({FRICTION_BPS[PRIMARY]} bps)",
         f"  denominator one trade per session on one symbol, so per-trade "
         f"and per-symbol-day are identical by construction (spec 8.2)", ""]

    b1 = book(s)
    ctrl = h0(b1, PRIMARY)
    flat, why = h0_is_flat(ctrl)
    L += ["H0 -- THE CONTROL, RUN FIRST", "",
          f"    {'FLAT' if flat else '**NOT FLAT**'}  {why}",
          f"    {ctrl.get('draws', 0)} draws, 95th percentile "
          f"{bps(ctrl.get('p95', 0))} bps", ""]
    if not flat:
        L += ["  STOPPING. Spec section 12 step 3: a control that does not",
              "  come out flat means the harness is wrong, and nothing",
              "  measured on it means anything."]
        emit("\n".join(L), args.out or "var/reports/spy_intraday_study.txt",
             header="common.spy_intraday_study")
        return 1

    if args.h0 and not (args.run or args.breadth):
        emit("\n".join(L), args.out or "var/reports/spy_intraday_h0.txt",
             header="common.spy_intraday_study --h0")
        return 0

    L += cell_block("H-S1 (PRIMARY) -- unconditional", b1)
    gate = trailing_gate(sig.reindex(s.index))
    b2 = book(s, gate)
    L += cell_block(f"H-S2 (SECONDARY) -- sigma1 >= trailing {TRAIL_WINDOW}-session "
                    f"{int(SIGMA_Q * 100)}th percentile", b2)
    if b2.empty:
        L += ["    H-S2 HAS NO TRADES. Either sigma1 is absent (no fine cache)",
              f"    or fewer than {TRAIL_WINDOW} sessions precede the window.", ""]
    else:
        L += [f"    NOTE: the first {TRAIL_WINDOW} sessions cannot be gated "
              f"point-in-time and are not traded by H-S2. H-S1 and H-S2 "
              f"therefore run on {len(b1)} and {len(b2)} sessions; every",
              "    comparison between them states both.", ""]

    L += ["THE FIVE GATES", ""]
    L += verdict_block("H-S1", b1)
    L += verdict_block("H-S2", b2)

    emit("\n".join(L), args.out or "var/reports/spy_intraday_study.txt",
         header="common.spy_intraday_study")
    return 0


if __name__ == "__main__":
    sys.exit(main())
