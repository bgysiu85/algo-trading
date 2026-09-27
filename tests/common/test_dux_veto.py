#!/usr/bin/env python3
"""G1 (docs/research/REGISTERED_dux_veto.md §0): unit tests for the three
tag functions, against hand-built fixtures, including every boundary value
the registration names exactly, before either is run against a real book."""
from __future__ import annotations

from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from common.dux_veto import (
    DailyBar,
    TAG_B_DOLLAR_BLOCK,
    TAG_B_LOOKBACK,
    TAG_G_GAP_PCT,
    TAG_G_PREMKT_VOL,
    _dollar_block_tagged,
    _green_run_ending_at,
    _is_run_day,
    _spike_metrics,
    _trailing_window,
    books_and_pairs,
    dollar_block_sensitivity,
    tag_crowded_gap,
    tag_dollar_block,
    tag_post_first_red_day,
)

ET = ZoneInfo("America/New_York")


def _bars(rows: list[tuple[str, float, float, float, float]]) -> pd.DataFrame:
    """rows: (HH:MM, high, low, close, volume) on 2026-01-05 ET."""
    idx = pd.DatetimeIndex(
        [pd.Timestamp(f"2026-01-05 {t}", tz=ET) for t, *_ in rows])
    return pd.DataFrame(
        {"high": [r[1] for r in rows], "low": [r[2] for r in rows],
         "close": [r[3] for r in rows], "volume": [r[4] for r in rows]},
        index=idx)


# =============================== TAG G ============================================

class TestTagCrowdedGap:
    def test_true_positive(self):
        df = _bars([("04:00", 15.0, 9.5, 10.0, 30_000_000),
                    ("04:01", 20.0, 14.0, 19.0, 30_000_000)])
        tagged, gap, vol = tag_crowded_gap(df, df.index[-1], prev_close=10.0)
        assert tagged is True
        assert gap == pytest.approx(100.0)
        assert vol == pytest.approx(60_000_000.0)

    def test_true_negative_gap_too_small(self):
        df = _bars([("04:00", 15.0, 9.5, 10.0, 60_000_000)])
        tagged, gap, _ = tag_crowded_gap(df, df.index[-1], prev_close=10.0)
        assert tagged is False
        assert gap == pytest.approx(50.0)

    def test_true_negative_volume_too_small(self):
        df = _bars([("04:00", 20.0, 9.5, 10.0, 40_000_000)])
        tagged, gap, vol = tag_crowded_gap(df, df.index[-1], prev_close=10.0)
        assert tagged is False
        assert gap == pytest.approx(100.0)
        assert vol == pytest.approx(40_000_000.0)

    def test_boundary_gap_exactly_100_pct_counts(self):
        # running high 20 vs prev close 10 -> gap = (20-10)/10*100 = 100.0
        df = _bars([("04:00", 20.0, 9.5, 15.0, 50_000_001)])
        tagged, gap, vol = tag_crowded_gap(df, df.index[-1], prev_close=10.0)
        assert gap == pytest.approx(TAG_G_GAP_PCT)
        assert tagged is True   # >= is inclusive at the boundary

    def test_boundary_gap_just_under_100_pct_excluded(self):
        df = _bars([("04:00", 19.999, 9.5, 15.0, 60_000_000)])
        tagged, gap, _ = tag_crowded_gap(df, df.index[-1], prev_close=10.0)
        assert gap < 100.0
        assert tagged is False

    def test_boundary_premkt_vol_exactly_50m_excluded(self):
        # strict ">" -- exactly 50,000,000 does NOT count
        df = _bars([("04:00", 20.0, 9.5, 15.0, 50_000_000)])
        tagged, gap, vol = tag_crowded_gap(df, df.index[-1], prev_close=10.0)
        assert vol == pytest.approx(TAG_G_PREMKT_VOL)
        assert gap >= 100.0
        assert tagged is False

    def test_boundary_premkt_vol_just_over_50m_counts(self):
        df = _bars([("04:00", 20.0, 9.5, 15.0, 50_000_001)])
        tagged, _, vol = tag_crowded_gap(df, df.index[-1], prev_close=10.0)
        assert vol > TAG_G_PREMKT_VOL
        assert tagged is True

    def test_missing_prev_close_is_untagged_not_false_positive(self):
        df = _bars([("04:00", 20.0, 9.5, 15.0, 60_000_000)])
        tagged, gap, vol = tag_crowded_gap(df, df.index[-1], prev_close=None)
        assert tagged is False
        assert gap != gap  # NaN
        assert vol != vol

    def test_zero_or_negative_prev_close_is_untagged(self):
        df = _bars([("04:00", 20.0, 9.5, 15.0, 60_000_000)])
        tagged, _, _ = tag_crowded_gap(df, df.index[-1], prev_close=0.0)
        assert tagged is False
        tagged, _, _ = tag_crowded_gap(df, df.index[-1], prev_close=-5.0)
        assert tagged is False

    def test_uses_running_high_not_entry_bar_close(self):
        # the pop already stalled by the entry bar -- gap must still be
        # measured off the SESSION'S running high, not the current close.
        df = _bars([("04:00", 25.0, 9.5, 24.0, 30_000_000),
                    ("04:05", 16.0, 15.0, 15.5, 30_000_000)])  # faded hard
        tagged, gap, _ = tag_crowded_gap(df, df.index[-1], prev_close=10.0)
        assert gap == pytest.approx(150.0)   # off the 25.0 running high
        assert tagged is True


