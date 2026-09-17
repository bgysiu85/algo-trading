#!/usr/bin/env python3
"""The ORB grid runner, end to end on a synthetic cache.

`docs/research/REGISTERED_orb_grid.md` decides how the cells are read. This
file asserts the runner obeys it, because a registration that nothing checks is
a paragraph.

WHAT IS ACTUALLY AT RISK HERE, and it is not arithmetic. A grid produces 120
plausible tables whether or not it is measuring what it claims. The failures
worth catching are the ones that still print a clean report: a "best cell" line
appearing, a thin cell being read, the multiplicity family count drifting from
four, the baseline drifting off the registered configuration, `opposite`
sneaking back in, or the bootstrap quietly becoming a different one from the
one MC5 was scored with.
"""
from __future__ import annotations

import csv
import gzip
import json
import random
from pathlib import Path

import pandas as pd
import pytest

from common import breadth as B
from strategy.orb import grid as G
from strategy.orb import orb as O

ET = "America/New_York"


# --------------------------------------------------------------------------
# a synthetic cache
# --------------------------------------------------------------------------

def write_day(cache: Path, symbol: str, day: str, seed: int) -> None:
    """One RTH session of 1-minute bars as the real cache stores them."""
    rng = random.Random(seed)
    idx = pd.date_range(f"{day} 09:30", f"{day} 15:59", freq="1min", tz=ET)
    px = 5.0
    o, h, l, c = [], [], [], []
    for _ in range(len(idx)):
        nxt = px * (1 + rng.uniform(-0.006, 0.0075))
        o.append(px); c.append(nxt)
        h.append(max(px, nxt) * 1.004); l.append(min(px, nxt) * 0.996)
        px = nxt
    df = pd.DataFrame({"open": o, "high": h, "low": l, "close": c,
                       "volume": [5000.0] * len(idx)},
                      index=idx.tz_convert("UTC"))
    cache.mkdir(parents=True, exist_ok=True)
    with gzip.open(cache / f"{symbol}_{day}.csv.gz", "wt", encoding="utf-8") as fh:
        df.to_csv(fh)


DAYS = ["2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05",
        "2026-03-06", "2026-03-09"]
SYMS = [f"S{i:02d}" for i in range(12)]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("orbgrid")
    cache = root / "3d_to_2000"
    seed = 0
    survivors, rejects = [], []
    for s in SYMS:
        for d in DAYS:
            seed += 1
            write_day(cache, s, d, seed)
            (survivors if int(s[1:]) < 9 else rejects).append(
                {"symbol": s, "date": d})
    sp = root / "pairs.json"; sp.write_text(json.dumps(survivors), encoding="utf-8")
    rp = root / "rejects.json"; rp.write_text(json.dumps(rejects), encoding="utf-8")
    (cache / "SOURCE.txt").write_text("databento XNAS.BASIC ohlcv-1m\n", encoding="utf-8")
    out = root / "grid.txt"; csvp = root / "cells.csv"
    rc = G.main(["--pairs", str(sp), str(rp), "--cache", str(cache),
                 "--window", "3d_to_2000", "--jobs", "1",
                 "--out", str(out), "--csv", str(csvp)])
    assert rc == 0
    return {"text": out.read_text(encoding="utf-8"),
            "rows": list(csv.DictReader(csvp.open(encoding="utf-8"))),
            "root": root, "cache": cache, "pairs": (sp, rp)}


# --------------------------------------------------------------------------
# the grid itself
# --------------------------------------------------------------------------

def test_there_are_exactly_120_cells_and_opposite_is_not_among_them():
    """§3. `opposite` is excluded because spec §6 set MAX_R_PCT = 12% BEFORE
    the pre-flight measured its median R at 9.26% of price. That is a
    pre-registered filter firing, and it stays a filter only while nothing
    quietly puts the arm back."""
    cs = G.cells()
    assert len(cs) == 120
    assert G.GRID_MINUTES == (5, 15, 30, 45), "amendment C.2: 45 added, 3 cannot be"
    assert {c.stop_mode for c in cs} == {"structure", "rangefrac"}
    assert "opposite" not in {c.stop_mode for c in cs}
    assert len({G.key_of(c) for c in cs}) == 120, "a cell key collides"


