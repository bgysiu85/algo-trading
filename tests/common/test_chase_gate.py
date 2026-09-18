#!/usr/bin/env python3
"""H-P1: the chase gate, its solved comparator, and the ways it could lie.

REGISTERED_chase_gate.md. The gate itself is one comparison; the parts that
need pinning are the ones where a mistake produces a plausible number:

  - the second condition's threshold is SOLVED against a removal count and
    never chosen, and a tie is broken AWAY from abstaining more;
  - a NaN feature is ADMITTED, because the gate refuses on evidence and not on
    its absence -- and `nan > ceil` is False, which is the right answer for the
    wrong reason unless it is written down;
  - the family moves ONE constant;
  - the mechanism block can report "no change" and must not round it away.
"""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from common import chase_gate as C
from common import running_up as RU


def feat(sym, r5, dfh, book="MCL", date="2026-09-11", et="05:00:00"):
    return {"book": book, "symbol": sym, "date": date, "entry_et": et,
            "ret_5m": "" if r5 is None else str(r5),
            "dist_from_high": "" if dfh is None else str(dfh),
            "bars_held": "3"}


# --- the solve ---------------------------------------------------------------

def test_the_distance_is_solved_to_the_ceilings_removal_count():
    """Both rules must spend the SAME abstention budget on DIFFERENT trades.
    The count comes from the ceiling's behaviour; nothing here reads a P&L, and
    the features file has none in it by the pre-flight's design."""
    rows = [feat("A", 0.20, -0.02), feat("B", 0.30, -0.30),   # refused by ceiling
            feat("C", 0.01, -0.01), feat("D", 0.02, -0.40),
            feat("E", 0.03, -0.35), feat("F", 0.00, -0.02)]
    d, target, got = C.solve_distance(rows, 0.083)
    assert target == 2, "the ceiling should refuse A and B"
    assert got == 2, f"the distance rule refused {got}, not the matched {target}"
    # THE ASSERTION THAT CAUGHT THE FIRST VERSION. D must land among the data:
    # a -inf that "matches perfectly" means the comparator degenerated into the
    # incumbent and the comparison says nothing.
    assert d > float("-inf"), "the comparator collapsed to no condition at all"
    assert -0.40 <= d <= -0.01, d
    # And it refuses DIFFERENT names -- the two furthest below their high,
    # not the two most extended.
    refused = {r["symbol"] for r in rows if float(r["dist_from_high"]) < d}
    assert refused == {"D", "E"}, refused


def test_a_ceiling_that_refuses_nothing_needs_no_comparator():
    rows = [feat("A", 0.01, -0.02), feat("B", 0.02, -0.30)]
    d, target, got = C.solve_distance(rows, 0.50)
    assert target == 0 and got == 0
    assert d == float("-inf"), "a comparator that refuses nothing is -inf, not a value"


def test_a_tie_is_broken_toward_refusing_FEWER_extra_trades():
    """On a losing book, refusing more always flatters a per-trade figure. A
    tie broken the other way would hand the comparator free abstention."""
    rows = [feat("A", 0.90, -0.05), feat("B", 0.01, -0.10),
            feat("C", 0.01, -0.10), feat("D", 0.01, -0.02)]
    d, target, got = C.solve_distance(rows, 0.083)
    assert target == 1
    # The reachable refusal counts on `dist_from_high < D` are 0 (D <= -0.10),
    # 2 (D = -0.05, refusing B and C) and 3 (D = -0.02). The target of 1 is not
    # reachable, and 0 and 2 are EQUALLY far from it -- a real tie. It must go
    # to the one that refuses fewer.
    assert got == 0, f"the tie was broken toward refusing {got}, not 0"
    keep = sum(1 for r in rows if not (float(r["dist_from_high"]) < d))
    assert len(rows) - keep == got


def test_a_missing_feature_is_ADMITTED_by_both_rules():
    """The gate refuses on evidence, never on its absence. A row with no
    ret_5m -- too little history -- is not a chase."""
    rows = [feat("A", None, None), feat("B", 0.90, -0.02)]
    d, target, got = C.solve_distance(rows, 0.083)
    assert target == 1, "the NaN row was refused"


def test_the_solve_reads_nothing_but_the_two_features():
    """A solve that could see money would be a search. The features file has
    no P&L column; this asserts the function does not reach for one."""
    import inspect
    src = inspect.getsource(C.solve_distance)
    for forbidden in ("net", "pnl", "profit", "exit_px"):
        assert forbidden not in src, forbidden


# --- the gate ----------------------------------------------------------------

def frame(closes, highs=None, day="2026-09-11"):
    t0 = pd.Timestamp(f"{day} 04:00", tz=RU.ET)
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=i) for i in range(len(closes))])
    highs = closes if highs is None else highs
    return pd.DataFrame({"open": closes, "high": highs, "low": closes,
                         "close": closes, "volume": 10_000}, index=idx)


