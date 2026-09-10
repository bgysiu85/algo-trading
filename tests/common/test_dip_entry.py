#!/usr/bin/env python3
"""Dip entries — the detector, and the trap that would make any result fake.

The census puts dip buying at 129 mentions against the micro pullback's 172, at
the same 0.7 red-day lift, and MCL implements only the second. So this is half
a method we inherited without noticing.

THE HEADLINE TEST IS `test_a_dip_entry_beats_mcl_on_fill_by_construction`. A
dip entry buys the pullback where MCL buys the breakout, so its price is lower
on every shared setup and its MFE is larger for free. If the study ever reports
that as an edge, the whole exercise is worthless -- so the mechanical part is
pinned here and printed separately there.
"""
from __future__ import annotations

from datetime import timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from common import dip_entry as DE
from common import dip_study as DS
from strategy.mcl import mcl as MCL
from strategy.mcl.mcl import TRAIL_PCT

ET = ZoneInfo("America/New_York")
CFG = DE.DipConfig()


def frame(closes, highs=None, lows=None):
    n = len(closes)
    highs = highs or [c * 1.001 for c in closes]
    lows = lows or [c * 0.999 for c in closes]
    t0 = pd.Timestamp("2026-03-02 04:00", tz=ET)
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=i) for i in range(n)],
                           tz=ET).tz_convert("UTC")
    return pd.DataFrame({"open": closes, "high": highs, "low": lows,
                         "close": closes, "volume": [5000.0] * n}, index=idx)


def pole_then_dip(pole=0.20, give_back=0.40, flat=5):
    """Flat, a clean impulse, then a pullback giving back `give_back` of it."""
    base = [4.00] * flat
    peak = 4.00 * (1 + pole)
    up = [round(4.00 + (peak - 4.00) * k / 8, 4) for k in range(1, 9)]
    floor = peak - (peak - 4.00) * give_back
    down = [round(peak - (peak - floor) * k / 3, 4) for k in range(1, 4)]
    return base + up + down


# --- the parameters are derived, not chosen ---------------------------------

def test_every_threshold_derives_from_something_already_settled():
    """Four free knobs would be four things to fit. TRAIL_PCT is validated at
    5% and hold-50% is `warrior_5_selection_in_practice` §1 in his own words."""
    assert CFG.impulse_min == pytest.approx(2 * TRAIL_PCT / 100.0)
    assert CFG.dip_min == pytest.approx(TRAIL_PCT / 100.0)
    assert CFG.hold_min == 0.50


def test_dip_max_is_hold_min_and_not_a_fifth_knob():
    """A pullback past half the impulse IS a hold-50% failure. Two constants
    for one boundary would let them drift apart and become a fitted pair."""
    assert CFG.dip_max == pytest.approx(1.0 - CFG.hold_min)


# --- the setup --------------------------------------------------------------

def test_a_clean_pole_and_pullback_fires():
    d = DE.find_dips(frame(pole_then_dip()), CFG)
    assert d, "the canonical setup produced no signal"
    assert d[0].retained >= CFG.hold_min


def test_a_move_smaller_than_twice_the_trail_is_not_an_impulse():
    """Inside the noise the stop already tolerates."""
    assert DE.find_dips(frame(pole_then_dip(pole=0.06)), CFG) == []


def test_a_pullback_shallower_than_the_trail_is_a_wiggle():
    """And by definition MCL would not have been stopped out of it, so there
    is nothing for a dip entry to be earlier than."""
    assert DE.find_dips(frame(pole_then_dip(give_back=0.10)), CFG) == []


def test_the_hold_fifty_rule_rejects_a_name_that_gave_it_all_back():
    """His own words: a name that pops and returns is 'not going to work.'
    This is the rejection the rule exists for, and it must be a REJECTION and
    not merely a deferral -- a deeper pullback must never re-qualify later."""
    assert DE.find_dips(frame(pole_then_dip(give_back=0.80)), CFG) == []


def test_the_boundary_is_inclusive_at_exactly_half():
    """A pullback to exactly 50% retained is held, not rejected. Off by one
    here silently changes which side of his stated rule we implement."""
    px = [4.0] * 5 + [5.0] * 3 + [4.5]
    # No wicks: with high == low == close the impulse is exactly 4.00 -> 5.00
    # and the pullback to 4.50 is exactly half of it. The default fixture puts
    # a 0.1% wick on every bar, which moves both ends and would make this test
    # about the fixture rather than about the boundary.
    d = DE.find_dips(frame(px, highs=list(px), lows=list(px)),
                     DE.DipConfig(dip_min=0.01))
    assert d and d[0].retained == pytest.approx(0.5)