def test_every_cell_is_printed(built):
    """Nothing ranked, every bucket printed. A grid that showed only the cells
    worth showing would be a maximum wearing a table."""
    for key in (G.key_of(c) for c in G.cells()):
        m, s, rt, e = key
        assert any(line.strip().startswith(f"{m} {s}")
                   and rt in line and e in line
                   for line in built["text"].splitlines()), key
    assert len(built["rows"]) == 120


def test_the_cells_are_printed_in_key_order_and_never_by_performance(built):
    """§7's first named failure is 'reporting a best-cell table'. Grepping for
    the words would be the wrong test -- the report SAYS "nothing ranked" and
    "no best cell table", so a word check fails on its own disclaimers. The
    property that actually matters is the ORDER: a ranked table is sorted by a
    metric, and this one must be sorted by the cell key."""
    seen = []
    for line in built["text"].splitlines():
        parts = line.split()
        if (len(parts) > 8 and parts[0] in {"5", "15", "30", "45"}
                and parts[1] in G.GRID_STOPS and parts[2] in G.GRID_RETESTS):
            seen.append((int(parts[0]), parts[1], parts[2], parts[3]))
    assert len(seen) == 120
    assert seen == sorted(seen), "the cell table is ordered by something else"


def test_a_grid_winner_is_labelled_a_lead_and_not_a_result(built):
    t = built["text"]
    assert "LEAD, NOT A" in t and "RESULT. It does not enter" in t
    assert "holdout.json` is not spent" in t


def test_multiplicity_is_counted_by_family(built):
    """§3.1. Four independent choices, not ninety and not one."""
    assert G.FAMILIES == ("length", "stop", "retest", "exit")
    assert "4 families" in built["text"]


def test_the_baseline_cell_is_the_registered_one(built):
    """§2 fixes every value from the sources, and names the 5-minute
    availability finding as a thing NOT to move the baseline toward."""
    assert G.BASELINE_KEY == (15, "structure", "none", "r_2")
    assert "§11's seven criteria are read HERE ONLY" in built["text"]


# --------------------------------------------------------------------------
# the refusals
# --------------------------------------------------------------------------

def test_a_thin_cell_is_printed_with_its_count_and_no_verdict():
    """§5. Below 100 trades, drop-top-5 removes 5% of the sample and stops
    meaning what it says."""
    cell = G.Cell()
    cell.by_symbol = {"A": [1.0] * 40}
    cell.trades = 40
    cell.by_symbol_day = {("A", "2026-03-02"): 40.0}
    cell.by_date = {"2026-03-02": 40.0}
    d = G.read(cell, "2026-03-03")
    assert d["thin"] is True
    assert G.MIN_TRADES == 100


def test_a_single_cells_two_denominators_can_never_disagree():
    """THE DEFECT THE FIRST DRAFT OF grid.py HAD, found by trying to write a
    failing case for it.

    `per_trade` and `per_symbol_day` are the SAME net over two positive
    divisors, so they always carry the same sign. A per-cell "denominators
    agree" flag can never fire -- identical in shape to breadth's withdrawn
    condition (b), which was (a) at a stricter level wearing the clothes of a
    magnitude check.

    This asserts the impossibility rather than the flag, so nobody can put the
    flag back."""
    cell = G.Cell()
    cell.by_symbol = {"A": [0.5] * 200, "B": [-150.0]}
    cell.trades = 201
    cell.by_symbol_day = {("A", f"2026-03-{i:02d}"): 100.0 for i in range(2, 9)}
    cell.by_symbol_day[("B", "2026-03-02")] = -150.0
    d = G.read(cell, "2026-03-05")
    assert (d["per_trade"] > 0) == (d["per_symbol_day"] > 0)
    assert "denominators_agree" not in d