# =============================== TAG B ============================================

class TestTagDollarBlock:
    def test_no_spike_day_in_window(self):
        daily = [DailyBar("2026-01-0{}".format(i), close=10.0 + i, volume=1000,
                          high=10.5 + i, low=9.8 + i) for i in range(1, 4)]
        tagged, block, level = tag_dollar_block(daily, entry_running_high=12.0)
        assert (tagged, block, level) == (False, None, None)

    def test_true_positive(self):
        daily = [
            DailyBar("2026-01-01", close=5.0, volume=1_000, high=5.2, low=4.9),
            DailyBar("2026-01-02", close=20.0, volume=8_000_000, high=22.0, low=9.0),  # spike, range 144%
            DailyBar("2026-01-03", close=18.0, volume=500, high=18.5, low=17.5),
        ]
        tagged, block, level = tag_dollar_block(daily, entry_running_high=20.5)
        assert level == pytest.approx(20.0)
        assert block == pytest.approx(20.0 * 8_000_000)
        assert tagged is True

    def test_excludes_a_non_spike_day_even_with_huge_dollar_volume(self):
        daily = [
            DailyBar("2026-01-01", close=10.0, volume=1_000, high=10.2, low=9.9),
            # NOT a spike: (11-10)/10 = 10% range, but a huge $ volume
            DailyBar("2026-01-02", close=11.0, volume=50_000_000, high=11.0, low=10.0),
            # IS a spike, smaller $ volume
            DailyBar("2026-01-03", close=15.0, volume=1_000_000, high=16.0, low=7.0),
        ]
        tagged, block, level = tag_dollar_block(daily, entry_running_high=15.2)
        assert level == pytest.approx(15.0)   # the spike day, not the bigger-$ day
        assert block == pytest.approx(15.0 * 1_000_000)

    def test_boundary_spike_range_exactly_100_pct_counts(self):
        daily = [
            DailyBar("2026-01-01", close=9.0, volume=100, high=9.1, low=8.9),
            DailyBar("2026-01-02", close=15.0, volume=10_000_000, high=20.0, low=10.0),  # (20-10)/10=100.0 exactly
        ]
        spike_range = (20.0 - 10.0) / 10.0 * 100.0
        assert spike_range == pytest.approx(100.0)
        tagged, block, level = tag_dollar_block(daily, entry_running_high=15.0)
        assert level == pytest.approx(15.0)  # the spike day was picked up

    def test_boundary_dollar_block_exactly_140m_counts(self):
        # close 20.0 * volume 7,000,000 = 140,000,000 exactly
        daily = [DailyBar("2026-01-01", close=20.0, volume=7_000_000, high=22.0, low=10.0)]
        tagged, block, level = tag_dollar_block(daily, entry_running_high=20.0)
        assert block == pytest.approx(TAG_B_DOLLAR_BLOCK)
        assert tagged is True

    def test_boundary_dollar_block_just_under_140m_excluded(self):
        daily = [DailyBar("2026-01-01", close=20.0, volume=6_999_999, high=22.0, low=10.0)]
        tagged, block, _ = tag_dollar_block(daily, entry_running_high=20.0)
        assert block < TAG_B_DOLLAR_BLOCK
        assert tagged is False

    def test_boundary_band_exactly_5_pct_counts(self):
        # trapped_level 20.0, +5% = 21.0 exactly
        daily = [DailyBar("2026-01-01", close=20.0, volume=7_000_000, high=22.0, low=10.0)]
        tagged, block, level = tag_dollar_block(daily, entry_running_high=21.0)
        assert level == pytest.approx(20.0)
        assert tagged is True

    def test_boundary_band_just_outside_5_pct_excluded(self):
        daily = [DailyBar("2026-01-01", close=20.0, volume=7_000_000, high=22.0, low=10.0)]
        tagged, _, _ = tag_dollar_block(daily, entry_running_high=21.01)
        assert tagged is False

    def test_below_band_lower_bound_also_excluded(self):
        daily = [DailyBar("2026-01-01", close=20.0, volume=7_000_000, high=22.0, low=10.0)]
        tagged, _, _ = tag_dollar_block(daily, entry_running_high=18.99)
        assert tagged is False

    def test_sensitivity_reports_130_140_150(self):
        daily = [DailyBar("2026-01-01", close=20.0, volume=7_000_000, high=22.0, low=10.0)]
        out = dollar_block_sensitivity(daily, entry_running_high=20.0)
        assert set(out) == {130_000_000.0, 140_000_000.0, 150_000_000.0}
        assert out[130_000_000.0] is True    # 140M block clears a 130M bar
        assert out[150_000_000.0] is False   # but not a 150M bar


