#!/usr/bin/env python3
"""HTF-Ben v2 report -- W15-0021, REGISTERED_htf_ben_v2.md sec 3 (every
item) and sec 4 (all nine criteria), scenario B only, training side.
Wires together v2_preflight (the inherited q_h/q_e), v2_runner (the one
and only v2 engine -- sec 2.4 has no ablations), v2_controls (C1/C2/C3,
sec 3.6, every one re-run fresh against v2's own trades), v2_grid (sec
5.3's 6-cell exit-side grid), v2_holdout (training-side cut -- NEVER
spend=True here), plus v0's own generic aggregation modules (book/account/
weekly/readback), unchanged.

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.htf.v2_report --out claude\\w15_0021_v2_report.json

ONLY SCENARIO B (sec 2.3: "Scenario B ... is the sole scenario in scope
... A-2H is not run for v2"). Unlike v0's report.py (4 scenarios) and
v1_report.py (B scored, A-2H reported alongside), this module has exactly
one scenario throughout -- there is no REPORTED_SCENARIOS/SCORED_SCENARIOS
split to make here, and no code path that could accidentally run or report
A-2H for v2.

NO ABLATIONS (sec 2.4: "None"). v1_report.py runs v1 four times per
scenario (v1, v1-curl, v1-F1, v1-F2) plus v1-X; v2 has a single fixed rule
set and this module calls v2_runner.run_v2 exactly once per report (at its
registered defaults) for the headline numbers, separately from the
CONTROLS (C1/C2/C3, sec 3.6) and the GRID (sec 5.3), which call it again
with specific kwargs for their own, clearly-labelled purposes -- none of
those extra calls are ablations of v2 itself, and none is scored.

WHY q_h/q_e ARE MODULE CONSTANTS HERE, NOT COMPUTED (unlike v1_report.py)
--------------------------------------------------------------------------
v1_report.py computes q_h/q_e once via v1_preflight.compute_percentiles
because v1 registers them as a training-side computation. v2 registers
them as INHERITED BY REFERENCE from v1 Amendment C (sec 2.1: "carried into
v2 by reference, not recomputed in G2") -- so this module imports the same
two constants v2_preflight.py uses (V2P.Q_H/V2P.Q_E), rather than
recomputing anything.

THE 286-TRADE FLAG (sec 5.2, sec 8)
-------------------------------------
Sec 5.2: "This gate is expected to land close to, but not necessarily
equal to, the 286 trades the v1-X ablation reported... a large divergence
from 286 is itself worth flagging to Ben." Sec 8 repeats this as a named
risk. v2's own trades_taken (post-E5, from run_v2 itself) is compared
against 286 here and flagged in the report and the CLI output if the
relative difference exceeds ORIGIN_TRADE_COUNT_FLAG_PCT -- a diagnostic
note, not a pass/fail criterion (sec 4 has no such criterion).
"""
from __future__ import annotations

import argparse
import dataclasses
import json
from pathlib import Path

import numpy as np
import pandas as pd

from strategy.htf import account as A
from strategy.htf import bars as B
from strategy.htf import book as BK
from strategy.htf import preflight as P
from strategy.htf import readback as RB
from strategy.htf import v2_controls as V2C
from strategy.htf import v2_grid as V2G
from strategy.htf import v2_holdout as VH
from strategy.htf import v2_preflight as V2P
from strategy.htf import v2_runner as V2R
from strategy.htf import weekly as W

SCENARIO = "B"                       # sec 2.3: the sole scenario in scope
MIN_NEIGHBOUR_POSITIVE = 4           # sec 4 criterion 8: "4 of the 6"
ORIGINATING_TRADE_COUNT = 286        # sec 0.2: the v1-X ablation number this hypothesis is built from
ORIGIN_TRADE_COUNT_FLAG_PCT = 0.20   # sec 5.2/sec 8: "a large divergence ... worth flagging"


def training_trades(trades: list) -> list:
    """Cuts a runner.Trade list to the training side, via v2_holdout's OWN
    split_dates(spend=False) -- never v0's or v1's ledgers. Same convention
    as v1_report.py's own training_trades."""
    if not trades:
        return []
    sessions = [str(t.session) for t in trades]
    keep_dates, _, _ = VH.split_dates(sessions, spend=False)
    keep = set(keep_dates)
    return [t for t in trades if str(t.session) in keep]


def seen_trades(trades: list) -> list:
    """v2's own trades whose entry session falls in the seen window (sec
    6: 2025-09-23 onward) -- "reported only" (sec 3 item 10), never
    scored."""
    if not trades:
        return []
    sessions = [str(t.session) for t in trades]
    keep = set(VH.seen_dates(sessions))
    return [t for t in trades if str(t.session) in keep]


