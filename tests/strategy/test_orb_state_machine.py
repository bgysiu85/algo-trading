#!/usr/bin/env python3
"""ORB's state machine, on HAND-BUILT BARS, before any backtest exists.

`claude/orb_strategy_spec.md` §14 item 8 names eight cases and says to write
them before running anything. Its reason is a specific scar: *the
`if trail_confirm_bars > 0:` regression -- a test on a PARAMETER that silently
dropped 46 trades -- was caught by a test and not by the numbers.* A grid of
ninety cells produces ninety plausible tables whether or not the rule is the
rule, so the rule is pinned here where every price is chosen and every
expected fill can be computed by hand.

THE FRAME SHAPE, and why it is built this way.

Fifteen one-minute bars from 09:30 make the opening range; after 09:45 there
is exactly ONE one-minute bar at the start of each five-minute bucket. That is
a legitimate resample -- `resample_bars` drops empty buckets rather than
synthesising flat ones -- and it means each trigger bar's OHLC is a number
written in this file rather than an emergent property of fifteen others.

THE ARITHMETIC, once, so every case below can be read against it.

    orb_high 10.00   orb_low 9.00   width 1.00   width_pct 11.11%
    trigger  the 09:45 bucket closes above 10.00
    entry    the 09:50 bucket's OPEN, 10.40, plus one tick  ->  10.41
    stop     structure: the anchor bar's low 10.00, minus 0.10% of 10.41
                                                          ->   9.98959
    R        10.41 - 9.98959                               ->   0.42041
    r_2      10.41 + 2R                                    ->  11.25082
"""
from __future__ import annotations

import pandas as pd
import pytest

from strategy.orb import orb as O

ET = "America/New_York"
DAY = "2026-03-02"          # a Monday

HI, LO, MID = 10.0, 9.0, 9.5
ENTRY_OPEN = 10.40
ENTRY = 10.41               # + one tick of slippage
STOP = 10.0 - 10.41 * 0.001
R = ENTRY - STOP
TARGET_2R = ENTRY + 2 * R


# --------------------------------------------------------------------------
# frame construction
# --------------------------------------------------------------------------

def opening(n: int = 15, hi: float = HI, lo: float = LO, mid: float = MID,
            first_minute: int = 30):
    """n one-minute bars from 09:`first_minute`, whose collective extremes are
    hi and lo. Only the FIRST bar carries them, so shortening the range from
    the front removes the extremes as well as the count -- which is what a
    missing open really costs."""
    rows = []
    for i in range(n):
        m = first_minute + i
        rows.append((f"09:{m:02d}", mid,
                     hi if i == 0 else mid, lo if i == 0 else mid, mid))
    return rows


def frame(rows, day: str = DAY) -> pd.DataFrame:
    idx = pd.DatetimeIndex([pd.Timestamp(f"{day} {t}", tz=ET) for t, *_ in rows])
    return pd.DataFrame(
        {"open": [r[1] for r in rows], "high": [r[2] for r in rows],
         "low": [r[3] for r in rows], "close": [r[4] for r in rows],
         "volume": [10_000.0] * len(rows)}, index=idx)


TRIGGER = ("09:45", 10.10, 10.60, 10.00, 10.50)     # closes above 10.00
ENTRY_BAR = ("09:50", ENTRY_OPEN, 10.70, 10.30, 10.60)


def run(trig_rows, cfg: O.Config = O.BASELINE, open_rows=None):
    rows = (open_rows if open_rows is not None else opening()) + list(trig_rows)
    return O.backtest_session(frame(rows), "TEST", DAY, cfg)


def only(res) -> O.Trade:
    assert len(res.trades) == 1, f"expected one trade, got {len(res.trades)}"
    return res.trades[0]


# --------------------------------------------------------------------------
# 1. a clean upside close
# --------------------------------------------------------------------------