# =============================== TAG R ============================================

def _daily(seq: list[tuple[str, float, float, float]]) -> list[DailyBar]:
    """seq: (date, close, volume, low); high is irrelevant to this tag and
    fixed at close+1 so bars stay internally consistent."""
    return [DailyBar(d, close=c, volume=v, high=c + 1.0, low=lo) for d, c, v, lo in seq]


class TestIsRunDay:
    def test_green_and_higher_dollar_volume_qualifies(self):
        daily = _daily([("d0", 10.0, 100, 9.5), ("d1", 15.0, 100, 14.5)])
        assert _is_run_day(daily, 1) is True

    def test_red_day_never_qualifies(self):
        daily = _daily([("d0", 15.0, 100, 14.5), ("d1", 10.0, 100, 9.5)])
        assert _is_run_day(daily, 1) is False

    def test_green_but_lower_dollar_volume_does_not_qualify(self):
        daily = _daily([("d0", 10.0, 1000, 9.5), ("d1", 10.5, 10, 10.0)])
        assert _is_run_day(daily, 1) is False


class TestGreenRunEndingAt:
    def test_run_breaks_when_dollar_volume_condition_fails(self):
        # _is_run_day is a per-day test against the IMMEDIATELY PRECEDING
        # calendar day, applied uniformly to every day in a run including
        # its first (the registration's "each [day]... strictly higher...
        # than the day before" names no exception for day 1). d2 fails that
        # test against d1 outright (800 < 3000) -- it does not merely "break
        # a run in progress", it is disqualified from being part of ANY run,
        # including as a fresh day-1, because there is only one calendar day
        # before it and it fails against that day. So d2 cannot restart a
        # run either; only d3 (which passes against d2: 6000 > 800) can, and
        # a length-1 run cannot itself qualify as a "run" under TAG_R (needs
        # >=2 with the >=1000% short-run clause or >=3 with the >=300%
        # clause) -- this fixture exists to pin exactly this boundary, not
        # to produce a qualifying run.
        daily = _daily([
            ("d0", 10.0, 100, 9.5),
            ("d1", 15.0, 200, 14.5),   # ok: 15*200=3000 > 10*100=1000
            ("d2", 16.0, 50, 15.5),    # green but 16*50=800 < 15*200=3000 -- disqualified outright
            ("d3", 20.0, 300, 19.0),   # ok relative to d2: 20*300=6000>16*50=800, but d2 wasn't in a run
        ])
        run = _green_run_ending_at(daily, 3)
        assert run == (3, 3)   # maximal run ending at d3 is d3 alone -- d2 does not qualify as its start

    def test_run_restarts_cleanly_after_a_disqualified_day(self):
        # A genuine restart: d2 is disqualified (as above), but d3 and d4
        # both individually qualify against their own immediate predecessor,
        # forming a fresh 2-day run (3, 4) that does not reach back to d2.
        daily = _daily([
            ("d0", 10.0, 100, 9.5),
            ("d1", 15.0, 200, 14.5),   # 15*200=3000 > 10*100=1000
            ("d2", 16.0, 50, 15.5),    # disqualified: 16*50=800 < 3000
            ("d3", 20.0, 300, 19.0),   # qualifies against d2: 6000 > 800
            ("d4", 25.0, 400, 24.0),   # qualifies against d3: 25*400=10000 > 6000
        ])
        run = _green_run_ending_at(daily, 4)
        assert run == (3, 4)