def test_one_signal_per_impulse():
    """'Buy the dip', not 'buy every bar of the dip'. Firing on each bar of a
    three-bar pullback would take three positions in one setup and make the
    signal count a function of pullback duration."""
    px = pole_then_dip()
    px += [px[-1]] * 4          # the dip persists for four more bars
    assert len(DE.find_dips(frame(px), CFG)) == 1


def test_a_second_impulse_can_fire_again():
    """Otherwise the one-per-impulse rule would be one-per-session."""
    px = pole_then_dip()
    peak2 = px[-1] * 1.30
    px += [round(px[-1] + (peak2 - px[-1]) * k / 6, 4) for k in range(1, 7)]
    px += [round(peak2 * 0.90, 4)]
    assert len(DE.find_dips(frame(px), CFG)) == 2


def test_the_base_is_the_lowest_low_not_the_lowest_close():
    """These are exactly the bars that ran hard off a wick. Using closes would
    understate the impulse on the setups the strategy is about."""
    px = [4.0] * 5 + [5.0] * 3 + [4.6]
    lows = [3.0] + [c * 0.999 for c in px[1:]]      # a deep wick on bar 0
    d = DE.find_dips(frame(px, lows=lows), DE.DipConfig(dip_min=0.01))
    assert d and d[0].base == pytest.approx(3.0)


def test_the_impulse_may_start_before_the_considered_window():
    """An impulse that began at 06:55 is the reason a 07:00 bar is a dip.
    Truncating the lookback at the window edge would make the first `lookback`
    bars of every session unable to signal, silently."""
    px = pole_then_dip()
    inside = DE.find_dips(frame(px), CFG)
    windowed = DE.find_dips(frame(px), CFG, lo=len(px) - 2)
    assert inside and windowed, "the impulse behind the signal was truncated"


def test_an_empty_or_one_bar_frame_does_not_raise():
    assert DE.find_dips(frame([]), CFG) == []
    assert DE.find_dips(frame([4.0]), CFG) == []


# --- excursions -------------------------------------------------------------

def test_excursions_are_forward_only_and_exclude_the_signal_bar():
    """Bar i is the bar the signal was READ from. Including its own high would
    credit the entry with a move that had already happened when the decision
    was made -- the same defect Ben identified in MCL and MC5."""
    df = frame([4.0, 9.0, 5.0, 3.0])
    mfe, mae = DE.excursions(df, 1, 9.0)
    assert mfe == pytest.approx((5.0 * 1.001 - 9.0) / 9.0)
    assert mae == pytest.approx((9.0 - 3.0 * 0.999) / 9.0)


def test_an_entry_on_the_last_bar_has_no_forward_window():
    df = frame([4.0, 5.0])
    assert DE.excursions(df, 1, 5.0) == (0.0, 0.0)


def test_the_ratio_floors_the_denominator_rather_than_dividing_by_zero():
    """A zero MAE is a real reading -- price never traded below the entry --
    and an infinity there would dominate any mean it entered."""
    r = DS.ratio(0.20, 0.0)
    assert r > 0 and r < float("inf")


# --- THE HEADLINE: the mechanical advantage that is not evidence -------------

def test_a_dip_entry_beats_mcl_on_fill_by_construction():
    """THE TRAP. A dip entry buys the pullback; a confirmation entry buys the
    break above it. On any shared setup the dip price is LOWER, so its MFE is
    larger and its MAE smaller before any edge exists.

    This test asserts the arithmetic so it can never be mistaken for a finding:
    the study prints the fill difference in its own block, labelled as what is
    free.
    """
    # A resumption after the dip, so both entries have a forward window. With
    # no bars after the signal both excursions are 0.0 and the test would pass
    # on 0 > 0 being false -- it did, the first time it was written.
    px = pole_then_dip()
    px += [round(px[-1] * (1 + 0.02 * k), 4) for k in range(1, 8)]
    df = frame(px)
    d = DE.find_dips(df, CFG)[0]
    breakout = float(df["high"].to_numpy()[:d.i + 1].max())
    assert d.price < breakout
    mfe_dip, mae_dip = DE.excursions(df, d.i, d.price, len(df))
    mfe_conf, mae_conf = DE.excursions(df, d.i, breakout, len(df))
    assert mfe_dip > mfe_conf and mae_dip < mae_conf


def test_the_study_prints_the_fill_difference_separately():
    """If it were folded into the headline the whole exercise is worthless."""
    import inspect
    src = inspect.getsource(DS.render)
    assert "what is free, and therefore not evidence" in src
    assert "fill difference" in src