def test_a_clean_upside_close_enters_on_the_next_bars_open():
    res = run([TRIGGER, ENTRY_BAR,
               ("09:55", 10.60, 11.40, 10.50, 11.30)])
    assert res.status == "OK"
    assert res.orb_high == HI and res.orb_low == LO
    assert res.up_trigger and res.up_trigger_bar == 0
    assert res.entry_px == pytest.approx(ENTRY)
    assert res.stop_px == pytest.approx(STOP)
    assert res.r_pct == pytest.approx(R / ENTRY * 100)

    t = only(res)
    assert t.entry_time == pd.Timestamp(f"{DAY} 09:50", tz=ET)
    assert t.exit_reason == "target"
    assert t.exit_px == pytest.approx(round(TARGET_2R - O.TICK, 4))
    assert t.shares == 100
    assert t.commission > 0
    assert t.net == pytest.approx(t.gross - t.commission)


def test_entry_is_never_the_trigger_close():
    """§9. The trigger close is a price that has already gone. Booking it
    would have added 9c a share here, on every trade, for free."""
    res = run([TRIGGER, ENTRY_BAR, ("09:55", 10.60, 11.40, 10.50, 11.30)])
    assert res.entry_px != pytest.approx(TRIGGER[4] + O.TICK)
    assert res.entry_px == pytest.approx(ENTRY_BAR[1] + O.TICK)


# --------------------------------------------------------------------------
# 2. a wick that exceeds the range but closes inside
# --------------------------------------------------------------------------

def test_a_wick_through_the_level_that_closes_inside_is_not_a_trigger():
    """The whole point of the close rule (§1.2). A resting order fills on this
    wick; a close-based rule needs the market to HOLD the level for five
    minutes."""
    res = run([("09:45", 9.90, 10.60, 9.80, 9.90),
               ("09:50", 9.90, 9.95, 9.70, 9.80)])
    assert res.status == "NO_TRIGGER"
    assert not res.up_trigger
    assert not res.trades


def test_the_same_wick_IS_v8s_entry():
    """The contrast case, and the reason `entry_on_close` is a cell rather
    than an assumption. Same bars, opposite answer."""
    cfg = O.replace(O.BASELINE, entry_on_close=False)
    res = run([("09:45", 9.90, 10.60, 9.80, 9.90),
               ("09:50", 9.90, 9.95, 9.70, 9.80)], cfg)
    assert res.up_trigger
    # The resting order is AT the level, not at the next open.
    assert res.entry_px == pytest.approx(HI + O.TICK)


def test_v8s_stop_anchors_on_the_last_bar_that_had_CLOSED():
    """A resting order fills DURING the trigger bar, so the trigger bar's own
    low is not knowable yet. Anchoring there would be a look-ahead worth about
    a third of R on this frame."""
    cfg = O.replace(O.BASELINE, entry_on_close=False)
    res = run([("09:45", 9.90, 10.60, 8.50, 9.90),
               ("09:50", 9.90, 9.95, 9.70, 9.80)], cfg)
    # Anchor is the 09:40 range bucket (low 9.50), NOT the 09:45 bar's 8.50.
    assert res.stop_px == pytest.approx(MID - res.entry_px * 0.001)


# --------------------------------------------------------------------------
# 3. a session with no 09:30 bar
# --------------------------------------------------------------------------

def test_a_missing_open_bar_is_recorded_even_when_the_range_still_counts():
    """§4 trap 1 SAYS the 09:30 bar must be present and then specifies a rule
    that only counts bars. Fourteen bars from 09:31 pass the count.

    This test pins what the code does, names the disagreement, and records the
    fact so a cut can be made on it later. It deliberately does NOT invent the
    filter: a rule added here would be a fifteenth uncalibrated parameter
    defended by a paragraph."""
    res = run([TRIGGER, ENTRY_BAR], open_rows=opening(n=14, first_minute=31))
    assert res.has_open_bar is False
    assert res.range_bars == 14
    assert res.status != "FEW_BARS", (
        "the count rule accepts this; the prose does not. Recorded, not fixed")