def test_the_refusal_lives_in_the_comparison_where_it_CAN_fail():
    """§5 item 1, where the disagreement is real: two cells trade different
    numbers of times on different numbers of symbol-days, so "beats the
    baseline" can come out one way per trade and the other way per
    symbol-day."""
    base, cell = G.Cell(), G.Cell()
    # Baseline: 10 trades over 10 symbol-days, +$100 -> +10.00 both ways.
    base.by_symbol = {f"B{i}": [10.0] for i in range(10)}
    base.trades = 10
    base.by_symbol_day = {(f"B{i}", "2026-03-02"): 10.0 for i in range(10)}
    # Cell: 40 trades over 4 symbol-days, +$240 -> +6.00 per trade (WORSE)
    # but +60.00 per symbol-day (BETTER).
    cell.by_symbol = {f"C{i}": [6.0] * 10 for i in range(4)}
    cell.trades = 40
    cell.by_symbol_day = {(f"C{i}", "2026-03-02"): 60.0 for i in range(4)}
    dd = G.deltas(cell, base)
    assert dd["d_per_trade"] < 0 < dd["d_per_symbol_day"]
    assert dd["denoms_agree"] is False

    assert G.deltas(base, base)["denoms_agree"] is True, (
        "the baseline compared against itself must never refuse")


def test_the_report_says_how_many_cells_it_refused_and_how_many_are_thin(built):
    t = built["text"]
    assert "are NOT READ (§5)" in t
    assert "REFUSED: measured against the" in t
    assert "could never fire" in t, (
        "the report must say WHY the refusal is not a per-cell check")


# --------------------------------------------------------------------------
# the boundary rule
# --------------------------------------------------------------------------

def test_the_boundary_rule_says_where_it_cannot_apply(built):
    """§4. A criterion that cannot fail is not a criterion, and reporting 'no
    boundary optimum' over a two-value family is claiming a check that was
    never performed."""
    t = built["text"]
    assert "BOTH ARE BOUNDARIES and the rule" in t
    assert "CANNOT APPLY" in t
    assert "unordered, so the rule does not apply" in t


def _flat(per_trade: dict, stop="structure", retest="none", exit_="r_2"):
    return {(m, stop, retest, exit_): {"thin": False, "per_trade": v}
            for m, v in per_trade.items()}


def test_a_win_on_the_upper_edge_is_not_an_optimum():
    ra = _flat({5: 0.5, 15: 1.0, 30: 2.0, 45: 3.0})
    out = "\n".join(G._boundary_block(ra))
    assert "ON A BOUNDARY: the upper edge, 45" in out
    assert "Criterion 7 is NOT MET" in out
    ra[(45, "structure", "none", "r_2")]["per_trade"] = 0.1
    interior = "\n".join(G._boundary_block(ra))
    assert "WINS: 30 minutes" in interior
    assert "Interior" in interior and "ON A BOUNDARY" not in interior


def test_the_lower_edge_is_reported_as_unpushable_and_not_as_a_push_to_3():
    """C.2. A 3-minute box does not end on a 5-minute trigger bar; asking for
    a push the design refuses would be a rule that cannot be followed."""
    out = "\n".join(G._boundary_block(_flat({5: 3.0, 15: 1.0, 30: 0.5, 45: 0.1})))
    assert "the lower edge, 5, WHICH CANNOT BE PUSHED" in out
    assert "pushed (3)" not in out
    with pytest.raises(Exception):
        O.Config(orb_minutes=3)


def test_wins_is_read_jointly_on_length_and_stop_within_the_none_arm_only():
    """C.1. On the first XNAS run the baseline row said 5 wins and the joint
    `none` reading said 30. A retest arm, however good, must not decide it,
    and neither may the baseline stop alone."""
    ra = _flat({5: 2.0, 15: 1.0, 30: 0.5, 45: 0.2})                 # structure
    ra.update(_flat({5: 1.0, 15: 1.5, 30: 6.6, 45: 0.3}, stop="rangefrac"))
    ra.update(_flat({5: 0.1, 15: 99.0, 30: 0.1, 45: 99.0}, retest="required"))
    out = "\n".join(G._boundary_block(ra))
    assert "WINS: 30 minutes (rangefrac / none / r_2" in out, out
    assert "ON A BOUNDARY" not in out


def test_a_thin_none_cell_cannot_win_the_boundary_read():
    ra = _flat({5: 0.5, 15: 1.0, 30: 2.0, 45: 0.1})
    ra[(45, "structure", "none", "trail_pct")] = {"thin": True, "per_trade": 50.0}
    out = "\n".join(G._boundary_block(ra))
    assert "WINS: 30 minutes" in out


