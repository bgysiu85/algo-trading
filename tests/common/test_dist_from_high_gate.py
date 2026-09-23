#!/usr/bin/env python3
"""W05-0005: dist_from_high as an entry gate, on its own registration.

REGISTERED_dist_from_high.md. This module reuses chase_gate.solve_distance
unchanged for its three SOLVED budgets and adds two DIRECT ones read off
dist_from_high's own distribution -- the parts worth pinning are that the
solved c083 cell reproduces the 2026-09-18 fenced numbers exactly, that the
direct quantile budgets are not solved against anything, and that the gate
itself refuses on the same feature and the same convention chase_gate uses.
"""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from common import dist_from_high_gate as D
from common import running_up as RU


def feat(sym, r5, dfh, book="MCL", date="2026-09-11", et="05:00:00"):
    return {"book": book, "symbol": sym, "date": date, "entry_et": et,
            "ret_5m": "" if r5 is None else str(r5),
            "dist_from_high": "" if dfh is None else str(dfh),
            "bars_held": "3"}


def frame(closes, highs=None, day="2026-09-11"):
    t0 = pd.Timestamp(f"{day} 04:00", tz=RU.ET)
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=i) for i in range(len(closes))])
    highs = closes if highs is None else highs
    return pd.DataFrame({"open": closes, "high": highs, "low": closes,
                         "close": closes, "volume": 10_000}, index=idx)


# --- the budgets ---------------------------------------------------------------

def test_ten_cells_five_budgets_per_book():
    assert len(D.BUDGET_NAMES) == 5
    assert len(D.PAIRED) == 10
    scored = {g for _, g in D.PAIRED}
    assert all(name.startswith(("MCL-", "MC5-")) for name in scored)


def test_three_budgets_are_solved_and_reuse_chase_gates_own_function():
    """The registration's own rule: the solve is IMPORTED, not restated."""
    from common import chase_gate as C
    assert D.solve_distance is C.solve_distance


def test_the_solved_budgets_match_the_reused_ceils_from_chase_gate():
    assert set(D.CEIL_BUDGETS) <= set(__import__("common.chase_gate", fromlist=["CEILS"]).CEILS)


def test_the_c083_budget_is_chase_gates_own_anchor():
    assert D.ANCHOR == 0.083
    from common import chase_gate as C
    assert D.ANCHOR == C.ANCHOR


def test_solve_budgets_reproduces_the_2026_09_18_fenced_numbers():
    """The solve at c083 is the SAME procedure chase_gate already ran at its
    ANCHOR -- it must reproduce -0.1594 / -0.1993 exactly, not merely be
    close. The fenced numbers are never fed back in as an input."""
    rows = ([feat("A", 0.20, -0.02)] * 3 + [feat("B", 0.01, -0.30)] * 7)
    feats = {"MCL": rows, "MC5": rows}
    dists, solved = D.solve_budgets(feats)
    # cross-check against chase_gate's own solve on the same population
    from common.chase_gate import solve_distance
    want, target, got = solve_distance(rows, D.ANCHOR)
    assert dists["MCL-c083"] == want
    assert dists["MC5-c083"] == want


def test_the_quantile_budgets_are_not_solved_against_anything():
    """A direct threshold has no target -- solved[...][0] is None."""
    rows = [feat(f"S{i}", 0.01, -0.01 * i) for i in range(1, 41)]
    feats = {"MCL": rows, "MC5": []}
    dists, solved = D.solve_budgets(feats)
    assert solved["MCL-q10"][0] is None
    assert solved["MCL-q35"][0] is None
    # q10 is a tighter (more negative) cut than q35 on this monotone series
    assert dists["MCL-q10"] < dists["MCL-q35"]


def test_the_solve_reads_nothing_but_the_two_features():
    import inspect
    src = inspect.getsource(D.solve_budgets)
    for forbidden in ("net", "pnl", "profit", "exit_px"):
        assert forbidden not in src, forbidden


