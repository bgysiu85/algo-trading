#!/usr/bin/env python3
"""HTF-Ben report -- W15-0004 step 7, checkpoint 11 (the last one).
REGISTERED_htf_ben_v0.md sec 3 (every item) and sec 4 (all nine criteria),
for B, A-2H, A-1H, A-4H side by side, training side only. Wires together
every module step 7 built: preflight (G2, via runner/controls), runner
(v0/C1), controls (C2/C3), book (aggregation + scoring), neighbours (sec 3
item 8), account (sec 3 item 9), weekly (sec 3 item 6), readback.coverage
(sec 3 item 11).

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.htf.report --out claude\\htf_ben_v0_report.json

THIS IS THE "STEP-7 BACKTEST RUNNER" holdout.py's own module docstring
names ("THE ONE IMPLEMENTATION the step-7 backtest runner must call").
Every scenario's trades are cut to the training side by calling
training_trades() below, which calls holdout.split_dates(dates,
spend=False) -- never by re-deriving 2010-06-06..2021-12-31 locally a
second time. This module NEVER calls split_dates(spend=True): spending the
holdout is Ben's own, separate, deliberate decision (its own command, run
by hand when he says so), not a side effect of running a report.

SCOPE OF "PER 1 MCL AND PER 1 CL" (sec 2.5)
---------------------------------------------
Every sec.3/sec.4 figure is computed at 1 MCL (the headline; sec 7: "per-
MCL at mid friction is the headline", and sec 4's scoring is explicitly "1
MCL"). A single CL-denominated summary (mid friction, whole training book)
is reported alongside for sec 2.5's "per 1 CL" -- not mirrored across
every year/half/friction level the way MCL is, since none of that is
scored and sec 7 explicitly warns against quoting CL as the result.
Account view (sec 3 item 9) is the one place CL gets its own full row
(n=1), as that item names explicitly.

KNOWN SCOPE NOTE -- C3's OWN DRAW POOL IS NOT DATE-RESTRICTED
-----------------------------------------------------------------
v0's own compared net (criterion 6) is training-only throughout (via
training_trades() below). controls.run_c3 has no parameter to restrict its
1,000 draws' entry pool to the training window, and adding one is judged
out of scope for this checkpoint (it would mean re-opening and re-testing
an already-committed, already-tested module for a refinement, not a
correctness bug: C3's sample being a broader pool than v0's own compared
net does not feed any holdout information INTO v0's own number, which
stays training-only). Flagged here, and in the report's own
"c3_pool_not_date_restricted" note, as a follow-up rather than silently
glossed over.

COST: the neighbour grid (sec 3 item 8) re-runs v0 18 times PER SCENARIO
it is asked for, and C3 (sec 3 item 7) draws 1,000 hypothetical portfolios
PER SCENARIO -- both correct per REGISTERED, both slow on 14+ years of
hourly bars, and neither is the only source of repeated work: run_v0/
run_c1/run_c2/run_c3/run_grid each independently rebuild the 1H/2H/4H
grids and their EMA/MACD series from scratch (every one of those functions
was built, checkpoint by checkpoint, to take a plain df_1h and do
everything itself -- see e.g. runner.py's own module docstring). This
module does not fight that convention; use --skip-neighbours / --skip-c3 /
--c3-draws to cut cost for a dry run. The committed JSON report from a
real run should use the registered defaults (all four scenarios, C3_DRAWS,
neighbours on B and A-2H).
"""
from __future__ import annotations

import argparse
import dataclasses
import json
from pathlib import Path

import pandas as pd

from strategy.htf import account as A
from strategy.htf import bars as B
from strategy.htf import book as BK
from strategy.htf import controls as CT
from strategy.htf import holdout as H
from strategy.htf import neighbours as NB
from strategy.htf import preflight as P
from strategy.htf import readback as RB
from strategy.htf import runner as R
from strategy.htf import weekly as W

SCORED_SCENARIOS = ("B", "A-2H")
ALL_SCENARIOS = P.ALL_SCENARIOS   # ("B", "A-2H", "A-1H", "A-4H")


def training_trades(trades: list) -> list:
    """Cuts a runner.Trade list to the training side, via
    holdout.split_dates(spend=False) -- THE one implementation (see module
    docstring), never a locally re-derived window. Each trade's own
    `session` (the ENTRY session, a date string) is what is checked; a
    trade whose entry falls in the training window is kept even if its
    exit (e.g. a multi-day scenario-B hold) spills past the lock date --
    the trade is a training-side trade because it was TAKEN there, exactly
    as G2/the runner's own training-window slicing already treats it
    (preflight.summarize keys off each entry's own session, not its
    eventual exit). Empty input returns empty."""
    if not trades:
        return []
    sessions = [str(t.session) for t in trades]
    keep_dates, _, _ = H.split_dates(sessions, spend=False)
    keep = set(keep_dates)
    return [t for t in trades if str(t.session) in keep]