def test_too_few_range_bars_is_skipped_and_counted():
    res = run([TRIGGER, ENTRY_BAR], open_rows=opening(n=9))
    assert res.status == "FEW_BARS"
    assert res.range_bars == 9
    assert not res.trades


def test_an_empty_session_says_so_rather_than_saying_no_trigger():
    """A day that was never read and a day that produced no signal are
    different facts, and only one of them is a cache problem."""
    res = O.backtest_session(frame([]), "TEST", DAY)
    assert res.status == "NO_RTH"
    assert res.rth_bars == 0


# --------------------------------------------------------------------------
# 4. a range narrower than MIN_RANGE_PCT, and wider than MAX
# --------------------------------------------------------------------------

def test_a_range_with_no_width_is_skipped():
    """The 'breakout' is noise and R is the denominator of every target."""
    res = run([("09:45", 9.52, 9.60, 9.51, 9.58)],
              open_rows=opening(hi=9.52, lo=9.50, mid=9.51))
    assert res.status == "TOO_NARROW"
    assert res.width_pct == pytest.approx(0.02 / 9.50 * 100)


def test_a_range_that_already_holds_the_days_move_is_skipped():
    res = run([("09:45", 13.0, 14.0, 12.9, 13.9)],
              open_rows=opening(hi=13.0, lo=9.0, mid=11.0))
    assert res.status == "TOO_WIDE"


# --------------------------------------------------------------------------
# 5. a retest that fails and closes below orb_low
# --------------------------------------------------------------------------

def test_a_retest_that_closes_below_the_range_is_abandoned():
    cfg = O.replace(O.BASELINE, retest_mode="required")
    res = run([TRIGGER,
               ("09:50", 10.40, 10.45, 8.40, 8.50),      # closes below orb_low
               ("09:55", 8.50, 10.60, 8.40, 10.50)], cfg)
    assert res.status == "RETEST_FAILED"
    assert not res.trades


def test_a_retest_that_never_comes_expires():
    cfg = O.replace(O.BASELINE, retest_mode="required", retest_max_bars=2)
    res = run([TRIGGER,
               ("09:50", 10.40, 10.70, 10.30, 10.60),
               ("09:55", 10.60, 10.90, 10.50, 10.80),
               ("10:00", 10.80, 11.00, 10.70, 10.90)], cfg)
    assert res.status == "RETEST_FAILED"


def test_one_bar_may_both_reach_the_level_and_reclaim_it():
    """A textbook retest-and-reclaim. Requiring the reclaim to take an extra
    bar would deepen every retest entry by one bar of drift, silently."""
    cfg = O.replace(O.BASELINE, retest_mode="required")
    res = run([TRIGGER,
               ("09:50", 10.40, 10.55, 9.95, 10.50),     # dips to 9.95, closes 10.50
               ("09:55", 10.60, 11.00, 10.50, 10.90),
               ("10:00", 10.90, 12.00, 10.80, 11.90)], cfg)
    assert res.status == "OK"
    assert only(res).entry_time == pd.Timestamp(f"{DAY} 09:55", tz=ET)


def test_the_zone_is_measured_from_orb_low_and_not_from_orb_high():
    """V4's 38-62% RETRACEMENT. A 38% pullback from the high is
    `orb_low + 0.62 * width` = 9.62 here, so a dip to 9.95 touches the level
    but is NOT deep enough for the zone. Reading the multiplier the other way
    round would put the boundary at 9.38 and admit this bar -- a 24%-of-range
    error in the permissive direction, which is the direction that manufactures
    trades."""
    bars = [TRIGGER,
            ("09:50", 10.40, 10.55, 9.95, 10.50),
            ("09:55", 10.60, 11.00, 10.50, 10.90),
            ("10:00", 10.90, 12.00, 10.80, 11.90)]
    assert LO + O.ZONE_HI * 1.00 == pytest.approx(9.62)
    shallow = run(bars, O.replace(O.BASELINE, retest_mode="zone"))
    assert shallow.status == "RETEST_FAILED"

    deeper = list(bars)
    deeper[1] = ("09:50", 10.40, 10.55, 9.55, 10.50)     # into the zone
    assert run(deeper, O.replace(O.BASELINE, retest_mode="zone")).status == "OK"


