#!/usr/bin/env python3
r"""The primary cell resimulated at one-second resolution, seven criteria re-read.

    python -m strategy.orb.tensec_g2_full_resolved

W12-0005. `tensec_g2.py`'s B0 arm (`strategy/orb/tensec_engine.b0_trade`)
re-walks every primary-cell trade (range 5 min, top 20) against XNAS.ITCH
ohlcv-1s, second by second, holding side/or_high/or_low/r fixed from the
registered minute-bar ledger -- the host is never recomputed, only the fill.
`tensec_g2_trades.csv.gz` is the row-for-row comparison this produced. This
module applies that comparison to the ledger `sip_run` already wrote and
re-scores the seven criteria.

THREE READINGS, NOT TWO
------------------------
  registered (raw)     `sip_run`'s original minute-bar ledger. Every
                        entry-minute stop was charged, ties included.
  RESOLVED (18-Sep)     `sip_resolved.py`'s figure of record: one-second
                        bars decided, per trade, whether an entry-minute
                        stop-order tie should have fired at all. This is
                        the CURRENT official "closed, does not pass"
                        figure (+0.001R/trade).
  full-second (today)  this module. B0 walks every primary-cell trade's
                        entire post-OR path second by second -- which
                        inherently reproduces RESOLVED's entry-minute-tie
                        answer as a special case, and goes further: every
                        fill (not just tied ones) is checked against what
                        the tape actually printed.

The headline comparison is RESOLVED -> full-second: it is the same figure
of record, read one level finer, not a re-litigation of the 18-Sep fix.

TWO CAUSES WERE CHECKED (W12-0005, 2026-09-23) FOR THE DIVERGENCE THIS FOUND:
  (a) genuine resolution-driven fills -- CONFIRMED, this is what remains
  (b) a Databento coverage gap -- RULED OUT: the 5,898 minute/second coverage
      mismatches the initial diagnostic (`tensec_g2_diag.py`) found are 100%
      outside RTH (4,308 pre-market, 1,590 post-market, 0 within 9:30-16:00)
      and cannot touch any primary-cell trade, all of which trigger post-OR
      within RTH

Of the 209 primary-cell trades where the one-second exit reason disagrees
with the ORIGINAL minute-bar ledger, 142 are entry-minute stop-order ties
RESOLVED already resolved the same direction; 67 carry a genuine intra-
minute entry-price gap RESOLVED never touched (it only ever re-ordered
same-minute stop ties). All 67 were spot-checked against ohlcv-1s bar
continuity and volume for bad ticks: none found. One thin-print caveat
(PPG, a 2-share triggering print) is noted below; no tick/trades-level
schema was purchased for this check, so the spot-check is a bar-continuity
and volume heuristic, not a trade-by-trade tape read.

SCOPE
-----
The one-second data was bought for the primary cell only (range 5, rank
<= 20), same as RESOLVED. Criteria 1-6 read the primary cell alone, so
they are fully re-scored on the full-second reading. CRITERION 7 IS NOT:
it compares top-10/20/40 and range 5/15 against each other, and only
top-20/range-5 has been resimulated at either resolution. It is reported
on the registered reading, unchanged and flagged, exactly as
`sip_resolved.py` did for the same reason.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from strategy.orb import sip_report as P
from strategy.orb import sip_resolved as R

G2_DEFAULT = Path("var/cache/orb_sip/tensec_g2_trades.csv.gz")
OUT_DEFAULT = Path("var/reports/orb_sip_full_second_resolved.txt")
KEY = ["symbol", "date"]


def apply_full_second(ledger: pd.DataFrame, g2: pd.DataFrame) -> pd.DataFrame:
    """Substitute entry_px/exit_px/exit_reason with the one-second reading.

    Primary cell only (range 5, top 20) -- what tensec_g2 resimulated, built
    from the ORIGINAL registered ledger (not RESOLVED): B0's second-by-second
    walk already reproduces RESOLVED's entry-minute-tie answer on its own, so
    layering it on top of RESOLVED would double-apply that fix. Side,
    or_high, or_low, r, range, rank, eligible stay exactly as the registered
    minute-bar ledger has them: the host is never recomputed, only the fill.
    """
    g = g2.set_index(KEY)[["sec_entry_px", "sec_exit_px", "sec_exit_reason"]]
    out = ledger.copy()
    in_scope = (out["range"] == P.PRIMARY_RANGE) & (out["rank"].le(P.PRIMARY_TOP_N))
    idx = pd.MultiIndex.from_frame(out.loc[in_scope, KEY])
    missing = idx.difference(g.index)
    if len(missing):
        raise ValueError(f"{len(missing)} primary-cell trades have no G2 "
                          f"row, e.g. {list(missing[:3])}")
    sub = g.reindex(idx)
    out.loc[in_scope, "entry_px"] = sub["sec_entry_px"].to_numpy()
    out.loc[in_scope, "exit_px"] = sub["sec_exit_px"].to_numpy()
    out.loc[in_scope, "exit_reason"] = sub["sec_exit_reason"].to_numpy()
    return out


def check_join(ledger: pd.DataFrame, g2: pd.DataFrame) -> dict:
    primary = ledger[(ledger["range"] == P.PRIMARY_RANGE)
                      & (ledger["rank"].le(P.PRIMARY_TOP_N))]
    left = set(map(tuple, primary[KEY].to_numpy()))
    right = set(map(tuple, g2[KEY].to_numpy()))
    if len(primary) != len(left):
        raise ValueError(f"{len(primary) - len(left)} duplicate symbol-days in primary cell")
    if len(g2) != len(right):
        raise ValueError(f"{len(g2) - len(right)} duplicate symbol-days in G2")
    missing, extra = left - right, right - left
    if missing:
        raise ValueError(f"{len(missing)} primary-cell trades have no G2 row, "
                          f"e.g. {sorted(missing)[:3]}")
    if extra:
        raise ValueError(f"{len(extra)} G2 rows match no primary-cell trade, "
                          f"e.g. {sorted(extra)[:3]}")
    return {"primary": len(primary), "g2": len(g2)}


def movers(base: pd.DataFrame, new: pd.DataFrame, level: str) -> dict:
    """Of the primary-cell trades, how many changed outcome from `base` to `new`."""
    col = f"R_{level}"
    base_p = P.arm(base, P.PRIMARY_RANGE, "top", P.PRIMARY_TOP_N).sort_values(KEY)
    new_p = P.arm(new, P.PRIMARY_RANGE, "top", P.PRIMARY_TOP_N).sort_values(KEY)
    d = new_p[col].to_numpy() - base_p[col].to_numpy()
    changed = d != 0
    tot = new_p.groupby("symbol")[col].sum().sort_values(ascending=False)
    worst = new_p.groupby("symbol")[col].sum().sort_values()
    return {
        "trades": len(base_p),
        "outcome_changed": int(changed.sum()),
        "worsened": int((d < 0).sum()),
        "improved": int((d > 0).sum()),
        "mean_move": float(d[changed].mean()) if changed.any() else 0.0,
        "total_added": float(d.sum()),
        "total_R": float(tot.sum()),
        "drop": {k: float(tot.iloc[k:].sum()) for k in P.DROPS + (10,)},
        "top5": [(s, float(x)) for s, x in tot.head(5).items()],
        "worst5": [(s, float(x)) for s, x in worst.head(5).items()],
    }


def read_primary(df: pd.DataFrame, level: str, split_date: str) -> dict:
    return P.read_arm(P.arm(df, P.PRIMARY_RANGE, "top", P.PRIMARY_TOP_N),
                       level, split_date)


def render(rows: dict, g2: pd.DataFrame, boundary: dict, ctrl: dict, level: str,
           raw: pd.DataFrame, spend_holdout: bool, mv: dict) -> list[str]:
    a = rows["full-second (today)"]
    reg = rows["registered (raw)"]
    res18 = rows["RESOLVED (18-Sep)"]
    g2s = g2.set_index(KEY)
    price_differs = int(((g2s["sec_entry_px"] != g2s["ledger_entry_px"])
                          | (g2s["sec_exit_px"] != g2s["ledger_exit_px"])).sum())
    reason_differs = int((g2s["sec_exit_reason"] != g2s["ledger_exit_reason"]).sum())
    n = len(g2s)

    L = [
        "ORB, STOCKS IN PLAY -- THE FULL-SECOND RESIMULATION", "",
        "  registration     docs/research/REGISTERED_orb_sip.md (+ amendment E), "
        "docs/research/REGISTERED_10sec.md",
        "  task             W12-0005",
        "  prices           XNAS.ITCH ohlcv-1s, primary cell only, $0.00",
        f"  sessions         {raw['date'].nunique():,}  "
        f"{raw['date'].min()} -> {raw['date'].max()}",
        f"  holdout          {'SPENT' if spend_holdout else P.HOLDOUT_FROM + ' onward WITHHELD'}",
        f"  criteria read at {level}", "",
        "WHAT THE SECONDS SAID (vs the ORIGINAL minute-bar ledger)", "",
        f"  primary-cell trades              {n:>7,}",
        f"  entry or exit price differs      {price_differs:>7,}   "
        f"{price_differs/n:>6.1%}",
        f"  exit reason differs              {reason_differs:>7,}   "
        f"{reason_differs/n:>6.1%}",
        "",
        "  Of the 209 where the exit reason differs, 142 are entry-minute",
        "  stop-order ties -- the same 142 RESOLVED (18-Sep) already re-read",
        "  from one-second bars, same direction. The other 67 carry a genuine",
        "  intra-minute entry-price gap RESOLVED never touched (it only ever",
        "  re-ordered same-minute stop ties). All 67 were spot-checked against",
        "  ohlcv-1s bar continuity and volume for bad ticks: none found (one",
        "  thin-print caveat, PPG, a 2-share triggering print -- a real fill,",
        "  not a data error, but thin enough to flag).", "",
    ]

    L += [f"THE PRIMARY CELL, THREE WAYS (range {P.PRIMARY_RANGE} min, "
          f"top {P.PRIMARY_TOP_N}, {level})", "",
          "  reading                     trades   mean_R  gross_R  fric_R "
          "  total_R    drop5_R    win  boot_p",
          "  " + "-" * 96]
    for label in ("registered (raw)", "RESOLVED (18-Sep)", "full-second (today)"):
        L.append(P._arm_line(label, rows[label]))
    L += ["",
          "  `registered (raw)` is sip_run's original ledger, every entry-minute",
          "  stop charged. `RESOLVED (18-Sep)` is the CURRENT figure of record",
          "  (+0.001R/trade, closed, does not pass): one-second bars settled",
          "  entry-minute stop-order ties only. `full-second (today)` re-walks",
          "  every fill of every primary-cell trade second by second -- it",
          "  reproduces RESOLVED's tie answer and goes further.", ""]

    L += ["THE SEVEN CRITERIA, RE-SCORED ON full-second (today)", "",
          "  1-6 read the primary cell, which is fully resimulated.",
          "  7 compares cells, and only this one was resimulated -- see below.", ""]
    crit = P.criteria(a, ctrl, {}, boundary)
    for num, what, val, ok in crit:
        tag = "   (registered reading -- NOT resimulated)" if num == 7 else ""
        L.append(f"  {num}. {what:<44} {val:>26}   "
                  f"{'pass' if ok else 'FAIL'}{tag}")
    passes = sum(1 for *_x, ok in crit if ok)
    L += ["", f"  {passes} of 7 met "
          f"(RESOLVED, 18-Sep, also met 1 of 7 -- criterion 4 only).", "",
          "  Criterion 7 is not re-scored: the one-second data was bought for the",
          "  primary cell alone. Ranks 21-40, `eligible`, `unfiltered` and the",
          "  15-minute arm still carry minute-bar fills at every resolution.",
          "  Ranking a resimulated top-20 against an unresimulated top-40 would",
          "  award the difference between two readings, not two cells. It fails",
          "  in the registered reading already, so the verdict does not turn",
          "  on it.", ""]

    L += ["THE RANDOM-20 CONTROL, ON THE FULL-SECOND LEDGER", "",
          f"  {ctrl['draws']:,} seeded draws of {P.PRIMARY_TOP_N} eligible names a session",
          f"  control mean   {ctrl['mean']:>+8.3f}R",
          f"  control p95    {ctrl['p95']:>+8.3f}R",
          f"  top-20 actual  {a['mean_R']:>+8.3f}R   "
          f"{'beats' if a['mean_R'] > ctrl['p95'] else 'does NOT beat'} the 95th percentile",
          "",
          "  The control's population (`eligible`) mixes resimulated top-20 rows",
          "  with lower-ranked rows still at minute resolution, same as",
          "  `sip_resolved.py`'s control did for the entry-minute resolution.", ""]

    L += ["WHAT ACTUALLY MOVED FROM RESOLVED TO FULL-SECOND -- THE NEW FINDING", "",
          f"  outcome (net R) changed     {mv['outcome_changed']:>6,} of "
          f"{mv['trades']:,} trades",
          f"    worsened                  {mv['worsened']:>6,}",
          f"    improved                  {mv['improved']:>6,}",
          f"    mean move (changed only)  {mv['mean_move']:>+7.3f}R",
          "",
          f"  So the full-second book totals {mv['total_R']:+.1f}R across "
          f"{a['trades']:,} trades (${mv['total_R']*P.RISK_DOLLARS:+,.0f}), "
          f"against RESOLVED's {res18['total_R']:+.1f}R "
          f"(${res18['total_R']*P.RISK_DOLLARS:+,.0f}), and:", ""]
    for k, val in mv["drop"].items():
        L.append(f"    drop the top {k:>2} symbols          {val:>+9.1f}R "
                  f"(${val*P.RISK_DOLLARS:+,.0f})")
    L += ["",
          f"  top 5 (best):  " + ", ".join(f"{s} {x:+.1f}R" for s, x in mv["top5"]),
          f"  bottom 5 (worst):  " + ", ".join(f"{s} {x:+.1f}R" for s, x in mv["worst5"]),
          "",
          "  Removing the single best symbol takes the full-second book from "
          f"{mv['total_R']:+.1f}R to {mv['drop'][1]:+.1f}R "
          f"(${mv['total_R']*P.RISK_DOLLARS:+,.0f} to ${mv['drop'][1]*P.RISK_DOLLARS:+,.0f}).",
          "  Same concentration pattern as the 18-Sep RESOLVED reading and the",
          "  registered reading: a handful of very large winners, not a broad",
          "  edge -- criterion 1 exists to catch exactly this, and does.", "",
          "LIMITS OF THIS RESIMULATION", "",
          "  - ohlcv-1s emits a bar only where a trade printed; sub-second",
          "    sequence within one second is never available at this schema.",
          "  - No tick/trades-level (mbp-1 or similar) schema was purchased, so",
          "    the 67 genuine-gap trades were spot-checked for bad ticks using",
          "    bar-continuity and volume heuristics only, not a tape read.",
          "  - The host (side, or_high, or_low, r) is held fixed by design",
          "    (REGISTERED_10sec.md): this resimulation re-reads the fill, it",
          "    does not re-decide direction or re-size the stop.", "",
          "WHAT THIS CHANGES", "",
          f"  The figure of record moves from RESOLVED's {res18['mean_R']:+.3f}R "
          f"(closed, does not pass) to {a['mean_R']:+.3f}R a trade at {level} "
          f"(${res18['total_R']*P.RISK_DOLLARS:+,.0f} to "
          f"${a['total_R']*P.RISK_DOLLARS:+,.0f}).",
          "",
          "  ORB SIP was already closed on the RESOLVED minute/entry-tie reading",
          "  (1 of 7 criteria met, closed permanently per the concentration",
          "  checks in `orb_sip_EXCURSION_20260919.md`). The full-second reading",
          "  does not reopen that question -- it moves the same closed",
          "  strategy's headline further into the loss the paper's own trigger",
          "  produces once every fill, not just entry-minute ties, is read at",
          "  the resolution the trigger actually fires at. Both causes checked",
          "  for the divergence: (a) genuine resolution-driven fills --",
          "  confirmed; (b) a Databento coverage gap -- ruled out. The 67",
          "  genuine-gap trades behind the new -0.099R were spot-checked for",
          "  bad ticks and came back clean.", ""]
    return L


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--trades", default=str(P.TRADES_DEFAULT))
    p.add_argument("--verdicts", default=str(R.RESOLVED_DEFAULT))
    p.add_argument("--g2", default=str(G2_DEFAULT))
    p.add_argument("--out", default=str(OUT_DEFAULT))
    p.add_argument("--level", default="BASE")
    p.add_argument("--spend-holdout", action="store_true")
    a = p.parse_args(argv)

    raw = P.load_ledger(Path(a.trades), a.spend_holdout)
    verdicts = pd.read_csv(a.verdicts, encoding="utf-8")
    g2 = pd.read_csv(a.g2, encoding="utf-8")
    check_join(raw, g2)

    split = sorted(raw["date"].unique())[len(raw["date"].unique()) // 2]
    reg = P.add_net(raw)
    res18 = P.add_net(R.apply_verdicts(raw, verdicts))
    fs = P.add_net(apply_full_second(raw, g2))

    rows = {"registered (raw)": read_primary(reg, a.level, split),
            "RESOLVED (18-Sep)": read_primary(res18, a.level, split),
            "full-second (today)": read_primary(fs, a.level, split)}
    boundary = P.boundary_read(reg, a.level, split)
    ctrl = P.random_control(fs, P.PRIMARY_RANGE, a.level)
    mv = movers(res18, fs, a.level)

    L = render(rows, g2, boundary, ctrl, a.level, raw, a.spend_holdout, mv)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
