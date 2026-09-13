#!/usr/bin/env python3
"""The cutoff is a wall, and if it leaks the whole measurement inverts.

Filtering on a session's dollar volume and then counting that session's runs is
circular -- a name that ran has high dollar volume BECAUSE it ran -- and the
resulting number would be enormous, plausible and worthless. So most of these
tests are about the wall: criteria may read only bars at or before it, outcomes
may only start after it, and neither may reach across.
"""
from __future__ import annotations

from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from common import universe_lift as U

ET = ZoneInfo("America/New_York")


def frame(closes, vols=None, start="04:00"):
    h, m = int(start[:2]), int(start[3:])
    t0 = pd.Timestamp(datetime.combine(pd.Timestamp("2026-09-11").date(),
                                       dtime(h, m), tzinfo=ET))
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=i)
                            for i in range(len(closes))])
    c = np.array(closes, dtype=float)
    v = (np.array(vols, dtype=float) if vols is not None
         else np.full(len(c), 10_000.0))
    return pd.DataFrame({"open": c, "high": c * 1.002, "low": c * 0.998,
                         "close": c, "volume": v}, index=idx.tz_convert("UTC"))


# --- the wall -----------------------------------------------------------------

def test_the_cutoff_index_counts_bars_at_or_before_it():
    df = frame([10.0] * 120)                    # 04:00 .. 05:59
    local = df.index.tz_convert(ET)
    assert U.cutoff_index(local, 5, 0) == 61    # 04:00..05:00 inclusive


def test_a_cutoff_before_the_first_bar_yields_nothing():
    df = frame([10.0] * 120)
    local = df.index.tz_convert(ET)
    assert U.cutoff_index(local, 3, 0) == 0


def test_NO_criterion_reads_a_bar_after_the_cutoff():
    """The decisive test. Replace everything past the wall with noise; every
    criterion must be bit-identical. A criterion that leaked would rank names
    by what they were about to do."""
    rng = np.random.default_rng(0)
    c = list(10.0 + np.cumsum(rng.normal(0, 0.02, 200)))
    v = list(np.abs(rng.normal(20_000, 4_000, 200)))
    df = frame(c, v)
    k = 61
    before = U.measure(df, k, 9.5)

    tampered = df.copy()
    for col in ("open", "high", "low", "close", "volume"):
        vals = tampered[col].to_numpy(dtype=float, copy=True)
        vals[k:] = rng.normal(5_000, 2_000, len(vals) - k)
        tampered[col] = vals
    after = U.measure(tampered, k, 9.5)

    for key in before:
        a, b = before[key], after[key]
        if a != a and b != b:
            continue
        assert a == b, f"criterion {key} moved when the FUTURE moved"


def test_a_run_starting_BEFORE_the_cutoff_is_not_counted():
    """Otherwise the criterion is being credited with a move already underway
    when it was measured."""
    c = [10.0] * 5 + [10.0 * (1 + 0.02 * i) for i in range(1, 11)] + [12.0] * 120
    df = frame(c)
    runs_late, _ = U.outcome(df, 60, (8.0, 15), 5.0)
    runs_all, _ = U.outcome(df, 0, (8.0, 15), 5.0)
    assert runs_all >= 1
    assert runs_late == 0


def test_a_run_starting_AFTER_the_cutoff_is_counted():
    c = ([10.0] * 70 + [10.0 * (1 + 0.02 * i) for i in range(1, 11)]
         + [12.0] * 80)
    df = frame(c)
    runs, bars = U.outcome(df, 61, (8.0, 15), 5.0)
    assert runs >= 1 and bars > 0


def test_a_run_may_FINISH_after_the_session_window_it_started_in():
    """Only the start is walled. Truncating the move would be a different
    measurement than the census made."""
    c = [10.0] * 70 + [10.0] * 5 + [11.0] * 40
    df = frame(c)
    runs, _ = U.outcome(df, 61, (8.0, 15), 5.0)
    assert runs >= 1


def test_eligible_bars_exclude_the_tail_that_cannot_complete_a_run():
    df = frame([10.0] * 200)
    _, bars = U.outcome(df, 61, (8.0, 15), 5.0)
    assert bars == 200 - 15 - 61


# --- the criteria themselves --------------------------------------------------