# --------------------------------------------------------------------------
# the registered prediction
# --------------------------------------------------------------------------

def test_the_prediction_is_scored_whichever_way_it_goes():
    """The amendment's §B, written before this runner existed. A prediction
    the report only mentions when it holds is not a prediction."""
    def rows(r2, other):
        return {(15, "structure", "none", e):
                {"thin": False, "per_trade": (r2 if e == "r_2" else other)}
                for e in G.GRID_EXITS}
    held = "\n".join(G._prediction_block(rows(1.0, 2.0)))
    assert "PREDICTION HELD" in held
    failed = "\n".join(G._prediction_block(rows(3.0, 1.0)))
    assert "PREDICTION FAILED" in failed
    assert "surprise" in failed


# --------------------------------------------------------------------------
# the bootstrap, and the withdrawn condition
# --------------------------------------------------------------------------

def test_the_bootstrap_is_breadths_own_call_and_not_a_second_one():
    """§4 of REGISTERED_breadth.md: one call, one set of parameters, both
    strategies. A grid with its own resampler would judge ORB and MC5 by two
    instruments while reporting one number."""
    assert G.cluster_bootstrap is B.cluster_bootstrap
    assert (G.RESAMPLES, G.SEED) == (B.RESAMPLES, B.SEED)

    # AND THAT THOSE VALUES REACH THE CALL. Asserting the constants match is
    # one step short of the thing it protects: `read()` could pass its own
    # resample count and seed while both module constants sat there agreeing.
    # A mutation that did exactly that survived the first pass of this file.
    cell = G.Cell()
    cell.by_symbol = {f"S{i}": [float(i) - 3.0] for i in range(9)}
    cell.trades = 9
    cell.by_symbol_day = {(f"S{i}", "2026-03-02"): float(i) - 3.0
                          for i in range(9)}
    cell.by_date = {"2026-03-02": sum(float(i) - 3.0 for i in range(9))}
    d = G.read(cell, "2026-03-03")
    want = B.cluster_bootstrap(cell.by_symbol, B.RESAMPLES, B.SEED)
    assert d["boot_p"] == pytest.approx(B.share_above_zero(want["totals"]))
    assert d["boot_lo"] == pytest.approx(B.pct(want["totals"], 0.025))
    assert d["boot_hi"] == pytest.approx(B.pct(want["totals"], 0.975))


def test_the_per_trade_interval_is_marked_as_not_a_pass_condition(built):
    """Condition (b) was withdrawn before use because it could not fail
    independently of (a). A figure printed beside a verdict it cannot change
    has to say so, or the next reader takes it for one."""
    assert "CONTEXT ONLY, not a pass condition" in built["text"]


def test_the_bootstrap_verdict_is_read_against_breadths_own_bar(built):
    assert f"{B.BOOT_MIN_P:.2f} bar" in built["text"]


# --------------------------------------------------------------------------
# coverage and the honest limitations
# --------------------------------------------------------------------------