def test_a_retest_rule_can_only_remove_trades():
    """§5.3's ordering property, and the reason the comparison is per-trade
    P/L rather than total. If a retest cell could ever ADD a trade the whole
    drop-top-N-on-the-delta construction would be measuring two populations."""
    bars = [TRIGGER, ENTRY_BAR, ("09:55", 10.60, 11.40, 10.50, 11.30)]
    base = run(bars)
    for mode in ("required", "zone"):
        got = run(bars, O.replace(O.BASELINE, retest_mode=mode))
        assert len(got.trades) <= len(base.trades)


# --------------------------------------------------------------------------
# 6. a bar containing both stop and target
# --------------------------------------------------------------------------

def test_a_bar_holding_both_stop_and_target_is_a_stop():
    """§7.2, and the count is reported rather than buried -- it says how often
    the assumption that keeps the result honest actually bit."""
    res = run([TRIGGER, ENTRY_BAR,
               ("09:55", 10.60, 11.50, 9.50, 10.00)])
    t = only(res)
    assert t.exit_reason == "stop"
    assert res.both_in_bar == 1


def test_a_bar_holding_only_the_target_is_a_target():
    """The control. Without it, 'stop wins' is indistinguishable from 'stop
    always'."""
    res = run([TRIGGER, ENTRY_BAR,
               ("09:55", 10.60, 11.50, 10.50, 11.40)])
    assert only(res).exit_reason == "target"
    assert res.both_in_bar == 0


# --------------------------------------------------------------------------
# 7. a gap-through stop
# --------------------------------------------------------------------------

def test_a_stop_gapped_through_fills_at_the_open_not_at_the_level():
    """§9. You cannot sell AT a level the market never offered. 48% of MC5's
    stop exits were affected by this one line, and it is worth 49c a share
    here."""
    res = run([TRIGGER, ENTRY_BAR,
               ("09:55", 9.50, 9.60, 9.40, 9.45)])
    t = only(res)
    assert t.exit_reason == "stop"
    assert t.exit_px == pytest.approx(round(9.50 - O.TICK, 4))
    assert t.exit_px < STOP, "filled at the level, i.e. at a price never offered"


def test_a_target_gapped_through_does_NOT_fill_better_than_the_level():
    """The deliberate asymmetry, and both halves are conservative. A resting
    limit that fills at the gap open would hand the strategy the one half of
    gap risk that flatters it."""
    res = run([TRIGGER, ENTRY_BAR,
               ("09:55", 12.50, 12.60, 12.40, 12.55)])
    t = only(res)
    assert t.exit_reason == "target"
    assert t.exit_px == pytest.approx(round(TARGET_2R - O.TICK, 4))


# --------------------------------------------------------------------------
# 8. a session that ends with the position open
# --------------------------------------------------------------------------

def test_the_flatten_bar_closes_the_position():
    res = run([TRIGGER, ENTRY_BAR,
               ("15:55", 10.60, 10.70, 10.50, 10.65)])
    t = only(res)
    assert t.exit_reason == "session_end"
    assert t.exit_px == pytest.approx(round(10.65 - O.TICK, 4))
    assert res.open_at_close is False


def test_bars_running_out_early_is_flagged_and_not_carried():
    """A silently-carried position is a P/L that never happened. The trade is
    closed at the last bar there was AND the day is marked, so the runner can
    exclude it rather than average it in."""
    res = run([TRIGGER, ENTRY_BAR,
               ("10:00", 10.60, 10.70, 10.50, 10.65)])
    assert res.open_at_close is True
    assert only(res).exit_reason == "session_end"


