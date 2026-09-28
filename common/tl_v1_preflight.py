#!/usr/bin/env python3
"""TL-v1 count-only pre-flight -- REGISTERED_tl_v1.md sec 5.1 gate G2 / sec 5.2.

    python -m common.tl_v1_preflight

TRAINING SIDE ONLY (2010-06-01 .. 2021-12-31). NO EXIT PRICE IS READ AND NO
P&L IS COMPUTED -- the runner refuses both, same discipline as
common/tl_v0_preflight.py (sec 5's own words, repeated verbatim for TL-v1 in
sec 5.2). This module never simulates a stop or a reversal outcome; it only
counts breaks, the reasons a break fails to become an A+ entry, and the
distribution of the trending filter's own indicator (ER(20)) so its
training-only percentile thresholds (q20/q25/q33) can be written into the
registration BEFORE anything about entries clearing them is judged.

Reuses W15-0014's engine end to end, per G6:
  - strategy.tl_v0.spec.MARKETS / PIVOT_SIZES     -- same 12 markets, same
    ensemble sleeves (Amendment A: no ZN)
  - strategy.tl_v0.bars.load_market                -- same archive loader,
    same roll rule, same holdout cut (training side only, enforced inside
    strategy.tl_v0.bars via common.tl_v1_holdout -- see NOTE below)
  - strategy.tl_v0.signals.weekly_state/align_weekly -- the E2 top-down
    filter, unchanged (REGISTERED_tl_v1.md sec 2.1: "as TL-v0")
  - common.tl_v0_lines.find_pivots, atr14           -- pivots and ATR

ONLY THE LINE AND THE A+ GATE ARE NEW (common/tl_v1_lines.py): her
extreme-anchor construction (sec 2.2) in place of TL-v0's "two most recent
pivots", and A1-A3 (sec 2.3) evaluated at each break.

NOTE ON THE HOLDOUT CUT: strategy.tl_v0.bars.load_market cuts through
common.tl_v0_holdout (TL-v0's own ledger), not common.tl_v1_holdout -- by
design (see strategy/tl_v0/bars.py's own docstring: "THE HOLDOUT IS CUT
FIRST"). Both ledgers lock the same 2010-06-01..2021-12-31 training window
off the same 2022-01-03 boundary (TL-v0's is 2022-01-01, one session
earlier -- immaterial here: 2022-01-01 was a Saturday, no session exists on
it either way), so reusing TL-v0's bars for training-side counting does not
touch TL-v1's own holdout or its own ledger. TL-v1's holdout is spent (or
not) only by W15-0020, through common.tl_v1_holdout directly on the date
list it builds its own backtest from -- this module never calls
common.tl_v1_holdout.split_dates(spend=True) and could not: it has no
candidate name to offer, being pre-flight, not a backtest.
"""
from __future__ import annotations
import argparse

import numpy as np
import pandas as pd

from common.tl_v0_lines import atr14, find_pivots
from common.tl_v1_lines import (
    build_series, touch_pivots_between, efficiency_ratio, a_plus_checklist,
    MIN_TOUCHES, MIN_SPAN_DAYS,
)
from common.report_io import emit
from strategy.tl_v0.spec import MARKETS, PIVOT_SIZES
from strategy.tl_v0.signals import weekly_state, align_weekly
from strategy.tsmom.registry import Root  # noqa: F401 (type import parity with bars.py)

ARCHIVE_DEFAULT = r"E:\Databento\GLBX.MDP3"
ER_LEN = 20
ER_PERCENTILES = (0.20, 0.25, 0.33)
STOP_RULE_MIN_ENTRIES = 150


def _span_days(dates: pd.Series, pA: int, t: int) -> float:
    return (dates.iloc[t] - dates.iloc[pA]).days


