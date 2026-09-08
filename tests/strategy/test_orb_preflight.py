#!/usr/bin/env python3
"""ORB's pre-flight measurements.

These run BEFORE any entry logic exists, which is the whole point: fifteen of
ORB's twenty parameters are guesses, and every one set from data here is one
that does not get set from a result later. So the measurements themselves have
to be right, and the definitional traps in orb_strategy_spec.md section 4 are
exactly the kind that return a plausible wrong answer rather than an error.
"""
from __future__ import annotations

import pandas as pd
import pytest

from strategy.orb import preflight as P

DAY = "2026-03-16"


def session(bars, start="09:30"):
    """bars: list of (open, high, low, close[, volume]) at one-minute spacing
    from `start` ET on DAY."""
    idx = pd.date_range(f"{DAY} {start}", periods=len(bars), freq="1min",
                        tz="America/New_York")
    rows = [(b if len(b) == 5 else (*b, 1000)) for b in bars]
    return pd.DataFrame(rows, index=idx,
                        columns=["open", "high", "low", "close", "volume"])


def flat(n, px=10.0, start="09:30"):
    return session([(px, px, px, px)] * n, start=start)


# --- the range ---------------------------------------------------------------

def test_the_range_is_wick_to_wick_over_the_window_only():
    """Spec section 4: wick to wick, not body to body -- and the window is the
    first N minutes, so a later high must not widen it."""
    bars = [(10, 11, 9, 10)] * 15 + [(10, 20, 5, 10)] * 10
    r = P.measure_day(session(bars), "AAA", DAY, "survivors", 15)
    assert r.status == "OK"
    assert r.orb_high == 11 and r.orb_low == 9


def test_a_partial_range_is_skipped_and_counted_not_traded():
    """A range built from a handful of bars is not the first fifteen minutes of
    trading, it is whatever printed."""
    r = P.measure_day(flat(4), "AAA", DAY, "survivors", 15)
    assert r.status == "FEW_BARS" and r.orb_high is None


def test_a_range_with_no_width_is_too_narrow():
    r = P.measure_day(flat(20), "AAA", DAY, "survivors", 15)
    assert r.status == "TOO_NARROW"


def test_an_enormous_range_is_refused_rather_than_traded_late():
    """Spec 4.3: if the first fifteen minutes already contained the day's move,
    a break of it is a late entry into a vertical."""
    bars = [(10, 20, 9, 10)] * 15 + [(10, 21, 10, 21)] * 5
    r = P.measure_day(session(bars), "AAA", DAY, "survivors", 15)
    assert r.status == "TOO_WIDE"


def test_no_rth_bars_is_its_own_status():
    r = P.measure_day(session([]).iloc[:0], "AAA", DAY, "survivors", 15)
    assert r.status == "NO_RTH"


def test_the_window_length_follows_orb_minutes():
    """5, 15 and 30 must slice different windows -- the parameter has to do
    something, and a fixed 15 would look identical on a quiet open."""
    bars = ([(10, 10.5, 9.5, 10)] * 5 + [(10, 12, 8, 10)] * 10
            + [(10, 10, 10, 10)] * 20)
    five = P.measure_day(session(bars), "AAA", DAY, "survivors", 5)
    fifteen = P.measure_day(session(bars), "AAA", DAY, "survivors", 15)
    assert five.orb_high == 10.5 and fifteen.orb_high == 12


# --- triggers ----------------------------------------------------------------

def test_the_trigger_is_a_CLOSE_beyond_the_level_not_a_touch():
    """Spec 5.1: a resting order fills on any wick; a close-based rule requires
    the market to hold the level. On this universe that is a large difference,
    and the project has been burnt by touch-based rules before."""
    # A 5-minute bar that WICKS to 12 but closes back at 10.
    bars = [(10, 11, 9, 10)] * 15 + [(10, 12, 10, 10)] * 5
    r = P.measure_day(session(bars), "AAA", DAY, "survivors", 15)
    assert r.status == "OK"
    assert not r.up_trigger, "a wick beyond the high triggered an entry"


def test_a_close_beyond_the_level_does_trigger():
    bars = [(10, 11, 9, 10)] * 15 + [(11, 12, 11, 11.5)] * 5
    r = P.measure_day(session(bars), "AAA", DAY, "survivors", 15)
    assert r.up_trigger and r.up_trigger_bar == 0


def test_the_downside_break_is_measured_even_though_it_is_not_traded():
    """Spec 5.4: long only discards roughly half the sources' signals, so the
    short side is measured and reported. If the edge is there, that is worth
    knowing before the borrow feasibility work, not after."""
    bars = [(10, 11, 9, 10)] * 15 + [(9, 9, 8, 8.5)] * 5
    r = P.measure_day(session(bars), "AAA", DAY, "survivors", 15)
    assert r.down_trigger and not r.up_trigger


