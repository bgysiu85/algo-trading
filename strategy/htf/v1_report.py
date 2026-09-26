#!/usr/bin/env python3
"""HTF-Ben v1 report -- W15-0011, REGISTERED_htf_ben_v1.md sec 3 (every
item) and sec 4 (all nine criteria), for B (scored) and A-2H (reported,
never scored), training side. Wires together every v1 module built this
item: v1_preflight (G2, percentiles), v1_runner (v1 + the sec 2.4
ablations), v1_controls (C1/C2/C3), v1_grid (the 24-cell neighbour grid),
v1_holdout (training-side cut -- NEVER spend=True here, see below), plus
v0's own generic aggregation modules (book/account/weekly/readback), which
take a plain trade list and know nothing about which study produced it.

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.htf.v1_report --out claude\\w15_0011_v1_report.json

THIS IS v1's OWN "STEP-7 BACKTEST RUNNER" v1_holdout.py's own module
docstring names ("THE ONE IMPLEMENTATION the step-7 backtest runner must
call"). Every scenario's trades are cut to the training side by calling
training_trades() below, which calls v1_holdout.split_dates(dates,
spend=False) -- never a locally re-derived window, and never v0's own
holdout.py (a different ledger, a two-day-different boundary phrasing that
happens to name the same trading days -- see v1_holdout.py's own module
docstring). This module NEVER calls split_dates(spend=True): spending the
v1 holdout is Ben's own, separate, deliberate decision, made only once
training-side scoring is complete (sec 6, sec 7's multiplicity discipline),
not a side effect of running a report.

WHY ONLY B GETS SCORED, AND WHY THE NEIGHBOUR GRID ONLY RUNS ON B
------------------------------------------------------------------
Sec 4's header is explicit: "v1, scenario B, 1 MCL, mid friction, training
side." A-2H is "reported beside it, not scored for the holdout" (sec 2.3)
-- and sec 4 is the training-side bar the holdout spend depends on, so
A-2H is not run through v1_score() at all (its numbers are emitted, sec 3
items 1-6/9-11 plus controls, exactly like v0-TL was reported in v0's own
report.py, never given a criteria list). The 24-cell neighbour grid is
tied one-for-one to criterion 8, which only exists for B, so it is only
ever run for B; running it for A-2H too would be sec-3-compliant reporting
but would not change anything sec 4 reads, at 24x the cost.

WHY C3'S POOL IS NOT DATE-RESTRICTED (same known scope note as v0's own
report.py)
-------------------------------------------------------------------------
v1's own compared net (criterion 6) is training-only throughout (via
training_trades() below). v1_controls.run_c3 has no parameter to restrict
its 1,000 draws' entry pool to the training window -- C3's sample being a
broader pool than v1's own compared net does not feed any holdout
information INTO v1's own number, which stays training-only. Flagged here,
and in the report's own "c3_pool_not_date_restricted" note.

SEEN WINDOW (sec 3, sec 6): "Never scored; reported only." run() reports
v1's own trades whose entry session falls in the seen window (2025-09-23
onward), via v1_holdout.seen_dates -- clearly labelled, never fed into
v1_score(), and never used to compute any of the sec 4 criteria.

COST: same shape as v0's own report.py -- the neighbour grid re-runs v1 24
times (scenario B only, not per scenario, see above) and C3 draws 1,000
hypothetical portfolios; run_v1/run_c1/run_c2/run_c3/run_grid each
independently rebuild the 1H/2H/4H grids and their MACD/EMA series from
scratch (every v1 module's own convention, inherited from v0's). Use
--skip-neighbours/--skip-c3/--c3-draws to cut cost for a dry run; the
committed JSON report from a real run should use the registered defaults.
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
from strategy.htf import v1_controls as V1C
from strategy.htf import v1_grid as V1G
from strategy.htf import v1_holdout as VH
from strategy.htf import v1_preflight as V1P
from strategy.htf import v1_runner as V1R
from strategy.htf import weekly as W

SCORED_SCENARIOS = ("B",)                  # sec 4 header: "v1, scenario B"
REPORTED_SCENARIOS = ("B", "A-2H")         # sec 3 header: "for B and A-2H"
MIN_NEIGHBOUR_POSITIVE = 16                # sec 4 criterion 8: "16 of the 24"


def training_trades(trades: list) -> list:
    """Cuts a runner.Trade list to the training side, via v1_holdout's OWN
    split_dates(spend=False) -- never holdout.py's (v0's own ledger, sec 6:
    "closed unspent"). Each trade's own `session` (the entry session) is
    what is checked, same convention as v0's report.py's training_trades
    and as v1_preflight.summarize's own training slicing: a trade is a
    training-side trade because it was TAKEN there, even if a multi-day
    scenario-B hold's exit spills past the boundary. Empty input returns
    empty."""
    if not trades:
        return []
    sessions = [str(t.session) for t in trades]
    keep_dates, _, _ = VH.split_dates(sessions, spend=False)
    keep = set(keep_dates)
    return [t for t in trades if str(t.session) in keep]


def seen_trades(trades: list) -> list:
    """v1's own trades whose entry session falls in the seen window (sec
    6: 2025-09-23 onward) -- "never scored; reported only" (sec 3). Never
    passed to v1_score()."""
    if not trades:
        return []
    sessions = [str(t.session) for t in trades]
    keep = set(VH.seen_dates(sessions))
    return [t for t in trades if str(t.session) in keep]


def v1_score(*, df_mid: pd.DataFrame, df_high: pd.DataFrame, year_net_mid: dict,
             net_c1: float | None, net_c2: float | None, c3_p95: float | None,
             neighbour_positive: int | None = None, neighbour_total: int | None = None,
             min_trades: int = 150,
             min_neighbour_positive: int = MIN_NEIGHBOUR_POSITIVE) -> list[BK.Criterion]:
    """REGISTERED_htf_ben_v1.md sec 4's nine criteria. Reuses every one of
    book.py's generic helpers (split_halves, top_year_share,
    bootstrap_by_year) unchanged -- only the criterion-8 threshold (16 of
    v1's 24 cells, not v0's 12 of 18) and the v1-flavoured labels differ
    from book.score, which is why this is its own function rather than a
    call into book.score with a monkeypatched constant."""
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
    crit.append(BK.Criterion(5, "Beats C1 and C2 on net (failing this closes v1)",
                             (net_mid > net_c1 and net_mid > net_c2) if have_c1c2 else None,
                             f"v1 ${net_mid:,.2f} vs C1 ${net_c1:,.2f} vs C2 ${net_c2:,.2f}"
                             if have_c1c2 else "NOT SUPPLIED"))
    crit.append(BK.Criterion(6, "Beats the p95 of C3 on net",
                             (net_mid > c3_p95) if c3_p95 is not None else None,
                             f"v1 ${net_mid:,.2f} vs C3 p95 ${c3_p95:,.2f}"
                             if c3_p95 is not None else "NOT SUPPLIED"))
    crit.append(BK.Criterion(7, "Still net > $0 at high friction", net_high > 0, f"${net_high:,.2f}"))
    if neighbour_positive is not None and neighbour_total is not None:
        crit.append(BK.Criterion(
            8, f"At least {min_neighbour_positive} of {neighbour_total} neighbour cells net > $0",
            neighbour_positive >= min_neighbour_positive, f"{neighbour_positive}/{neighbour_total}"))
    else:
        crit.append(BK.Criterion(
            8, f"At least {min_neighbour_positive} of 24 neighbour cells net > $0",
            None, "NOT YET BUILT"))
    crit.append(BK.Criterion(9, f"At least {min_trades} trades on the training side",
                             n_trades >= min_trades, f"{n_trades} trades"))
    return crit


def verdict(criteria: list[BK.Criterion]) -> dict:
    """sec 4, verbatim: 'Failing criterion 5 closes v1 whatever else
    passes.' Reported separately from the plain all-pass check so a run
    that fails on, say, criterion 9 (too few trades, sec 4 item 9: 'NOT
    READ, not failed' when trades < 150) is never confused with the
    criterion-5 close-out, which is unconditional."""
    by_n = {c.n: c for c in criteria}
    c5 = by_n.get(5)
    closed_on_c5 = bool(c5 is not None and c5.passed is False)
    all_pass = all(c.passed is True for c in criteria)
    return {"all_nine_pass": all_pass, "closed_on_criterion_5": closed_on_c5,
           "failing": [c.n for c in criteria if c.passed is False],
           "not_evaluated": [c.n for c in criteria if c.passed is None]}


def run_scenario(df_1h: pd.DataFrame, daily_adj: pd.DataFrame, *, scenario: str,
                 q_h: float, q_e: float, symbol: str = "MCL",
                 run_neighbours: bool = True, run_c3: bool = True,
                 n_draws: int = V1C.C3_DRAWS, seed_prefix: str = "") -> dict:
    """Every sec.3 item for ONE scenario, training side only (see
    training_trades). Scoring (v1_score) is only attached when `scenario`
    is a SCORED_SCENARIOS member -- callers get numbers for A-2H either
    way, per sec 3, but no criteria list, per sec 4's own header."""
    v1_all, v1_counts = V1R.run_v1(df_1h, scenario=scenario, q_h=q_h, q_e=q_e)
    curl_all, curl_counts = V1R.run_v1(df_1h, scenario=scenario, q_h=q_h, q_e=q_e,
                                       curl_enabled=False)
    f1_all, f1_counts = V1R.run_v1(df_1h, scenario=scenario, q_h=q_h, q_e=q_e,
                                   f1_enabled=False)
    f2_all, f2_counts = V1R.run_v1(df_1h, scenario=scenario, q_h=q_h, q_e=q_e,
                                   f2_enabled=False)
    x_all, x_counts = V1R.run_v1_no_signal_exits(df_1h, scenario=scenario, q_h=q_h, q_e=q_e)
    c1_all, c1_counts = V1C.run_c1(df_1h, scenario=scenario, q_h=q_h, q_e=q_e)
    c2_all, c2_counts = V1C.run_c2(df_1h, scenario=scenario)

    v1 = training_trades(v1_all)
    curl = training_trades(curl_all)
    f1v = training_trades(f1_all)
    f2v = training_trades(f2_all)
    xv = training_trades(x_all)
    c1 = training_trades(c1_all)
    c2 = training_trades(c2_all)
    seen = seen_trades(v1_all)

    df_low = BK.net_table(v1, symbol, "low")
    df_mid = BK.net_table(v1, symbol, "mid")
    df_high = BK.net_table(v1, symbol, "high")
    year_net_mid = BK.year_table(df_mid)
    first_half, second_half = BK.split_halves(df_mid)

    net_c1 = float(BK.net_table(c1, symbol, "mid")["net"].sum()) if c1 else None
    net_c2 = float(BK.net_table(c2, symbol, "mid")["net"].sum()) if c2 else None

    c3 = None
    if run_c3 and v1:
        c3 = V1C.run_c3(df_1h, scenario=scenario, v1_trades=v1, symbol=symbol,
                        level="mid", n_draws=n_draws, seed_prefix=seed_prefix)
    c3_p95 = c3["p95"] if c3 else None

    neighbours = None
    if run_neighbours:
        neighbours = V1G.run_grid(df_1h, scenario=scenario, symbol=symbol, level="mid",
                                  train_start=P.TRAIN_START, train_end=P.TRAIN_END)
    n_pos = neighbours["n_net_positive"] if neighbours else None
    n_tot = neighbours["n_cells"] if neighbours else None

    criteria = None
    score_verdict = None
    if scenario in SCORED_SCENARIOS:
        criteria = v1_score(df_mid=df_mid, df_high=df_high, year_net_mid=year_net_mid,
                            net_c1=net_c1, net_c2=net_c2, c3_p95=c3_p95,
                            neighbour_positive=n_pos, neighbour_total=n_tot)
        score_verdict = verdict(criteria)

    alignment = W.trade_alignment(v1, daily_adj)
    weekly_net = W.net_by_alignment(alignment, symbol, "mid")

    session_calendar = sorted(daily_adj["date"].tolist()) if scenario == "B" else None
    account_mcl = A.account_view(v1, "MCL", "mid", session_calendar=session_calendar)
    account_cl = A.account_view(v1, "CL", "mid", session_calendar=session_calendar)

    def _ablation(trades, all_trades):
        return {"summary_mid": BK.summarize(BK.net_table(trades, symbol, "mid")) if trades else None,
               "trades_training": len(trades), "trades_full_history": len(all_trades)}

    return {
        "scenario": scenario, "symbol": symbol, "scored": scenario in SCORED_SCENARIOS,
        "q_h": q_h, "q_e": q_e,
        "counts_full_history": {"v1": v1_counts, "v1-curl": curl_counts, "v1-F1": f1_counts,
                                "v1-F2": f2_counts, "v1-X": x_counts, "c1": c1_counts,
                                "c2": c2_counts},
        "trades_training": {"v1": len(v1), "v1-curl": len(curl), "v1-F1": len(f1v),
                            "v1-F2": len(f2v), "v1-X": len(xv), "c1": len(c1), "c2": len(c2)},
        "ablations": {                                                            # sec 2.4
            "v1-curl": _ablation(curl, curl_all), "v1-F1": _ablation(f1v, f1_all),
            "v1-F2": _ablation(f2v, f2_all), "v1-X": _ablation(xv, x_all),
            "note": ("reported beside v1, never ranked and never scored against "
                    "sec 4's criteria -- REGISTERED sec 2.4, sec 3"),
        },
        "summary": {"low": BK.summarize(df_low), "mid": BK.summarize(df_mid),
                   "high": BK.summarize(df_high)},                                # item 1 (MCL)
        "summary_cl_mid": BK.summarize(BK.net_table(v1, "CL", "mid")),            # sec 2.5, "and per 1 CL"
        "year_net_mid": year_net_mid,                                             # item 2
        "both_halves_mid": {"first": first_half, "second": second_half},         # item 3
        "exit_reasons_mid": BK.exit_reason_counts(df_mid),                       # item 4
        "trail_started_share_mid": BK.trail_started_share(df_mid),              # item 4
        "median_hold_hours_mid": BK.median_hold_hours(df_mid),                  # item 5
        "weekly_context": weekly_net,                                            # item 6
        "controls": {"c1_net_mid": net_c1, "c2_net_mid": net_c2, "c3": c3,
                     "c3_pool_not_date_restricted": bool(c3)},                   # sec 3 controls
        "neighbour_grid": neighbours,                                            # sec 3 grid
        "account_view": {"MCL": account_mcl, "CL": account_cl},                 # item 9
        "sample_trades_mid": BK.sample_trades(v1, symbol, "mid"),               # item 10
        "seen_window": {                                                         # sec 3, sec 6
            "n_trades": len(seen), "summary_mid": BK.summarize(BK.net_table(seen, symbol, "mid")),
            "sample_trades_mid": BK.sample_trades(seen, symbol, "mid", every=1),
            "note": "seen -- not evidence. 2025-09-23 onward, never scored (sec 3, sec 6).",
        },
        "criteria": criteria,                                                    # sec 4 (B only)
        "verdict": score_verdict,
    }


def run(archive_1h, *, symbol: str = "MCL", scenarios=REPORTED_SCENARIOS,
       neighbour_scenarios=SCORED_SCENARIOS, run_c3: bool = True,
       n_draws: int = V1C.C3_DRAWS, seed_prefix: str = "") -> dict:
    """The whole sec.3/sec.4 emission, B and A-2H side by side (sec 3's own
    header). q_h/q_e are computed once here (v1_preflight.compute_percentiles,
    training-side 4H bars, the registered 25th percentile/N=9 -- see
    v1_preflight.run's identical call) and reused across both scenarios, so
    a single report run cannot silently score B against one percentile pair
    and A-2H against another."""
    df_1h = B.load_1h(archive_1h)
    grids, daily_adj = P.prepare_grids(df_1h)
    coverage = RB.coverage(df_1h)
    q_h, q_e, _, _, _ = V1P.compute_percentiles(grids["4H"])

    reports = {}
    for scenario in scenarios:
        reports[scenario] = run_scenario(
            df_1h, daily_adj, scenario=scenario, q_h=q_h, q_e=q_e, symbol=symbol,
            run_neighbours=(scenario in neighbour_scenarios),
            run_c3=run_c3, n_draws=n_draws, seed_prefix=seed_prefix)

    return {
        "coverage": coverage,                                                    # item 11
        "q_h": q_h, "q_e": q_e,
        "scenarios": reports,
        "holdout_status": VH.describe(daily_adj["date"].tolist()),
        "note": ("Training side only throughout (v1_holdout.split_dates("
                "spend=False), via training_trades()). The v1 holdout has "
                "not been spent by this run, and v1_report.py never spends "
                "it -- see module docstring."),
    }


def _jsonable(obj):
    """Same converter as v0's report.py -- dataclasses (book.Summary,
    book.Criterion) need dataclasses.asdict, not json's default=str
    fallback, or they serialize as an opaque repr string."""
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
        description="HTF-Ben v1 report: REGISTERED sec 3 + sec 4, training side.")
    ap.add_argument("--archive", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None, help="write the full JSON report here too")
    ap.add_argument("--symbol", default="MCL", choices=("MCL", "CL"))
    ap.add_argument("--scenarios", nargs="+", default=list(REPORTED_SCENARIOS),
                    choices=list(REPORTED_SCENARIOS))
    ap.add_argument("--skip-neighbours", action="store_true",
                    help="skip the 24-cell neighbour grid entirely (fast dry run)")
    ap.add_argument("--skip-c3", action="store_true",
                    help="skip C3 (random-entry control) entirely")
    ap.add_argument("--c3-draws", type=int, default=V1C.C3_DRAWS)
    ap.add_argument("--seed-prefix", default="")
    a = ap.parse_args(argv)

    from common.tsmom_fetch import default_archive
    archive = a.archive or default_archive()

    neighbour_scenarios = () if a.skip_neighbours else tuple(
        s for s in a.scenarios if s in SCORED_SCENARIOS)

    report = run(archive, symbol=a.symbol, scenarios=tuple(a.scenarios),
                neighbour_scenarios=neighbour_scenarios, run_c3=not a.skip_c3,
                n_draws=a.c3_draws, seed_prefix=a.seed_prefix)

    cov = report["coverage"]["bars_per_year"]
    print(f"HTF-Ben v1 -- sec 3 report, sec 4 scoring (training side, "
          f"{a.symbol}, mid friction headline)\n")
    print(f"q_h={report['q_h']:.4f}  q_e={report['q_e']:.4f}")
    print(f"coverage: {cov['n_total']} bars, {cov['first']} .. {cov['last']}, "
          f"{len(report['coverage']['roll_sessions'])} roll sessions, "
          f"{len(report['coverage']['gaps_over_3h'])} gaps > 3h\n")

    for scenario, r in report["scenarios"].items():
        s = r["summary"]["mid"]
        scored = " [SCORED]" if r["scored"] else " [reported, not scored]"
        print(f"-- {scenario}{scored} --")
        print(f"  trades(training)={s.trades}  net(mid, 1 {a.symbol})=${s.net:,.2f}  "
              f"wins={s.wins} losses={s.losses}  worst_loss_streak={s.worst_loss_streak}")
        if r["criteria"]:
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

    hard_fail = any(
        c.passed is False
        for scenario in SCORED_SCENARIOS if scenario in report["scenarios"]
        for c in (report["scenarios"][scenario]["criteria"] or [])
    )
    return 1 if hard_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