class TestTagPostFirstRedDay:
    def test_true_positive_3day_run_exactly_300pct(self):
        # pre-run close 10.0; run 15 -> 25 -> 40 (peak); range (40-10)/10*100=300.0
        daily = _daily([
            ("d-1", 10.0, 100, 9.5),
            ("d0", 15.0, 100, 14.5),
            ("d1", 25.0, 100, 24.0),
            ("d2", 40.0, 100, 39.0),
            ("d3", 38.0, 100, 25.0),   # first red day; giveback below
        ])
        tagged, detail = tag_post_first_red_day(daily, entry_date="d4")
        assert detail["run_len"] == 3
        assert detail["run_range_pct"] == pytest.approx(300.0)
        assert detail["pre_run_close"] == pytest.approx(10.0)
        assert detail["peak_close"] == pytest.approx(40.0)
        # giveback = (40-25)/(40-10)*100 = 50.0 exactly -> NOT > 50, so it fires
        assert detail["giveback_pct"] == pytest.approx(50.0)
        assert tagged is True

    def test_boundary_giveback_exactly_50_pct_fires(self):
        daily = _daily([
            ("d-1", 10.0, 100, 9.5), ("d0", 15.0, 100, 14.5),
            ("d1", 25.0, 100, 24.0), ("d2", 40.0, 100, 39.0),
            ("d3", 38.0, 100, 25.0),   # low=25 -> giveback exactly 50.0
        ])
        tagged, detail = tag_post_first_red_day(daily, entry_date="d4")
        assert detail["giveback_pct"] == pytest.approx(50.0)
        assert tagged is True

    def test_boundary_giveback_just_over_50_pct_skips(self):
        daily = _daily([
            ("d-1", 10.0, 100, 9.5), ("d0", 15.0, 100, 14.5),
            ("d1", 25.0, 100, 24.0), ("d2", 40.0, 100, 39.0),
            ("d3", 38.0, 100, 24.99),   # low just below 25 -> giveback just over 50%
        ])
        tagged, detail = tag_post_first_red_day(daily, entry_date="d4")
        assert detail["giveback_pct"] > 50.0
        assert tagged is False

    def test_true_positive_2day_run_exactly_1000pct(self):
        # pre-run close 10.0; peak 110.0 -> range (110-10)/10*100 = 1000.0
        daily = _daily([
            ("d-1", 10.0, 100, 9.5),
            ("d0", 50.0, 100, 49.0),
            ("d1", 110.0, 200, 100.0),   # dollar vol 110*200=22000 > 50*100=5000, run len 2
            ("d2", 100.0, 100, 60.0),    # first red day; giveback (110-60)/(110-10)*100=50.0
        ])
        tagged, detail = tag_post_first_red_day(daily, entry_date="d3")
        assert detail["run_len"] == 2
        assert detail["run_range_pct"] == pytest.approx(1000.0)
        assert tagged is True

    def test_2day_run_just_under_1000pct_does_not_qualify(self):
        daily = _daily([
            ("d-1", 10.0, 100, 9.5),
            ("d0", 50.0, 100, 49.0),
            ("d1", 109.0, 200, 100.0),   # range (109-10)/10*100=990% < 1000
            ("d2", 100.0, 100, 60.0),
        ])
        tagged, detail = tag_post_first_red_day(daily, entry_date="d3")
        assert tagged is False
        # a 2-day run under 1000% never qualifies (3+ days need only 300%,
        # but this run is length 2, so the 300% branch does not apply to it)
        assert detail["run_range_pct"] < 1000.0

    def test_3day_run_just_under_300pct_does_not_qualify(self):
        daily = _daily([
            ("d-1", 10.0, 100, 9.5),
            ("d0", 14.0, 100, 13.5),
            ("d1", 20.0, 100, 19.0),
            ("d2", 29.0, 100, 28.0),     # range (29-10)/10*100=190%
            ("d3", 27.0, 100, 20.0),
        ])
        tagged, detail = tag_post_first_red_day(daily, entry_date="d4")
        assert tagged is False
        assert detail["run_range_pct"] < 300.0

    def test_no_tag_when_day_before_entry_is_green(self):
        daily = _daily([
            ("d-1", 10.0, 100, 9.5), ("d0", 15.0, 100, 14.5),
            ("d1", 25.0, 100, 24.0), ("d2", 40.0, 100, 39.0),
            ("d3", 45.0, 100, 44.0),   # still green -- not a red day
        ])
        tagged, detail = tag_post_first_red_day(daily, entry_date="d4")
        assert tagged is False
        assert detail["run_start"] is None

    def test_no_tag_when_no_run_precedes_the_red_day(self):
        daily = _daily([
            ("d-1", 10.0, 100, 9.5), ("d0", 9.0, 100, 8.5),   # red, not green
            ("d1", 12.0, 100, 11.5),   # green (one day only)
            ("d2", 11.0, 100, 5.0),    # red day, but only a 1-day "run" precedes it
        ])
        tagged, detail = tag_post_first_red_day(daily, entry_date="d3")
        assert tagged is False   # a 1-day run never qualifies (needs >= 2)

    def test_too_short_history_returns_untagged(self):
        daily = _daily([("d0", 10.0, 100, 9.5)])
        tagged, detail = tag_post_first_red_day(daily, entry_date="d1")
        assert tagged is False