def test_how_far_past_the_level_it_closed_is_recorded():
    """This is what sets ENTRY_BUFFER_PCT, which is 0.0 until measured."""
    bars = [(10, 10.0, 9, 10)] * 15 + [(10, 10.01, 10, 10.005)] * 5
    r = P.measure_day(session(bars), "AAA", DAY, "survivors", 15)
    assert r.up_trigger
    assert r.up_close_over_pct == pytest.approx(0.05, abs=0.01)
    assert r.near_level is True


# --- entry and R -------------------------------------------------------------

def test_entry_is_the_next_bars_open_not_the_trigger_close():
    """The trigger close is a price that has already gone."""
    bars = ([(10, 11, 9, 10)] * 15
            + [(11, 12, 11, 11.5)] * 5          # trigger bar, closes 11.5
            + [(11.8, 12, 11.7, 11.9)] * 5)     # next bar opens 11.8
    r = P.measure_day(session(bars), "AAA", DAY, "survivors", 15)
    assert r.entry_px == 11.8


def test_a_trigger_on_the_last_bar_yields_no_entry_rather_than_a_guess():
    bars = [(10, 11, 9, 10)] * 15 + [(11, 12, 11, 11.5)] * 5
    r = P.measure_day(session(bars), "AAA", DAY, "survivors", 15)
    assert r.up_trigger and r.entry_px is None


def test_the_three_stop_modes_give_different_R_and_opposite_is_the_widest():
    """Spec 6: expect `opposite` to be structurally enormous on this universe
    and CHECK it. VW9's structure stop produced a median R of 9.4% of price and
    nobody knew until after the study."""
    bars = ([(10, 12, 8, 10)] * 15                 # range 8..12, 50% wide
            + [(12, 13, 12, 12.5)] * 5             # trigger, low 12
            + [(12.6, 13, 12.5, 12.8)] * 5)
    r = P.measure_day(session(bars), "AAA", DAY, "survivors", 30)
    assert r.status == "TOO_WIDE"                  # 50% > MAX_RANGE_PCT
    bars = ([(10, 10.5, 9.5, 10)] * 15
            + [(10.6, 11, 10.4, 10.8)] * 5
            + [(10.9, 11, 10.8, 10.95)] * 5)
    r = P.measure_day(session(bars), "AAA", DAY, "survivors", 15)
    assert r.r_structure_pct < r.r_opposite_pct, (
        "the opposite-side stop must be wider than the structure stop -- if it "
        "is not, the range is being measured wrong")


# --- the population split ----------------------------------------------------

def test_the_population_label_is_carried_through():
    """10.2b compares survivors against rejects. A row that loses its label
    cannot be on either side of that comparison."""
    bars = [(10, 11, 9, 10)] * 15 + [(11, 12, 11, 11.5)] * 5
    r = P.measure_day(session(bars), "AAA", DAY, "rejected", 15)
    assert r.population == "rejected"


# --- the honesty about RVOL --------------------------------------------------

def test_rvol_is_reported_as_not_computable_rather_than_approximated():
    """The cache holds three sessions; relative_volume_10d_calc needs ten. A
    screen simulated on three of its four rules is not the screen, and a
    two-session stand-in would make that invisible downstream."""
    bars = [(10, 11, 9, 10)] * 15 + [(11, 12, 11, 11.5)] * 5
    rows = [P.measure_day(session(bars), "AAA", DAY, "survivors", m)
            for m in (5, 15, 30)]
    out = "\n".join(P.render(rows))
    assert "NOT COMPUTABLE" in out
    assert not any(f.startswith("rvol") for f in vars(rows[0])), (
        "a field called rvol exists -- if it is ever populated from fewer than "
        "ten sessions the report above becomes a lie")


def test_the_report_names_the_screen_rules_it_could_check():
    bars = [(10, 11, 9, 10)] * 15 + [(11, 12, 11, 11.5)] * 5
    out = "\n".join(P.render([P.measure_day(session(bars), "AAA", DAY,
                                            "survivors", 15)]))
    assert "change_from_open" in out and "$2-20 band" in out


# --- the report's own warnings ----------------------------------------------

