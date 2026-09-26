"""Tests for strategy/htf/tl_variant.py (v0-TL). W15-0007."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.htf import bars as B
from strategy.htf import preflight as P
from strategy.htf import tl_variant as TLV


def _synth_1h(n_days=900, seed=7):
    """Same generator as test_preflight.py's fixture -- kept local so this
    file has no import-order dependency on it."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2010-06-07", periods=24 * n_days, freq="h", tz="UTC")
    steps = rng.normal(loc=0.002, scale=0.35, size=len(idx))
    t = np.arange(len(idx))
    drift = 3.0 * np.sin(t / 800.0)
    close = 50.0 + np.cumsum(steps) * 0.05 + drift
    close = np.clip(close, 5.0, None)
    high = close + np.abs(rng.normal(0.1, 0.05, len(idx)))
    low = close - np.abs(rng.normal(0.1, 0.05, len(idx)))
    open_ = close - rng.normal(0, 0.05, len(idx))
    df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                       "volume": 100.0, "held_id": 1}, index=idx)
    return df


@pytest.fixture(scope="module")
def grids_and_daily():
    df_1h = _synth_1h()
    return P.prepare_grids(df_1h)


class TestMapToLastClosed4h:
    def test_last_closed_bar_is_strictly_before_trigger_open(self):
        four_h_t_open = np.array(["2020-01-01T00:00", "2020-01-01T04:00",
                                  "2020-01-01T08:00", "2020-01-01T12:00"],
                                 dtype="datetime64[ns]")
        # a trigger opening exactly at 08:00 (the start of the 3rd 4H bar,
        # which is therefore still forming) must resolve to bar 1 (04:00),
        # not bar 2 (08:00) -- the 08:00 bar has not closed yet.
        entry_t_open = np.array(["2020-01-01T08:00"], dtype="datetime64[ns]")
        idx = TLV.map_to_last_closed_4h(entry_t_open, four_h_t_open)
        assert idx.tolist() == [1]

    def test_exactly_at_a_bars_close_uses_that_bar(self):
        four_h_t_open = np.array(["2020-01-01T00:00", "2020-01-01T04:00"],
                                 dtype="datetime64[ns]")
        # a trigger opening at 04:00 (== bar 0's own close) may use bar 0
        entry_t_open = np.array(["2020-01-01T04:00"], dtype="datetime64[ns]")
        idx = TLV.map_to_last_closed_4h(entry_t_open, four_h_t_open)
        assert idx.tolist() == [0]

    def test_before_any_4h_bar_closes_returns_minus_one(self):
        four_h_t_open = np.array(["2020-01-01T00:00"], dtype="datetime64[ns]")
        entry_t_open = np.array(["2020-01-01T02:00"], dtype="datetime64[ns]")
        idx = TLV.map_to_last_closed_4h(entry_t_open, four_h_t_open)
        assert idx.tolist() == [-1]

    def test_scenario_b_maps_each_bar_to_at_most_the_one_immediately_before_it(self, grids_and_daily):
        """B's entry chart IS the 4H chart, so every trigger's last-closed
        4H bar can never be its own bar or later -- and where consecutive
        4H bars really are exactly 4h apart (no session/weekend gap), it
        must be exactly the previous one. A session gap (weekend, holiday)
        makes an EARLIER bar the correct answer for some i, which is
        correct behaviour, not an off-by-one -- so this only asserts the
        <= i-1 bound plus exactness on the (majority) contiguous bars."""
        grids, _ = grids_and_daily
        four_h = grids["4H"]
        t_open = four_h["t_open"].values
        idx = TLV.map_to_last_closed_4h(t_open, t_open)
        assert (idx[1:] <= np.arange(len(t_open) - 1)).all()
        contiguous = (t_open[1:] - t_open[:-1]) == np.timedelta64(4, "h")
        expected_contiguous = np.arange(len(t_open) - 1)[contiguous]
        assert idx[1:][contiguous].tolist() == expected_contiguous.tolist()