# =============================== real-archive wiring (Tag B/R) ====================
# `_spike_metrics`/`_dollar_block_tagged` is the refactor `run_day` relies on to
# avoid re-scanning the daily window on every bar (and, for the sensitivity
# reading, at every threshold); `_trailing_window` is the slicing +
# split-guard-adjustment step between the raw archive and the tag functions;
# `books_and_pairs` is what turns a `--tags` selection into the BOOKS/PAIRED
# structure `run_day` and `main` build the real study from. None of this
# changes `tag_dollar_block`/`tag_post_first_red_day` themselves -- the
# TestTagDollarBlock / TestTagPostFirstRedDay classes above are untouched and
# still exercise those functions directly.

class TestSpikeMetricsRefactor:
    def test_matches_tag_dollar_block_when_tagged(self):
        daily = [
            DailyBar("2026-01-01", close=9.0, volume=100, high=9.1, low=8.9),
            DailyBar("2026-01-02", close=15.0, volume=10_000_000, high=20.0, low=10.0),
        ]
        entry_running_high = 15.3  # within +/-5% of the 15.0 trapped_level
        want = tag_dollar_block(daily, entry_running_high)
        metrics = _spike_metrics(daily)
        got = (_dollar_block_tagged(metrics, entry_running_high), *metrics)
        assert got == want
        assert want[0] is True

    def test_matches_tag_dollar_block_when_no_spike(self):
        daily = [DailyBar("2026-01-01", close=9.0, volume=100, high=9.1, low=8.9)]
        want = tag_dollar_block(daily, entry_running_high=100.0)
        assert want == (False, None, None)
        assert _spike_metrics(daily) is None
        # _dollar_block_tagged must also read "no metrics" as untagged, not raise
        assert _dollar_block_tagged(None, 100.0) is False

    def test_matches_tag_dollar_block_out_of_band(self):
        daily = [
            DailyBar("2026-01-01", close=9.0, volume=100, high=9.1, low=8.9),
            DailyBar("2026-01-02", close=15.0, volume=10_000_000, high=20.0, low=10.0),
        ]
        entry_running_high = 50.0  # far outside the +/-5% band
        want = tag_dollar_block(daily, entry_running_high)
        metrics = _spike_metrics(daily)
        got = (_dollar_block_tagged(metrics, entry_running_high), *metrics)
        assert got == want
        assert want[0] is False

    def test_metrics_reused_across_several_thresholds_matches_sensitivity(self):
        # this is exactly how run_day evaluates TAG_B_SENSITIVITY per bar
        # without re-scanning the daily window at each threshold
        daily = [DailyBar("2026-01-01", close=20.0, volume=7_000_000, high=22.0, low=10.0)]
        metrics = _spike_metrics(daily)
        want = dollar_block_sensitivity(daily, entry_running_high=20.0)
        got = {t: _dollar_block_tagged(metrics, 20.0, threshold=t) for t in want}
        assert got == want


