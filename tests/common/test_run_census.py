#!/usr/bin/env python3
"""A census that looks forward is an oracle, and an oracle is easy to mistake
for a result.

The failure mode here is not a crash. It is a large, true dollar figure that a
reader takes as achievable, or a grid cell picked after the fact. So the tests
are mostly about arithmetic that must be exactly right (a run is a run, and one
move is one run) and about what the report must refuse to imply.
"""
from __future__ import annotations

from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from common import run_census as C

ET = ZoneInfo("America/New_York")


def frame(closes, lows=None, start="04:00"):
    h, m = int(start[:2]), int(start[3:])
    t0 = pd.Timestamp(datetime.combine(pd.Timestamp("2026-09-11").date(),
                                       dtime(h, m), tzinfo=ET))
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=i)
                            for i in range(len(closes))])
    c = np.array(closes, dtype=float)
    lo = np.array(lows, dtype=float) if lows is not None else c * 0.999
    return pd.DataFrame({"open": c, "high": c * 1.001, "low": lo,
                         "close": c, "volume": np.full(len(c), 50_000.0)},
                        index=idx.tz_convert("UTC"))


# --- the arithmetic -----------------------------------------------------------

def test_a_clean_rise_is_found():
    c = [10.0] * 5 + [10.0 * (1 + 0.02 * k) for k in range(1, 11)] + [11.0] * 40
    got = C.runs_in(np.array(c), np.array(c) * 0.999, 5.0, [8.0], [10])
    assert len(got[(8.0, 10)]) >= 1
    t0, k, ratio = got[(8.0, 10)][0]
    assert ratio >= 1.08


def test_a_move_that_dips_past_the_tolerance_first_is_NOT_a_run():
    """The dip guard is the whole difference between a census and a fantasy:
    without it this counts moves a stop would have been taken out of."""
    c = [10.0, 9.0, 12.0] + [12.0] * 40          # -10% then +20%
    lo = [10.0, 8.9, 12.0] + [12.0] * 40
    got = C.runs_in(np.array(c), np.array(lo), 5.0, [8.0], [10])
    starts = [t for t, _, _ in got[(8.0, 10)]]
    assert 0 not in starts, "counted a move that dipped 10% on the way"


def test_a_dip_INSIDE_the_tolerance_still_counts():
    c = [10.0, 9.8, 11.0] + [11.0] * 40          # -2% dip, trail is 5%
    lo = [10.0, 9.75, 11.0] + [11.0] * 40
    got = C.runs_in(np.array(c), np.array(lo), 5.0, [8.0], [10])
    assert 0 in [t for t, _, _ in got[(8.0, 10)]]


def test_the_deadline_is_enforced():
    """+10% but it takes 20 bars: inside N=30, outside N=5."""
    c = [10.0] + [10.0 + 0.5 * min(k, 20) / 20 * 2 for k in range(1, 60)]
    a = np.array(c)
    got = C.runs_in(a, a * 0.999, 5.0, [8.0], [5, 30])
    assert not got[(8.0, 5)]
    assert got[(8.0, 30)]


def test_ONE_move_is_ONE_run_not_one_per_bar():
    """A thirteen-bar climb starts at every one of its bars. Counting each
    would multiply the population by the length of its own moves."""
    c = [10.0] + [10.0 * (1 + 0.012 * k) for k in range(1, 14)] + [11.6] * 40
    a = np.array(c)
    got = C.runs_in(a, a * 0.999, 5.0, [8.0], [15])
    assert len(got[(8.0, 15)]) == 1, f"{len(got[(8.0,15)])} runs for one move"


def test_two_separated_moves_are_two_runs():
    leg = [10.0 * (1 + 0.012 * k) for k in range(1, 14)]
    c = [10.0] + leg + [11.6] * 20 + [11.6 * (1 + 0.012 * k)
                                      for k in range(1, 14)] + [13.5] * 20
    a = np.array(c)
    got = C.runs_in(a, a * 0.999, 5.0, [8.0], [15])
    assert len(got[(8.0, 15)]) == 2


def test_a_flat_tape_yields_nothing():
    a = np.full(200, 10.0)
    got = C.runs_in(a, a, 5.0, C.R_PCTS, C.N_BARS)
    assert all(len(v) == 0 for v in got.values())


def test_a_bigger_R_never_finds_more_runs_than_a_smaller_one():
    """Monotonicity is a free internal check: nothing about a harder threshold
    can create runs. A violation means the non-overlap walk is wrong."""
    rng = np.random.default_rng(4)
    c = 10.0 * np.exp(np.cumsum(rng.normal(0, 0.004, 400)))
    got = C.runs_in(c, c * 0.995, 5.0, C.R_PCTS, C.N_BARS)
    for nb in C.N_BARS:
        counts = [len(got[(r, nb)]) for r in sorted(C.R_PCTS)]
        assert counts == sorted(counts, reverse=True), counts


def test_a_longer_deadline_never_finds_fewer_runs():
    rng = np.random.default_rng(5)
    c = 10.0 * np.exp(np.cumsum(rng.normal(0, 0.004, 400)))
    got = C.runs_in(c, c * 0.995, 5.0, C.R_PCTS, C.N_BARS)
    for r in C.R_PCTS:
        counts = [len(got[(r, nb)]) for nb in sorted(C.N_BARS)]
        assert counts == sorted(counts), counts