def v2_score(*, df_mid: pd.DataFrame, df_high: pd.DataFrame, year_net_mid: dict,
            net_c1: float | None, net_c2: float | None, c3_p95: float | None,
            neighbour_positive: int | None = None, neighbour_total: int | None = None,
            min_trades: int = 150,
            min_neighbour_positive: int = MIN_NEIGHBOUR_POSITIVE) -> list[BK.Criterion]:
    """REGISTERED_htf_ben_v2.md sec 4's nine criteria -- same nine as v0/v1
    (book.py's generic helpers, unchanged); only the criterion-8 threshold
    (4 of v2's 6 cells, not v1's 16 of 24) and the v2-flavoured labels
    differ, same reasoning as v1_report.v1_score's own docstring."""
    net_mid = float(df_mid["net"].sum()) if len(df_mid) else 0.0
    net_high = float(df_high["net"].sum()) if len(df_high) else 0.0
    first, second = BK.split_halves(df_mid)
    top_year, top_share = BK.top_year_share(year_net_mid)
    boot = BK.bootstrap_by_year(year_net_mid)
    n_trades = len(df_mid)

    crit = []
    crit.append(BK.Criterion(1, "Net > $0", net_mid > 0, f"${net_mid:,.2f}"))
    crit.append(BK.Criterion(2, "Both halves net > $0", (first > 0) and (second > 0),
                             f"${first:,.2f} / ${second:,.2f}"))
    crit.append(BK.Criterion(3, "No single calendar year > 50% of net",
                             (abs(top_share) <= 0.50) if year_net_mid else None,
                             f"{top_year}: {top_share:.1%}" if top_year is not None else "n/a"))
    crit.append(BK.Criterion(4, "Bootstrap by year: net > 0 in >= 95%",
                             (boot >= 0.95) if not np.isnan(boot) else None,
                             f"{boot:.1%}" if not np.isnan(boot) else "NOT ENOUGH YEARS"))
    have_c1c2 = net_c1 is not None and net_c2 is not None
    crit.append(BK.Criterion(5, "Beats v2's own, fresh C1 and C2 on net (failing this closes v2)",
                             (net_mid > net_c1 and net_mid > net_c2) if have_c1c2 else None,
                             f"v2 ${net_mid:,.2f} vs C1 ${net_c1:,.2f} vs C2 ${net_c2:,.2f}"
                             if have_c1c2 else "NOT SUPPLIED"))
    crit.append(BK.Criterion(6, "Beats the p95 of v2's own C3 on net",
                             (net_mid > c3_p95) if c3_p95 is not None else None,
                             f"v2 ${net_mid:,.2f} vs C3 p95 ${c3_p95:,.2f}"
                             if c3_p95 is not None else "NOT SUPPLIED"))
    crit.append(BK.Criterion(7, "Still net > $0 at high friction", net_high > 0, f"${net_high:,.2f}"))
    if neighbour_positive is not None and neighbour_total is not None:
        crit.append(BK.Criterion(
            8, f"At least {min_neighbour_positive} of {neighbour_total} neighbour cells net > $0",
            neighbour_positive >= min_neighbour_positive, f"{neighbour_positive}/{neighbour_total}"))
    else:
        crit.append(BK.Criterion(
            8, f"At least {min_neighbour_positive} of 6 neighbour cells net > $0",
            None, "NOT YET BUILT"))
    crit.append(BK.Criterion(9, f"At least {min_trades} trades on the training side",
                             n_trades >= min_trades, f"{n_trades} trades"))
    return crit


def verdict(criteria: list[BK.Criterion]) -> dict:
    """Same shape as v1_report.verdict: sec 4, verbatim -- criterion 5
    "closes v2 regardless of the rest, exactly as it closed v1"."""
    by_n = {c.n: c for c in criteria}
    c5 = by_n.get(5)
    closed_on_c5 = bool(c5 is not None and c5.passed is False)
    all_pass = all(c.passed is True for c in criteria)
    return {"all_nine_pass": all_pass, "closed_on_criterion_5": closed_on_c5,
           "failing": [c.n for c in criteria if c.passed is False],
           "not_evaluated": [c.n for c in criteria if c.passed is None]}