def run_market(root, m):
    from strategy.tl_v0.bars import load_market
    mb, _c0 = load_market(ARCHIVE_DEFAULT, m)
    frame = mb.frame
    dates = frame["date"]
    o, h, lo, c = (frame[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    n = len(c)
    a = atr14(h, lo, c)
    er = efficiency_ratio(c, ER_LEN)
    er_thresholds = {p: float(np.nanquantile(er, p)) for p in ER_PERCENTILES}

    entries, counts = [], []
    for R in PIVOT_SIZES:
        ph = find_pivots(h, R, "high")
        pl = find_pivots(lo, R, "low")
        touch_h = find_pivots(h, 2, "high")
        touch_l = find_pivots(lo, 2, "low")

        res_out = build_series(n, ph, c, a, "res")
        sup_out = build_series(n, pl, c, a, "sup")

        w = weekly_state(frame, R)
        al = align_weekly(frame["date"], w, ["dir"])
        weekly_dir = al["dir"].fillna(0).to_numpy(dtype=float)

        n_breaks = n_fail_a1 = n_fail_a2 = n_fail_a3 = n_fail_weekly = 0
        n_entries = n_reversals = n_flat_after_blocked_reversal = 0
        touches_med, span_med = [], []
        position = None
        for kind, out, other in (("res", res_out, sup_out), ("sup", sup_out, res_out)):
            direction = "long" if kind == "res" else "short"
            touch_pivots = touch_h if kind == "res" else touch_l
            fires = np.nonzero(out["breaks"])[0]
            for t in fires:
                n_breaks += 1
                pA = out["anchor_bar"][t]
                cnt, _hits = touch_pivots_between(pA, t, touch_pivots, out["line"], a, kind)
                span = _span_days(dates, pA, t) if pA >= 0 else 0.0
                ok, detail = a_plus_checklist(
                    t, pA, cnt, span, er[t] if t < len(er) else np.nan,
                    er_thresholds[0.25])
                if not detail["A1_touches"]:
                    n_fail_a1 += 1
                if not detail["A2_span"]:
                    n_fail_a2 += 1
                if not detail["A3_trending"]:
                    n_fail_a3 += 1
                if not ok:
                    continue
                wf_ok = (weekly_dir[t] == 1 and direction == "long") or \
                        (weekly_dir[t] == -1 and direction == "short")
                if not wf_ok:
                    n_fail_weekly += 1
                    continue
                touches_med.append(cnt)
                span_med.append(span)
                if position is None or position == direction:
                    n_entries += 1
                    position = direction
                else:
                    # opposite-side A+ break while in a position: v0-rev-style
                    # reversal ONLY if it itself passes A+ + weekly (sec 2.4) --
                    # it already has here, so it reverses.
                    n_reversals += 1
                    position = direction

        counts.append(dict(
            market=root, R=R, breaks=int(n_breaks),
            fail_A1_touches=int(n_fail_a1), fail_A2_span=int(n_fail_a2),
            fail_A3_trending=int(n_fail_a3), fail_weekly=int(n_fail_weekly),
            entries=int(n_entries), reversals=int(n_reversals),
            median_touches=float(np.median(touches_med)) if touches_med else np.nan,
            median_span_days=float(np.median(span_med)) if span_med else np.nan,
        ))
        entries.append(dict(market=root, R=R, n_entries=n_entries))

    return counts, entries, {"n_bars": n, "first": str(dates.min().date()),
                              "last": str(dates.max().date())}, er_thresholds


def build_report(cdf: pd.DataFrame, er_by_market: dict) -> str:
    lines = []
    def p(s=""):
        lines.append(s)

    p("TL-v1 PRE-FLIGHT -- REGISTERED_tl_v1.md sec 5.1 gate G2 / sec 5.2 (W15-0019)")
    p("Training side only (2010-06-01 .. 2021-12-31). NO EXIT PRICE READ, NO P&L COMPUTED.")
    p("Reuses W15-0014's engine (bars, weekly filter); line geometry is TL-v1's own (sec 2.2).")
    p("")
    p("=" * 78); p("1. BREAKS AND WHY THEY DID NOT BECOME AN A+ ENTRY"); p("=" * 78)
    p("(a break can fail more than one of A1/A2/A3; entries only requires all three + weekly)")
    summ = cdf.groupby("R")[["breaks", "fail_A1_touches", "fail_A2_span",
                              "fail_A3_trending", "fail_weekly", "entries",
                              "reversals"]].sum()
    p(summ.to_string()); p("")
    total_entries = int(cdf["entries"].sum())
    p(f"TOTAL TL-v1 entries, all markets, all three pivot sleeves: {total_entries}")
    p(f"Stop rule (sec 5.2): fewer than {STOP_RULE_MIN_ENTRIES} entries -> stop as underpowered,")
    p("report as the finding, back to Ben before any P&L.")
    if total_entries < STOP_RULE_MIN_ENTRIES:
        p(f"*** STOP RULE HIT: {total_entries} < {STOP_RULE_MIN_ENTRIES}. Underpowered on this reading. ***")
    else:
        p(f"Clears the stop rule ({total_entries} >= {STOP_RULE_MIN_ENTRIES}).")

    p(""); p("=" * 78); p("2. PER-MARKET BREAKDOWN, R=5 (reported neighbour; 3 & 8 in the CSV)"); p("=" * 78)
    sub = cdf[cdf.R == 5][["market", "breaks", "fail_A1_touches", "fail_A2_span",
                            "fail_A3_trending", "fail_weekly", "entries",
                            "median_touches", "median_span_days"]]
    p(sub.to_string(index=False))

    p(""); p("=" * 78); p("3. ER(20) TRAINING-ONLY PERCENTILE THRESHOLDS (A3), PER MARKET"); p("=" * 78)
    p("Written back into REGISTERED_tl_v1.md sec 2.3 as a PRE-RUN amendment (this table).")
    p("A3 in this run used q25 (the registration's default reading); q20/q33 reported alongside")
    p("for the neighbour grid (sec 3).")
    for mkt, th in er_by_market.items():
        p(f"  {mkt}: q20={th[0.20]:.3f}  q25={th[0.25]:.3f}  q33={th[0.33]:.3f}")

    p(""); p("=" * 78); p("4. WHAT THIS RUN DOES NOT ANSWER"); p("=" * 78)
    p("""
No stop distance, no sizeability, no exit, no P&L, no reversal outcome
(a "reversal" above only means an opposite-direction A+ break fired while a
position from the other side was open -- whether that reverses profitably is
step 4's question, W15-0020, not this one's). A3's threshold is read off the
SAME training window it is applied to (sec 2.3 names this explicitly as the
PRE-RUN write-back this gate performs) -- not a look-ahead into the holdout,
since the holdout (2022-01-03 onward) never reaches this loader at all
(strategy.tl_v0.bars cuts it before a row is folded).
""")
    return "\n".join(lines)


def main(argv=None) -> int:
    global ARCHIVE_DEFAULT
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--markets", nargs="+", default=list(MARKETS))
    ap.add_argument("--archive", default=ARCHIVE_DEFAULT)
    ap.add_argument("--report", default="var/reports/tl_v1_preflight.txt")
    ap.add_argument("--entries-csv", default="var/reports/tl_v1_preflight_entries.csv")
    ap.add_argument("--counts-csv", default="var/reports/tl_v1_preflight_counts.csv")
    a = ap.parse_args(argv)
    ARCHIVE_DEFAULT = a.archive

    all_counts, all_entries, er_by_market = [], [], {}
    for root in a.markets:
        m = MARKETS[root]
        try:
            counts, entries, _notes, er_th = run_market(root, m)
        except Exception as e:  # noqa: BLE001 -- reported, not swallowed
            print(f"{root}: FAILED -- {e}")
            continue
        all_counts += counts
        all_entries += entries
        er_by_market[root] = er_th

    cdf = pd.DataFrame(all_counts)
    edf = pd.DataFrame(all_entries)
    cdf.to_csv(a.counts_csv, index=False)
    edf.to_csv(a.entries_csv, index=False)
    text = build_report(cdf, er_by_market)
    emit(text, a.report, header="common.tl_v1_preflight")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