def run_scenario(df_1h: pd.DataFrame, daily_adj: pd.DataFrame, *, scenario: str,
                 symbol: str = "MCL", run_neighbours: bool = True,
                 run_c3: bool = True, n_draws: int = CT.C3_DRAWS,
                 seed_prefix: str = "") -> dict:
    """Every sec.3 item and sec.4 criterion for ONE scenario, training side
    only (see training_trades). `daily_adj` is passed in, not recomputed,
    so weekly context and the B-only overnight-margin session calendar
    share one build across scenarios; run_v0/run_c1/run_c2/run_c3/run_grid
    still each rebuild their own grids internally (module docstring,
    COST)."""
    v0_all, v0_counts = R.run_v0(df_1h, scenario=scenario)
    c1_all, c1_counts = R.run_c1(df_1h, scenario=scenario)
    c2_all, c2_counts = CT.run_c2(df_1h, scenario=scenario)
    v0tl_all, v0tl_counts = R.run_v0_tl(df_1h, scenario=scenario)

    v0 = training_trades(v0_all)
    c1 = training_trades(c1_all)
    c2 = training_trades(c2_all)
    v0tl = training_trades(v0tl_all)

    df_low = BK.net_table(v0, symbol, "low")
    df_mid = BK.net_table(v0, symbol, "mid")
    df_high = BK.net_table(v0, symbol, "high")
    year_net_mid = BK.year_table(df_mid)
    first_half, second_half = BK.split_halves(df_mid)

    net_c1 = float(BK.net_table(c1, symbol, "mid")["net"].sum()) if c1 else None
    net_c2 = float(BK.net_table(c2, symbol, "mid")["net"].sum()) if c2 else None

    c3 = None
    if run_c3 and v0:
        c3 = CT.run_c3(df_1h, scenario=scenario, v0_trades=v0, symbol=symbol,
                       level="mid", n_draws=n_draws, seed_prefix=seed_prefix)
    c3_p95 = c3["p95"] if c3 else None

    neighbours = None
    if run_neighbours:
        neighbours = NB.run_grid(df_1h, scenario=scenario, symbol=symbol, level="mid",
                                 train_start=P.TRAIN_START, train_end=P.TRAIN_END)
    n_pos = neighbours["n_positive"] if neighbours else None
    n_tot = neighbours["n_total"] if neighbours else None

    criteria = BK.score(df_mid=df_mid, df_high=df_high, year_net_mid=year_net_mid,
                        net_c1=net_c1, net_c2=net_c2, c3_p95=c3_p95,
                        neighbour_positive=n_pos, neighbour_total=n_tot)

    alignment = W.trade_alignment(v0, daily_adj)
    weekly_net = W.net_by_alignment(alignment, symbol, "mid")

    session_calendar = sorted(daily_adj["date"].tolist()) if scenario == "B" else None
    account_mcl = A.account_view(v0, "MCL", "mid", session_calendar=session_calendar)
    account_cl = A.account_view(v0, "CL", "mid", session_calendar=session_calendar)

    v0tl_summary_mid = BK.summarize(BK.net_table(v0tl, symbol, "mid")) if v0tl else None

    return {
        "scenario": scenario, "symbol": symbol,
        "counts_full_history": {"v0": v0_counts, "c1": c1_counts, "c2": c2_counts,
                                "v0-TL": v0tl_counts},
        "trades_training": {"v0": len(v0), "c1": len(c1), "c2": len(c2), "v0-TL": len(v0tl)},
        "v0_tl": {"summary_mid": v0tl_summary_mid,                                       # W15-0007
                 "sample_trades_mid": BK.sample_trades(v0tl, symbol, "mid") if v0tl else [],
                 "note": ("reported beside v0, never ranked and never scored "
                          "against sec 4's criteria -- REGISTERED sec 2.6, sec 3")},
        "summary": {"low": BK.summarize(df_low), "mid": BK.summarize(df_mid),
                   "high": BK.summarize(df_high)},                                 # item 1 (MCL)
        "summary_cl_mid": BK.summarize(BK.net_table(v0, "CL", "mid")),             # sec 2.5, "and per 1 CL"
        "year_net_mid": year_net_mid,                                              # item 2
        "both_halves_mid": {"first": first_half, "second": second_half},           # item 3
        "exit_reasons_mid": BK.exit_reason_counts(df_mid),                         # item 4
        "trail_started_share_mid": BK.trail_started_share(df_mid),                 # item 4
        "median_hold_hours_mid": BK.median_hold_hours(df_mid),                     # item 5
        "weekly_context": weekly_net,                                              # item 6
        "controls": {"c1_net_mid": net_c1, "c2_net_mid": net_c2, "c3": c3,
                     "c3_pool_not_date_restricted": bool(c3)},                     # item 7
        "neighbour_grid": neighbours,                                              # item 8
        "account_view": {"MCL": account_mcl, "CL": account_cl},                    # item 9
        "sample_trades_mid": BK.sample_trades(v0, symbol, "mid"),                  # item 10
        "criteria": criteria,                                                      # sec 4
    }