def run(archive_1h, *, symbol: str = "MCL", run_neighbours: bool = True,
       run_c3: bool = True, n_draws: int = V2C.C3_DRAWS, seed_prefix: str = "") -> dict:
    """Every sec.3 item, scenario B only, training side (see
    training_trades). q_h/q_e are the inherited constants (module
    docstring) -- never recomputed."""
    df_1h = B.load_1h(archive_1h)
    grids, daily_adj = P.prepare_grids(df_1h)
    coverage = RB.coverage(df_1h)
    q_h, q_e = V2P.Q_H, V2P.Q_E

    v2_all, v2_counts = V2R.run_v2(df_1h, scenario=SCENARIO, q_h=q_h, q_e=q_e)
    c1_all, c1_counts = V2C.run_c1(df_1h, scenario=SCENARIO, q_h=q_h, q_e=q_e)
    c2_all, c2_counts = V2C.run_c2(df_1h, scenario=SCENARIO)

    v2 = training_trades(v2_all)
    c1 = training_trades(c1_all)
    c2 = training_trades(c2_all)
    seen = seen_trades(v2_all)

    df_low = BK.net_table(v2, symbol, "low")
    df_mid = BK.net_table(v2, symbol, "mid")
    df_high = BK.net_table(v2, symbol, "high")
    year_net_mid = BK.year_table(df_mid)
    first_half, second_half = BK.split_halves(df_mid)

    net_c1 = float(BK.net_table(c1, symbol, "mid")["net"].sum()) if c1 else None
    net_c2 = float(BK.net_table(c2, symbol, "mid")["net"].sum()) if c2 else None

    c3 = None
    if run_c3 and v2:
        c3 = V2C.run_c3(df_1h, scenario=SCENARIO, v2_trades=v2, symbol=symbol,
                        level="mid", n_draws=n_draws, seed_prefix=seed_prefix)
    c3_p95 = c3["p95"] if c3 else None

    neighbours = None
    if run_neighbours:
        neighbours = V2G.run_grid(df_1h, scenario=SCENARIO, q_h=q_h, q_e=q_e, symbol=symbol,
                                  level="mid", train_start=P.TRAIN_START, train_end=P.TRAIN_END)
    n_pos = neighbours["n_net_positive"] if neighbours else None
    n_tot = neighbours["n_cells"] if neighbours else None

    criteria = v2_score(df_mid=df_mid, df_high=df_high, year_net_mid=year_net_mid,
                        net_c1=net_c1, net_c2=net_c2, c3_p95=c3_p95,
                        neighbour_positive=n_pos, neighbour_total=n_tot)
    score_verdict = verdict(criteria)

    alignment = W.trade_alignment(v2, daily_adj)
    weekly_net = W.net_by_alignment(alignment, symbol, "mid")

    session_calendar = sorted(daily_adj["date"].tolist())
    account_mcl = A.account_view(v2, "MCL", "mid", session_calendar=session_calendar)
    account_cl = A.account_view(v2, "CL", "mid", session_calendar=session_calendar)

    trades_taken = len(v2)
    origin_pct_diff = (abs(trades_taken - ORIGINATING_TRADE_COUNT) / ORIGINATING_TRADE_COUNT
                       if ORIGINATING_TRADE_COUNT else float("nan"))
    origin_flag = origin_pct_diff > ORIGIN_TRADE_COUNT_FLAG_PCT

    scenario_report = {
        "scenario": SCENARIO, "symbol": symbol, "scored": True,
        "q_h": q_h, "q_e": q_e,
        "counts_full_history": {"v2": v2_counts, "c1": c1_counts, "c2": c2_counts},   # item 5
        "trades_training": {"v2": len(v2), "c1": len(c1), "c2": len(c2)},
        "summary": {"low": BK.summarize(df_low), "mid": BK.summarize(df_mid),
                   "high": BK.summarize(df_high)},                                # item 1 (MCL)
        "summary_cl_mid": BK.summarize(BK.net_table(v2, "CL", "mid")),           # sec 2.5, "and per 1 CL"
        "year_net_mid": year_net_mid,                                             # item 2
        "both_halves_mid": {"first": first_half, "second": second_half},         # item 3
        "exit_reasons_mid": BK.exit_reason_counts(df_mid),                       # item 4
        "trail_started_share_mid": BK.trail_started_share(df_mid),              # item 4
        "median_hold_hours_mid": BK.median_hold_hours(df_mid),                  # item 4
        "weekly_context": weekly_net,                                            # inherited reporting infra (v0/v1), not separately numbered in v2's own sec 3
        "controls": {"c1_net_mid": net_c1, "c2_net_mid": net_c2, "c3": c3,
                     "c3_pool_not_date_restricted": bool(c3)},                   # item 6
        "neighbour_grid": neighbours,                                            # item 7, sec 5.3
        "account_view": {"MCL": account_mcl, "CL": account_cl},                 # item 8
        "sample_trades_mid": BK.sample_trades(v2, symbol, "mid"),               # item 9
        "seen_window": {                                                         # item 10, sec 6
            "n_trades": len(seen), "summary_mid": BK.summarize(BK.net_table(seen, symbol, "mid")),
            "sample_trades_mid": BK.sample_trades(seen, symbol, "mid", every=1),
            "note": "seen -- not evidence. 2025-09-23 onward, never scored (sec 0.6, sec 6).",
        },
        "originating_trade_count_check": {                                       # sec 5.2, sec 8
            "originating_trade_count": ORIGINATING_TRADE_COUNT,
            "trades_taken": trades_taken,
            "relative_difference": origin_pct_diff,
            "flag": origin_flag,
            "note": ("v1-X's own engine reported 286 trades for this same "
                    "recombination (sec 0.2). A large divergence here is "
                    "worth checking against G4's E5 recombination test "
                    "before trusting anything downstream (sec 5.2, sec 8)."),
        },
        "criteria": criteria,                                                    # sec 4
        "verdict": score_verdict,
    }

    return {
        "coverage": coverage,
        "q_h": q_h, "q_e": q_e,
        "scenarios": {SCENARIO: scenario_report},
        "holdout_status": VH.describe(daily_adj["date"].tolist()),
        "note": ("Training side only throughout (v2_holdout.split_dates("
                "spend=False), via training_trades()). The v2 holdout has "
                "not been spent by this run, and v2_report.py never spends "
                "it -- see module docstring."),
    }