def test_the_split_point_is_the_median_date_and_is_not_swept(built):
    assert "median session date, not swept" in built["text"]
    assert DAYS[len(DAYS) // 2] in built["text"]


def test_the_halves_of_a_cell_sum_to_its_net(built):
    for r in built["rows"]:
        if int(r["trades"]):
            assert float(r["early"]) + float(r["late"]) == pytest.approx(
                float(r["net"]), abs=1e-6), r["exit_mode"]


def test_the_report_states_the_screen_is_three_of_its_four_rules(built):
    """§11 criterion 6 is tested on three rules, and the one that cannot be
    simulated is the one the outside literature says carries everything."""
    t = built["text"]
    assert "three" in t and "relative_volume_10d_calc" in t
    assert "carries everything" in t


def test_both_populations_reach_the_csv(built):
    """§10.2b. The reject arm is not a footnote -- a strategy that trades the
    day's range is structurally more exposed to a filter that read the day's
    range."""
    cols = set(built["rows"][0])
    assert any(c.startswith("arm_survivors") for c in cols)
    assert any(c.startswith("arm_rejected") for c in cols)


def test_the_stop_and_target_in_one_bar_count_is_reported(built):
    assert "stop AND target in one bar" in built["text"]
    assert "the stop won every one" in built["text"]


def test_the_delta_table_is_paired_on_the_same_unit_as_the_level_table():
    """Drop-top-N on the delta, per symbol, because that is the unit the
    level's drop-top-N uses and the unit the bootstrap resamples. Two
    measurements on different units under one heading is the defect."""
    base, cell = G.Cell(), G.Cell()
    base.by_symbol = {"A": [10.0], "B": [5.0]}
    cell.by_symbol = {"A": [14.0], "C": [2.0]}
    d = G.deltas(cell, base)
    assert d["delta"] == pytest.approx(4.0 - 5.0 + 2.0)
    assert d["delta_drop1"] == pytest.approx(-5.0 + 2.0)


def test_the_runner_produces_the_same_numbers_on_one_job_and_several(built):
    """The parallel path merges partial accumulators. A merge that dropped or
    double-counted a symbol would move every figure in the report and break
    nothing visible."""
    out = built["root"] / "grid8.txt"
    csvp = built["root"] / "cells8.csv"
    sp, rp = built["pairs"]
    assert G.main(["--pairs", str(sp), str(rp), "--cache", str(built["cache"]),
                   "--window", "3d_to_2000", "--jobs", "4",
                   "--out", str(out), "--csv", str(csvp)]) == 0
    many = list(csv.DictReader(csvp.open(encoding="utf-8")))
    one = {(r["orb_minutes"], r["stop_mode"], r["retest_mode"],
            r["exit_mode"]): r for r in built["rows"]}
    for r in many:
        k = (r["orb_minutes"], r["stop_mode"], r["retest_mode"], r["exit_mode"])
        for col in ("trades", "symbols", "net", "drop5", "early", "late"):
            assert float(r[col]) == pytest.approx(float(one[k][col]), abs=1e-6), \
                (k, col)


# --------------------------------------------------------------------------
# the tape
# --------------------------------------------------------------------------

def test_the_first_full_run_was_on_the_wrong_tape_and_this_is_why_it_refuses(built):
    """2026-09-16: the grid's default --cache pointed at bar_cache_db, which
    holds EQUS.MINI -- the tape retracted for the pre-flight because it carries
    4.8% of the consolidated prints. The runner recorded no tape, so the report
    looked exactly like a real one. The only sign was three status counts that
    matched the EQUS pre-flight to the unit.

    So: read SOURCE.txt, refuse anything but the registered tape, and say so in
    the first lines when overridden."""
    root, cache = built["root"], built["cache"]
    sp, rp = built["pairs"]
    marker = cache / "SOURCE.txt"
    keep = marker.read_text(encoding="utf-8")
    try:
        marker.write_text("databento EQUS.MINI ohlcv-1m\n", encoding="utf-8")
        with pytest.raises(SystemExit) as e:
            G.main(["--pairs", str(sp), str(rp), "--cache", str(cache),
                    "--window", "3d_to_2000", "--jobs", "1", "--limit", "5",
                    "--out", str(root / "x.txt"), "--csv", ""])
        assert "REFUSING TO RUN" in str(e.value)
        assert "EQUS.MINI" in str(e.value) and "XNAS.BASIC" in str(e.value)

        out = root / "anyway.txt"
        assert G.main(["--pairs", str(sp), str(rp), "--cache", str(cache),
                       "--window", "3d_to_2000", "--jobs", "1", "--limit", "5",
                       "--out", str(out), "--csv", "", "--anyway"]) == 0
        text = out.read_text(encoding="utf-8")
        assert "NOT THE REGISTERED TAPE" in text
        assert "tape         EQUS.MINI" in text
        assert "none of it enters section 11" in text
    finally:
        marker.write_text(keep, encoding="utf-8")


def test_an_unknown_tape_is_refused_rather_than_measured(built):
    """'We do not know what this is' is not a reason to measure it and find
    out afterwards."""
    assert G.tape_check("", "XNAS.BASIC", False) is not None
    assert "UNKNOWN" in G.tape_check("", "XNAS.BASIC", False)
    assert G.tape_check("XNAS.BASIC", "XNAS.BASIC", False) is None


def test_the_report_names_its_tape_in_the_header_and_the_provenance_block(built):
    t = built["text"]
    assert "tape=XNAS.BASIC" in t.splitlines()[1]
    assert "WHAT THIS RUN MEASURED" in t
    assert "tape         XNAS.BASIC" in t
    assert "Quote no figure below without this block" in t


def test_the_entry_time_histogram_and_exit_reasons_are_printed(built):
    """§5 item 6. The first full run omitted this block entirely -- a
    registration requirement the runner did not meet, found by reading the
    report against the registration rather than against itself."""
    t = built["text"]
    assert "WHEN THE BASELINE ENTERS" in t
    assert "09:30" in t or "10:00" in t
    assert "exit reasons" in t


# --------------------------------------------------------------------------
# amendment C.3 -- a leg is not a trade
# --------------------------------------------------------------------------

def _trade(net, leg=0, entry="2026-03-02 09:50", px=5.0, reason="target"):
    t = pd.Timestamp(entry, tz=ET)
    return O.Trade(symbol="A", date="2026-03-02", entry_time=t, entry_px=px,
                   shares=50, exit_time=t, exit_px=px, exit_reason=reason,
                   r=0.1, orb_width=0.2, gross=net, commission=0.0, net=net,
                   bars_held=3, leg=leg)


def test_a_two_leg_position_is_one_round_trip_with_two_legs():
    """`r_3_trim` books two `Trade` legs per position. Counted as two trades,
    its per-trade figure was per-leg: 6,722 'trades' on 4,875 symbol-days in
    the first XNAS run."""
    res = O.SessionResult(symbol="A", date="2026-03-02", status="OK")
    res.trades = [_trade(+30.0, leg=1), _trade(-10.0, leg=2, reason="be_stop")]
    c = G.Cell()
    c.add(res, "survivors")
    assert (c.trades, c.legs) == (1, 2)
    assert c.by_symbol == {"A": [20.0]}, "the bootstrap must draw the position"
    assert c.wins == 1, "a win is the position's net, not either leg's"
    assert sum(c.entry_hhmm.values()) == 1
    assert sum(c.exit_reason.values()) == 2, "exit reasons stay per leg"
    d = G.read(c, "2026-03-03")
    assert d["per_trade"] == pytest.approx(20.0)
    assert d["legs"] == 2


def test_round_trips_survive_the_parallel_merge():
    a, b = G.Cell(), G.Cell()
    r1 = O.SessionResult(symbol="A", date="2026-03-02", status="OK")
    r1.trades = [_trade(1.0, 1), _trade(2.0, 2)]
    r2 = O.SessionResult(symbol="A", date="2026-03-03", status="OK")
    r2.trades = [_trade(3.0, entry="2026-03-03 10:00")]
    a.add(r1, "survivors"); b.add(r2, "survivors")
    a.merge(b)
    assert (a.trades, a.legs) == (2, 3)


def test_the_r_3_trim_trades_column_in_the_real_run_counts_positions(built):
    rows = {(r["orb_minutes"], r["stop_mode"], r["retest_mode"],
             r["exit_mode"]): r for r in built["rows"]}
    trim = rows[("15", "structure", "none", "r_3_trim")]
    assert int(trim["trades"]) <= int(trim["symbol_days"]), (
        "one entry per session: round trips cannot exceed symbol-days")
    assert int(trim["legs"]) >= int(trim["trades"])


# --------------------------------------------------------------------------
# coverage -- a missing cache file is counted, and a large gap is refused
# --------------------------------------------------------------------------

def test_a_universe_the_cache_does_not_cover_is_refused(built, tmp_path):
    """2026-09-17: 2,537 of the 6,170 point-in-time symbol-days had no file,
    and the ones that did were there because they were also stage-2
    survivors. A bare `continue` would have run the leak under the PIT name."""
    sp, _ = built["pairs"]
    rows = json.loads(sp.read_text(encoding="utf-8"))
    rows += [{"symbol": "NOPE", "date": d} for d in DAYS]
    bad = tmp_path / "gappy.json"; bad.write_text(json.dumps(rows), encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        G.main(["--pairs", str(bad), "--cache", str(built["cache"]),
                "--window", "3d_to_2000", "--jobs", "1",
                "--out", str(tmp_path / "x.txt"), "--csv", ""])
    assert "REFUSING TO RUN" in str(e.value) and "no file" in str(e.value)

    out = tmp_path / "allowed.txt"
    assert G.main(["--pairs", str(bad), "--cache", str(built["cache"]),
                   "--window", "3d_to_2000", "--jobs", "1",
                   "--max-missing-pct", "20", "--labels", "pit",
                   "--out", str(out), "--csv", ""]) == 0
    text = out.read_text(encoding="utf-8")
    assert f"requested    {len(rows):,}" in text
    assert f"no file      {len(DAYS):,}" in text, "the skip must be COUNTED"


def test_the_coverage_limit_passes_a_fully_covered_universe(built):
    sp, rp = built["pairs"]
    pairs = G.load_pairs([str(sp), str(rp)], None)
    assert G.coverage_check(built["cache"], pairs, G.MAX_MISSING_PCT) is None
    assert "no file      0" in built["text"]


def test_population_labels_name_the_universe_and_must_match_the_files(built, tmp_path):
    sp, rp = built["pairs"]
    got = G.load_pairs([str(sp)], None, ["pit"])
    assert {r["population"] for r in got} == {"pit"}
    with pytest.raises(SystemExit):
        G.load_pairs([str(sp), str(rp)], None, ["pit"])
    assert {r["population"] for r in G.load_pairs([str(sp), str(rp)], None)} == {
        "survivors", "rejected"}


# --------------------------------------------------------------------------
# amendment D.2 -- the §10.2 screen may not read the day's close
# --------------------------------------------------------------------------

def _session(closes_after: float, at_945: float = 5.30, day="2026-03-02"):
    idx = pd.date_range(f"{day} 09:30", f"{day} 15:59", freq="1min", tz=ET)
    px = [5.0] * len(idx)
    for i, t in enumerate(idx):
        if t.hour == 9 and t.minute < 45:
            px[i] = 5.0 + (at_945 - 5.0) * (i + 1) / 15
        else:
            px[i] = closes_after
    return pd.DataFrame({"open": [5.0] + px[:-1], "high": px, "low": px,
                         "close": px, "volume": [1000.0] * len(idx)}, index=idx)


def test_the_screen_is_decided_at_range_end_and_cannot_see_the_close():
    """The first runner read `sess['close'].iloc[-1]`, the 15:59 close, so
    'passes' meant 'closed up more than 5%' -- a split on the outcome."""
    up_early = _session(closes_after=4.0, at_945=5.30)     # +6% at 09:45, dies
    flat_early = _session(closes_after=9.0, at_945=5.05)   # +1% at 09:45, runs
    assert G._rth_screen(up_early) is True
    assert G._rth_screen(flat_early) is False


def test_the_screen_gives_the_same_answer_through_rth_session():
    """Same answer through the loader's own ET conversion, on UTC input."""
    from strategy.orb.preflight import rth_session
    df = _session(closes_after=4.0, at_945=5.30)
    df.index = df.index.tz_convert("UTC")
    assert G._rth_screen(rth_session(df, "2026-03-02")) is True


def test_a_name_surfaced_after_the_earliest_range_end_is_refused():
    """The grid does not floor entries at first_seen; that is only honest
    while nothing surfaces after 09:35 ET."""
    ok = [{"symbol": "A", "date": "2026-03-02",
           "first_seen": "2026-03-02T14:30:00+00:00"}]          # 09:30 EST
    assert G.first_seen_check(ok) is None
    assert G.first_seen_check([{"symbol": "A", "date": "2026-03-02"}]) is None
    late = [{"symbol": "B", "date": "2026-03-02",
             "first_seen": "2026-03-02T15:05:00+00:00"}]        # 10:05 EST
    msg = G.first_seen_check(late)
    assert msg and "REFUSING TO RUN" in msg and "B 2026-03-02 10:05" in msg