class TestTrailingWindow:
    def _bars(self, dates: list[str]) -> list[DailyBar]:
        return [DailyBar(d, close=10.0 + i, volume=1_000.0 + i, high=10.5 + i, low=9.5 + i)
                for i, d in enumerate(dates)]

    def test_empty_input_returns_empty(self):
        assert _trailing_window([], "2026-01-10") == []

    def test_excludes_the_entry_date_itself_and_later(self):
        bars = self._bars(["2026-01-01", "2026-01-02", "2026-01-03"])
        out = _trailing_window(bars, "2026-01-02")
        assert [b.date for b in out] == ["2026-01-01"]

    def test_no_prior_history_returns_empty(self):
        bars = self._bars(["2026-01-05", "2026-01-06"])
        assert _trailing_window(bars, "2026-01-01") == []

    def test_respects_the_lookback_cap(self):
        dates = [f"2026-01-{d:02d}" for d in range(1, 11)]  # 10 sessions
        bars = self._bars(dates)
        out = _trailing_window(bars, "2026-01-11", lookback=3)
        assert [b.date for b in out] == dates[-3:]

    def test_shorter_history_than_lookback_returns_all_of_it(self):
        bars = self._bars(["2026-01-01", "2026-01-02"])
        out = _trailing_window(bars, "2026-01-05", lookback=252)
        assert len(out) == 2

    def test_applies_split_guard_adjustment_anchored_to_the_window(self):
        # a 2-for-1 split between the two bars in the window; the window
        # ends strictly before entry_date, so adjustment anchors to the
        # LAST bar actually in the window (2026-01-02), not to anything
        # after entry_date, even if `bars` itself continues past entry.
        bars = [
            DailyBar("2026-01-01", close=100.0, volume=1_000_000.0, high=101.0, low=99.0),
            DailyBar("2026-01-02", close=50.0, volume=2_000_000.0, high=51.0, low=49.0),
            DailyBar("2026-01-03", close=51.0, volume=1_100_000.0, high=52.0, low=50.0),
        ]
        out = _trailing_window(bars, "2026-01-03")
        assert [b.date for b in out] == ["2026-01-01", "2026-01-02"]
        assert out[0].close == pytest.approx(50.0)   # 2026-01-01 rescaled to 2026-01-02's scale
        assert out[1].close == pytest.approx(50.0)   # 2026-01-02 itself, untouched

    def test_a_later_split_does_not_contaminate_an_earlier_entrys_window(self):
        # the split lands AFTER the queried entry_date -- _trailing_window
        # must never see it, since it only ever looks at bars strictly
        # before entry_date.
        bars = [
            DailyBar("2026-01-01", close=100.0, volume=1_000_000.0, high=101.0, low=99.0),
            DailyBar("2026-01-02", close=101.0, volume=1_050_000.0, high=102.0, low=100.0),
            DailyBar("2026-01-03", close=50.0, volume=2_100_000.0, high=51.0, low=49.0),  # split here
        ]
        out = _trailing_window(bars, "2026-01-03")
        assert [b.date for b in out] == ["2026-01-01", "2026-01-02"]
        assert out[0].close == pytest.approx(100.0)  # unrescaled -- the split is not in this window
        assert out[1].close == pytest.approx(101.0)


class TestBooksAndPairs:
    def test_single_tag_g_only(self):
        books, paired = books_and_pairs(["G"])
        assert books == (
            ("MCL", "mcl", None), ("MCL-duxG", "mcl", "G"),
            ("MC5", "mc5", None), ("MC5-duxG", "mc5", "G"),
        )
        assert paired == (("MCL", "MCL-duxG"), ("MC5", "MC5-duxG"))

    def test_all_three_tags(self):
        books, paired = books_and_pairs(["G", "B", "R"])
        names = [b[0] for b in books]
        assert names == [
            "MCL", "MCL-duxG", "MCL-duxB", "MCL-duxR",
            "MC5", "MC5-duxG", "MC5-duxB", "MC5-duxR",
        ]
        assert len(paired) == 6
        assert ("MCL", "MCL-duxB") in paired
        assert ("MC5", "MC5-duxR") in paired

    def test_baseline_has_no_gate_tag(self):
        books, _ = books_and_pairs(["B"])
        baseline = {name: tag for name, _, tag in books if tag is None}
        assert set(baseline) == {"MCL", "MC5"}

    def test_gated_name_encodes_its_own_tag_letter(self):
        books, _ = books_and_pairs(["B", "R"])
        for name, _, tag in books:
            if tag is not None:
                assert name == f"{name.split('-dux')[0]}-dux{tag}"
