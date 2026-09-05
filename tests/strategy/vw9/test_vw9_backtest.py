#!/usr/bin/env python3
"""
Unit tests for strategy/vw9/backtest.py -- the §4.3 entry gates, §5 exits,
and §9 execution model layered on top of strategy.vw9.vw9.find_setups()'s
raw (ungated) triggers. Sibling to test_vw9_strategy.py: same practice,
every scenario below was built by printing apply_indicators()'s columns and
the resulting Trade list, checking the numbers were what the scenario
intended, THEN pinning the assertion -- not derived by hand from the
EMA/VWAP/ATR recursions, which is impractical past a handful of bars.

`timeframe_minutes=1` is used throughout so backtest_session_tf() does not
resample -- the hand-built rows ARE the bars the engine sees, keeping every
scenario's arithmetic traceable to the rows that produced it. Timeframe
handling itself (resampling before finding setups) is strategy.vw9.vw9's
resample_bars(), already covered by tests/common/test_indicators.py.
"""

from __future__ import annotations

import pandas as pd
import pytest
from zoneinfo import ZoneInfo

from strategy.vw9.backtest import (MAX_ENTRIES_PER_SESSION, backtest_session_tf)
from strategy.vw9.vw9 import find_setups

ET = ZoneInfo("America/New_York")
VOL = 100_000
DATE = pd.Timestamp("2026-09-04").date()


def make_bars(rows, start="2026-09-04 04:00", freq_min=1):
    idx = pd.date_range(start, periods=len(rows), freq=f"{freq_min}min",
                        tz="America/New_York")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"],
                        index=idx)


def warmup(n=8, price=10.0, rng=0.3, vol=VOL):
    """Flat bars so regime is None (not yet mature) through bar 8, exactly
    as in test_vw9_strategy.py -- see that module for why."""
    return [(price, price + rng, price - rng, price, vol)] * n


def impulse(start_close=10.0, step=0.15, n=20, rng=0.25, vol=VOL):
    """A gentle, steady climb -- identical helper to test_vw9_strategy.py's,
    reused here because it reliably produces a clean Setup B (see that
    module's docstring for why the gentle slope matters)."""
    rows = []
    c = start_close
    for _ in range(n):
        o = c
        c = round(c + step, 2)
        h = round(max(o, c) + rng, 2)
        l = round(min(o, c) - rng, 2)
        rows.append((o, h, l, c, vol))
    return rows


def base_rows():
    """warmup(8) + a clean 2-bar-bearish VWAP reclaim (Setup A), trigger at
    bar_index=10 -- verified interactively: entry_ref=10.2, structure_low=9.4,
    atr14 at the trigger bar = 0.594898, ext_atr = 0.511 (comfortably under
    MAX_EXT_ATR=2.0) and trigger-bar dollar volume = ~$1.02M (comfortably
    over MIN_TRIGGER_DV_PER_MIN's 1-minute threshold of $40,000) -- i.e. this
    is the "passes every gate" baseline every exit-mechanics test below
    builds on. entry fills next bar (bar_index=11) at that bar's open + 1
    tick; stop = 9.4 - 0.10*0.594898 = 9.340510(2); R = entry_price - stop.
    """
    return warmup(8) + [(10.0, 9.6, 9.4, 9.5, VOL), (9.5, 9.6, 9.4, 9.5, VOL),
                        (9.5, 10.3, 9.4, 10.2, VOL)]


def one_trade(rows, exit_mode="fixed_2r", timeframe_minutes=1):
    trades = backtest_session_tf(make_bars(rows), DATE, ET, timeframe_minutes,
                                 exit_mode=exit_mode)
    assert len(trades) == 1, f"expected exactly one trade, got {trades}"
    return trades[0]


# --- §9 fill model -----------------------------------------------------