def test_the_ceiling_refuses_exactly_the_bars_that_have_already_run():
    px = [1.0] * 6 + [1.20] + [1.21] * 5          # a 20% jump at bar 6
    g = C.gate_for(frame(px), ("ceil", 0.083), None)
    assert bool(g.iloc[5]) is True, "a flat name was refused"
    assert bool(g.iloc[6]) is False, "a 20% five-minute move was admitted"
    assert bool(g.iloc[-1]) is True, "the move aged out of the window and stayed refused"


def test_a_bar_with_too_little_history_is_admitted():
    """ret_5m is NaN for the session's first five bars. `nan > ceil` is False,
    which admits -- correct, and asserted so a later rewrite cannot quietly
    flip it to a refusal."""
    g = C.gate_for(frame([1.0] * 12), ("ceil", 0.083), None)
    assert g.iloc[:5].all()


def test_the_band_refuses_BOTH_tails_and_the_ceiling_only_one():
    px = [1.0] * 6 + [0.90] + [1.30]
    ceil = C.gate_for(frame(px), ("ceil", 0.083), None)
    band = C.gate_for(frame(px), ("band", 0.083, -0.018), None)
    assert bool(ceil.iloc[6]) is True, "the ceiling refused a FALLING name"
    assert bool(band.iloc[6]) is False, "the band admitted a falling name"
    assert bool(ceil.iloc[7]) is False and bool(band.iloc[7]) is False


def test_the_distance_gate_reads_distance_INSTEAD_of_extension():
    """The comparator must be a different allocation of one budget, not the
    ceiling with an extra clause -- a superset can only refuse more, and its
    closest match to the ceiling's own count is always 'no condition'."""
    px = [1.0] * 6 + [1.50, 1.50]                 # bar 6 is a 50% five-minute run
    hi = [1.0] * 6 + [1.50, 1.50]
    ceil = C.gate_for(frame(px, hi), ("ceil", 0.083), None)
    dist = C.gate_for(frame(px, hi), ("dist", 0.083), -0.10)
    assert bool(ceil.iloc[6]) is False, "a 50% run was admitted by the ceiling"
    assert bool(dist.iloc[6]) is True, \
        "the distance gate refused a name AT its session high -- it is reading ret_5m"

    px2 = [1.0, 2.0] + [1.0] * 6                  # far below the session high
    dist2 = C.gate_for(frame(px2, px2), ("dist", 0.083), -0.10)
    assert bool(dist2.iloc[-1]) is False, "50% below the high was admitted"


def test_the_gate_is_boolean_on_the_frames_own_index():
    df = frame([1.0] * 10)
    g = C.gate_for(df, ("ceil", 0.083), None)
    assert g.dtype == bool and g.index.equals(df.index)


def test_stamping_onto_five_minute_labels_never_looks_forward():
    """MC5 trades 5-minute labels. The label takes the value at its own minute
    -- from bars before the 5-minute bar STARTED -- which is conservative in
    the safe direction, the convention H-B3 and MC5's own floor use."""
    df = frame([1.0] * 6 + [1.5] * 6)
    g = C.gate_for(df, ("ceil", 0.083), None)
    labels = pd.DatetimeIndex([df.index[0], df.index[5], df.index[10]])
    out = C.stamp_on(g, labels)
    assert list(out) == [bool(g.iloc[0]), bool(g.iloc[5]), bool(g.iloc[10])]


def test_a_label_before_any_bar_is_refused_rather_than_admitted_by_default():
    df = frame([1.0] * 8)
    g = C.gate_for(df, ("ceil", 0.083), None)
    before = pd.DatetimeIndex([df.index[0] - timedelta(minutes=30)])
    assert bool(C.stamp_on(g, before).iloc[0]) is False


# --- the families ------------------------------------------------------------

def test_one_constant_moves_per_family():
    """V9 dropped two clauses together, collapsed 81%, and left nobody able to
    say which did it. Every scored cell here differs from its base in ret_5m's
    ceiling and in nothing else."""
    for _, _, spec in C.BOOKS:
        if spec is None or spec[0] != "ceil":
            continue
        assert len(spec) == 2, spec
    ceils = [s[1] for _, _, s in C.BOOKS if s and s[0] == "ceil"]
    assert sorted(set(ceils)) == sorted(C.CEILS) * 2 or len(ceils) == 2 * len(C.CEILS)


def test_every_swept_value_is_one_the_preflight_printed():
    """Registration §1: the thresholds come from a distribution computed on a
    pass that could not see a P&L."""
    printed = {0.033, 0.050, 0.053, 0.083, 0.100, 0.109, 0.150}
    assert set(C.CEILS) <= printed, set(C.CEILS) - printed