def test_an_entry_after_the_last_entry_time_is_refused():
    """§3.3. A position opened at 15:56 exists to be flattened four minutes
    later; it is not the strategy."""
    res = run([("15:50", 10.10, 10.60, 10.00, 10.50),
               ("15:55", 10.40, 10.70, 10.30, 10.60)])
    assert res.status == "TOO_LATE"
    assert not res.trades


# --------------------------------------------------------------------------
# the stop modes, and the R cap
# --------------------------------------------------------------------------

def test_each_stop_mode_puts_the_stop_where_its_source_says():
    bars = [TRIGGER, ENTRY_BAR, ("09:55", 10.60, 11.40, 10.50, 11.30)]
    buf = ENTRY * 0.001
    want = {"structure": 10.00 - buf,          # the anchor bar's low
            "opposite": LO - buf,              # orb_low
            "rangefrac": ENTRY - 0.5 * 1.00}   # entry - 0.5 * width
    for mode, level in want.items():
        cfg = O.replace(O.BASELINE, stop_mode=mode, max_r_pct=100.0)
        assert run(bars, cfg).stop_px == pytest.approx(level), mode


def test_an_unusable_stop_is_skipped_and_counted_not_resized():
    """§6. A size cap does not fix an unusable stop -- it makes the loss
    smaller and the sample thinner. `opposite` on this range is 13.5% of
    price against a 12% cap, which is exactly where VW9's stop sat."""
    cfg = O.replace(O.BASELINE, stop_mode="opposite")
    res = run([TRIGGER, ENTRY_BAR, ("09:55", 10.60, 11.40, 10.50, 11.30)], cfg)
    assert res.status == "R_TOO_WIDE"
    assert res.r_pct > cfg.max_r_pct
    assert not res.trades


def test_a_stop_at_or_above_the_fill_is_undefined_not_small():
    """R is the denominator of every target in §7.1. A non-positive R would
    put a target below the entry and book the result as a win."""
    cfg = O.replace(O.BASELINE, stop_mode="structure")
    res = run([("09:45", 10.10, 10.60, 10.55, 10.50),   # anchor low ABOVE entry
               ("09:50", 10.40, 10.70, 10.30, 10.60)], cfg)
    assert res.status == "R_NOT_POSITIVE"
    assert not res.trades


# --------------------------------------------------------------------------
# the exit modes
# --------------------------------------------------------------------------

@pytest.mark.parametrize("mode,mult", [("r_2", 2.0), ("r_1_5", 1.5)])
def test_the_fixed_r_targets_sit_where_their_sources_say(mode, mult):
    cfg = O.replace(O.BASELINE, exit_mode=mode)
    res = run([TRIGGER, ENTRY_BAR, ("09:55", 10.60, 12.50, 10.50, 12.40)], cfg)
    t = only(res)
    assert t.exit_reason == "target"
    assert t.exit_px == pytest.approx(round(ENTRY + mult * R - O.TICK, 4))


def test_range_1x_targets_the_range_width_and_not_a_multiple_of_R():
    cfg = O.replace(O.BASELINE, exit_mode="range_1x")
    res = run([TRIGGER, ENTRY_BAR, ("09:55", 10.60, 12.50, 10.50, 12.40)], cfg)
    assert only(res).exit_px == pytest.approx(round(ENTRY + 1.00 - O.TICK, 4))


def test_range_1x_moves_the_stop_to_break_even_after_half_the_range():
    """V8's rule. The move takes effect from the NEXT bar: a bar's own high
    must not arm a stop that the same bar's low then hits, which would be an
    exit at a level the position never reached in that order."""
    cfg = O.replace(O.BASELINE, exit_mode="range_1x")
    res = run([TRIGGER, ENTRY_BAR,
               ("09:55", 10.60, 10.95, 10.50, 10.90),    # tags 10.91, arms BE
               ("10:00", 10.90, 10.95, 10.20, 10.30)], cfg)
    t = only(res)
    assert t.exit_reason == "be_stop"
    assert t.exit_px == pytest.approx(round(ENTRY - O.TICK, 4))


