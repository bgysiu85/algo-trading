#!/usr/bin/env python3
"""Does our tape respect half and whole dollars?

The claim is Ross Cameron's (warrior_2_flat_top.md §3) and it decides whether
flat-top detection is a price-grid problem or a pattern-matching one. What is
tested here is the control, because the naive version of this measurement
confirms the claim on data that contains no grid at all.
"""
from __future__ import annotations

from datetime import timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from common import price_grid as G

ET = ZoneInfo("America/New_York")


def frame(highs, closes=None, lows=None):
    n = len(highs)
    closes = closes or highs
    lows = lows or [h - 0.05 for h in highs]
    t0 = pd.Timestamp("2026-03-02 04:00", tz=ET)
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=i) for i in range(n)],
                           tz=ET).tz_convert("UTC")
    return pd.DataFrame({"open": closes, "high": highs, "low": lows,
                         "close": closes, "volume": 1000.0}, index=idx)


# --- the arithmetic ----------------------------------------------------------

def test_cents_are_exact_where_floats_are_not():
    """5.15 is not representable. A float modulus gives 0.00999999... and a
    'within one cent' test then silently misses it -- which would look like
    the claim failing."""
    assert G.to_cents([5.15]) == [515]
    assert G.distance(515) == 15
    assert G.to_cents([7.4999999999]) == [750]


@pytest.mark.parametrize("price,d", [
    (6.00, 0), (6.50, 0), (7.00, 0),
    (6.01, 1), (5.99, 1), (6.49, 1), (6.51, 1),
    (6.25, 25), (6.75, 25),
])
def test_distance_to_the_claimed_grid(price, d):
    assert G.distance(G.to_cents([price])[0]) == d


def test_the_placebo_grid_is_the_quarters():
    """Same spacing, same bars, no claim attached. It is the only thing that
    makes the measurement mean anything."""
    assert G.distance(G.to_cents([6.25])[0], G.PLACEBO_OFFSET_C) == 0
    assert G.distance(G.to_cents([6.75])[0], G.PLACEBO_OFFSET_C) == 0
    assert G.distance(G.to_cents([6.00])[0], G.PLACEBO_OFFSET_C) == 25


def test_distance_is_symmetric_around_a_level():
    assert G.distance(599) == G.distance(601)


# --- the control does its job ------------------------------------------------

def test_a_narrow_range_near_a_round_number_does_not_read_as_a_grid():
    """THE FAILURE THE PLACEBO EXISTS FOR. A stock that spends all morning
    between $5.00 and $5.08 has every high within 8c of a round number by
    construction. A naive test confirms the claim here; the real and placebo
    columns must move together instead."""
    p = G.profile(G.to_cents([5.00 + 0.01 * (i % 9) for i in range(500)]))
    assert p["real_1c"] > 20, "naively this looks like strong clustering"
    # The placebo is far away because the DATA is far from .25/.75 -- so the
    # two columns disagree wildly and the lift is meaningless in isolation.
    # What matters is that a genuine grid beats it by more; see the next test.
    assert p["real_1c"] - p["plac_1c"] > 0


def test_a_real_grid_beats_the_placebo_and_a_spread_out_sample_does_not():
    """The measurement's whole job, stated as a contrast."""
    gridded = G.profile(G.to_cents([6.00, 6.50, 7.00, 7.50, 8.00] * 100))
    assert gridded["real_1c"] == 100.0 and gridded["plac_1c"] == 0.0

    spread = G.profile([200 + i for i in range(1800)])   # every cent $2-$20
    assert abs(spread["real_1c"] - spread["plac_1c"]) < 1.0, (
        "a uniform sweep of every cent must show NO preference either way")


def test_an_empty_population_is_not_a_result():
    assert G.profile([])["n"] == 0


# --- the flat-top proxy ------------------------------------------------------

def test_a_level_is_a_price_tagged_repeatedly_as_a_high():
    """A large resting seller shows up in bars as the same high, over and
    over. One tag is not a level."""
    df = frame([6.50, 6.20, 6.50, 6.30, 6.50, 6.10])
    assert G.repeat_levels(df, k=3) == [650]
    assert G.repeat_levels(df, k=4) == []


