"""Fixture tests for common.split_guard, per REGISTERED_dux_veto.md sec 10's
own G1-equivalent gate: a true-positive forward split, a true-positive
reverse split, a genuine organic move that must NOT be flagged, the exact
tolerance boundaries (3.0% price, 25.0% volume), and a multi-split window to
confirm compounding rescales correctly.
"""
from common.split_guard import (
    CANDIDATE_FACTORS, PRICE_TOL, VOLUME_TOL,
    DailyBar, detect_split, adjust_for_splits,
)


def _bar(date, close, volume, high=None, low=None) -> DailyBar:
    return DailyBar(date, close=close, volume=volume,
                    high=high if high is not None else close + 1.0,
                    low=low if low is not None else close - 1.0)


class TestConstants:
    def test_registered_tolerances(self):
        assert PRICE_TOL == 3.0
        assert VOLUME_TOL == 25.0

    def test_registered_factors(self):
        assert set(CANDIDATE_FACTORS) == {
            2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0,
            1 / 2, 1 / 3, 1 / 4, 1 / 5, 1 / 6, 1 / 8, 1 / 10,
        }


class TestDetectSplitTruePositives:
    def test_2for1_forward_split(self):
        # price halves, volume exactly doubles -- textbook forward split
        prev = _bar("d0", 100.0, 1_000_000.0)
        curr = _bar("d1", 50.0, 2_000_000.0)
        assert detect_split(prev, curr) == 2.0

    def test_1for10_reverse_split(self):
        # price 10x's up, volume drops to 1/10th -- textbook reverse split
        prev = _bar("d0", 1.0, 50_000_000.0)
        curr = _bar("d1", 10.0, 5_000_000.0)
        assert detect_split(prev, curr) == 1 / 10

    def test_3for1_forward_split(self):
        prev = _bar("d0", 30.0, 900_000.0)
        curr = _bar("d1", 10.0, 2_700_000.0)
        assert detect_split(prev, curr) == 3.0


class TestDetectSplitTrueNegatives:
    def test_genuine_organic_spike_not_flagged(self):
        # price ratio alone matches 1/2 (a 100% gap up) but volume moves the
        # WRONG way for a split (up 50%, not down ~50%) -- a real move, must
        # not be eaten.
        prev = _bar("d0", 10.0, 1_000_000.0)
        curr = _bar("d1", 20.0, 1_500_000.0)
        assert detect_split(prev, curr) is None

    def test_ordinary_day_no_match(self):
        prev = _bar("d0", 10.0, 1_000_000.0)
        curr = _bar("d1", 10.3, 1_050_000.0)
        assert detect_split(prev, curr) is None

    def test_price_matches_but_volume_unchanged(self):
        # price ratio matches 2.0 but volume did not move at all
        prev = _bar("d0", 100.0, 1_000_000.0)
        curr = _bar("d1", 50.0, 1_000_000.0)
        assert detect_split(prev, curr) is None

    def test_non_positive_prior_close_returns_none(self):
        prev = _bar("d0", 0.0, 1_000_000.0)
        curr = _bar("d1", 50.0, 2_000_000.0)
        assert detect_split(prev, curr) is None

    def test_non_positive_prior_volume_returns_none(self):
        prev = _bar("d0", 100.0, 0.0)
        curr = _bar("d1", 50.0, 2_000_000.0)
        assert detect_split(prev, curr) is None


class TestToleranceBoundaries:
    # These pin PRICE_TOL's boundary just inside vs. just outside 3.0%,
    # rather than at the literal knife-edge: deriving curr_close by dividing
    # and detect_split re-dividing to recover the ratio round-trips through
    # floating point, so a value constructed to land at EXACTLY 3.0000...%
    # can come back as 3.0000000000000027% and fail a strict <= for reasons
    # that have nothing to do with the heuristic's actual logic. 2.99%/3.01%
    # still exercises the real boundary -- inside is accepted, outside is
    # not -- without hinging on float round-trip precision.
    def test_price_ratio_just_inside_3pct_edge_detects(self):
        prev_close = 100.0
        curr_close = prev_close / (2.0 * 1.0299)
        prev = _bar("d0", prev_close, 1_000_000.0)
        curr = _bar("d1", curr_close, 2_000_000.0)  # volume ratio exactly 2.0, safely inside
        assert detect_split(prev, curr) == 2.0

    def test_price_ratio_just_outside_3pct_edge_does_not_detect(self):
        prev_close = 100.0
        curr_close = prev_close / (2.0 * 1.0301)
        prev = _bar("d0", prev_close, 1_000_000.0)
        curr = _bar("d1", curr_close, 2_000_000.0)
        assert detect_split(prev, curr) is None

    def test_volume_ratio_at_exact_25pct_edge_detects(self):
        # factor 2.0, price ratio exact; volume ratio at +25% exactly -> detected
        prev = _bar("d0", 100.0, 1_000_000.0)
        curr = _bar("d1", 50.0, 2_500_000.0)  # 2.5 / 2.0 - 1 = 25.0% exactly
        assert detect_split(prev, curr) == 2.0

    def test_volume_ratio_just_past_25pct_edge_does_not_detect(self):
        prev = _bar("d0", 100.0, 1_000_000.0)
        curr = _bar("d1", 50.0, 2_500_001.0)
        assert detect_split(prev, curr) is None


class TestAdjustForSplits:
    def test_no_split_series_unchanged(self):
        daily = [_bar("d0", 10.0, 1_000_000.0), _bar("d1", 10.3, 1_050_000.0),
                 _bar("d2", 10.1, 980_000.0)]
        out = adjust_for_splits(daily)
        assert out == daily

    def test_single_split_rescales_everything_before_it(self):
        daily = [_bar("d0", 100.0, 1_000_000.0), _bar("d1", 50.0, 2_000_000.0),
                 _bar("d2", 51.0, 1_100_000.0)]
        out = adjust_for_splits(daily)
        # d0 rescaled to d1's post-split scale; d1 and d2 untouched
        assert out[0].close == 50.0
        assert out[0].volume == 2_000_000.0
        assert out[1] == daily[1]
        assert out[2] == daily[2]

    def test_two_splits_in_one_window_compound_correctly(self):
        # d0 -> d1 is a 2-for-1; d1 -> d2 is another 2-for-1. After
        # adjustment every bar should read on d2's scale: close $100,
        # volume 1,000,000, exactly.
        daily = [_bar("d0", 400.0, 250_000.0), _bar("d1", 200.0, 500_000.0),
                 _bar("d2", 100.0, 1_000_000.0)]
        out = adjust_for_splits(daily)
        for b in out:
            assert b.close == 100.0
            assert b.volume == 1_000_000.0
        assert out[2] == daily[2]  # the most recent bar is never touched

    def test_genuine_spike_day_survives_adjustment_untouched(self):
        # a real spike between d1/d2 (price up, volume up -- not a split
        # signature) must not be rescaled by adjust_for_splits either.
        daily = [_bar("d0", 10.0, 1_000_000.0), _bar("d1", 10.2, 1_020_000.0),
                 _bar("d2", 20.4, 1_530_000.0)]  # +100% price, +50% volume
        out = adjust_for_splits(daily)
        assert out == daily

    def test_empty_and_single_bar_do_not_raise(self):
        assert adjust_for_splits([]) == []
        one = [_bar("d0", 10.0, 1_000_000.0)]
        assert adjust_for_splits(one) == one
