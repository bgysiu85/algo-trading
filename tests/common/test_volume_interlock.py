#!/usr/bin/env python3
"""Does the interlock census count the shape it claims to?

This measures a rule against itself, which is the easiest kind of module to
write so that it always agrees with whoever wrote it. Three specific ways it
could be quietly wrong:

  * counting WARM-UP bars, where trail_avg is undefined and c_floor is False
    for a reason that has nothing to do with the interlock. That inflates
    every figure and would make a rare interlock look routine.
  * counting a bar as a hand-off when the two bars are not adjacent, or when
    the shape runs the other way.
  * recomputing the entry conditions here instead of reading the ones
    `signals()` emits, producing a second implementation of the rule that
    agrees until one of them changes.

The gate is also DERIVED, not chosen, so a test pins that it still falls out
of the strategy's own constants.
"""
from __future__ import annotations

from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from common import volume_interlock as V
from strategy.mcl import mcl as MCL

ET = ZoneInfo("America/New_York")


def frame(rows):
    """rows = [(c_macd, c_mfi, c_rsi, c_vol, c_floor, prev_vol, trail_avg, vol)]"""
    idx = pd.DatetimeIndex([
        pd.Timestamp(datetime.combine(pd.Timestamp("2026-09-11").date(),
                                      dtime(7, 0), tzinfo=ET))
        + timedelta(minutes=i) for i in range(len(rows))])
    cols = ["c_macd", "c_mfi", "c_rsi", "c_vol", "c_floor", "prev_vol",
            "trail_avg", "volume"]
    d = pd.DataFrame(rows, columns=cols, index=idx)
    for c in cols[:5]:
        d[c] = d[c].astype(bool)
    d["entry"] = d["c_macd"] & d["c_mfi"] & d["c_rsi"] & d["c_vol"] \
        & d["c_floor"]
    return d


# --- the gate is derived ------------------------------------------------------

def test_the_gate_falls_out_of_the_strategys_own_constants():
    """1.5x is not a number chosen here. If VOL_MULTIPLE or FLOOR_FRACTION
    move, the window moves with them."""
    assert V.opens_at(MCL) == pytest.approx(MCL.VOL_MULTIPLE
                                            * MCL.FLOOR_FRACTION)

    class Fake:
        VOL_MULTIPLE, FLOOR_FRACTION = 4.0, 0.25
    assert V.opens_at(Fake) == pytest.approx(1.0)


def test_the_conditions_are_READ_not_recomputed():
    """A frame missing a condition column must raise, not silently fall back
    to computing it -- a second implementation of the entry rule is how the
    live path and the backtest drifted apart for three days."""
    d = frame([(1, 1, 1, 0, 1, 100.0, 200.0, 500.0)]).drop(columns=["c_floor"])
    with pytest.raises(ValueError, match="c_floor"):
        V.per_session(d, MCL)


# --- warm-up must not count ---------------------------------------------------

def test_bars_with_no_trailing_average_are_not_judgeable():
    """Early in a session trail_avg is NaN. c_floor is False there for a
    reason that is not the interlock."""
    d = frame([(1, 1, 1, 1, 0, 100.0, float("nan"), 500.0),
               (1, 1, 1, 1, 0, 100.0, 200.0, 100.0)])
    r = V.per_session(d, MCL)
    assert r["judgeable"] == 1, "the NaN bar must not be judged"


def test_a_zero_trailing_average_is_not_judgeable_either():
    d = frame([(1, 1, 1, 1, 0, 100.0, 0.0, 500.0)])
    assert V.per_session(d, MCL)["judgeable"] == 0


def test_a_bar_failing_a_NON_volume_condition_is_not_judgeable():
    """The question is about the volume pair. A bar MACD already rejected says
    nothing about whether the volume window was open."""
    d = frame([(0, 1, 1, 1, 0, 100.0, 200.0, 100.0)])
    assert V.per_session(d, MCL)["judgeable"] == 0


# --- 1. the empty window ------------------------------------------------------

def test_an_empty_window_is_counted():
    """volume 100 against trail_avg 200 is 0.5x, well under 1.5x -- no
    prev_vol could satisfy both conditions."""
    d = frame([(1, 1, 1, 0, 0, 100.0, 200.0, 100.0)])
    r = V.per_session(d, MCL)
    assert r["judgeable"] == 1 and r["window_empty"] == 1


def test_an_OPEN_window_is_not_counted_as_empty():
    """volume 400 against trail_avg 200 is 2.0x: the window exists, and a bar
    that still failed did so on timing, not arithmetic."""
    d = frame([(1, 1, 1, 0, 0, 100.0, 200.0, 400.0)])
    r = V.per_session(d, MCL)
    assert r["judgeable"] == 1 and r["window_empty"] == 0


def test_exactly_at_the_gate_is_OPEN_not_empty():
    """1.5x is where the window opens. A boundary that excluded its own value
    would be the defect this project keeps finding."""
    d = frame([(1, 1, 1, 0, 0, 100.0, 200.0, 300.0)])
    assert V.per_session(d, MCL)["window_empty"] == 0


# --- 2. the hand-off ----------------------------------------------------------