class TestFillModel:
    def test_fill_is_next_bar_open_plus_slippage_not_trigger_bar_close(self):
        """§9: 'fill_price = Next bar's open + modelled slippage.' The
        trigger bar (bar_index=10) closes at 10.2; if the engine wrongly
        filled at the trigger bar's close (MCL's convention, NOT VW9's) the
        entry price would be 10.21, not 10.51."""
        rows = base_rows() + [
            (10.5, 10.6, 10.4, 10.5, VOL),   # fill bar: open=10.5 -> entry=10.51
            (10.5, 10.7, 10.4, 10.55, VOL),  # last bar of session
        ]
        t = one_trade(rows)
        assert t.entry_price == pytest.approx(10.51)
        assert t.entry_time == "2026-09-04 04:11:00-04:00"  # fill bar, not bar 10
        assert t.setup_kind == "A"


# --- §4.3 entry gates ----------------------------------------------------

class TestEntryGates:
    def test_liquidity_gate_blocks_thin_trigger_bar(self):
        """Same reclaim as the baseline, but the trigger bar's own volume is
        cut to 50 shares -- dollar volume ~$510, far under the 1-minute
        threshold ($40,000). find_setups() still finds it (gates don't
        apply there); the backtest must produce no trade."""
        rows = warmup(8) + [(10.0, 9.6, 9.4, 9.5, VOL), (9.5, 9.6, 9.4, 9.5, VOL),
                            (9.5, 10.3, 9.4, 10.2, 50)]
        assert len(find_setups(make_bars(rows))) == 1   # ungated: it's there
        rows += [(10.5, 10.6, 10.4, 10.5, VOL), (10.5, 10.6, 10.4, 10.5, VOL)]
        trades = backtest_session_tf(make_bars(rows), DATE, ET, 1)
        assert trades == []

    def test_extension_gate_blocks_overextended_reclaim(self):
        """A reclaim from 8.0 to 15.0 -- verified interactively:
        ext_atr = (15.0-10.424)/1.137281 = 4.02, nearly double
        MAX_EXT_ATR(2.0). Again present ungated, absent from the backtest."""
        rows = warmup(8) + [(10.0, 8.1, 7.9, 8.0, VOL), (8.0, 8.1, 7.9, 8.0, VOL),
                            (8.0, 15.1, 7.9, 15.0, VOL)]
        assert len(find_setups(make_bars(rows))) == 1
        rows += [(15.0, 15.2, 14.8, 15.0, VOL), (15.0, 15.2, 14.8, 15.0, VOL)]
        trades = backtest_session_tf(make_bars(rows), DATE, ET, 1)
        assert trades == []

    def test_pullback_volume_gate_blocks_heavy_down_volume(self):
        """§4.3: 'largest down-bar volume in the pullback must not exceed
        the largest up-bar volume of the impulse.' The pullback's one
        down-bar is given DOUBLE the impulse bars' volume -- verified
        interactively: impulse_max_up_vol=100000, pullback_max_down_vol=
        200000 on the resulting Setup. Present ungated, absent gated."""
        rows = warmup() + impulse() + [
            (13.0, 13.0, 12.1, 12.2, VOL * 2),   # pullback down-bar, 2x volume
            (12.2, 12.6, 12.15, 12.5, VOL),       # reclaim
        ]
        setups = find_setups(make_bars(rows))
        assert len(setups) == 1 and setups[0].kind == "B"
        assert setups[0].pullback_max_down_vol > setups[0].impulse_max_up_vol
        rows += [(12.5, 12.6, 12.4, 12.5, VOL), (12.5, 12.6, 12.4, 12.5, VOL)]
        trades = backtest_session_tf(make_bars(rows), DATE, ET, 1)
        assert trades == []

    def test_pullback_volume_gate_allows_equal_volume(self):
        """Positive control for the test above: the SAME scenario with the
        pullback's down-bar volume equal to (not exceeding) the impulse's
        up-bar volume must clear the gate -- proving it is a real
        comparison, not a blanket rejection of Setup B."""
        rows = warmup() + impulse() + [
            (13.0, 13.0, 12.1, 12.2, VOL),        # pullback down-bar, SAME volume
            (12.2, 12.6, 12.15, 12.5, VOL),        # reclaim
            (12.5, 12.6, 12.4, 12.5, VOL),         # fill bar
            (12.5, 12.6, 12.4, 12.5, VOL),         # last bar -> session_close
        ]
        t = one_trade(rows)
        assert t.setup_kind == "B"
        assert t.reason == "session_close"