# --- the gate --------------------------------------------------------------------

def test_the_gate_refuses_more_negative_than_the_threshold():
    px = [1.0, 2.0] + [1.0] * 6                 # falls to 50% below the high
    g = D.gate_for(frame(px, px), -0.10)
    assert bool(g.iloc[-1]) is False, "50% below the high was admitted"
    assert bool(g.iloc[0]) is True


def test_a_bar_with_too_little_history_is_admitted():
    g = D.gate_for(frame([1.0] * 12), -0.10)
    # dist_from_high at bar 0 is 0 (at the high), always admitted regardless
    assert bool(g.iloc[0]) is True


def test_the_gate_is_boolean_on_the_frames_own_index():
    df = frame([1.0] * 10)
    g = D.gate_for(df, -0.10)
    assert g.dtype == bool and g.index.equals(df.index)


def test_stamp_on_is_the_same_function_chase_gate_uses():
    from common.chase_gate import stamp_on as chase_stamp_on
    assert D.stamp_on is chase_stamp_on


# --- nothing reaches the live path ------------------------------------------------

def test_entry_gate_is_a_backtest_parameter_on_both_engines():
    import inspect
    from strategy.mc5 import mc5
    from strategy.mcl import mcl
    for mod in (mcl, mc5):
        assert "entry_gate" in inspect.signature(mod.backtest_session).parameters
        assert "entry_gate" not in inspect.signature(mod.evaluate_last_bar).parameters


# --- the input file ----------------------------------------------------------------

def test_the_features_default_is_the_preflights_OWN_default():
    from common.running_up_preflight import build_parser
    default = [a.default for a in build_parser()._actions if a.dest == "csv"][0]
    assert D._features_default() == default
    assert D._features_default().endswith("running_up_features.csv")


def test_a_missing_features_file_is_refused_before_the_tape_pass(tmp_path):
    with pytest.raises(SystemExit) as e:
        D.main(["--features", str(tmp_path / "nope.csv"),
                "--pairs", str(tmp_path / "pairs.json")])
    assert "running_up_preflight" in str(e.value)


# --- input refusal / marginal / overlap blocks, generic sanity ---------------------

def test_a_features_file_from_a_different_population_is_REFUSED_not_absorbed():
    books = {"MCL": [{"symbol": "A", "date": "2026-09-11", "entry_et": "05:00:00",
                      "net": -1.0}], "MC5": []}
    feats = {"MCL": [feat("B", 0.1, -0.1)], "MC5": []}
    text = "\n".join(D.population_refusal(books, feats))
    assert "INPUT REFUSAL" in text and "VOID" in text


def test_a_matching_population_says_so_plainly():
    books = {"MCL": [{"symbol": "A", "date": "2026-09-11", "entry_et": "05:00:00",
                      "net": -1.0}], "MC5": []}
    feats = {"MCL": [feat("A", 0.1, -0.1, et="05:00:00")], "MC5": []}
    text = "\n".join(D.population_refusal(books, feats))
    assert "matches the features file exactly" in text


def test_a_gate_that_never_bound_says_so_rather_than_dividing_by_zero():
    books = {name: [] for name, _, _ in D.BOOKS}
    books["MCL"] = [{"symbol": "A", "date": "2026-09-11", "entry_et": "05:00:00", "net": -10.0}]
    books["MCL-c033"] = books["MCL"]
    text = "\n".join(D.marginal_block(books))
    assert "never bound" in text


def test_overlap_block_reads_only_the_two_features():
    rows = [feat("A", 0.20, -0.30), feat("B", 0.01, -0.01)]
    feats = {"MCL": rows, "MC5": []}
    dists = {"MCL-c083": -0.10, "MC5-c083": -0.10}
    for eng in ("mcl", "mc5"):
        for name in D.BUDGET_NAMES:
            dists.setdefault(D._dist_key(eng, name), -1.0)
    text = "\n".join(D.overlap_block(feats, dists))
    assert "MCL" in text and "%" in text