def _jsonable(obj):
    """Same converter as v0's/v1's report.py."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _jsonable(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return [_jsonable(v) for v in obj.tolist()]
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    return str(obj)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="HTF-Ben v2 report: REGISTERED sec 3 + sec 4, scenario B, training side.")
    ap.add_argument("--archive", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None, help="write the full JSON report here too")
    ap.add_argument("--symbol", default="MCL", choices=("MCL", "CL"))
    ap.add_argument("--skip-neighbours", action="store_true",
                    help="skip the 6-cell neighbour grid entirely (fast dry run)")
    ap.add_argument("--skip-c3", action="store_true",
                    help="skip C3 (random-entry control) entirely")
    ap.add_argument("--c3-draws", type=int, default=V2C.C3_DRAWS)
    ap.add_argument("--seed-prefix", default="")
    a = ap.parse_args(argv)

    from common.tsmom_fetch import default_archive
    archive = a.archive or default_archive()

    report = run(archive, symbol=a.symbol, run_neighbours=not a.skip_neighbours,
                run_c3=not a.skip_c3, n_draws=a.c3_draws, seed_prefix=a.seed_prefix)

    cov = report["coverage"]["bars_per_year"]
    print(f"HTF-Ben v2 -- sec 3 report, sec 4 scoring (training side, "
          f"{a.symbol}, mid friction headline, scenario B only)\n")
    print(f"q_h={report['q_h']:.6f}  q_e={report['q_e']:.6f}  (inherited from v1 Amendment C)")
    print(f"coverage: {cov['n_total']} bars, {cov['first']} .. {cov['last']}, "
          f"{len(report['coverage']['roll_sessions'])} roll sessions, "
          f"{len(report['coverage']['gaps_over_3h'])} gaps > 3h\n")

    r = report["scenarios"]["B"]
    s = r["summary"]["mid"]
    print("-- B [SCORED] --")
    print(f"  trades(training)={s.trades}  net(mid, 1 {a.symbol})=${s.net:,.2f}  "
          f"wins={s.wins} losses={s.losses}  worst_loss_streak={s.worst_loss_streak}")
    occ = r["originating_trade_count_check"]
    flag_str = " *** FLAG ***" if occ["flag"] else ""
    print(f"  trades vs v1-X's originating 286: {occ['trades_taken']} "
          f"({occ['relative_difference']:.1%} difference){flag_str}")
    for c in r["criteria"]:
        status = "PASS" if c.passed else ("n/a " if c.passed is None else "FAIL")
        print(f"    [{status}] {c.n}. {c.label} -- {c.detail}")
    v = r["verdict"]
    print(f"    VERDICT: {'ALL 9 PASS' if v['all_nine_pass'] else 'NOT ALL PASS'}"
          f"{'  (CLOSED ON CRITERION 5)' if v['closed_on_criterion_5'] else ''}")
    print()

    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(_jsonable(report), indent=2), encoding="utf-8")
        print(f"full report: {a.out}")

    hard_fail = any(c.passed is False for c in report["scenarios"]["B"]["criteria"])
    return 1 if hard_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