# --- §5.3 hard exits, priority order --------------------------------------

class TestHardExits:
    def test_stop_exit(self):
        """§5.1: stop = structure_low - STOP_BUFFER_ATR*atr14 = 9.4 -
        0.10*0.594898 = 9.340510(2). A bar whose low (9.2) breaches it exits
        there, at stop - 1 tick, and does not run on to the next bar."""
        rows = base_rows() + [
            (10.5, 10.6, 10.4, 10.5, VOL),   # fill: entry=10.51
            (10.4, 10.5, 9.2, 9.3, VOL),      # low 9.2 breaches stop ~9.3405
            (9.3, 9.4, 9.1, 9.2, VOL),        # must NOT be reached
        ]
        t = one_trade(rows)
        assert t.reason == "stop"
        assert t.exit_price == pytest.approx(9.3305, abs=1e-4)
        assert t.exit_time == "2026-09-04 04:12:00-04:00"
        assert t.bars_held == 1

    def test_vwap_lost_exit_even_though_stop_not_touched(self):
        """§5.3 #2: 'any bar closing below VWAP exits the position at that
        close, regardless of mode or P/L.' The bar's low (9.5) stays well
        above the ~9.34 stop, but its close (9.5) is below that bar's own
        VWAP (~9.946) -- the position must exit here, not ride to a later
        bar or the stop."""
        rows = base_rows() + [
            (10.5, 10.6, 10.4, 10.5, VOL),    # fill
            (10.4, 10.5, 9.5, 9.5, VOL),       # close <= vwap, low > stop
        ]
        t = one_trade(rows)
        assert t.reason == "vwap_lost"
        assert t.exit_price == pytest.approx(9.49)

    def test_session_close_exit_flat_at_last_bar(self):
        """§5.3 #3: flat at the session's last bar if nothing else fired."""
        rows = base_rows() + [
            (10.5, 10.6, 10.4, 10.5, VOL),
            (10.5, 10.7, 10.4, 10.55, VOL),   # last bar: no stop/vwap/target hit
        ]
        t = one_trade(rows)
        assert t.reason == "session_close"
        assert t.exit_price == pytest.approx(10.54)

    def test_intrabar_stop_and_target_ambiguity_stop_wins(self):
        """§5.3: 'if a bar's range contains both stop and target, assume the
        stop filled first.' One bar's range (low=9.0, high=13.0) spans both
        the ~9.34 stop and the ~12.85 fixed_2r target -- the trade must exit
        at the stop, not the target, and must not continue to the next bar."""
        rows = base_rows() + [
            (10.5, 10.6, 10.4, 10.5, VOL),     # fill: entry=10.51
            (10.5, 13.0, 9.0, 11.0, VOL),       # contains BOTH stop and target
            (11.0, 11.1, 10.9, 11.0, VOL),      # must NOT be reached
        ]
        t = one_trade(rows, exit_mode="fixed_2r")
        assert t.reason == "stop"
        assert t.exit_price == pytest.approx(9.3305, abs=1e-4)


# --- §5.2 the three EXIT_MODE variants -------------------------------------

