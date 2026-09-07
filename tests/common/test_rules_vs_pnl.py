#!/usr/bin/env python3
"""Comparing a losing sample against itself, without loading the scales.

The traded set is a $114,982.92 loss. Every way of quietly moving P/L from one
side of this comparison to the other produces a conclusion that looks earned
and is not, so the tests are mostly about that.
"""
from __future__ import annotations

import pandas as pd
import pytest

from common import rules_vs_pnl as R
from common.screen import Config


def feats(rows):
    """rows: (symbol, date, prior_close, prior_avg_dollar_vol, rvol, range_pct)"""
    return pd.DataFrame(rows, columns=["symbol", "date", "prior_close",
                                       "prior_avg_dollar_vol", "rvol",
                                       "range_pct"])


class Day:
    def __init__(self, pnl, gross=None, comm=0.0, execs=1, pos=100):
        self.net_pnl = pnl
        self.gross_pnl = gross if gross is not None else pnl
        self.commission = comm
        self.executions = execs
        self.max_position = pos


# --- conformance ------------------------------------------------------------

def test_the_rules_are_evaluated_independently():
    """A pair can fail several. Knowing WHICH is the whole point -- a rule
    whose rejects were profitable is costing money, and a sequential
    evaluation would attribute every such reject to whichever rule ran first."""
    cfg = Config()
    row = {"prior_close": 100.0,        # fails the sanity band
           "prior_avg_dollar_vol": 1.0,  # fails the floor
           "rvol": 99.0, "range_pct": 99.0}
    f = R.rule_flags(row, cfg)
    assert f["prior-close sanity"] is False
    assert f["liquidity floor"] is False
    assert f["RVOL"] is True and f["day range"] is True


def test_conforming_means_every_rule_not_the_capped_list():
    """The 60-a-day cap is a budget for buying minute bars, not a trading rule.
    A trade the cap excluded followed the rules perfectly well, and marking it
    non-conforming would move its P/L across the comparison for a reason that
    has nothing to do with the rules."""
    cfg = Config()
    f = feats([("AAA", "2025-06-04", 5.0, 1e6, 50.0, 50.0)])
    rows, _ = R.join({("AAA", "2025-06-04"): Day(100.0)}, f, cfg)
    assert rows[0]["conforms"] is True


# --- the unmatched must not become non-conforming ---------------------------

def test_a_symbol_day_with_no_daily_bar_is_excluded_not_rejected():
    """'The rules said no' and 'we could not ask' are different claims.
    Folding the second into the first loads every gap in the archive onto the
    discretion side of the comparison."""
    cfg = Config()
    f = feats([("AAA", "2025-06-04", 5.0, 1e6, 50.0, 50.0)])
    days = {("AAA", "2025-06-04"): Day(100.0),
            ("ZZZ", "2023-01-05"): Day(-500.0)}
    rows, excluded = R.join(days, f, cfg)
    assert len(rows) == 1
    assert [(e["symbol"], e["reason"]) for e in excluded] == [("ZZZ", "ABSENT")]


def test_a_name_too_new_to_score_is_its_own_category():
    """THE finding this split exists for. All seven exclusions on the real data
    were PRESENT in the dataset and traded on their first or second session --
    RVOL needs a prior average and one does not exist yet. Reporting that as
    'no daily bar, probably before the start date' was simply wrong, and it hid
    a structural blind spot worth $14,151 of losses."""
    cfg = Config()
    f = feats([("NEW", "2026-07-13", 5.0, float("nan"), float("nan"), 50.0)])
    rows, excluded = R.join({("NEW", "2026-07-13"): Day(-13_241.28)}, f, cfg)
    assert rows == []
    assert excluded[0]["reason"] == "TOO NEW"
    assert excluded[0]["prior"] == 0


def test_the_two_exclusion_reasons_are_reported_separately():
    cfg = Config()
    f = feats([("NEW", "2026-07-13", 5.0, float("nan"), float("nan"), 50.0),
               ("AAA", "2025-06-04", 5.0, 1e6, 50.0, 50.0)])
    rows, excluded = R.join({("NEW", "2026-07-13"): Day(-9_999.0),
                             ("AAA", "2025-06-04"): Day(100.0),
                             ("GONE", "2023-01-05"): Day(-42.0)}, f, cfg)
    out = R.render(rows, excluded, cfg, "EQUS.SUMMARY")
    assert "TOO NEW" in out and "ABSENT" in out
    assert "-9,999.00" in out
    assert "structural blind" in out


# --- the summary ------------------------------------------------------------

