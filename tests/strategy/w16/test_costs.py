#!/usr/bin/env python3
"""Amendment A figures and the L0-L3 friction ladder.
REGISTERED_w16_session_baselines.md sec 4 (gate G5)."""
from __future__ import annotations

import pytest

import strategy.w16.costs as C


def test_amendment_a_all_in_figures():
    """Read 2026-09-27 from ninjatrader.com/pricing/commissions/ -- pinned
    so a future edit can't silently drift from what was actually read."""
    assert C.ALL_IN_L1 == {"MES": 0.94, "MNQ": 0.94, "ES": 2.87, "NQ": 2.87}


def test_tick_values_match_registered_sec2_and_margin_page():
    assert C.TICK_VALUE == {"MES": 1.25, "MNQ": 0.50, "ES": 12.50, "NQ": 5.00}
    for sym, pv in C.POINT_VALUE.items():
        assert C.TICK_VALUE[sym] == pytest.approx(pv * C.TICK_POINTS)


def test_l1_charges_no_ticks():
    for sym in C.TICK_VALUE:
        assert C.per_side(sym, "L1") == C.ALL_IN_L1[sym]


def test_l2_adds_one_tick_on_market_or_stop_only():
    for sym in C.TICK_VALUE:
        assert C.per_side(sym, "L2", fill_kind="market_or_stop") == pytest.approx(
            C.ALL_IN_L1[sym] + C.TICK_VALUE[sym])
        assert C.per_side(sym, "L2", fill_kind="target") == C.ALL_IN_L1[sym]


def test_l3_adds_two_ticks_on_market_or_stop_only():
    for sym in C.TICK_VALUE:
        assert C.per_side(sym, "L3", fill_kind="market_or_stop") == pytest.approx(
            C.ALL_IN_L1[sym] + 2 * C.TICK_VALUE[sym])
        assert C.per_side(sym, "L3", fill_kind="target") == C.ALL_IN_L1[sym]


def test_l0_is_free():
    for sym in C.TICK_VALUE:
        for kind in C.FILL_KINDS:
            assert C.per_side(sym, "L0", fill_kind=kind) == 0.0


def test_trade_cost_prices_entry_and_exit_independently():
    """A winner (market entry, target exit) and a loser (market entry, stop
    exit) must NOT cost the same at L2/L3."""
    winner = C.trade_cost("MES", "L2", entry_kind="market_or_stop", exit_kind="target")
    loser = C.trade_cost("MES", "L2", entry_kind="market_or_stop", exit_kind="market_or_stop")
    assert loser > winner
    assert winner == pytest.approx(C.ALL_IN_L1["MES"] + C.TICK_VALUE["MES"] + C.ALL_IN_L1["MES"])
    assert loser == pytest.approx(2 * (C.ALL_IN_L1["MES"] + C.TICK_VALUE["MES"]))


def test_unknown_symbol_or_level_refused():
    with pytest.raises(ValueError):
        C.per_side("YM", "L2")
    with pytest.raises(ValueError):
        C.per_side("MES", "L4")
    with pytest.raises(ValueError):
        C.per_side("MES", "L2", fill_kind="limit")


def test_pnl_dollars_long_and_short():
    assert C.pnl_dollars("MES", 5000.0, 5001.0, "long") == pytest.approx(5.0)
    assert C.pnl_dollars("MES", 5000.0, 5001.0, "short") == pytest.approx(-5.0)
    assert C.pnl_dollars("ES", 5000.0, 5001.0, "long") == pytest.approx(50.0)


def test_full_and_micro_symbol_maps_are_consistent():
    assert C.FULL_TO_MICRO == {"ES": "MES", "NQ": "MNQ"}
    assert C.MICRO_TO_FULL == {"MES": "ES", "MNQ": "NQ"}
    for full, micro in C.FULL_TO_MICRO.items():
        assert C.MICRO_TO_FULL[micro] == full


def test_overnight_margin_reported_not_scored():
    assert C.OVERNIGHT_MARGIN["MES"]["initial"] == pytest.approx(2881.37)
    assert C.OVERNIGHT_MARGIN["MNQ"]["initial"] == pytest.approx(4762.37)


# ---------------------------------------------------------------------
# W16-0040 gate G5: the IBKR table is separate; the NinjaTrader table that
# SB-v0, DVP and BB-v0 price with does not move
# ---------------------------------------------------------------------

def test_ibkr_table_matches_the_owa_registration():
    assert C.IBKR_ALL_IN == {"MNQ": 0.62, "NQ": 2.26}
    assert [C.ibkr_per_side("MNQ", lvl) for lvl in C.FRICTION_LEVELS] == pytest.approx(
        [0.0, 0.62, 1.12, 1.62])
    assert [C.ibkr_round_trip("MNQ", lvl) for lvl in ("L1", "L2", "L3")] == pytest.approx(
        [1.24, 2.24, 3.24])
    assert C.ibkr_per_side("NQ", "L2") == pytest.approx(7.26)
    with pytest.raises(ValueError):
        C.ibkr_per_side("MES", "L2")
    with pytest.raises(ValueError):
        C.ibkr_per_side("MNQ", "L4")


def test_adding_ibkr_left_the_ninjatrader_figures_alone():
    assert C.ALL_IN_L1 == {"MES": 0.94, "MNQ": 0.94, "ES": 2.87, "NQ": 2.87}
    assert [C.per_side("MNQ", lvl) for lvl in C.FRICTION_LEVELS] == pytest.approx(
        [0.0, 0.94, 1.44, 1.94])
    assert [C.per_side("NQ", lvl) for lvl in C.FRICTION_LEVELS] == pytest.approx(
        [0.0, 2.87, 7.87, 12.87])
    assert C.trade_cost("MNQ", "L2") == pytest.approx(2.88)