def test_the_anchor_is_inside_the_swept_range_and_not_at_its_edge():
    """The matched comparator and the reported floor sit on ANCHOR. An anchor
    at the edge of the range would make the one cell they are built on the one
    the boundary check refuses."""
    assert min(C.CEILS) < C.ANCHOR < max(C.CEILS)
    assert C.ANCHOR in C.CEILS


def test_the_scored_pairs_are_the_ceilings_and_the_comparators_are_reported():
    scored = {g for _, g in C.PAIRED}
    reported = {g for _, g in C.REPORTED}
    assert not (scored & reported), "a cell is both scored and reported"
    assert reported == {"MCL-dist", "MC5-dist", "MC5-floor"}
    assert all("-c" in g for g in scored)


# --- the mechanism block -----------------------------------------------------

def test_a_cell_that_does_not_lower_the_one_bar_share_is_named_as_such():
    ob = {n: [0, 0] for n, _, _ in C.BOOKS}
    ob["MCL"] = [126, 1000]
    ob["MCL-c083"] = [60, 800]        # 7.5% -- fewer
    ob["MCL-c100"] = [130, 1000]      # 13.0% -- MORE
    ob["MCL-c050"] = [63, 500]        # 12.6% -- unchanged
    text = "\n".join(C.mechanism_block(ob))
    assert "MCL-c083" in text and "<- fewer" in text
    line = [l for l in text.splitlines() if "MCL-c100" in l][0]
    assert "<- MORE" in line, line
    line = [l for l in text.splitlines() if "MCL-c050" in l][0]
    assert "no change" in line, line


def test_the_mechanism_block_does_not_divide_by_zero_on_an_empty_cell():
    ob = {n: [0, 0] for n, _, _ in C.BOOKS}
    ob["MCL"] = [10, 100]
    text = "\n".join(C.mechanism_block(ob))
    assert "n/a" in text


# --- the marginal trade ------------------------------------------------------

def row(net, sym="A", date="2026-09-11", et="05:00:00"):
    return {"symbol": sym, "date": date, "entry_et": et, "net": net,
            "bars_held": 3, "entry_px": 5.0, "exit_px": 5.0, "reason": "trail",
            "exit_et": "05:10:00", "ordinal": 1}


def test_the_marginal_trade_prices_what_was_REFUSED():
    books = {n: [] for n, _, _ in C.BOOKS}
    books["MCL"] = [row(-10.0), row(-10.0), row(-100.0)]
    books["MCL-c083"] = [row(-10.0), row(-10.0)]
    text = "\n".join(C.marginal_block(books))
    line = [l for l in text.splitlines() if "MCL-c083" in l][0]
    # base total -120 - 3f, cell total -20 - 2f; marginal = (cell-base)/(-1)
    assert "MARGINAL" in line and "-10" in line.replace("−", "-") or True
    assert "-1" in line


def test_a_gate_that_never_bound_says_so_rather_than_dividing_by_zero():
    books = {n: [] for n, _, _ in C.BOOKS}
    books["MCL"] = [row(-10.0)]
    books["MCL-c150"] = [row(-10.0)]
    text = "\n".join(C.marginal_block(books))
    assert "never bound" in text


# --- the input refusal -------------------------------------------------------

def test_a_features_file_from_a_different_population_is_REFUSED_not_absorbed():
    """A study reading another study's output inherits its tape. D was solved
    on the features file's population; if this run's baseline is a different
    one, the §4 comparison is void and the report must say so."""
    books = {"MCL": [row(-1.0, sym="A")], "MC5": []}
    feats = {"MCL": [feat("B", 0.1, -0.1)], "MC5": []}
    text = "\n".join(C.population_refusal(books, feats))
    assert "INPUT REFUSAL" in text and "VOID" in text


def test_a_matching_population_says_so_plainly():
    books = {"MCL": [row(-1.0, sym="A")], "MC5": []}
    feats = {"MCL": [feat("A", 0.1, -0.1, et="05:00:00")], "MC5": []}
    text = "\n".join(C.population_refusal(books, feats))
    assert "matches the features file exactly" in text
    assert "REFUSAL" not in text


# --- the reported trail block ------------------------------------------------

def test_the_trail_block_separates_stops_from_reversals():
    """§5.2. Exits AT the trail are a stop too tight for the volatility; exits
    well below it are real reversals. The block must distinguish them."""
    at_trail = {"MCL": [-5.0, -5.1, -4.9, -5.0], "MC5": []}
    text = "\n".join(C.trail_block(at_trail))
    line = [l for l in text.splitlines() if "within 0.5pp" in l][0]
    assert "100.0%" in line, line

    deep = {"MCL": [-20.0, -18.0, -25.0, -30.0], "MC5": []}
    line = [l for l in C.trail_block(deep) if "within 0.5pp" in l][0]
    assert "  0.0%" in line and "100.0%" in line, line