def run(archive_1h, *, symbol: str = "MCL", scenarios=ALL_SCENARIOS,
       neighbour_scenarios=SCORED_SCENARIOS, run_c3: bool = True,
       n_draws: int = CT.C3_DRAWS, seed_prefix: str = "") -> dict:
    """The whole sec.3/sec.4 emission, every scenario in `scenarios`
    (default all four, side by side, per sec 3's own header). Sec 3 item
    11 (coverage) is archive-wide, computed once, not per scenario.

    `neighbour_scenarios` (default: the two SCORED ones, B/A-2H) controls
    which scenarios pay the neighbour grid's 18x cost -- sec 3 item 8 says
    "18 cells per scenario" without saying every reported neighbour chart
    must carry it too, and A-1H/A-4H's own criterion 8 never gates the
    holdout spend either way (sec 4: "cannot spend the holdout"); pass
    neighbour_scenarios=scenarios to run it everywhere REGISTERED could be
    read as requiring it."""
    df_1h = B.load_1h(archive_1h)
    _, daily_adj = P.prepare_grids(df_1h)
    coverage = RB.coverage(df_1h)

    reports = {}
    for scenario in scenarios:
        reports[scenario] = run_scenario(
            df_1h, daily_adj, scenario=scenario, symbol=symbol,
            run_neighbours=(scenario in neighbour_scenarios),
            run_c3=run_c3, n_draws=n_draws, seed_prefix=seed_prefix)

    return {
        "coverage": coverage,                                                     # item 11
        "scenarios": reports,
        "holdout_status": H.describe(daily_adj["date"].tolist()),
        "note": ("Training side only throughout (holdout.split_dates("
                "spend=False), via training_trades()). The HTF-Ben holdout "
                "has not been spent by this run, and report.py never spends "
                "it -- see module docstring."),
    }


def _jsonable(obj):
    """Deep-converts a run()/run_scenario() result into something
    json.dumps can write without a default= fallback mangling dataclasses
    (book.Summary, book.Criterion) into an opaque repr string."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _jsonable(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    return str(obj)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="HTF-Ben report: REGISTERED sec 3 + sec 4, training side.")
    ap.add_argument("--archive", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None, help="write the full JSON report here too")
    ap.add_argument("--symbol", default="MCL", choices=("MCL", "CL"))
    ap.add_argument("--scenarios", nargs="+", default=list(ALL_SCENARIOS),
                    choices=list(ALL_SCENARIOS))
    ap.add_argument("--skip-neighbours", action="store_true",
                    help="skip the sec 3 item 8 neighbour grid entirely (fast dry run)")
    ap.add_argument("--all-neighbours", action="store_true",
                    help="run the neighbour grid on every --scenarios given, not just B/A-2H")
    ap.add_argument("--skip-c3", action="store_true",
                    help="skip C3 (random-entry control, sec 3 item 7) entirely")
    ap.add_argument("--c3-draws", type=int, default=CT.C3_DRAWS)
    ap.add_argument("--seed-prefix", default="")
    a = ap.parse_args(argv)

    from common.tsmom_fetch import default_archive
    archive = a.archive or default_archive()

    if a.skip_neighbours:
        neighbour_scenarios: tuple = ()
    elif a.all_neighbours:
        neighbour_scenarios = tuple(a.scenarios)
    else:
        neighbour_scenarios = tuple(s for s in a.scenarios if s in SCORED_SCENARIOS)

    report = run(archive, symbol=a.symbol, scenarios=tuple(a.scenarios),
                neighbour_scenarios=neighbour_scenarios, run_c3=not a.skip_c3,
                n_draws=a.c3_draws, seed_prefix=a.seed_prefix)

    cov = report["coverage"]["bars_per_year"]
    print(f"HTF-Ben v0 -- sec 3 report, sec 4 scoring (training side, "
          f"{a.symbol}, mid friction headline)\n")
    print(f"coverage: {cov['n_total']} bars, {cov['first']} .. {cov['last']}, "
          f"{len(report['coverage']['roll_sessions'])} roll sessions, "
          f"{len(report['coverage']['gaps_over_3h'])} gaps > 3h\n")

    for scenario, r in report["scenarios"].items():
        s = r["summary"]["mid"]
        scored = " [SCORED]" if scenario in SCORED_SCENARIOS else " [reported neighbour]"
        print(f"-- {scenario}{scored} --")
        print(f"  trades(training)={s.trades}  net(mid, 1 {a.symbol})=${s.net:,.2f}  "
              f"wins={s.wins} losses={s.losses}  worst_loss_streak={s.worst_loss_streak}")
        for c in r["criteria"]:
            status = "PASS" if c.passed else ("n/a " if c.passed is None else "FAIL")
            print(f"    [{status}] {c.n}. {c.label} -- {c.detail}")
        print()

    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(_jsonable(report), indent=2), encoding="utf-8")
        print(f"full report: {a.out}")

    hard_fail = any(
        c.passed is False
        for scenario in SCORED_SCENARIOS if scenario in report["scenarios"]
        for c in report["scenarios"][scenario]["criteria"]
    )
    return 1 if hard_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