class TestTlBreakRetestSeries:
    def _flat_frame(self, n=40, tick=0.01):
        idx = pd.date_range("2020-01-01", periods=n, freq="4h", tz="UTC")
        close = np.full(n, 100.0)
        return idx, close

    def test_no_line_no_signal(self):
        """A dead-flat series has no pivots at all -> no break, no retest."""
        idx, close = self._flat_frame()
        four_h = pd.DataFrame({"t_open": idx, "high_adj": close + 0.05,
                               "low_adj": close - 0.05, "close_adj": close})
        bull, bear = TLV.tl_break_retest_series(four_h)
        assert not bull.any()
        assert not bear.any()

    def test_hand_built_break_then_retest_is_flagged_within_window(self):
        """Descending swing highs (a falling resistance line), a clean
        break above it, a pullback that retests it from above and closes
        back beyond it -- bullish_ok must fire at the retest bar, and only
        within TL_LOOKBACK_BARS of the break."""
        n = 60
        idx = pd.date_range("2020-01-01", periods=n, freq="4h", tz="UTC")
        # a strictly decreasing baseline (not literally flat) so find_pivots'
        # >= comparison never ties two bars against each other -- a tie
        # would itself register as a spurious pivot and disrupt the
        # intended two-pivot line construction below
        close = 100.0 - np.arange(n) * 0.0001
        high = close + 0.5
        low = close - 0.5
        # two descending swing highs at positions 10 and 30 (L=R=5 default)
        high[10] = 110.0
        high[30] = 105.0
        # after the second pivot confirms (30+5=35), extrapolate the line
        # and break it upward a few bars later, then retest it
        # line value at j = 105.0 + slope*(j-30); slope = (105-110)/20 = -0.25
        break_bar = 38
        line_at_break = 105.0 + (-0.25) * (break_bar - 30)
        close[break_bar] = line_at_break + 1.0   # clears BUFFER_MULT*ATR
        high[break_bar] = close[break_bar] + 0.2
        retest_bar = break_bar + 2
        line_at_retest = 105.0 + (-0.25) * (retest_bar - 30)
        low[retest_bar] = line_at_retest + 0.01   # within 0.25*ATR of the line
        close[retest_bar] = line_at_retest + 0.5  # closes back beyond (above) it
        four_h = pd.DataFrame({"t_open": idx, "high_adj": high, "low_adj": low,
                               "close_adj": close})
        bull, bear = TLV.tl_break_retest_series(four_h)
        assert bull[retest_bar], "expected a flagged retest at the built retest bar"
        assert not bear.any()

    def test_retest_far_past_lookback_from_its_break_is_not_flagged(self):
        """Same construction as above, but the retest is pushed well past
        TL_LOOKBACK_BARS bars after its own break -- must NOT be flagged
        (module docstring: 'one event per break, on its first retest',
        bounded by TL_LOOKBACK_BARS)."""
        n = 80
        idx = pd.date_range("2020-01-01", periods=n, freq="4h", tz="UTC")
        close = 100.0 - np.arange(n) * 0.0001
        high = close + 0.5
        low = close - 0.5
        high[10] = 110.0
        high[30] = 105.0
        break_bar = 38
        line_at_break = 105.0 + (-0.25) * (break_bar - 30)
        close[break_bar] = line_at_break + 1.0
        high[break_bar] = close[break_bar] + 0.2
        retest_bar = break_bar + TLV.TL_LOOKBACK_BARS + 5   # well outside the window
        line_at_retest = 105.0 + (-0.25) * (retest_bar - 30)
        low[retest_bar] = line_at_retest + 0.01
        close[retest_bar] = line_at_retest + 0.5
        four_h = pd.DataFrame({"t_open": idx, "high_adj": high, "low_adj": low,
                               "close_adj": close})
        bull, bear = TLV.tl_break_retest_series(four_h)
        assert not bull[retest_bar]


class TestDetectV0TlInvariants:
    """Mirrors test_preflight.py's TestDetectV0Invariants, extended by the
    v0-TL-only 'blocked_no_tl_setup' bucket."""

    @pytest.mark.parametrize("scenario", list(P.ALL_SCENARIOS))
    def test_counts_partition_every_trigger(self, grids_and_daily, scenario):
        grids, daily_adj = grids_and_daily
        entry_adj = grids[P.SCENARIO_GRID[scenario]]
        four_h_adj = grids["4H"]
        entries, counts = TLV.detect_v0_tl(entry_adj, daily_adj, four_h_adj, scenario=scenario)
        accounted = (counts["lapsed"] + counts["blocked_daily_filter"]
                    + counts["blocked_no_tl_setup"] + counts["blocked_end_of_session"]
                    + counts["voided"] + counts["entries"])
        assert accounted == counts["triggers"]
        assert len(entries) == counts["entries"]

    @pytest.mark.parametrize("scenario", list(P.ALL_SCENARIOS))
    def test_entries_have_positive_stop_distance(self, grids_and_daily, scenario):
        grids, daily_adj = grids_and_daily
        entry_adj = grids[P.SCENARIO_GRID[scenario]]
        four_h_adj = grids["4H"]
        entries, _ = TLV.detect_v0_tl(entry_adj, daily_adj, four_h_adj, scenario=scenario)
        assert all(e["stop_dist"] > 0 for e in entries)

    def test_v0_tl_entries_are_a_subset_of_v0s_own_triggers(self, grids_and_daily):
        """Every v0-TL entry is also one of v0's own triggers at the same
        fill bar -- the TL gate can only narrow v0, never invent a new
        entry v0 itself would not have reached (same E1-E3/S1 walk, sec
        2.6: 'E1-E4 plus')."""
        grids, daily_adj = grids_and_daily
        entry_adj = grids["4H"]
        four_h_adj = grids["4H"]
        v0_entries, _ = P.detect_v0(entry_adj, daily_adj, scenario="B")
        tl_entries, _ = TLV.detect_v0_tl(entry_adj, daily_adj, four_h_adj, scenario="B")
        v0_fills = {(e["t_open"], e["direction"]) for e in v0_entries}
        for e in tl_entries:
            assert (e["t_open"], e["direction"]) in v0_fills

    def test_no_lookahead_a_bar_far_after_t_does_not_change_the_decision_at_t(self, grids_and_daily):
        """G4-style guard: mutating price data strictly after a trigger's
        own last-closed 4H bar must not change whether that trigger's TL
        gate passes."""
        grids, daily_adj = grids_and_daily
        entry_adj = grids["B"] if "B" in grids else grids["4H"]
        four_h_adj = grids["4H"].copy()
        entries_before, counts_before = TLV.detect_v0_tl(
            grids["4H"], daily_adj, four_h_adj, scenario="B")

        mutated = grids["4H"].copy()
        # blow up the last 20 bars -- far beyond any trigger near the start
        mutated.loc[mutated.index[-20:], ["high_adj", "low_adj", "close_adj"]] *= 3
        entries_after, counts_after = TLV.detect_v0_tl(
            grids["4H"], daily_adj, mutated, scenario="B")

        n = len(grids["4H"])
        cutoff = n - 20 - TLV.TL_LOOKBACK_BARS - 10  # comfortably before the mutated tail
        early_before = [e for e in entries_before
                        if pd.Timestamp(e["t_open"]) < grids["4H"]["t_open"].iloc[cutoff]]
        early_after = [e for e in entries_after
                      if pd.Timestamp(e["t_open"]) < grids["4H"]["t_open"].iloc[cutoff]]
        assert early_before == early_after
