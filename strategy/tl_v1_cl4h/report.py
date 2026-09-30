#!/usr/bin/env python3
"""Text report + CSV frames for the TL-v1 CL 4-hour variant (W15-0027). Negatives in brackets.
REPORTED ONLY: no verdict line, no criterion is scored, nothing is ranked."""
from __future__ import annotations

import numpy as np
import pandas as pd

from strategy.tl_v0.spec import PIVOT_SIZES
from strategy.tl_v1_cl4h import engine as E

VARIANT_ORDER = ("v1", "v1-A+", "v1-A3", "v1-2touch", "C2 v0-rev", "C1")


def money(v, dp=0) -> str:
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "n/a"
    s = f"{abs(v):,.{dp}f}"
    return f"(${s})" if round(v, dp) < 0 else f"${s}"


def _book(res, spec, book) -> pd.DataFrame:
    b = res[spec][book]
    return b if spec == "C1" else E.ensemble(b)


def stats(df: pd.DataFrame, frame: pd.DataFrame, lv: str = "mid") -> dict:
    if df is None or not len(df):
        return dict(trades=0, wins=0, losses=0, gross=0.0, costs=0.0, net=0.0, net_low=0.0, net_mid=0.0,
                    net_high=0.0, avg_win=None, avg_loss=None, worst_loss=None, max_dd=0.0,
                    half1=0.0, half2=0.0, net_per_std=None, rolls=0)
    n = df["net_" + lv]
    order = df.sort_values("exit_time")
    cum = order["net_" + lv].cumsum().to_numpy()
    dd = float(np.max(np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:] - cum)) if len(cum) else 0.0
    med = df["entry_time"].sort_values().iloc[len(df) // 2]
    h1 = float(df.loc[df["entry_time"] < med, "net_" + lv].sum())
    h2 = float(df.loc[df["entry_time"] >= med, "net_" + lv].sum())
    sessions = pd.to_datetime(frame["session"]).drop_duplicates().sort_values()
    daily = df.groupby(pd.to_datetime(df["exit_session"]))["net_" + lv].sum().reindex(sessions, fill_value=0.0)
    sd = float(daily.std())
    return dict(trades=len(df), wins=int((n > 0).sum()), losses=int((n <= 0).sum()),
                gross=float(df["gross"].sum()), costs=float(df["cost_" + lv].sum()), net=float(n.sum()),
                net_low=float(df["net_low"].sum()), net_mid=float(df["net_mid"].sum()),
                net_high=float(df["net_high"].sum()),
                avg_win=float(n[n > 0].mean()) if (n > 0).any() else None,
                avg_loss=float(n[n <= 0].mean()) if (n <= 0).any() else None,
                worst_loss=float(n.min()), max_dd=dd, half1=h1, half2=h2,
                net_per_std=(float(n.sum()) / sd if sd > 0 else None), rolls=int(df["n_rolls"].sum()))


def render(frame, daily, res, counts, gates, c3, grid, notes=None, scoped=False) -> tuple[str, dict]:
    L = []
    w = L.append
    w("W15-0027 TL-v1 CL 4-hour variant (REGISTERED_tl_v1.md sec 2.5) -- REPORTED ONLY, training side")
    w("Unranked. Cannot spend the holdout. Not a sec 4 criterion. No verdict is given and none is implied.")
    if scoped:
        w("*** SCOPED RUN: not the registered configuration. ***")
    w(f"Window: sessions {E.TRAIN_START} .. {E.TRAIN_END} (cut on the 1-hour frame before any bar was built).")
    w(f"Frame: {len(frame):,} 4H bars, {len(daily):,} daily sessions, "
      f"{int((frame['held_id'] != frame['held_id'].shift(1)).sum() - 1)} held-contract rolls. "
      f"First bar {frame['date'].iloc[0]}, last {frame['date'].iloc[-1]}.")
    w("1 MCL, costs = HTF-Ben v0 Amendment A (NinjaTrader Free plan) (MCL $1.09 / $2.09 / $3.09 per side: low / mid / high). Negatives in brackets.")
    for n in (notes or []):
        w(n)
    w("")

    tabs, summary = {}, []
    w("HEADLINE -- FIX book (ensemble of the three sleeves, 1 MCL in total), mid friction")
    w(f"{'spec':<11}{'trades':>7}{'W/L':>9}{'gross':>10}{'costs':>9}{'net mid':>10}{'net low':>10}{'net high':>10}"
      f"{'avg win':>9}{'avg loss':>10}{'max DD':>9}{'half 1':>9}{'half 2':>9}")
    for spec in VARIANT_ORDER:
        st = stats(_book(res, spec, "FIX"), frame)
        tabs[spec] = st
        w(f"{spec:<11}{st['trades']:>7}{str(st['wins']) + '/' + str(st['losses']):>9}{money(st['gross']):>10}"
          f"{money(st['costs']):>9}{money(st['net_mid']):>10}{money(st['net_low']):>10}{money(st['net_high']):>10}"
          f"{money(st['avg_win']):>9}{money(st['avg_loss']):>10}{money(st['max_dd']):>9}"
          f"{money(st['half1']):>9}{money(st['half2']):>9}")
        summary.append(dict(spec=spec, book="FIX", R="ens", **st))
    w("")

    w("BOOKS -- TL-v1 (v1) in each sizing, mid friction")
    w(f"{'book':<8}{'part':<9}{'trades':>7}{'W/L':>9}{'net mid':>10}{'net low':>10}{'net high':>10}{'max DD':>9}")
    for book in E.BOOKS:
        st = stats(E.ensemble(res["v1"][book]), frame)
        w(f"{book:<8}{'ensemble':<9}{st['trades']:>7}{str(st['wins']) + '/' + str(st['losses']):>9}"
          f"{money(st['net_mid']):>10}{money(st['net_low']):>10}{money(st['net_high']):>10}{money(st['max_dd']):>9}")
        summary.append(dict(spec="v1", book=book, R="ens", **st))
        for R in PIVOT_SIZES:
            st = stats(res["v1"][book][(R, "alone")], frame)
            w(f"{book:<8}{'R=' + str(R) + ' alone':<9}{st['trades']:>7}{str(st['wins']) + '/' + str(st['losses']):>9}"
              f"{money(st['net_mid']):>10}{money(st['net_low']):>10}{money(st['net_high']):>10}{money(st['max_dd']):>9}")
            summary.append(dict(spec="v1", book=book, R=str(R), **st))
    w("")

    w("PER YEAR -- FIX book, mid friction (year of exit session)")
    yrs = {}
    for spec in ("v1", "v1-A+", "C2 v0-rev", "C1"):
        df = _book(res, spec, "FIX")
        yrs[spec] = (df.groupby(pd.to_datetime(df["exit_session"]).dt.year)["net_mid"].sum()
                     if len(df) else pd.Series(dtype=float))
    years = sorted(set().union(*[set(s.index) for s in yrs.values()]))
    w(f"{'year':<6}" + "".join(f"{s:>12}" for s in yrs))
    for y in years:
        w(f"{y:<6}" + "".join(f"{money(float(s.get(y, 0.0))):>12}" for s in yrs.values()))
    w("")

    v1 = tabs["v1"]
    w("CONTROLS (FIX book, mid friction, same bars, sizing and costs)")
    w(f"  C1 Donchian 20/10 (no daily filter): trades {tabs['C1']['trades']}  net {money(tabs['C1']['net_mid'])}  "
      f"net/std of daily net {tabs['C1']['net_per_std'] if tabs['C1']['net_per_std'] is None else round(tabs['C1']['net_per_std'], 2)}")
    w(f"  TL-v1 net/std of daily net: "
      f"{v1['net_per_std'] if v1['net_per_std'] is None else round(v1['net_per_std'], 2)}")
    w(f"  C2 v0-rev on the same 4H bars (reference): trades {tabs['C2 v0-rev']['trades']}  net {money(tabs['C2 v0-rev']['net_mid'])}")
    if c3 is not None:
        beat = float(np.mean(v1['net_mid'] > c3['totals']))
        w(f"  C3 random selection of v1-A+ breaks, {c3['draws']} seeded draws: p5 {money(c3['p5'])}  p50 {money(c3['p50'])}  "
          f"p95 {money(c3['p95'])};  TL-v1 beats {beat * 100:.1f}% of draws.  "
          f"Selected breaks {c3['selected_breaks']} of pool {c3['pool_breaks']}; median filled entries per draw {c3['entries_median']:.0f} "
          f"(TL-v1: {v1['trades']}).")
    if grid is not None:
        pos = int((grid["net_mid"] > 0).sum())
        w(f"  Neighbour grid (27 cells, unranked, FIX mid): {pos} of {len(grid)} cells net > $0.  "
          f"Range {money(float(grid['net_mid'].min()))} to {money(float(grid['net_mid'].max()))}.")
    w("")

    w("COUNTS -- raw sec 2.2 breaks and where each was stopped (per sleeve R)")
    w(f"{'R':>3}{'raw breaks':>12}{'A+ breaks':>11}{'fail A1':>9}{'fail A2':>9}{'fail A3':>9}{'A2 pre-flight reading fails':>29}")
    ev_rows = []
    for R in PIVOT_SIZES:
        g = gates[("v1", R)]
        raw = int(g.raw_up.sum() + g.raw_dn.sum())
        q = int(g.qual_up.sum() + g.qual_dn.sum())
        f1 = int(g.fail_a1_up.sum() + g.fail_a1_dn.sum())
        f2 = int(g.fail_a2_up.sum() + g.fail_a2_dn.sum())
        f3 = int(g.fail_a3_up.sum() + g.fail_a3_dn.sum())
        f2p = int(np.sum(g.raw_up & ~(g.span_to_break_up >= 7)) + np.sum(g.raw_dn & ~(g.span_to_break_dn >= 7)))
        w(f"{R:>3}{raw:>12}{q:>11}{f1:>9}{f2:>9}{f3:>9}{f2p:>29}")
        ev_rows.append(dict(R=R, raw=raw, aplus=q, fail_a1=f1, fail_a2=f2, fail_a3=f3, fail_a2_preflight=f2p))
    cv = counts[(counts["spec"] == "v1") & (counts["book"] == "FIX") & (counts["share"] == "sleeve")]
    w("  simulator counts, v1 FIX sleeves (sum of R): " + ", ".join(
        f"{k} {int(cv[k].sum())}" for k in ("signals", "entries", "reversals", "reversal_blocked_flat",
                                            "htf_blocked", "not_aplus", "voided", "no_stop", "ignored_in_position")))
    er = {q: round(float(np.nanquantile(_ER(frame), q)), 4) for q in (0.20, 0.25, 0.33)}
    w(f"  A3 threshold used (CL 4H ER(20), training bars): q25 = {er[0.25]}  (q20 {er[0.20]}, q33 {er[0.33]})")
    w("")
    w("CAVEATS")
    w("  Bar-count parameters keep their registered numbers in 4H bars (W 250, span 400, pivots 3/5/8, touch pivots 2); A2 is 7 calendar days.")
    w("  The safety line is the opposing DAILY line -/+ 0.25 x 4H ATR. P&L is the adjusted move (= leg sum across rolls); no separate stop-slip tick (Amendment A levels carry it).")
    w("  One market, one sample of about 11.5 years: a description of this variant, not evidence. The daily TL-v1 verdict (W15-0020) is not changed by it.")
    return "\n".join(L) + "\n", dict(summary=pd.DataFrame(summary), events=pd.DataFrame(ev_rows))


def _ER(frame):
    from common.tl_v1_lines import efficiency_ratio
    return efficiency_ratio(frame["close"].to_numpy(dtype=float), 20)
