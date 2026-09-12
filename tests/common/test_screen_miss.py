#!/usr/bin/env python3
"""Why the simulated screen missed a live name.

The measurement replaces an inference -- a capture ratio measured on the missed
names, from which a cause would have been guessed. Every input is on disk, so
each name is simply asked which clause it failed.

The failure that matters is calling a name eligible when it never satisfied the
clauses TOGETHER: a name can reach +25% at 04:10 and the volume floor at 08:40
and never once hold both, and per-clause maxima would report it as pushed out
by the rank cap.
"""
from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from common import screen_miss as M
from common.screen_sim import ScreenConfig, accumulate

ET = ZoneInfo("America/New_York")
D = date(2026, 3, 2)
CFG = ScreenConfig()


def bars(spec, symbol="AAA"):
    """spec = [(minute offset from 04:00, close, volume)]"""
    b = pd.Timestamp(datetime.combine(D, dtime(4, 0), tzinfo=ET))
    idx = pd.DatetimeIndex([(b + timedelta(minutes=m)).tz_convert("UTC")
                            for m, _c, _v in spec])
    return pd.DataFrame({"symbol": symbol,
                         "close": [c for _m, c, _v in spec],
                         "volume": [float(v) for _m, _c, v in spec]}, index=idx)


def run(spec, prior, symbol="AAA", cadence=60):
    return M.diagnose(accumulate(bars(spec), CFG), symbol, prior, D, CFG,
                      cadence)


# --- the causes -------------------------------------------------------------

def test_a_name_absent_from_the_tape_is_named_as_such():
    """No threshold change reaches these, and a capture measurement would not
    have surfaced it at all."""
    assert run([(0, 5.0, 99_999)], 4.0, symbol="ZZZ")["why"] == M.NOT_ON_TAPE


def test_a_name_with_no_prior_close_is_dropped_before_any_clause():
    assert run([(0, 5.0, 99_999)], None)["why"] == M.NO_PRIOR
    assert run([(0, 5.0, 99_999)], 0.0)["why"] == M.NO_PRIOR


def test_a_name_short_only_on_volume_is_attributed_to_VOLUME():
    """+25%, in band, and never reaches the scaled floor. This is the capture
    hypothesis and the one the report sizes."""
    got = run([(m, 5.0, 100) for m in range(30)], 4.0)
    assert got["why"] == "VOLUME"
    assert got["change"] == pytest.approx(25.0)
    assert got["volume"] < CFG.volume_min_on_tape


def test_a_name_short_only_on_change_is_attributed_to_CHANGE():
    got = run([(m, 4.2, 20_000) for m in range(30)], 4.0)
    assert got["why"] == "CHANGE"
    assert got["volume"] >= CFG.volume_min_on_tape


def test_a_name_out_of_the_price_band_is_attributed_to_PRICE():
    got = run([(m, 60.0, 20_000) for m in range(30)], 40.0)
    assert "PRICE" in got["why"]


# --- the simultaneity rule --------------------------------------------------

def test_clauses_met_at_different_times_are_not_counted_as_eligible():
    """+25% at 04:00 on thin volume, then the volume arrives after the price
    has fallen back. Per-clause maxima would call this RANK ONLY."""
    spec = ([(0, 5.0, 10)]                       # +25%, almost no volume
            + [(m, 4.0, 30_000) for m in range(1, 10)])   # volume, 0% change
    got = run(spec, 4.0)
    assert got["why"] != M.RANK_ONLY
    assert got["why"] == "NEVER SIMULTANEOUS"


def test_a_name_that_did_pass_everything_at_one_tick_is_RANK_ONLY():
    """It cleared all three together and still did not appear, so the top-40
    cap pushed it out. Counting this as a clause failure would overstate them."""
    got = run([(m, 5.0, 30_000) for m in range(10)], 4.0)
    assert got["why"] == M.RANK_ONLY


def test_a_bar_counts_only_once_it_has_closed():
    """`visible_at <= t` is the same blindness rule screen_accumulated uses.
    A cadence that read the forming bar would find volume a minute early."""
    spec = [(m, 5.0, 30_000) for m in range(10)]
    acc = accumulate(bars(spec), CFG)
    assert (acc["visible_at"] > acc.index).all()


# --- the report -------------------------------------------------------------

def out(rows, n=4):
    return "\n".join(M.render(rows, CFG, n, 1.0))


def test_the_report_sizes_the_volume_shortfall_rather_than_asserting_it():
    rows = [{"date": "2026-09-10", "symbol": f"S{i}", "why": "VOLUME",
             "change": 30.0, "volume": CFG.volume_min_on_tape * 0.4,
             "close_at_best": 5.0} for i in range(4)]
    o = out(rows)
    assert "failed ONLY the volume floor" in o
    assert "40% of the scaled threshold" in o
    assert "capture_sensitivity" in o


def test_names_not_on_the_tape_are_called_out_as_unfixable_by_a_threshold():
    rows = [{"date": "2026-09-10", "symbol": "X", "why": M.NOT_ON_TAPE}]
    o = out(rows)
    assert "NEVER PRINT on this tape" in o
    assert "No" in o and "threshold change reaches these" in o


def test_rank_only_names_are_excluded_from_the_threshold_argument():
    rows = [{"date": "2026-09-10", "symbol": "X", "why": M.RANK_ONLY,
             "change": 30.0, "volume": 90_000.0, "close_at_best": 5.0}]
    o = out(rows)
    assert "pushed out by the top-40 cap" in o
    assert "must not be counted as evidence about the" in o


def test_the_scaled_threshold_and_its_provenance_are_stated():
    o = out([{"date": "d", "symbol": "X", "why": M.NOT_ON_TAPE}])
    assert f"{CFG.volume_min_on_tape:,}" in o
    assert f"{CFG.capture:.3f}" in o


def test_nothing_missed_says_so_rather_than_printing_an_empty_table():
    assert "surfaced every live name" in out([])


def test_the_report_refuses_to_be_read_as_a_fix():
    rows = [{"date": "d", "symbol": "X", "why": "VOLUME", "change": 30.0,
             "volume": 1000.0, "close_at_best": 5.0}]
    o = out(rows)
    assert "Not a fix" in o
    assert "not tuned until" in o


def test_a_name_with_no_measurement_prints_a_dash_not_a_zero():
    """NOT ON THIS TAPE and NO PRIOR CLOSE carry no bests. A 0 or a -inf in
    those columns would put a figure where there is no measurement."""
    o = out([{"date": "2026-09-10", "symbol": "X", "why": M.NOT_ON_TAPE},
             {"date": "2026-09-10", "symbol": "Y", "why": M.NO_PRIOR}])
    line = [ln for ln in o.splitlines() if " X " in ln][0]
    assert "-" in line and "0.00" not in line and "inf" not in line