def test_drop_top_removes_the_largest_winners():
    """A split that survives only because of two names is a fact about those
    names. Concentration has already killed three strategies in this project."""
    assert R.drop_top([100.0, 50.0, -10.0], 1) == pytest.approx(40.0)
    assert R.drop_top([100.0, 50.0, -10.0], 2) == pytest.approx(-10.0)


def test_a_thin_side_refuses_to_compare_means():
    """With a handful on one side a difference in means is noise, and the
    paragraph that reports it reads exactly as confidently as a real one."""
    cfg = Config()
    rows = ([{"symbol": f"S{i}", "date": "2025-06-04", "net_pnl": 10.0,
              "conforms": True, **{f"pass_{r}": True for r in R.RULES}}
             for i in range(40)]
            + [{"symbol": "T", "date": "2025-06-04", "net_pnl": -500.0,
                "conforms": False, "pass_RVOL": False,
                **{f"pass_{r}": True for r in R.RULES if r != "RVOL"}}])
    out = R.render(rows, [], cfg, "EQUS.SUMMARY")
    assert "TOO FEW ON ONE SIDE" in out


def make_rows(conf_pnl, non_pnl):
    rows = []
    for i, p in enumerate(conf_pnl):
        rows.append({"symbol": f"C{i}", "date": "2025-06-04", "net_pnl": p,
                     "conforms": True,
                     **{f"pass_{r}": True for r in R.RULES}})
    for i, p in enumerate(non_pnl):
        rows.append({"symbol": f"N{i}", "date": "2025-06-04", "net_pnl": p,
                     "conforms": False, "pass_RVOL": False,
                     **{f"pass_{r}": True for r in R.RULES if r != "RVOL"}})
    return rows


def test_rules_being_the_better_half_is_stated_plainly():
    out = R.render(make_rows([10.0] * 40, [-10.0] * 40), [], Config(), "X")
    assert "THE RULES LOOK LIKE THE BETTER HALF" in out


def test_rules_being_the_worse_half_is_stated_just_as_plainly():
    """The uncomfortable answer has to be as easy to read as the comfortable
    one, or the report is an argument rather than a measurement."""
    out = R.render(make_rows([-10.0] * 40, [10.0] * 40), [], Config(), "X")
    assert "THE RULES LOOK LIKE THE WORSE HALF" in out


def test_a_verdict_that_one_trade_reverses_is_refused():
    """THE defect this report shipped with. On the real data the conforming
    half led by $11,828 on the total and TRAILED by $26,140 after removing a
    single symbol-day -- and the verdict was computed from the total alone,
    while the 'check the drop-top rows' caution was attached only to the
    UNFAVOURABLE branch. The comfortable answer escaped the scrutiny."""
    conf = [40_000.0] + [-300.0] * 60      # one huge winner carries the half
    non = [-200.0] * 60
    out = R.render(make_rows(conf, non), [], Config(), "X")
    assert "THE RANKING REVERSES ON ONE TRADE" in out
    assert "THE RULES LOOK LIKE THE BETTER HALF" not in out


def test_a_stable_lead_still_gets_its_verdict():
    """The guard must not refuse every conclusion -- a lead that survives
    dropping the top three is a real one."""
    out = R.render(make_rows([10.0] * 60, [-10.0] * 60), [], Config(), "X")
    assert "survives dropping" in out


def test_both_halves_losing_is_said_out_loud():
    """'Better half' is a ranking. Without this line a reader takes a verdict
    about which side won as a case for the rules being profitable."""
    out = R.render(make_rows([-10.0] * 40, [-50.0] * 40), [], Config(), "X")
    assert "BOTH halves lost money" in out


def test_the_report_says_recall_is_not_the_objective():
    """Guarding the framing, not the arithmetic: this sample is a loss, and a
    screen tuned to reproduce all of it reproduces the loss."""
    out = R.render(make_rows([10.0] * 40, [-10.0] * 40), [], Config(), "X")
    assert "Recall is NOT the objective" in out


def test_each_rules_rejected_pnl_is_reported():
    """A rule whose rejects were profitable is costing money. That is the
    actionable line in the whole report."""
    out = R.render(make_rows([10.0] * 40, [250.0] * 40), [], Config(), "X")
    assert "WHICH RULE REJECTS THE MONEY" in out
    assert "10,000.00" in out          # 40 x 250 rejected by RVOL


def test_an_empty_join_says_so_rather_than_dividing_by_zero():
    assert "NO TRADED SYMBOL-DAYS MATCHED" in R.render([], [], Config(), "X")
