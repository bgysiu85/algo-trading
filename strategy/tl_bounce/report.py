#!/usr/bin/env python3
"""TL-bounce sec 3 report and sec 4 verdict. W15-0016.
REGISTERED_tl_bounce.md sec 3 ("What every run must emit") and sec 4 ("The
bar to clear").

Reuses strategy.htf.book's generic scoring machinery unchanged (net_table,
summarize, year_table, split_halves, top_year_share, bootstrap_by_year,
exit_reason_counts, sample_trades, trail_started_share, median_hold_hours):
those functions only ever read a plain list of Trade-shaped objects
(session, entry_t, exit_t, direction, exit_reason, trail_started, n_rolls,
gross_pnl()/cost()/net_pnl()) -- exactly what strategy.tl_bounce.engine.Trade
and strategy.tl_bounce.controls' own C1/C2 trades already are, so nothing
here reimplements dollar aggregation a second time.

sec 4's nine criteria differ from HTF-Ben v0's (strategy.htf.book.score):
criterion 5 here is "beats C1" alone (not "beats C1 AND C2"), criterion 6 is
"beats the p95 of C2" (not C3), and criterion 8's bar is 18/27, not 12/18 --
so this module has its own score(), built from the SAME book.py primitives.

criterion 9 ("at least 150 trades") is registered as a STOP RULE, not an
ordinary pass/fail: "Fewer -> NOT READ, not failed" (sec 4, and sec 5.2's
G2 stop rule is the same rule applied earlier, before any P&L). render()
marks the whole verdict UNDERPOWERED rather than scoring criteria 1-8 when
this fires, mirroring preflight.py's own stop-rule handling.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from strategy.htf import book as BK
from strategy.tl_bounce.spec import RISK_EQUITIES, STOP_RULE_MIN_ENTRIES

MULT = {"MCL": 100.0, "CL": 1000.0}


def money(v, w: int = 12) -> str:
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "n/a".rjust(w)
    s = f"${abs(v):,.0f}"
    return (f"({s})" if v < 0 else f" {s} ").rjust(w)


def pct(v, w: int = 7) -> str:
    if v is None or not np.isfinite(v):
        return "n/a".rjust(w)
    return f"{100 * v:.0f}%".rjust(w)


@dataclass
class Criterion:
    n: int
    label: str
    passed: bool | None    # None = not evaluated
    detail: str


def score(*, df_mid: pd.DataFrame, df_high: pd.DataFrame, year_net_mid: dict,
         net_c1: float | None, c2_p95: float | None,
         neighbour_positive: int | None, neighbour_total: int | None,
         min_trades: int = STOP_RULE_MIN_ENTRIES) -> list[Criterion]:
    net_mid = float(df_mid["net"].sum()) if len(df_mid) else 0.0
    net_high = float(df_high["net"].sum()) if len(df_high) else 0.0
    first, second = BK.split_halves(df_mid)
    top_year, top_share = BK.top_year_share(year_net_mid)
    boot = BK.bootstrap_by_year(year_net_mid)
    n_trades = len(df_mid)

    crit = []
    crit.append(Criterion(1, "Net > $0", net_mid > 0, f"${net_mid:,.2f}"))
    crit.append(Criterion(2, "Both halves net > $0", (first > 0) and (second > 0),
                          f"${first:,.2f} / ${second:,.2f}"))
    crit.append(Criterion(3, "No single calendar year > 50% of net",
                          (abs(top_share) <= 0.50) if year_net_mid else None,
                          f"{top_year}: {top_share:.1%}" if top_year is not None else "n/a"))
    crit.append(Criterion(4, "Bootstrap by year: total > 0 in >= 95%",
                          (boot >= 0.95) if not np.isnan(boot) else None,
                          f"{boot:.1%}" if not np.isnan(boot) else "NOT ENOUGH YEARS"))
    crit.append(Criterion(5, "Beats C1 (Donchian) on net",
                          (net_mid > net_c1) if net_c1 is not None else None,
                          f"bounce ${net_mid:,.2f} vs C1 ${net_c1:,.2f}"
                          if net_c1 is not None else "NOT SUPPLIED"))
    crit.append(Criterion(6, "Beats the p95 of C2 (random entries) on net",
                          (net_mid > c2_p95) if c2_p95 is not None else None,
                          f"bounce ${net_mid:,.2f} vs C2 p95 ${c2_p95:,.2f}"
                          if c2_p95 is not None else "NOT SUPPLIED"))
    crit.append(Criterion(7, "Still net > $0 at high friction", net_high > 0, f"${net_high:,.2f}"))
    if neighbour_positive is not None and neighbour_total is not None:
        crit.append(Criterion(8, "At least 18 of 27 neighbour cells net > $0",
                              neighbour_positive >= 18, f"{neighbour_positive}/{neighbour_total}"))
    else:
        crit.append(Criterion(8, "At least 18 of 27 neighbour cells net > $0", None, "NOT SUPPLIED"))
    crit.append(Criterion(9, f"At least {min_trades} trades on the training side",
                          n_trades >= min_trades, f"{n_trades} trades"))
    return crit


def _section3(symbol: str, level: str, trades: list, qty: int = 1) -> str:
    df = BK.net_table(trades, symbol, level, qty)
    s = BK.summarize(df)
    year_net = BK.year_table(df)
    lines = [
        f"  trades={s.trades}  wins={s.wins}  losses={s.losses}  "
        f"gross={money(s.gross)}  cost={money(s.cost)}  net={money(s.net)}",
        f"  avg_win={money(s.avg_win)}  avg_loss={money(s.avg_loss)}  "
        f"largest_loss={money(s.largest_loss)}  worst_loss_streak={s.worst_loss_streak}",
        f"  exit reasons: {BK.exit_reason_counts(df)}",
        f"  trail started on {pct(BK.trail_started_share(df))} of trades  "
        f"median hold: {BK.median_hold_hours(df)!s} hours",
        "  net by year: " + ", ".join(f"{y}: {money(v,10)}" for y, v in sorted(year_net.items())),
    ]
    return "\n".join(lines)


def render(*, symbol: str, qty: int, trades_by_level: dict[str, list],
          neighbour: dict | None, c1_trades: list, c2_result: dict,
          not_built: dict, header_notes: list[str], stamp: str) -> tuple[str, list]:
    """trades_by_level: {'low'|'mid'|'high': [Trade, ...]} for "bounce" on
    the 4-hour chart, training side only (caller's job to slice). Returns
    (report_text, criteria)."""
    out = [f"TL-bounce backtest -- training side only ({stamp})",
          "=" * 70, ""]
    out += header_notes + [""]

    for level in ("low", "mid", "high"):
        out.append(f"-- {level} friction --")
        out.append(_section3(symbol, level, trades_by_level[level], qty))
        out.append("")

    df_mid = BK.net_table(trades_by_level["mid"], symbol, "mid", qty)
    df_high = BK.net_table(trades_by_level["high"], symbol, "high", qty)
    year_net_mid = BK.year_table(df_mid)

    net_c1 = (sum(t.net_pnl(symbol, "mid", qty) for t in c1_trades)
             if c1_trades is not None else None)
    c2_p95 = c2_result.get("p95") if c2_result else None

    n_trades_mid = len(df_mid)
    underpowered = n_trades_mid < STOP_RULE_MIN_ENTRIES
    out.append("-- sec 4: the bar to clear --")
    if underpowered:
        out.append(f"  UNDERPOWERED: {n_trades_mid} training-side trades, need >= "
                   f"{STOP_RULE_MIN_ENTRIES} (criterion 9). NOT READ, not failed -- "
                   "back to Ben before any other criterion is scored.")
        crit = []
    else:
        crit = score(df_mid=df_mid, df_high=df_high, year_net_mid=year_net_mid,
                    net_c1=net_c1, c2_p95=c2_p95,
                    neighbour_positive=(neighbour["n_positive"] if neighbour else None),
                    neighbour_total=(neighbour["n_total"] if neighbour else None))
        for c in crit:
            verdict = "n/a" if c.passed is None else ("PASS" if c.passed else "FAIL")
            out.append(f"  {c.n}. {c.label}: {verdict}  ({c.detail})")
        closes = any((c.n == 5) and (c.passed is False) for c in crit)
        if closes:
            out.append("  criterion 5 FAILS -> study closes whatever else passes (sec 4).")

    out.append("")
    out.append("-- C1 Donchian (20/10), same bars/fills/sizing/costs, mid friction --")
    out.append(_section3(symbol, "mid", c1_trades, qty) if c1_trades is not None else "  n/a")
    out.append("")
    out.append("-- C2 random entries (1,000 draws), net $ percentiles --")
    if c2_result and c2_result.get("p5") is not None:
        out.append(f"  n_draws={c2_result['n_draws']}  pool_size={c2_result['pool_size']}  "
                   f"trades_per_draw={c2_result['n_trades_per_draw']}")
        out.append(f"  p5={money(c2_result['p5'])}  p50={money(c2_result['p50'])}  "
                   f"p95={money(c2_result['p95'])}")
    else:
        out.append("  n/a (no bounce trades or no flat pool to draw from)")
    out.append("")

    if neighbour:
        out.append(f"-- neighbour grid: {neighbour['n_positive']}/{neighbour['n_total']} "
                   f"cells net positive ({neighbour['share_positive']:.0%}) --")
        for r in neighbour["cells"]:
            out.append(f"  touch={r['touch_buf']:.2f} x1={r['x1_buf']:.2f} R={r['pivot_R']}: "
                       f"net={money(r['net'],10)}  trades={r['trades']}")
    out.append("")

    out.append(f"-- not yet built (reported, cannot spend holdout, cannot close the study): "
               f"variants={not_built.get('variants')}, controls={not_built.get('controls')} --")
    out.append("-- known approximation: bounce-once is coded as 'no re-entry at all', "
               "narrower than the registered 'one entry per line' (sim.py/engine.py "
               "docstrings) -- does not affect 'bounce' itself --")

    out.append("")
    out.append("-- sample trades (every 20th, mid friction) --")
    for s in sample_trades(trades_by_level["mid"], symbol, "mid", qty):
        out.append(f"  {s}")

    return "\n".join(out), crit


def sample_trades(trades: list, symbol: str, level: str, qty: int = 1, every: int = 20) -> list[dict]:
    """sec 3 item 10: every 1/every'th trade (not the best), in order. Not
    strategy.htf.book.sample_trades: that reads t.initial_stop_adj, a
    field HTF-Ben's Trade has and tl_bounce's own does not (this study
    carries a stop DISTANCE, fill_raw + stop_dist, sec 2.4's re-anchoring
    reasoning -- engine.py's own docstring)."""
    out = []
    for i in range(0, len(trades), every):
        t = trades[i]
        out.append({
            "entry_t": str(t.entry_t), "exit_t": str(t.exit_t), "direction": t.direction,
            "fill": t.fill_raw, "stop_dist": t.stop_dist, "exit": t.exit_price_raw,
            "exit_reason": t.exit_reason, "net": t.net_pnl(symbol, level, qty),
        })
    return out