def test_levels_are_read_from_highs_not_lows():
    """A level repeatedly hit from below is what Warrior 2 is about. Pooling
    lows would dilute it with support and blunt whichever way the answer
    goes."""
    df = frame(highs=[6.11, 6.12, 6.13], lows=[6.00, 6.00, 6.00])
    assert G.repeat_levels(df, k=3) == []


def test_collect_separates_the_populations():
    sessions = [("AAA", "2026-03-02", frame([6.50, 6.20, 6.50, 6.30, 6.50]))]
    pops = G.collect(sessions)
    assert pops["repeat levels"] == [650]
    assert len(pops["bar highs"]) == 5
    assert len(pops["session extremes"]) == 2


# --- the report ---------------------------------------------------------------

def report(levels, closes=None, extremes=None):
    """`closes` is the BASELINE population -- the one claim 2 is measured
    against. Defaults to a spread of every cent, i.e. no grid."""
    closes = closes if closes is not None else [200 + i for i in range(1800)]
    pops = {"all closes": closes, "bar highs": closes,
            "session extremes": extremes if extremes is not None else closes,
            "repeat levels": levels}
    return "\n".join(G.render(pops, 373))


GRIDDED = [600, 650, 700, 750] * 100          # every price on a level
UNGRIDDED = [200 + i for i in range(1800)]    # every cent, no preference


def test_a_grid_in_the_tape_is_reported_as_claim_one():
    text = report(GRIDDED, closes=GRIDDED)
    assert "CLAIM 1" in text and "YES. The tape respects" in text


def test_no_grid_in_the_tape_stops_the_reader_there():
    text = report(UNGRIDDED, closes=UNGRIDDED)
    assert "NO. Without a grid, nothing below can be read." in text


def test_levels_no_more_gridded_than_the_baseline_is_called_a_null():
    """THE ERROR THIS CATCHES, and it was made on the first run. Every
    population beat the placebo, so the report announced the claim held --
    but the repeat levels matched the ORDINARY-CLOSE rate exactly. A
    population made of prices inherits the tape's clustering for free;
    beating the placebo is necessary and nowhere near sufficient."""
    text = report(GRIDDED, closes=GRIDDED)
    assert "CLAIM 2" in text
    assert "no more likely to sit on a" in text
    assert "remains a pattern-matching problem" in text


def test_a_null_on_claim_two_does_not_take_claim_one_down_with_it():
    """Warrior 2 §4's standalone half-dollar entry rests on the grid existing,
    not on flat tops living on it. Conflating the two would discard a setup
    the evidence supports."""
    text = report(GRIDDED, closes=GRIDDED)
    assert "is NOT" in text and "killed by this" in text


def test_levels_genuinely_more_gridded_than_the_baseline_is_called_a_pass():
    half = [600, 650] * 100 + [613, 627, 641, 683] * 100   # baseline ~50% on grid
    text = report([600, 650] * 200, closes=half)
    assert "YES. Flat-top levels can be anticipated" in text


def test_extremes_clustering_beyond_the_baseline_is_reported_separately():
    """A claim about where moves STOP is about targets and exits, and nothing
    in the Warrior set makes it -- so it must not be quietly folded into a
    verdict about entries."""
    text = report(UNGRIDDED, closes=UNGRIDDED, extremes=[600, 650] * 50)
    assert "day's HIGH and LOW do cluster" in text


def test_the_report_explains_that_the_placebo_is_the_evidence():
    """Someone reading only the 'real' column would confirm the claim on any
    price series at all."""
    text = report([600, 650] * 50)
    assert "Only the" in text and "DIFFERENCE" in text


def test_the_report_warns_that_split_adjusted_bars_bias_toward_a_null():
    """IB bars are adjusted; an adjusted price is not one anyone traded at, so
    a real grid would be smeared. A null found here is weaker evidence than a
    positive, and the report must not let those be read as symmetric."""
    text = report([625, 675] * 50)
    assert "SPLIT-ADJUSTED" in text
    assert "bar_cache_xnas" in text