def recs(n, r, first="2026-01"):
    """`n` records at ratio `r`, spread across TWO months so the halves
    control actually divides. Confining a bucket to one month makes one half
    empty, which is a different failure and now gets its own branch."""
    return [{"date": f"2026-{1 + i % 2:02d}-{1 + i % 28:02d}",
             "mfe": r / 10.0, "mae": 0.10, "ratio": r} for i in range(n)]


def test_the_verdict_rests_on_the_added_trades_not_the_shared_ones():
    """DIP ONLY is the question: those are the setups the confirmation entry
    refused. A verdict driven by the PAIRED bucket would be driven by the fill,
    which is free.

    So: a paired bucket that looks spectacular and an added bucket that does
    not. The verdict must be negative. Asserted on the rendered output rather
    than on the source text, because a source-text assertion passes on a
    comment.
    """
    g = {"both": recs(30, 9.0), "dip_only": recs(30, 0.4),
         "mcl_only": recs(10, 2.0), "earlier": [5] * 30, "later": [],
         "fill_edge": [0.04] * 30}
    out = "\n".join(DS.render(g, recs(30, 2.0), 70, "training", CFG))
    assert "DO NOT STAND ON THEIR OWN" in out
    assert "the fill trap predicts" in out


def test_a_strong_added_bucket_does_reach_the_positive_verdict():
    """And the other way, or the negative branch proves nothing."""
    g = {"both": recs(30, 3.0), "dip_only": recs(30, 5.0),
         "mcl_only": recs(10, 2.0), "earlier": [5] * 30, "later": [],
         "fill_edge": [0.04] * 30}
    out = "\n".join(DS.render(g, recs(30, 2.0), 70, "training", CFG))
    assert "STAND ON THEIR OWN" in out and "DO NOT" not in out


# --- bucketing --------------------------------------------------------------

class T:
    def __init__(self, ts, px):
        self.entry_time, self.entry_price = ts, px


def test_a_session_never_lands_in_two_buckets():
    """MCL ONLY takes only the sessions where no dip fired; when both fired,
    MCL's side of the pair is collected by paired_mcl. Double-counting would
    put the same session on both sides of the comparison."""
    df = frame(pole_then_dip())
    dips = DE.find_dips(df, CFG)
    rows = [{"symbol": "A", "date": "2026-03-02", "n_bars": len(df),
             "mcl": [(2, 4.0)], "dips": dips, "df": df},
            {"symbol": "B", "date": "2026-03-03", "n_bars": len(df),
             "mcl": [(2, 4.0)], "dips": [], "df": df}]
    g = DS.collect(rows, CFG)
    assert len(g["both"]) == 1 and len(g["mcl_only"]) == 1
    assert len(g["dip_only"]) == 0


def test_a_dip_after_mcls_entry_is_counted_as_late_not_early():
    """It is a re-entry into a position MCL already holds, not an earlier
    entry, and the four convergent findings were about being EARLIER."""
    df = frame(pole_then_dip())
    dips = DE.find_dips(df, CFG)
    late = [{"symbol": "A", "date": "2026-03-02", "n_bars": len(df),
             "mcl": [(0, 4.0)], "dips": dips, "df": df}]
    g = DS.collect(late, CFG)
    assert len(g["later"]) == 1 and len(g["earlier"]) == 0


def test_the_report_renders_and_refuses_a_verdict_on_too_few_added_trades():
    df = frame(pole_then_dip())
    dips = DE.find_dips(df, CFG)
    # A real baseline, or the NO BASELINE branch fires first and this test
    # would be about the wrong refusal.
    rows = [{"symbol": "A", "date": f"2026-03-{i:02d}", "n_bars": len(df),
             "mcl": [(2, 4.0)], "dips": dips, "df": df} for i in range(2, 8)]
    g = DS.collect(rows, CFG)
    g["dip_only"] = recs(6, 3.0)
    out = "\n".join(DS.render(g, DS.paired_mcl(rows), 6, "training", CFG))
    assert "TOO FEW ADDED TRADES" in out


def test_no_signals_at_all_is_reported_as_such():
    df = frame([4.0] * 30)
    rows = [{"symbol": "A", "date": "2026-03-02", "n_bars": len(df),
             "mcl": [], "dips": [], "df": df}]
    out = "\n".join(DS.render(DS.collect(rows, CFG), [], 1, "training", CFG))
    assert "NO DIP SIGNALS FIRED" in out


def test_the_study_guards_the_holdout_like_every_other():
    import inspect
    src = inspect.getsource(DS)
    assert "split_sessions" in src and "--spend-holdout" in src