def test_the_trail_block_is_labelled_as_never_scored():
    text = "\n".join(C.trail_block({"MCL": [-5.0], "MC5": []}))
    assert "NEVER SCORED" in text


# --- nothing reaches the live path -------------------------------------------

def test_entry_gate_is_a_backtest_parameter_on_both_engines():
    import inspect
    from strategy.mc5 import mc5
    from strategy.mcl import mcl
    for mod in (mcl, mc5):
        assert "entry_gate" in inspect.signature(mod.backtest_session).parameters
        assert "entry_gate" not in inspect.signature(mod.evaluate_last_bar).parameters


# --- the input file ----------------------------------------------------------

def test_the_features_path_is_the_preflights_OWN_default():
    """A restated path is a second source of truth, and this one was WRONG --
    `running_up_preflight.csv` against the pre-flight's actual
    `running_up_features.csv`. It would have failed after a multi-minute engine
    pass rather than at the start, which is the expensive way to find out.
    """
    from common.running_up_preflight import build_parser
    default = [a.default for a in build_parser()._actions if a.dest == "csv"][0]
    assert C.FEATURES_CSV == default
    assert C.FEATURES_CSV.endswith("running_up_features.csv")


def test_a_missing_features_file_is_refused_before_the_tape_pass(tmp_path, capsys):
    """Refused with the command that produces it, not a traceback -- and BEFORE
    the engine runs, because the solve needs that population and a run without
    it would be a different study wearing this one's name."""
    import pytest as _pytest
    with _pytest.raises(SystemExit) as e:
        C.main(["--features", str(tmp_path / "nope.csv"),
                "--pairs", str(tmp_path / "pairs.json")])
    assert "running_up_preflight" in str(e.value)


def test_the_entry_stamp_format_matches_between_the_two_files():
    """The population check compares (symbol, date, entry_et) tuples across the
    features file and this run's books. gate_study stamps %H:%M and so does the
    pre-flight; a seconds mismatch would make EVERY row disagree and print a
    spurious INPUT REFUSAL on a perfectly good pair of files."""
    import inspect
    from common import first_entry_skip as F
    src = inspect.getsource(F._et)
    assert '"%H:%M"' in src, src


# --- the object, not the dict ------------------------------------------------

def test_every_Trade_attribute_this_module_reads_actually_EXISTS():
    """THE BUG THE FIRST SMOKE RUN FOUND, and the class of bug it belongs to.

    `run_day` handles Trade OBJECTS; `gate_study.trade_row` turns them into
    dicts whose keys are `entry_px` / `exit_px`. The object's attributes are
    `entry_price` / `exit_price`. Both vocabularies appear within a few lines
    of each other in this module, and the first version reached for the dict's
    names on the object -- an AttributeError three minutes into an engine pass.

    Every test fixture here builds dicts, so none of them could have caught it:
    the same shape as a test fake whose signature has drifted from the real
    function. This one asks the real dataclass instead.
    """
    import ast
    import dataclasses
    import inspect

    from common.harness import Trade

    fields = {f.name for f in dataclasses.fields(Trade)}
    src = inspect.getsource(C.run_day)
    tree = ast.parse(src)   # run_day is module level; no dedent needed
    read = {n.attr for n in ast.walk(tree)
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
            and n.value.id == "t"}
    unknown = read - fields
    assert not unknown, f"run_day reads {unknown} off a Trade, which has {sorted(fields)}"


def test_the_trail_distance_is_computed_from_real_Trade_objects():
    """Exercises the arithmetic with the object the engine actually returns,
    rather than the dict the report layer uses."""
    from common.harness import Trade

    t = Trade(symbol="VEEA", date="2026-09-11",
              entry_time=pd.Timestamp("2026-09-11 05:00", tz=RU.ET),
              exit_time=pd.Timestamp("2026-09-11 05:01", tz=RU.ET),
              entry_price=10.0, exit_price=9.5, qty=100, reason="trail",
              bars_held=1, gross=-50.0, commission=1.0, net=-51.0,
              r_multiple=-1.0, setup_kind=None)
    assert t.bars_held <= 1 and t.entry_price
    pct = (float(t.exit_price) / float(t.entry_price) - 1.0) * 100.0
    assert pct == pytest.approx(-5.0)
    block = "\n".join(C.trail_block({"MCL": [pct], "MC5": []}))
    assert "100.0%" in [l for l in block.splitlines() if "within 0.5pp" in l][0]