def test_the_TNON_shape_is_counted():
    """07:35 clears the multiple and fails the floor; 07:36 does the reverse."""
    d = frame([(1, 1, 1, 1, 0, 20_000.0, 45_000.0, 158_000.0),
               (1, 1, 1, 0, 1, 158_000.0, 45_000.0, 169_000.0)])
    assert V.per_session(d, MCL)["handoff"] == 1


def test_the_REVERSE_shape_is_not_a_hand_off():
    d = frame([(1, 1, 1, 0, 1, 158_000.0, 45_000.0, 169_000.0),
               (1, 1, 1, 1, 0, 20_000.0, 45_000.0, 158_000.0)])
    assert V.per_session(d, MCL)["handoff"] == 0


def test_non_adjacent_bars_are_not_a_hand_off():
    d = frame([(1, 1, 1, 1, 0, 20_000.0, 45_000.0, 158_000.0),
               (1, 1, 1, 1, 1, 50_000.0, 45_000.0, 160_000.0),
               (1, 1, 1, 0, 1, 158_000.0, 45_000.0, 169_000.0)])
    assert V.per_session(d, MCL)["handoff"] == 0


def test_the_last_bar_cannot_hand_off_to_a_bar_that_does_not_exist():
    d = frame([(1, 1, 1, 1, 0, 20_000.0, 45_000.0, 158_000.0)])
    assert V.per_session(d, MCL)["handoff"] == 0


def test_a_hand_off_in_warm_up_is_not_counted():
    d = frame([(1, 1, 1, 1, 0, 20_000.0, float("nan"), 158_000.0),
               (1, 1, 1, 0, 1, 158_000.0, 45_000.0, 169_000.0)])
    assert V.per_session(d, MCL)["handoff"] == 0


# --- reporting ----------------------------------------------------------------

def rows_for(n=3, judge=10, empty=4, hand=2):
    return [{"bars": 300, "judgeable": judge, "window_empty": empty,
             "handoff": hand, "entries": 1,
             "ratios": [0.5, 0.9, 1.2, 1.5, 2.0, 3.0, 4.0, 6.0, 9.0, 12.0],
             "symbol": f"S{i}", "date": "2026-09-11"} for i in range(n)]


def test_an_empty_population_is_named_not_scored():
    """0 judgeable bars is a population with nothing in it, not a finding that
    the interlock never binds."""
    rows = [{"bars": 5, "judgeable": 0, "window_empty": 0, "handoff": 0,
             "entries": 0, "ratios": [], "symbol": "A", "date": "d"}]
    text = "\n".join(V.render(rows, "p.json", MCL, 0, 0.1))
    assert "NOTHING JUDGEABLE" in text
    assert "not a finding about the interlock" in text


def test_the_report_names_its_population():
    text = "\n".join(V.render(rows_for(), "var/state/traded_pairs.json",
                              MCL, 0, 0.1))
    assert "var/state/traded_pairs.json" in text
    assert "a different pairs file is a" in text


def test_untested_symbol_days_are_counted_not_dropped():
    text = "\n".join(V.render(rows_for(), "p.json", MCL, 41, 0.1))
    assert "41" in text and "NOT" in text


def test_the_report_refuses_to_claim_profit():
    text = "\n".join(V.render(rows_for(), "p.json", MCL, 0, 0.1))
    assert "does not say a trade would have been profitable" in text
    assert "does not say the interlock is a defect" in text


# --- against the REAL signals(), not a hand-built frame ------------------------

def test_it_runs_end_to_end_on_mcl_signals_output():
    """Every test above builds the condition columns by hand. That is exactly
    the setup that let an unreachable attribute ship in `regular_close`: the
    only path that could break was the one no test took. This one takes it."""
    import numpy as np

    rng = np.random.default_rng(7)
    n = 220
    t0 = pd.Timestamp(datetime.combine(pd.Timestamp("2026-09-11").date(),
                                       dtime(4, 0), tzinfo=ET))
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=i) for i in range(n)])
    c = 7.0 + np.cumsum(rng.normal(0, 0.01, n))
    v = rng.integers(4000, 9000, n).astype(float)
    v[150] = v[149] * 8          # a burst after a quiet bar: the TNON shape
    df = pd.DataFrame({"open": c, "high": c * 1.002, "low": c * 0.998,
                       "close": c, "volume": v}, index=idx)

    sig = MCL.signals(df)
    r = V.per_session(sig, MCL)
    assert r["bars"] == n
    assert r["judgeable"] > 0, "no judgeable bar -- the fixture proves nothing"
    assert len(r["ratios"]) == r["judgeable"]
    assert all(x == x for x in r["ratios"]), "a NaN ratio reached the output"


def test_the_column_contract_with_signals_is_pinned():
    """If signals() stops emitting one of these, this module must fail loudly
    rather than measure something else."""
    import numpy as np

    n = 120
    t0 = pd.Timestamp(datetime.combine(pd.Timestamp("2026-09-11").date(),
                                       dtime(4, 0), tzinfo=ET))
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=i) for i in range(n)])
    c = np.full(n, 7.0)
    df = pd.DataFrame({"open": c, "high": c, "low": c, "close": c,
                       "volume": np.full(n, 5000.0)}, index=idx)
    sig = MCL.signals(df)
    for col in ["c_macd", "c_mfi", "c_rsi", "c_vol", "c_floor", "prev_vol",
                "trail_avg", "volume"]:
        assert col in sig.columns, f"signals() no longer emits {col}"