def test_an_undivided_halves_control_is_not_a_refutation():
    """THE DEFECT THIS PROJECT KEEPS HITTING: a control whose output is
    indistinguishable from the failure it detects. An empty half has a median
    of zero and fails the both-halves test for exactly the same reason a
    genuinely bad half does. The first version of render() scored an undivided
    run as a refutation of dip buying.
    """
    # Every added trade AFTER everything else, so the derived split cannot
    # put any of them in the early half.
    one_side = [{"date": f"2026-09-{1 + i:02d}", "mfe": 0.5, "mae": 0.1,
                 "ratio": 5.0} for i in range(20)]
    g = {"both": recs(30, 3.0), "dip_only": one_side,
         "mcl_only": recs(10, 2.0), "earlier": [5] * 30, "later": [],
         "fill_edge": [0.04] * 30}
    out = "\n".join(DS.render(g, recs(30, 2.0), 70, "training", CFG))
    assert "DID NOT DIVIDE" in out and "NO VERDICT" in out
    assert "DO NOT STAND ON THEIR OWN" not in out


# --- the two defects the first real run exposed -----------------------------

def test_the_entry_mapping_raises_rather_than_returning_a_short_list():
    """THE ONE THAT ACTUALLY HAPPENED. `Trade.entry_time` is a STRING. The
    first version keyed the position map by Timestamp, matched nothing, and 71
    real MCL trades became an empty baseline -- against which every positive
    dip reading wins. Dropping unmatched entries is what turned a type bug into
    a finding.
    """
    df = frame([4.0] * 5)

    class Bad:
        entry_time, entry_price = "2099-01-01 00:00:00+00:00", 4.0

    with pytest.raises(KeyError):
        DS.strict_positions(df, [Bad()])


def test_a_string_entry_time_maps_to_the_right_bar():
    """The actual type the engine emits, mapped by value and not by identity."""
    df = frame([4.0, 5.0, 6.0])

    class Good:
        entry_price = 5.0
        entry_time = str(df.index[1])

    assert DS.strict_positions(df, [Good()]) == [(1, 5.0)]


def test_an_empty_baseline_refuses_a_verdict():
    """A median of 0.00 is beaten by any positive reading. The first real run
    printed 'THE ADDED TRADES STAND ON THEIR OWN' against exactly that."""
    g = {"both": [], "dip_only": recs(60, 5.0), "mcl_only": [],
         "earlier": [], "later": [], "fill_edge": []}
    out = "\n".join(DS.render(g, [], 66, "training", CFG))
    assert "NO BASELINE" in out
    assert "STAND ON THEIR OWN" not in out


def test_the_detector_is_bounded_to_mcls_own_session():
    """THE LEAK THE FIRST RUN EXPOSED. `load_sessions` returns a THREE-DAY
    frame so the indicators can warm up; MCL trades only 04:00-09:30 on the
    last day. Unbounded, the detector fired on the warm-up days and the report
    said dips came a median of 245 bars -- four hours, a previous session --
    'earlier' than MCL's entry, then scored their excursion over everything
    that followed. That is a look-ahead window, not an earlier entry.
    """
    px = [4.0] * 5 + pole_then_dip()
    n = len(px)
    t0 = pd.Timestamp("2026-03-02 04:00", tz=ET)      # the day BEFORE
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=i) for i in range(n)],
                           tz=ET).tz_convert("UTC")
    df = pd.DataFrame({"open": px, "high": [c * 1.001 for c in px],
                       "low": [c * 0.999 for c in px], "close": px,
                       "volume": [5000.0] * n}, index=idx)
    lo, hi = DS.session_bounds(df, "2026-03-03")
    assert (lo, hi) == (0, 0), "bars from another day were counted as session"
    assert DE.find_dips(df, CFG, lo=lo, hi=hi) == []
    # And the same frame DOES yield its own day.
    assert DS.session_bounds(df, "2026-03-02") == (0, n)


def test_the_session_window_comes_from_the_strategy_not_a_local_copy():
    """A second copy of 04:00-09:30 here would let the two drift and silently
    compare different windows."""
    import inspect
    src = inspect.getsource(DS.session_bounds)
    assert "MCL.SESSION_START" in src and "MCL.SESSION_END" in src


def test_bars_after_the_session_close_are_excluded():
    n = 8 * 60
    t0 = pd.Timestamp("2026-03-02 04:00", tz=ET)
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=i) for i in range(n)],
                           tz=ET).tz_convert("UTC")
    df = pd.DataFrame({"open": [4.0] * n, "high": [4.0] * n, "low": [4.0] * n,
                       "close": [4.0] * n, "volume": [1.0] * n}, index=idx)
    lo, hi = DS.session_bounds(df, "2026-03-02")
    last = df.index.tz_convert(ET)[hi - 1]
    assert last.time() <= MCL.SESSION_END
    assert hi < n, "the 09:30 close was not enforced"