def test_r_3_trim_closes_two_legs_and_pays_commission_on_both():
    """§7.1's warning is only true if the model charges what it warns about.
    Partial exits were rejected on this universe at P(>0) = 0.0%, and
    commissions are per ORDER."""
    cfg = O.replace(O.BASELINE, exit_mode="r_3_trim")
    res = run([TRIGGER, ENTRY_BAR,
               ("09:55", 10.60, 11.30, 10.50, 11.20),    # 2R
               ("10:00", 11.20, 11.80, 11.10, 11.70)], cfg)
    assert len(res.trades) == 2
    a, b = res.trades
    assert a.shares == 50 and b.shares == 50
    assert a.exit_px == pytest.approx(round(ENTRY + 2 * R - O.TICK, 4))
    assert b.exit_px == pytest.approx(round(ENTRY + 3 * R - O.TICK, 4))
    assert a.commission > 0 and b.commission > 0


def test_the_trail_peak_starts_at_the_FILL_and_not_at_the_trigger_bars_high():
    """§9, and the same defect the live trader carried until 2026-09-16.

    The 09:45 trigger bar prints 13.00 here -- before the order existed. A
    peak seeded from it puts the trail at 12.35, above the 10.41 fill, and the
    position stops out on the bar it opened on. The trade below must survive
    its own entry bar."""
    cfg = O.replace(O.BASELINE, exit_mode="trail_pct")
    res = run([("09:45", 10.10, 13.00, 10.00, 10.50),
               ENTRY_BAR,
               ("09:55", 10.60, 10.70, 10.50, 10.65),
               ("15:55", 10.65, 10.70, 10.60, 10.68)], cfg)
    t = only(res)
    assert t.exit_reason == "session_end", "stopped out on its own entry bar"


def test_the_entry_bars_own_high_cannot_raise_the_trail_during_that_bar():
    """A SEPARATE defect from the one above, and it survived the first
    mutation pass.

    Entry is at the 09:50 bar's OPEN, so that bar's high IS post-entry and does
    belong in the peak -- but only once the bar has happened. Seeding the peak
    with it at the moment of the fill puts the trail at 11.40 before the bar
    has traded there, and the same bar's 10.00 low then 'gives back' a move
    that has not occurred yet.

    So the giveback is real and the exit is right; it is one bar late, which is
    the only honest place for it. Asserted on `bars_held`, because the exit
    price is identical either way and only the timing separates them."""
    cfg = O.replace(O.BASELINE, exit_mode="trail_pct")
    res = run([TRIGGER,
               ("09:50", ENTRY_OPEN, 12.00, 10.00, 11.90),
               ("09:55", 11.90, 11.95, 11.00, 11.10),
               ("15:55", 11.10, 11.20, 11.00, 11.15)], cfg)
    t = only(res)
    assert t.exit_reason == "trail"
    assert t.bars_held == 1, "the entry bar gave back a peak it had not made yet"
    assert t.exit_px == pytest.approx(round(12.00 * 0.95 - O.TICK, 4))


def test_the_trail_takes_over_once_the_peak_has_risen_past_the_fixed_stop():
    """Both are live: the fixed stop defines R and never moves, the trail
    rides above it once there is profit to give back. Whichever is higher
    binds."""
    cfg = O.replace(O.BASELINE, exit_mode="trail_pct")
    res = run([TRIGGER, ENTRY_BAR,
               ("09:55", 10.60, 14.00, 10.50, 13.90),    # peak 14.00
               ("10:00", 13.90, 13.95, 13.00, 13.10)], cfg)
    t = only(res)
    assert t.exit_reason == "trail"
    assert t.exit_px == pytest.approx(round(14.00 * 0.95 - O.TICK, 4))