def test_a_wide_opposite_stop_is_called_out_against_the_spec_threshold():
    """MAX_R_PCT is 12% in the spec. A mode above it should be eliminated, not
    capped -- a size cap makes the loss smaller and the sample thinner without
    fixing an unusable stop."""
    rows = []
    for i in range(5):
        r = P.DayRow(symbol=f"S{i}", date=DAY, population="survivors",
                     orb_minutes=15, status="OK", entry_px=10.0,
                     r_structure_pct=2.0, r_opposite_pct=18.0,
                     r_rangefrac_pct=9.0, width_pct=5.0)
        rows.append(r)
    out = "\n".join(P.render(rows))
    assert "above the spec's" in out and "Eliminate the mode" in out


def test_range_guards_excluding_most_days_are_called_out():
    rows = [P.DayRow(symbol=f"S{i}", date=DAY, population="survivors",
                     orb_minutes=15,
                     status="TOO_WIDE" if i % 2 else "OK", width_pct=30.0)
            for i in range(10)]
    out = "\n".join(P.render(rows))
    assert "doing the strategy's job" in out


def test_the_report_refuses_to_claim_an_edge():
    rows = [P.DayRow(symbol="A", date=DAY, population="survivors",
                     orb_minutes=15, status="OK", width_pct=5.0)]
    out = "\n".join(P.render(rows))
    assert "Nothing here is a P/L and nothing here is an edge" in out
    assert "unchanged" in out and "unmet" in out


def test_no_numpy_scalars_escape_into_the_record():
    """A numpy bool reaches a CSV looking correct and a SQL Boolean column as
    an unbindable type. Caught once by an `is True`, which is not an idiom
    anyone writes by default -- so it is asserted for the whole record."""
    import numpy as np
    bars = ([(10, 10.0, 9, 10)] * 15 + [(10, 10.01, 10, 10.005)] * 5
            + [(10.1, 10.2, 10.0, 10.15)] * 5)
    r = P.measure_day(session(bars), "AAA", DAY, "survivors", 15)
    for name, v in vars(r).items():
        assert not isinstance(v, np.generic), (
            f"{name} is a numpy scalar ({type(v).__name__}), not a Python type")


# --- 10.1b: telling a thin open apart from a missing session ----------------

def test_the_whole_session_bar_count_is_recorded_even_when_the_range_fails():
    """FEW_BARS on its own cannot distinguish a thin OPEN on a name that traded
    all day from a hole in the cache. The first full run excluded 67% of
    symbol-days and could not say which."""
    # Three bars at the open, then a full afternoon. The range window is
    # 09:30-09:45, so the later bars must NOT rescue it -- and must still be
    # counted, because they are what says the name traded.
    import pandas as pd
    sess = pd.concat([session([(10, 10, 10, 10)] * 3, start="09:30"),
                      session([(10, 11, 9, 10)] * 200, start="10:00")])
    r = P.measure_day(sess, "AAA", DAY, "survivors", 15)
    assert r.status == "FEW_BARS"
    assert r.range_bars == 3
    assert r.rth_bars == 203, "the session's own bar count was not kept"


def test_the_report_separates_a_cache_hole_from_a_thin_open():
    rows = [
        P.DayRow(symbol="EMPTY", date=DAY, population="survivors",
                 orb_minutes=15, status="NO_RTH", rth_bars=0, range_bars=0),
        P.DayRow(symbol="THINOPEN", date=DAY, population="survivors",
                 orb_minutes=15, status="FEW_BARS", rth_bars=300,
                 range_bars=4),
        P.DayRow(symbol="THINDAY", date=DAY, population="survivors",
                 orb_minutes=15, status="FEW_BARS", rth_bars=20, range_bars=2),
    ]
    out = "\n".join(P.render(rows, "EQUS.MINI"))
    assert "nothing published on this tape" in out
    assert "visible all day, invisible at the open" in out
    assert "indistinguishable" in out


def test_the_report_shows_what_the_bar_threshold_costs():
    """MIN_RANGE_BARS is 10 of 15 and was never measured. A flat curve means
    the data is the constraint; a steep one means the threshold is a choice."""
    rows = [P.DayRow(symbol=f"S{i}", date=DAY, population="survivors",
                     orb_minutes=15, status="OK", range_bars=i % 16,
                     rth_bars=300, width_pct=5.0)
            for i in range(64)]
    out = "\n".join(P.render(rows, "EQUS.MINI"))
    assert "MIN_RANGE_BARS is 10 of 15 and was never measured" in out
    for k in (3, 5, 8, 10, 12):
        assert f">= {k:>2} of 15 bars" in out


def _few_bars_rows():
    return [P.DayRow(symbol="A", date=DAY, population="survivors",
                     orb_minutes=15, status="FEW_BARS", rth_bars=40,
                     range_bars=1)]


