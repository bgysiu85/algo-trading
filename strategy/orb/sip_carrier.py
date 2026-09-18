#!/usr/bin/env python3
r"""Is the concentration in the symbols, or in the days?

    python -m strategy.orb.sip_carrier

`REGISTERED_orb_sip.md` amendment G. DESCRIPTIVE. No gate is applied, no SPY
state is added, no variant is simulated and no P/L for any variant is produced
-- deliberately, so that G cannot later be read as the gate's result.

WHY THE QUESTION DECIDES THE GATE
---------------------------------
The book is +4.8R over 7,239 trades and turns on five symbols. A market-context
gate switches whole SESSIONS on and off, so it can only reach that
concentration if the concentration lives in days. If the carrying trades are
single names doing single-name things on unrelated sessions, no market-wide
rule can touch them at any threshold, and the gate is dead before it is
written.

G.3's primary reading is therefore NOT "did the big winners share days" but
"were the days they landed on generally good days" -- because a gate cannot
keep the one trade and drop the rest of that session. It takes the day or
leaves it.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from common.breadth import SEED
from strategy.orb import sip_report as P
from strategy.orb import sip_resolved as R

CARRIER_NS = (20, 50)        # G.2, both reported, neither chosen after
LIFT_BAR = 0.10              # G.3
DRAWS = 2000                 # G.4
REPORT_DEFAULT = Path("var/reports/orb_sip_carrier.txt")


def carriers(d: pd.DataFrame, n: int, col: str = "R_BASE") -> pd.Index:
    """The n largest trades by net R. Ties broken by index, not by symbol."""
    return d.nlargest(n, col).index


def lift(d: pd.DataFrame, n: int, col: str = "R_BASE") -> dict:
    """G.3: the REST of the book on carrier days, against all other days.

    The carrier trades themselves are excluded from both sides. Including them
    would measure that big winners are big, which is true and empty.
    """
    idx = carriers(d, n, col)
    days = set(d.loc[idx, "date"])
    on_day = d["date"].isin(days).to_numpy()
    is_carrier = d.index.isin(idx)

    rest = d[on_day & ~is_carrier][col]
    other = d[~on_day][col]
    m_rest = float(rest.mean()) if len(rest) else float("nan")
    m_other = float(other.mean()) if len(other) else float("nan")
    return {"n": n, "carrier_days": len(days), "rest_trades": len(rest),
            "other_trades": len(other), "rest_mean": m_rest,
            "other_mean": m_other, "lift": m_rest - m_other,
            "meets_bar": bool(m_rest - m_other >= LIFT_BAR)}


def clustering(d: pd.DataFrame, n: int, draws: int = DRAWS,
               seed: int = SEED, col: str = "R_BASE") -> dict:
    """G.4: observed distinct days against a permutation null.

    The null draws n trades at random FROM THE SAME LEDGER, so it inherits the
    real distribution of trades per session instead of assuming a flat one.
    """
    obs = d.loc[carriers(d, n, col), "date"].nunique()
    rng = np.random.default_rng(seed)
    dates = d["date"].to_numpy()
    null = np.empty(draws, dtype=int)
    for i in range(draws):
        null[i] = len(np.unique(rng.choice(dates, size=n, replace=False)))
    # one-sided: FEWER distinct days than chance is clustering
    p = float(np.mean(null <= obs))
    return {"n": n, "observed": int(obs), "null_mean": float(null.mean()),
            "null_p05": float(np.percentile(null, 5)), "p": p,
            "clustered": bool(p < 0.05)}


def verdict(lifts: list[dict]) -> dict:
    """G.3: the bar must be met at EVERY N. A split is a refusal."""
    met = [x["meets_bar"] for x in lifts]
    return {"all": all(met), "any": any(met), "split": any(met) and not all(met),
            "register_gate": all(met)}


def render(d: pd.DataFrame, lifts: list[dict], clus: list[dict],
           v: dict, top_sym: pd.Series) -> list[str]:
    L = ["ORB, STOCKS IN PLAY -- SYMBOLS OR DAYS? (amendment G)", "",
         "  registration   docs/research/REGISTERED_orb_sip.md amendment G,",
         "                 committed before this ran",
         "  scope          resolved primary cell, range 5, rank <= 20",
         "  data           the ledger already on disk; nothing bought",
         "", "  NO GATE IS APPLIED HERE. No SPY state, no variant, no P/L for",
         "  one -- so this cannot be read as the gate's result (G.6).", "",
         f"  trades         {len(d):>7,}",
         f"  sessions       {d['date'].nunique():>7,}",
         f"  book           {d['R_BASE'].sum():>+8.1f}R", "",
         "THE FIVE SYMBOLS THE BOOK TURNS ON", ""]
    for s, x in top_sym.head(5).items():
        L.append(f"    {s:<6} {x:>+7.1f}R")

    L += ["", "G.3 PRIMARY -- WERE THE CARRIER DAYS GENERALLY GOOD DAYS?", "",
          "  The carrier trades are excluded from both sides: a gate takes the",
          "  whole session or leaves it, so what it could trade is the REST.", "",
          "   N   days   rest of book      all other days        lift   bar "
          f"{LIFT_BAR:+.2f}R",
          "  " + "-" * 74]
    for x in lifts:
        L.append(f"  {x['n']:>2}   {x['carrier_days']:>4}   "
                 f"{x['rest_mean']:>+7.3f}R ({x['rest_trades']:>5,})   "
                 f"{x['other_mean']:>+7.3f}R ({x['other_trades']:>5,})   "
                 f"{x['lift']:>+7.3f}R   "
                 f"{'MET' if x['meets_bar'] else 'missed'}")

    L += ["", "G.4 SUPPORTING -- DID THE CARRIERS CLUSTER ON FEWER DAYS?", "",
          f"  {DRAWS:,} permutation draws from the same ledger, seed {SEED}", "",
          "   N   distinct days   null mean   null p05      p",
          "  " + "-" * 54]
    for c in clus:
        L.append(f"  {c['n']:>2}   {c['observed']:>13}   {c['null_mean']:>9.1f}   "
                 f"{c['null_p05']:>8.1f}   {c['p']:>5.3f}"
                 f"   {'clustered' if c['clustered'] else 'no'}")

    L += ["", "VERDICT, AS REGISTERED", ""]
    if v["register_gate"]:
        L += ["  The lift clears +0.10R at every N. Carrier days ARE generally",
              "  good days, so a session-level gate has something to bite on.",
              "  §5's market-context gate EARNS A REGISTRATION -- and nothing",
              "  more. It is not adopted, and its own pre-stated prior still",
              "  expects NOT ADOPTABLE.", ""]
    elif v["split"]:
        L += ["  The bar is met at one N and missed at another. G.3 calls that",
              "  a REFUSAL, not a result: the reading depends on where the",
              "  carrier line was drawn, which is not a property of the tape.",
              "  The gate is neither registered nor retired on this evidence.", ""]
    else:
        L += ["  The lift misses +0.10R. The days the carrying trades landed on",
              "  were not generally good days -- the rest of the book on those",
              "  sessions reads like the rest of the book anywhere else.",
              "",
              "  A gate switches whole sessions. There is no session-level",
              "  signal here for one to switch on, so no threshold on any",
              "  market-context variable can reach this concentration.",
              "",
              "  §5's MARKET-CONTEXT GATE IS RETIRED UNRUN, joining",
              "  luck_vs_edge_RESULT_20260917, cold_veto_RESULT_20260917,",
              "  spy_intraday_RESULT_20260918 H-S2 and the BandWidth squeeze",
              "  pre-flight. The concentration is in the SYMBOLS.", ""]

    L += [f"  G.5 predicted the lift would miss the bar and the gate be retired.",
          f"  That prediction is {'WRONG' if v['register_gate'] else 'correct'}"
          f", and is recorded either way.",
          f"  G.5's secondary predicted no clustering beyond chance: "
          f"{'WRONG' if any(c['clustered'] for c in clus) else 'correct'}.", ""]
    return L


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--trades", default=str(P.TRADES_DEFAULT))
    p.add_argument("--verdicts", default=str(R.RESOLVED_DEFAULT))
    p.add_argument("--report", default=str(REPORT_DEFAULT))
    a = p.parse_args(argv)

    raw = P.load_ledger(Path(a.trades))
    res = P.add_net(R.apply_verdicts(raw, pd.read_csv(a.verdicts, encoding="utf-8")))
    d = P.arm(res, P.PRIMARY_RANGE, "top", P.PRIMARY_TOP_N)

    lifts = [lift(d, n) for n in CARRIER_NS]
    clus = [clustering(d, n) for n in CARRIER_NS]
    v = verdict(lifts)
    top_sym = d.groupby("symbol")["R_BASE"].sum().sort_values(ascending=False)

    L = render(d, lifts, clus, v, top_sym)
    Path(a.report).parent.mkdir(parents=True, exist_ok=True)
    Path(a.report).write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    print(f"\nwrote {a.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