class TestExitModes:
    def test_fixed_2r_target_hit(self):
        """R = entry_price - stop = 10.51 - 9.3405102 = 1.1694898; target =
        entry + 2R = 12.8489796. A bar with high=13.0 clears it and must
        exit there (at target - 1 tick), not run to the trailing bar."""
        rows = base_rows() + [
            (10.5, 10.6, 10.4, 10.5, VOL),      # fill
            (10.5, 13.0, 10.4, 12.9, VOL),       # high clears the ~12.85 target
            (12.9, 13.0, 12.8, 12.9, VOL),       # must NOT be reached
        ]
        t = one_trade(rows, exit_mode="fixed_2r")
        assert t.reason == "target_2r"
        assert t.r_multiple == pytest.approx(2.0, abs=0.02)
        assert t.bars_held == 1

    def test_ride_ema9_exit_on_close_below_ema9(self):
        """Price holds above ema9 for a bar, then closes at 10.1 -- verified
        interactively: ema9 there is ~10.127 (below) while vwap is ~10.025
        (still above, so vwap_lost must NOT preempt this) -- the
        ride_ema9-specific exit must fire."""
        rows = base_rows() + [
            (10.5, 10.6, 10.4, 10.5, VOL),     # fill
            (10.5, 10.8, 10.4, 10.6, VOL),      # still above ema9
            (10.6, 10.7, 10.05, 10.1, VOL),     # closes below ema9, above vwap
            (10.1, 10.2, 10.0, 10.1, VOL),      # must NOT be reached
        ]
        t = one_trade(rows, exit_mode="ride_ema9")
        assert t.reason == "ema9_lost"
        assert t.bars_held == 2

    def test_trail_atr_exit(self):
        """Peak rises to 12.2 across two rallying bars, then a bar's low
        (10.3) undercuts peak - TRAIL_ATR*atr14 (~10.75 at that bar) while
        staying above both the ~9.34 stop and that bar's own VWAP -- the
        ATR trail, and only the trail, must fire."""
        rows = base_rows() + [
            (10.5, 10.6, 10.4, 10.5, VOL),      # fill
            (10.5, 12.0, 10.4, 11.9, VOL),       # rally
            (11.9, 12.2, 11.8, 12.1, VOL),        # peak -> 12.2 after this bar
            (12.1, 12.2, 10.3, 10.4, VOL),        # undercuts the trail, not the stop
            (10.4, 10.5, 10.3, 10.4, VOL),        # must NOT be reached
        ]
        t = one_trade(rows, exit_mode="trail_atr")
        assert t.reason == "trail_atr"
        assert t.exit_price == pytest.approx(10.7381, abs=1e-3)
        assert t.bars_held == 3


# --- §4.3 re-entry gate ----------------------------------------------------

class TestReentryGate:
    def test_max_entries_and_no_overlapping_reentries(self):
        """A session engineered to produce FIVE raw Setup A/B triggers, each
        with a fast exit that reopens the two bearish bars a fresh reclaim
        needs -- verified interactively (find_setups returns 5). Only
        MAX_ENTRIES_PER_SESSION(4) may become trades, and every trade's
        entry must come strictly after the previous trade's exit (the >= 1
        bar re-entry gap, which also rules out overlapping positions)."""
        def cycle(o_start):
            bearish = (o_start, o_start - 0.1, o_start - 1.0, o_start - 0.9, VOL)
            r_open = o_start - 0.9
            reclaim = (r_open, r_open + 1.2, r_open - 0.1, r_open + 1.1, VOL)
            exit_close = r_open + 1.1 - 0.9
            fill_exit = (r_open + 1.1, r_open + 1.15, exit_close - 0.1, exit_close, VOL)
            return [bearish, reclaim, fill_exit], exit_close

        rows = base_rows() + [
            (10.5, 10.6, 10.4, 10.5, VOL),     # fill (Setup A #1)
            (10.4, 10.5, 9.0, 9.2, VOL),         # quick stop exit -> bearish
        ]
        last_close = 9.2
        for _ in range(6):
            c, last_close = cycle(last_close + 1.0)
            rows += c

        df = make_bars(rows)
        assert len(find_setups(df)) == 5   # ungated: five raw triggers exist

        trades = backtest_session_tf(df, DATE, ET, 1)
        assert len(trades) == MAX_ENTRIES_PER_SESSION == 4

        exit_times = [pd.Timestamp(t.exit_time) for t in trades]
        entry_times = [pd.Timestamp(t.entry_time) for t in trades]
        for i in range(1, len(trades)):
            assert entry_times[i] > exit_times[i - 1], (
                "each trade must open strictly after the previous one's exit")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