def test_dollar_volume_is_price_times_cumulative_volume():
    df = frame([10.0] * 100, [1_000.0] * 100)
    m = U.measure(df, 50, None)
    assert m["dollar_vol"] == pytest.approx(10.0 * 50 * 1_000.0)
    assert m["volume"] == pytest.approx(50_000.0)


def test_bars_traded_ignores_size_and_counts_only_prints():
    v = [0.0] * 30 + [5_000.0] * 30
    df = frame([10.0] * 60, v)
    assert U.measure(df, 60, None)["bars_traded"] == 30.0


def test_the_gap_is_against_the_PRIOR_session_close():
    df = frame([11.0] * 60)
    assert U.measure(df, 60, 10.0)["gap_pct"] == pytest.approx(10.0)


def test_a_missing_prior_close_yields_nan_not_zero():
    """Zero would rank a name with no history alongside a flat one."""
    m = U.measure(frame([11.0] * 60), 60, None)
    assert m["gap_pct"] != m["gap_pct"]


def test_too_few_bars_before_the_cutoff_is_refused():
    assert U.measure(frame([10.0] * 60), 5, None) is None


def test_an_out_of_range_price_is_refused():
    assert U.measure(frame([0.20] * 60), 60, None) is None
    assert U.measure(frame([50_000.0] * 60), 60, None) is None


# --- ranking ------------------------------------------------------------------

def rows(vals, runs, bars=100):
    return [{**{c: 0.0 for c in U.CRITERIA}, "dollar_vol": v,
             "runs": r, "bars": bars, "symbol": f"S{i}"}
            for i, (v, r) in enumerate(zip(vals, runs))]


def test_the_top_N_are_the_HIGHEST_on_the_criterion():
    got = U.rank_and_slice(rows([1, 2, 3, 4, 5], [0, 0, 0, 0, 9]), "dollar_vol")
    assert got[5][0] == 9
    got2 = U.rank_and_slice(rows([1, 2, 3, 4, 5], [9, 0, 0, 0, 0]),
                            "dollar_vol")
    assert got2[5][0] == 9


def test_a_smaller_watchlist_is_a_subset_of_a_larger_one():
    r = rows(list(range(300)), [1] * 300)
    got = U.rank_and_slice(r, "dollar_vol")
    counts = [got[t][0] for t in U.TOP_N]
    assert counts == sorted(counts), counts


def test_ranking_skips_a_criterion_that_is_nan_for_that_name():
    """A name with no prior close must not be ranked on gap as though it had
    gapped zero."""
    r = rows([1.0, 2.0, 3.0], [0, 0, 5])
    r[2]["gap_pct"] = float("nan")
    r[0]["gap_pct"] = 50.0
    r[1]["gap_pct"] = 10.0
    got = U.rank_and_slice(r, "gap_pct")
    assert got[5][0] == 0, "the NaN row was ranked anyway"


# --- what the report must say -------------------------------------------------

def totals_for_report():
    return {c: {t: (10, 1000) for t in U.TOP_N} for c in U.CRITERIA}


def text_of():
    return "\n".join(U.render(totals_for_report(), (100, 100_000), 10, 500,
                              {}, "05:00", (8.0, 15), 5.0, 1.0))


def test_the_report_states_the_cutoff_and_what_it_walls():
    t = text_of()
    assert "05:00 ET" in t
    assert "AT OR BEFORE" in t and "START after it" in t


def test_EVERY_criterion_appears():
    t = text_of()
    for c in U.CRITERIA:
        assert c in t, f"{c} omitted"


def test_the_report_names_price_as_the_CONTROL():
    """Without a control there is no way to tell a real lift from what this
    method produces out of nothing."""
    t = text_of()
    assert "control" in t.lower()
    assert "not against 1.00x" in t


def test_the_report_says_it_is_not_the_screen_itself():
    t = text_of()
    assert "Not the screen itself" in t
    assert "prior_close" in t


def test_the_report_frames_the_question_as_a_check_on_the_earlier_claim():
    t = text_of()
    assert "20.2x" in t
    assert "marginal" in t


def test_the_holdout_is_named_as_untouched():
    assert "holdout.json" in text_of()


def test_an_empty_run_is_named_not_scored():
    t = "\n".join(U.render(totals_for_report(), (0, 0), 0, 0, {}, "05:00",
                           (8.0, 15), 5.0, 1.0))
    assert "NOTHING TO RANK" in t