def test_a_time_stop_is_off_unless_asked_for():
    bars = [TRIGGER, ENTRY_BAR,
            ("09:55", 10.60, 10.70, 10.50, 10.65),
            ("10:00", 10.65, 10.75, 10.55, 10.70),
            ("15:55", 10.70, 10.75, 10.65, 10.72)]
    assert only(run(bars)).exit_reason == "session_end"
    cfg = O.replace(O.BASELINE, time_stop_bars=1)
    t = only(run(bars, cfg))
    assert t.exit_reason == "time_stop" and t.bars_held == 1


# --------------------------------------------------------------------------
# the band, and the measurements that are never traded
# --------------------------------------------------------------------------

def test_the_price_band_is_enforced_before_any_p_and_l_exists():
    """PROGRAM_INDEX §1 and §5. VW9 shipped without it and took positions at
    $4,152 a share; its headline moved by $35,000 when the band was applied."""
    rows = [(t, o * 3, h * 3, l * 3, c * 3) for t, o, h, l, c in
            [TRIGGER, ENTRY_BAR, ("09:55", 10.60, 11.40, 10.50, 11.30)]]
    res = run(rows, open_rows=opening(hi=HI * 3, lo=LO * 3, mid=MID * 3))
    assert res.status == "OUT_OF_BAND"
    assert not res.trades


def test_the_downside_break_is_measured_and_never_traded():
    """§5.4. Long-only discards roughly half the sources' signals by
    construction; the discarded half is counted, not assumed away."""
    res = run([("09:45", 9.50, 9.60, 8.40, 8.50),
               ("09:50", 8.50, 8.60, 8.30, 8.40)])
    assert res.down_trigger is True
    assert res.down_trigger_bar == 0
    assert not res.trades, "a short was opened; §5.4 says measured, not traded"


def test_the_v2_fade_is_measured_on_a_break_that_closes_back_inside():
    """One source in ten does not trade this breakout -- he fades the failed
    one. It is the only genuine counter-hypothesis in the set and it costs two
    columns."""
    res = run([TRIGGER,
               ("09:50", 10.40, 10.45, 9.60, 9.70),      # back inside
               ("09:55", 9.70, 9.80, 9.50, 9.60)])
    assert res.faded is True
    assert res.fade_return_pct == pytest.approx((9.70 - LO) / 9.70 * 100)


def test_a_break_that_holds_records_faded_false_rather_than_nothing():
    """An absent value and a False are different claims, and only the second
    says the measurement was made."""
    res = run([TRIGGER, ENTRY_BAR, ("09:55", 10.60, 11.40, 10.50, 11.30)])
    assert res.faded is False


# --------------------------------------------------------------------------
# the config itself
# --------------------------------------------------------------------------

def test_a_misspelt_mode_raises_rather_than_selecting_the_baseline():
    """Ninety cells come from grid literals. A cell that quietly ran
    `structure` while labelled `rangefrac` would be published as a comparison
    between two identical arms."""
    for kw in ({"stop_mode": "structural"}, {"retest_mode": "require"},
               {"exit_mode": "r2"}):
        with pytest.raises(ValueError):
            O.replace(O.BASELINE, **kw)


def test_a_range_that_is_not_a_whole_number_of_trigger_bars_raises():
    with pytest.raises(ValueError):
        O.replace(O.BASELINE, orb_minutes=13)


def test_v8s_resting_order_refuses_to_be_combined_with_a_retest():
    """No source specifies the combination. Picking one silently would put an
    invented strategy in a cell labelled as someone else's."""
    with pytest.raises(ValueError, match="retest"):
        O.replace(O.BASELINE, entry_on_close=False, retest_mode="required")


def test_the_baseline_is_the_one_registered_before_any_data_was_seen():
    """REGISTERED_orb_grid.md §2 fixes every value from the sources, and names
    the 5-minute availability finding as a thing NOT to move it toward."""
    b = O.BASELINE
    assert (b.orb_minutes, b.trigger_bar_minutes) == (15, 5)
    assert b.entry_on_close is True
    assert (b.retest_mode, b.stop_mode, b.exit_mode) == ("none", "structure", "r_2")
    assert b.max_entries_per_session == 1
    assert b.entry_buffer_pct == 0.0
