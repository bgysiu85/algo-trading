"""Tests for strategy/htf/costs.py. W15-0004 step 7, Amendment A pricing."""
from __future__ import annotations

import pytest

from strategy.htf import costs as C


class TestPerSide:
    def test_low_is_the_amendment_a_all_in_fee(self):
        assert C.per_side("MCL", "low") == pytest.approx(1.09)
        assert C.per_side("CL", "low") == pytest.approx(2.99)

    def test_mid_adds_one_tick(self):
        assert C.per_side("MCL", "mid") == pytest.approx(1.09 + 1.0)
        assert C.per_side("CL", "mid") == pytest.approx(2.99 + 10.0)

    def test_high_adds_two_ticks(self):
        assert C.per_side("MCL", "high") == pytest.approx(1.09 + 2.0)
        assert C.per_side("CL", "high") == pytest.approx(2.99 + 20.0)

    def test_unknown_symbol_raises(self):
        with pytest.raises(ValueError):
            C.per_side("ES", "low")

    def test_unknown_level_raises(self):
        with pytest.raises(ValueError):
            C.per_side("MCL", "extreme")


class TestRoundTripCost:
    def test_one_round_trip_is_two_sides(self):
        assert C.round_trip_cost("MCL", "mid", n_round_trips=1) == pytest.approx(2 * 2.09)

    def test_a_roll_crossing_trade_charges_two_round_trips(self):
        assert C.round_trip_cost("MCL", "mid", n_round_trips=2) == pytest.approx(4 * 2.09)

    def test_scales_with_qty(self):
        assert C.round_trip_cost("MCL", "low", n_round_trips=1, qty=3) == pytest.approx(3 * 2 * 1.09)

    def test_negative_inputs_raise(self):
        with pytest.raises(ValueError):
            C.round_trip_cost("MCL", "low", n_round_trips=-1)
        with pytest.raises(ValueError):
            C.round_trip_cost("MCL", "low", qty=-1)


class TestPnlDollars:
    def test_long_profits_when_exit_above_entry(self):
        # MCL multiplier 100: $0.50/bbl move -> $50
        assert C.pnl_dollars("MCL", 100.0, 100.50, "long") == pytest.approx(50.0)

    def test_short_profits_when_exit_below_entry(self):
        assert C.pnl_dollars("MCL", 100.0, 99.50, "short") == pytest.approx(50.0)

    def test_cl_multiplier_is_ten_times_mcl(self):
        assert C.pnl_dollars("CL", 100.0, 100.50, "long") == pytest.approx(500.0)

    def test_scales_with_qty(self):
        assert C.pnl_dollars("MCL", 100.0, 100.50, "long", qty=4) == pytest.approx(200.0)

    def test_bad_direction_raises(self):
        with pytest.raises(ValueError):
            C.pnl_dollars("MCL", 100.0, 100.5, "sideways")
