"""Pin the published IBKR / TradeZero schedules and the plan-switching contract.

The strategy tests deliberately only assert net == gross - commission, so the
fee schedule itself has to be checked here or nowhere. These numbers come from
claude/ibkr_commission_structure.md and the sources it cites; if a broker
changes a rate, this file is what should fail first.
"""
import pytest

from common import commissions as C


# --- the two IBKR plans, at the size actually traded -------------------------

def test_fixed_order_minimum_dominates_at_100_shares():
    # 100 x 0.005 = 0.50, below the $1.00 order minimum, so the minimum binds.
    assert C.fixed_cost(100, 5.0, False).commission == pytest.approx(1.00)
    # 300 x 0.005 = 1.50, above it, so the per-share rate binds.
    assert C.fixed_cost(300, 5.0, False).commission == pytest.approx(1.50)


def test_fixed_is_capped_at_one_percent_of_trade_value():
    # 100 shares at $0.50 is $50 of value; 1% of that is $0.50, which is BELOW
    # the $1.00 minimum. The cap wins -- max applies after min.
    assert C.fixed_cost(100, 0.50, False).commission == pytest.approx(0.50)


def test_tiered_passes_through_what_fixed_absorbs():
    fx = C.fixed_cost(100, 5.0, False)
    td = C.tiered_cost(100, 5.0, False, removing=True)
    assert fx.exchange == 0.0 and fx.clearing == 0.0
    assert td.exchange == pytest.approx(0.30)      # 0.0030 x 100
    assert td.clearing == pytest.approx(0.02)      # 0.00020 x 100


def test_tiered_beats_fixed_at_100_shares_and_loses_at_200():
    """The whole practical finding, pinned."""
    assert C.round_trip(100, 5.0, "ibkr_tiered") < C.round_trip(100, 5.0, "ibkr_fixed")
    assert C.round_trip(200, 5.0, "ibkr_tiered") > C.round_trip(200, 5.0, "ibkr_fixed")


def test_crossover_is_150_shares_and_price_independent():
    # Both plans are per-share above their minimums, so the crossing point
    # depends only on minimums and rates -- not on price.
    for price in (2.0, 5.0, 10.0, 20.0):
        assert C.crossover(price, removing=True) == 150


def test_add_rebate_flips_the_answer():
    """A strategy that POSTED liquidity would want Tiered at every size."""
    for q in (100, 200, 1000):
        assert C.round_trip(q, 5.0, "ibkr_tiered", removing=False) < \
               C.round_trip(q, 5.0, "ibkr_fixed", removing=False)


def test_sub_dollar_removal_fee_is_not_a_penalty():
    """Checked because I assumed the opposite. At exactly $1.00 the per-share
    and percentage forms agree; below it the percentage is smaller."""
    at_one = C.tiered_cost(100, 1.00, False).exchange
    below = C.tiered_cost(100, 0.50, False).exchange
    assert at_one == pytest.approx(0.30)
    assert below == pytest.approx(0.15)
    assert below < at_one


# --- TradeZero ---------------------------------------------------------------

def test_tradezero_free_window_starts_at_0700():
    """MCL trades from 04:00, so this is not an academic boundary."""
    early = C.tradezero_cost(100, 5.0, False, minutes_et=6 * 60 + 59,
                             removing=False, free_requires_non_marketable=False)
    late = C.tradezero_cost(100, 5.0, False, minutes_et=7 * 60,
                            removing=False, free_requires_non_marketable=False)
    assert early.commission == pytest.approx(0.50)     # 0.005 x 100
    assert late.commission == 0.0


def test_tradezero_free_commission_is_not_a_free_trade():
    """Removing liquidity still pays the ECN and routing fees."""
    c = C.tradezero_cost(100, 5.0, False, minutes_et=8 * 60, removing=True,
                         free_requires_non_marketable=False)
    assert c.commission == 0.0
    assert c.exchange == pytest.approx(0.32)           # (0.0030 + 0.0002) x 100
    assert c.total > 0.0


def test_tradezero_strict_reading_never_frees_a_marketable_order():
    c = C.tradezero_cost(100, 5.0, False, minutes_et=8 * 60, removing=True,
                         free_requires_non_marketable=True)
    assert c.commission == pytest.approx(0.50)


def test_tradezero_sub_dollar_has_its_own_minimum():
    c = C.tradezero_cost(50, 0.80, False, minutes_et=8 * 60, removing=True)
    assert c.commission == pytest.approx(C.TZ_MIN_SUB_DOLLAR)


# --- the plan-switching contract --------------------------------------------

def test_legacy_plan_reproduces_the_old_flat_model():
    """Every published P/L in claude/*.md was computed this way. If this
    breaks, those results stop being reproducible."""
    assert C.order_cost(100, 5.0, False, "legacy") == pytest.approx(0.50)
    assert C.order_cost(100, 5.0, True, "legacy") == pytest.approx(0.50)
    assert C.round_trip(100, 5.0, "legacy") == pytest.approx(1.00)


def test_order_cost_is_zero_for_zero_quantity():
    for plan in C.PLANS:
        assert C.order_cost(0, 5.0, False, plan) == 0.0


def test_unknown_plan_raises_rather_than_defaulting():
    with pytest.raises(ValueError):
        C.order_cost(100, 5.0, False, "ibkr")


def test_every_named_plan_is_callable():
    for plan in C.PLANS:
        assert C.order_cost(100, 5.0, False, plan, minutes_et=8 * 60) >= 0.0
