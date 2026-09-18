"""Amendment F's excursion measurement and its pre-registered decision rule."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.orb import sip as S
from strategy.orb import sip_excursion as X


def _bars(minutes, highs, lows, closes):
    return (np.array(minutes), np.array(highs, float),
            np.array(lows, float), np.array(closes, float))


def test_long_excursion_is_measured_in_multiples_of_risk():
    m, h, l, c = _bars([600, 601, 602], [100, 101, 104], [99, 98, 103], [100, 98, 103])
    mae, mfe, end, before, n = X.excursion(m, h, l, c, S.LONG, 600, 100.0, 1.0)
    assert mae == pytest.approx(2.0)     # low 98, two 1.0-risk units down
    assert mfe == pytest.approx(4.0)     # high 104
    assert end == pytest.approx(3.0)     # close 103
    assert n == 3


def test_short_excursion_flips_both_directions():
    m, h, l, c = _bars([600, 601], [102, 101], [99, 95], [96, 96])
    mae, mfe, end, before, n = X.excursion(m, h, l, c, S.SHORT, 600, 100.0, 2.0)
    assert mae == pytest.approx(1.0)     # high 102, one 2.0-risk unit against
    assert mfe == pytest.approx(2.5)     # low 95
    assert end == pytest.approx(2.0)     # close 96, favourable for a short


def test_bars_before_the_entry_minute_are_excluded():
    # the 30-point crash at 599 happened before the position existed
    m, h, l, c = _bars([599, 600, 601], [100, 100, 101], [70, 99, 100], [70, 100, 101])
    mae, *_ = X.excursion(m, h, l, c, S.LONG, 600, 100.0, 1.0)
    assert mae == pytest.approx(1.0)


def test_bars_after_the_last_rth_minute_are_excluded():
    after = S.LAST_BAR_MIN + 1
    m, h, l, c = _bars([600, after], [101, 101], [99, 50], [100, 50])
    mae, _mfe, end, *_ = X.excursion(m, h, l, c, S.LONG, 600, 100.0, 1.0)
    assert mae == pytest.approx(1.0)
    assert end == pytest.approx(0.0)     # the 600 close, not the after-hours one


def test_order_is_recorded_adverse_extreme_first():
    m, h, l, c = _bars([600, 601, 602], [100, 100, 106], [98, 99, 105], [99, 99, 105])
    *_x, before, _n = X.excursion(m, h, l, c, S.LONG, 600, 100.0, 1.0)
    assert before is True


def test_order_is_recorded_when_it_ran_first_and_gave_it_back():
    m, h, l, c = _bars([600, 601, 602], [106, 100, 100], [100, 99, 98], [105, 99, 101])
    *_x, before, _n = X.excursion(m, h, l, c, S.LONG, 600, 100.0, 1.0)
    assert before is False


def test_one_bar_holding_both_extremes_counts_against_the_favourable_case():
    m, h, l, c = _bars([600], [110], [90], [101])
    *_x, before, _n = X.excursion(m, h, l, c, S.LONG, 600, 100.0, 1.0)
    assert before is False


def test_no_bars_at_or_after_entry_returns_none():
    m, h, l, c = _bars([598, 599], [101, 101], [99, 99], [100, 100])
    assert X.excursion(m, h, l, c, S.LONG, 600, 100.0, 1.0) is None


def test_zero_risk_returns_none_rather_than_dividing():
    m, h, l, c = _bars([600], [101], [99], [100])
    assert X.excursion(m, h, l, c, S.LONG, 600, 100.0, 0.0) is None


# --------------------------------------------------------------- F.3 / F.3.1

def _losers(rows):
    return pd.DataFrame(rows, columns=["mae_r", "end_r", "mae_before_mfe"])


def test_rescuable_needs_all_three_conditions():
    d = _losers([
        (1.0, +1.0, True),    # rescuable
        (2.5, +1.0, True),    # went too far against
        (1.0, -1.0, True),    # never recovered
        (1.0, +1.0, False),   # ran first, gave it back
    ])
    assert list(X.rescuable(d)) == [True, False, False, False]


def test_the_gate_is_a_greater_than_or_equal_at_twenty_five_percent():
    d = _losers([(1.0, 1.0, True)] + [(3.0, -1.0, True)] * 3)
    v = X.verdict(d)
    assert v["share"] == pytest.approx(0.25)
    assert v["proceed"] is True


def test_below_the_gate_closes_orb():
    d = _losers([(1.0, 1.0, True)] + [(3.0, -1.0, True)] * 4)
    v = X.verdict(d)
    assert v["share"] == pytest.approx(0.20)
    assert v["proceed"] is False
    assert v["closes"] is True
    assert v["width"] is None


def test_the_width_is_the_smallest_k_reaching_the_cover_bar():
    # the 2.4R trade is NOT rescuable (F.3 caps it at 2R), so the three
    # rescuable ones are the denominator: 1 of 3 inside 1.5R, 3 of 3 inside 2R
    d = _losers([(1.2, 1.0, True), (1.7, 1.0, True),
                 (1.9, 1.0, True), (2.4, 1.0, True)])
    v = X.verdict(d)
    assert v["proceed"] is True
    assert v["rescuable"] == 3
    assert v["cover"][1.5] == pytest.approx(1 / 3)
    assert v["cover"][2.0] == pytest.approx(1.0)
    assert v["width"] == 2.0


def test_the_two_R_width_always_covers_every_rescuable_trade():
    """F.3 caps rescuable at 2R, so cover[2.0] is 1.0 by construction.

    This is why F.3.1's "no width reaches the bar" branch cannot fire while
    any rescuable trade exists, and why the width can only be 1.5 or 2.0.
    """
    d = _losers([(1.9, 1.0, True), (1.95, 1.0, True), (0.4, 1.0, True)])
    v = X.verdict(d)
    assert v["cover"][2.0] == pytest.approx(1.0)
    assert v["width"] in (1.5, 2.0)


def test_a_width_is_never_chosen_when_the_gate_says_close():
    # one rescuable trade well inside 1.5R, but only 1 of 5 losers
    d = _losers([(0.5, 1.0, True)] + [(3.0, -1.0, True)] * 4)
    v = X.verdict(d)
    assert v["proceed"] is False
    assert v["width"] is None
    assert v["closes"] is True


def test_cover_is_measured_over_rescuable_losers_not_all_losers():
    d = _losers([(1.0, 1.0, True),                 # rescuable, inside 1.5
                 (5.0, -1.0, True), (6.0, -1.0, True), (7.0, -1.0, True)])
    v = X.verdict(d)
    assert v["cover"][1.5] == pytest.approx(1.0)   # 1 of 1 rescuable, not 1 of 4
    assert v["width"] == 1.5


def test_an_empty_loser_set_does_not_divide_by_zero():
    v = X.verdict(_losers([]))
    assert v["share"] == 0.0 and v["proceed"] is False and v["closes"] is True