def test_no_run_reads_past_the_end_of_the_session():
    """A run completing after the last bar would be borrowed from a session
    that has not happened."""
    c = np.array([10.0] * 5 + [20.0])
    got = C.runs_in(c, c * 0.99, 5.0, [8.0], [30])
    for t, k, _ in got[(8.0, 30)]:
        assert t + k < len(c)


# --- the frame wrapper --------------------------------------------------------

def test_a_short_session_is_skipped_not_censused():
    got, n, _why = C.census_frame(frame([10.0] * 10), "A", "2026-09-11", 5.0)
    assert n == 0 and got == {}


def test_a_sub_dollar_name_is_skipped():
    """Below a dollar the tick IS the move; a 3% run is two cents of spread."""
    c = [0.50] * 60
    got, n, _why = C.census_frame(frame(c), "A", "2026-09-11", 5.0)
    assert n == 0


def test_run_rows_carry_ET_time_not_UTC():
    c = [10.0] * 5 + [10.0 * (1 + 0.02 * k) for k in range(1, 11)] + [12.0] * 60
    got, n, _why = C.census_frame(frame(c, start="07:30"), "A", "2026-09-11", 5.0)
    rows = got[(8.0, 15)]
    assert rows and rows[0]["et"].startswith("07:"), rows[0]["et"]
    # 07:30 ET is 210 minutes past the 04:00 open; the run starts a few bars in.
    assert 210 <= rows[0]["mins"] <= 225, rows[0]["mins"]


def test_the_dollar_column_is_per_100_shares():
    c = [10.0] * 3 + [11.0] * 60          # +10% = $100 on 100 shares
    got, n, _why = C.census_frame(frame(c), "A", "2026-09-11", 5.0)
    rows = got[(8.0, 10)]
    assert rows and abs(rows[0]["move"] - 100.0) < 1e-6


# --- what the report must refuse to imply -------------------------------------

def cells_for_report():
    c = [10.0] * 5 + [10.0 * (1 + 0.02 * k) for k in range(1, 11)] + [12.0] * 60
    got, n, _why = C.census_frame(frame(c), "A", "2026-09-11", 5.0)
    return got, n


def test_the_report_calls_the_total_a_CEILING():
    got, n = cells_for_report()
    text = "\n".join(C.render(got, n, 1, 1, {}, "cache", 5.0, 0.1))
    assert "CEILING" in text
    assert "oracle" in text.lower()


def test_the_report_says_it_is_not_a_strategy():
    got, n = cells_for_report()
    text = "\n".join(C.render(got, n, 1, 1, {}, "cache", 5.0, 0.1))
    assert "NOT A STRATEGY" in text
    assert "after the start" in text.lower()


def test_the_report_states_the_base_rate():
    """The count alone flatters. Runs per thousand bars is the number an entry
    signal actually has to beat."""
    got, n = cells_for_report()
    text = "\n".join(C.render(got, n, 1, 1, {}, "cache", 5.0, 0.1))
    assert "BASE RATE" in text
    assert "per 1,000 bars" in text


def test_every_grid_cell_is_printed_even_the_empty_ones():
    got, n = cells_for_report()
    text = "\n".join(C.render(got, n, 1, 1, {}, "cache", 5.0, 0.1))
    for r in C.R_PCTS:
        for nb in C.N_BARS:
            assert f"{r:.0f}% in {nb}" in text, f"cell {r}/{nb} omitted"


def test_the_report_never_names_a_best_cell():
    got, n = cells_for_report()
    low = "\n".join(C.render(got, n, 1, 1, {}, "cache", 5.0, 0.1)).lower()
    for banned in ("best cell", "optimal", "recommend", "we should use",
                   "the right cell"):
        assert banned not in low, f"the census chooses: {banned!r}"


def test_the_time_of_day_cell_is_named_as_nearest_not_best():
    got, n = cells_for_report()
    text = "\n".join(C.render(got, n, 1, 1, {}, "cache", 5.0, 0.1))
    assert "nearest, not because it is best" in text


def test_the_adverse_tolerance_is_reported_and_sourced():
    """A census run with a different dip tolerance is a different census, and
    the number must be on the page rather than implied by the default."""
    got, n = cells_for_report()
    text = "\n".join(C.render(got, n, 1, 1, {}, "cache", 7.5, 0.1))
    assert "7.5%" in text
    assert "MCL's own trail" in text


def test_the_default_tolerance_is_read_off_the_strategy():
    from strategy.mcl.mcl import TRAIL_PCT
    assert C.A_PCT == float(TRAIL_PCT)
    assert C.build_parser().parse_args([]).adverse == float(TRAIL_PCT)


def test_an_empty_census_is_named_not_scored():
    text = "\n".join(C.render({(r, n): [] for r in C.R_PCTS for n in C.N_BARS},
                              0, 0, 0, {}, "cache", 5.0, 0.1))
    assert "NOTHING TO COUNT" in text