def test_the_report_names_the_tape_before_the_counts():
    """The first version of 10.1b labelled 12,702 symbol-days "thin all day".
    They are not known to be thin on EQUS.MINI, whose measured capture is a
    median 4.8% of the consolidated tape, so an ordinarily-traded name appears
    with about 19 bars of 390. The counts were being read as a fact about
    liquidity when they were a fact about the tape."""
    out = "\n".join(P.render(_few_bars_rows(), "EQUS.MINI"))
    assert "READ THE TAPE CAVEAT BELOW BEFORE THE COUNTS" in out
    assert "EQUS.MINI" in out and "4.8%" in out
    assert out.index("EQUS.MINI") < out.index("no RTH bars at all")


def test_the_caveat_follows_the_tape_instead_of_being_hardcoded():
    """THIS TEST REPLACES ONE THAT PINNED THE BUG.

    The version above used to be called with no tape argument and asserted the
    EQUS.MINI paragraph appeared -- so the suite required the report to claim
    EQUS.MINI whatever cache it had read. The first XNAS.BASIC run duly printed
    that paragraph over XNAS.BASIC numbers, telling the reader to dismiss the
    counts the tape change had just fixed, and the test passed.
    """
    out = "\n".join(P.render(_few_bars_rows(), "XNAS.BASIC"))
    assert "XNAS.BASIC" in out
    assert "4.8% at 16:00" not in out
    assert "none of the rows below can be read as a fact about liquidity" \
        not in out
    assert "NOT COMPARABLE" in out, \
        "a tape change moves every count -- the report must say so"
    assert out.index("XNAS.BASIC") < out.index("no RTH bars at all")


def test_an_unidentified_cache_is_not_given_a_tape():
    """The IB cache has no SOURCE.txt. Guessing a dataset for it is how the
    original defect worked; saying so is the only honest third option."""
    out = "\n".join(P.render(_few_bars_rows(), ""))
    assert "TAPE UNKNOWN" in out
    assert "EQUS.MINI" not in out.split("no RTH bars at all")[0].split(
        "TAPE UNKNOWN")[1]


def test_the_tape_is_read_from_the_caches_own_marker(tmp_path):
    """bar_cache_build writes SOURCE.txt beside the window directory precisely
    so a cache can say what it is. Read it rather than assuming."""
    root = tmp_path / "bar_cache_x"
    (root / "3d_to_2000").mkdir(parents=True)
    (root / "SOURCE.txt").write_text("databento XNAS.BASIC ohlcv-1m\nRAW\n")
    assert P.cache_tape(root / "3d_to_2000") == "XNAS.BASIC"

    (root / "SOURCE.txt").write_text("databento EQUS.MINI ohlcv-1m\nRAW\n")
    assert P.cache_tape(root / "3d_to_2000") == "EQUS.MINI"

    (root / "SOURCE.txt").unlink()
    assert P.cache_tape(root / "3d_to_2000") == "", \
        "a missing marker must report UNKNOWN, never a default dataset"


def test_the_verdict_is_derived_from_the_curve_not_asserted():
    """The closing paragraph used to state that even >= 3 of 15 leaves most
    symbol-days out. True on EQUS.MINI, false on a fuller tape, printed either
    way. It now follows the measured curve."""
    thin = [P.DayRow(symbol=f"S{i}", date=DAY, population="survivors",
                     orb_minutes=15, status="FEW_BARS", rth_bars=40,
                     range_bars=1) for i in range(50)]
    assert "cannot be evaluated on these bars" in "\n".join(
        P.render(thin, "EQUS.MINI"))

    rich = [P.DayRow(symbol=f"S{i}", date=DAY, population="survivors",
                     orb_minutes=15, status="OK", rth_bars=300,
                     range_bars=14, width_pct=5.0) for i in range(50)]
    out = "\n".join(P.render(rich, "XNAS.BASIC"))
    assert "cannot be evaluated on these bars" not in out
    assert "The range is measurable on this tape" in out
    assert "not evidence for it" in out, \
        "a measurable range is a precondition, not a result"


def test_the_report_says_orb_cannot_be_evaluated_rather_than_rejected():
    """A measurement that cannot be made is not a negative result, and the
    difference decides whether ORB is abandoned or the cache is rebuilt."""
    rows = [P.DayRow(symbol="A", date=DAY, population="survivors",
                     orb_minutes=15, status="FEW_BARS", rth_bars=40,
                     range_bars=1)]
    out = "\n".join(P.render(rows))
    assert "it does not reject ORB" in out
    assert "cannot be" in out and "evaluated on these bars" in out
    assert "XNAS.BASIC" in out
