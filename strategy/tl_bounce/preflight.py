#!/usr/bin/env python3
"""G2 -- TL-bounce pre-flight (training side only, NO EXIT PRICES, NO P&L).
W15-0015. REGISTERED_tl_bounce.md sec 5.1 (gate G2) and sec 5.2.

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.tl_bounce.preflight

Per sec 5.2: touch bars, held, E0-blocked, ignored, voided, entries,
re-entries, per year, on 4-hour (primary) and 1-hour (reported); initial
stop distance in $ per MCL and per CL (median, p90, max); share sizeable at
1% of $10k and $22k. NO EXIT PRICE IS READ AND NO P&L IS COMPUTED -- there
is no exit-price column or dollar-P&L arithmetic anywhere in this module;
sim.py's own Entry records carry a bar index and reason, never a $ result.

STOP RULE (sec 5.2): fewer than STOP_RULE_MIN_ENTRIES TL-bounce entries on
the 4-hour chart, training side -> stop as underpowered, reported as the
finding, back to Ben before any P&L is read.

WHAT IS RUN, AND WHAT IS NOT YET BUILT
-------------------------------------------
Built here: the "bounce" rule set and its bounce-noX1 / bounce-noE0 /
bounce-once variants (sec 2.5), on 4H and 1H. NOT yet built: bounce-limit
(a structurally different resting-limit E1/E2, sim.py's own docstring) and
control C3 (break entries on TL-v0's action line, sec 2.5's "Not coded"
list does not cover C3 -- it is simply not written yet). Both are reported
here as "not_built": true rather than silently omitted or zero-filled, so
the report cannot be misread as "this variant found zero entries".
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from strategy.htf import bars as B
from strategy.tl_bounce import lines as L
from strategy.tl_bounce import sim as S
from strategy.tl_bounce.signals import market_signals
from strategy.tl_bounce.spec import (ATR_LEN, FRICTION, FRICTION_CL,
                                     PIVOT_R, RISK_EQUITIES, STOP_RULE_MIN_ENTRIES,
                                     TRAIN_END, TRAIN_START, VARIANTS)

MULT = {"MCL": 100.0, "CL": 1000.0}     # $ per $1/bbl move, one contract
ENTRY_HIGHER = {"4H": ("1D", 24), "1H": ("4H", 4)}

BUILT_VARIANTS = {
    "bounce": dict(e0_on=True, x1_on=True, allow_reentry=True),
    "bounce-noX1": dict(e0_on=True, x1_on=False, allow_reentry=True),
    "bounce-noE0": dict(e0_on=False, x1_on=True, allow_reentry=True),
    "bounce-once": dict(e0_on=True, x1_on=True, allow_reentry=False),
}
NOT_BUILT_VARIANTS = ("bounce-limit",)
NOT_BUILT_CONTROLS = ("C3",)


def prepare_grids(df_1h: pd.DataFrame) -> dict:
    """{entry_chart: (entry_frame, higher_frame, higher_bar_hours)},
    all back-adjusted (sec 2.1: lines and indicators run on the
    back-adjusted series, inherited from HTF-Ben v0 sec 2.1)."""
    out = {}
    for entry_chart, (higher_chart, higher_hours) in ENTRY_HIGHER.items():
        entry_frame = B.back_adjust(B.resample(df_1h, entry_chart))
        if higher_chart == "1D":
            higher_frame = B.back_adjust(B.daily(df_1h))
        else:
            higher_frame = B.back_adjust(B.resample(df_1h, higher_chart))
        out[entry_chart] = (entry_frame, higher_frame, higher_hours)
    return out


def run_variant(entry_frame: pd.DataFrame, higher_frame: pd.DataFrame,
                higher_bar_hours: int, *, e0_on: bool, x1_on: bool,
                allow_reentry: bool) -> tuple[list[S.Entry], S.Counts, pd.Series]:
    e0 = L.e0_filter(entry_frame, higher_frame, higher_bar_hours, R=PIVOT_R,
                     atr_len=ATR_LEN) if e0_on else None
    sig = market_signals(entry_frame, e0=e0)
    entries, counts = S.simulate(sig, e0_on=e0_on, x1_on=x1_on,
                                 allow_reentry=allow_reentry)
    return entries, counts, entry_frame["session"]


def _pct(values, q):
    return float(np.percentile(values, q)) if values else None


def _sizeable_share(dists_usd: list[float], equities) -> dict:
    """Share of entries whose 1%-of-equity contract count (floor) is >= 1,
    at each of RISK_EQUITIES (sec 2.4, 'reported only')."""
    out = {}
    for eq in equities:
        if not dists_usd:
            out[str(int(eq))] = None
            continue
        risk = 0.01 * eq
        sizeable = sum(1 for d in dists_usd if d > 0 and np.floor(risk / d) >= 1)
        out[str(int(eq))] = sizeable / len(dists_usd)
    return out


def run_all(archive_1h) -> dict:
    df_1h = B.load_1h(archive_1h)
    grids = prepare_grids(df_1h)

    report: dict = {"variants": {}, "not_built": {
        "variants": list(NOT_BUILT_VARIANTS), "controls": list(NOT_BUILT_CONTROLS)}}
    bounce_4h_training_entries = None

    for variant, opts in BUILT_VARIANTS.items():
        report["variants"][variant] = {}
        for entry_chart, (entry_frame, higher_frame, higher_hours) in grids.items():
            entries, counts, sessions = run_variant(
                entry_frame, higher_frame, higher_hours, **opts)
            opens = entry_frame["open_adj"].to_numpy()
            dists_mcl, dists_cl = [], []
            per_year: dict[int, dict] = {}
            train_entries = []
            for e in entries:
                sess = str(sessions.iloc[e.entry_j])[:10]
                if not (TRAIN_START <= sess <= TRAIN_END):
                    continue
                train_entries.append(e)
                d_mcl = abs(opens[e.entry_j] - e.stop_init) * MULT["MCL"]
                d_cl = abs(opens[e.entry_j] - e.stop_init) * MULT["CL"]
                dists_mcl.append(d_mcl)
                dists_cl.append(d_cl)
                y = int(sess[:4])
                per_year.setdefault(y, []).append(d_mcl)

            totals = counts.as_dict()
            totals["entries_training"] = len(train_entries)
            totals["re_entries_training"] = sum(1 for e in train_entries if e.is_reentry)
            totals["stop_dist_mcl_median"] = _pct(dists_mcl, 50)
            totals["stop_dist_mcl_p90"] = _pct(dists_mcl, 90)
            totals["stop_dist_mcl_max"] = (max(dists_mcl) if dists_mcl else None)
            totals["sizeable_share_1pct"] = _sizeable_share(dists_mcl, RISK_EQUITIES)
            totals["underpowered"] = totals["entries_training"] < STOP_RULE_MIN_ENTRIES

            by_year = {y: {"entries": len(ds), "stop_dist_mcl_median": _pct(ds, 50),
                          "stop_dist_mcl_p90": _pct(ds, 90)}
                      for y, ds in sorted(per_year.items())}

            report["variants"][variant][entry_chart] = {
                "counts_full_history": counts.as_dict(),
                "totals": totals, "per_year": by_year,
            }
            if variant == "bounce" and entry_chart == "4H":
                bounce_4h_training_entries = totals["entries_training"]

    report["stop_rule"] = {
        "min_required": STOP_RULE_MIN_ENTRIES,
        "bounce_4h_entries_training": bounce_4h_training_entries,
        "underpowered": (bounce_4h_training_entries or 0) < STOP_RULE_MIN_ENTRIES,
    }
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="G2: TL-bounce pre-flight (no P&L).")
    ap.add_argument("--archive", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)

    from common.tsmom_fetch import default_archive
    archive = a.archive or default_archive()

    report = run_all(archive)
    print("G2 -- TL-bounce pre-flight (training side, no P&L, no exit prices)\n")
    for variant in BUILT_VARIANTS:
        for entry_chart in ("4H", "1H"):
            t = report["variants"][variant][entry_chart]["totals"]
            print(f"{variant:12s} {entry_chart:3s}  touch={t['touch_bars']:5d}  "
                  f"held={t['held']:5d}  e0_blk={t['e0_blocked']:5d}  "
                  f"ignored={t['ignored_in_position']:5d}  voided={t['voided']:4d}  "
                  f"entries(training)={t['entries_training']:5d}  "
                  f"re_entries={t['re_entries_training']:4d}  "
                  f"stop$ median={t['stop_dist_mcl_median']!s:>8s}")
    sr = report["stop_rule"]
    print(f"\nstop rule (sec 5.2): bounce 4H entries(training)="
          f"{sr['bounce_4h_entries_training']} (need >= {sr['min_required']}) -> "
          f"{'UNDERPOWERED -- STOP, back to Ben' if sr['underpowered'] else 'OK, continue'}")
    print(f"\nnot yet built (see module docstring): "
          f"variants={report['not_built']['variants']}, "
          f"controls={report['not_built']['controls']}")

    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"\nfull report: {a.out}")

    return 1 if sr["underpowered"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
