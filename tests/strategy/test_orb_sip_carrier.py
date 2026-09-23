"""Amendment G: carrier days, the lift, and the bar that decides the gate."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.orb import sip_carrier as C


def _led(rows):
    """rows: (date, symbol, R_BASE)"""
    return pd.DataFrame(rows, columns=["date", "symbol", "R_BASE"])


def test_carriers_are_the_largest_trades_by_net_r():
    d = _led([("d1", "A", 5.0), ("d2", "B", 1.0), ("d3", "C", 9.0)])
    assert sorted(d.loc[C.carriers(d, 2), "symbol"]) == ["A", "C"]


def test_the_carrier_trade_itself_is_excluded_from_the_lift():
    # one huge carrier on d1; the rest of d1 is ordinary
    d = _led([("d1", "A", 40.0), ("d1", "B", 0.0), ("d1", "C", 0.0),
              ("d2", "D", 0.0), ("d2", "E", 0.0)])
    x = C.lift(d, 1)
    assert x["rest_trades"] == 2          # B and C, not A
    assert x["rest_mean"] == pytest.approx(0.0)
    assert x["lift"] == pytest.approx(0.0)


def test_a_good_carrier_day_shows_as_lift():
    d = _led([("d1", "A", 40.0), ("d1", "B", 1.0), ("d1", "C", 1.0),
              ("d2", "D", 0.0), ("d2", "E", 0.0)])
    x = C.lift(d, 1)
    assert x["rest_mean"] == pytest.approx(1.0)
    assert x["other_mean"] == pytest.approx(0.0)
    assert x["lift"] == pytest.approx(1.0)
    assert x["meets_bar"] is True


def test_the_bar_is_a_greater_than_or_equal_at_one_tenth_r():
    d = _led([("d1", "A", 9.0), ("d1", "B", 0.10),
              ("d2", "C", 0.0), ("d2", "D", 0.0)])
    x = C.lift(d, 1)
    assert x["lift"] == pytest.approx(0.10)
    assert x["meets_bar"] is True


def test_just_under_the_bar_misses():
    d = _led([("d1", "A", 9.0), ("d1", "B", 0.09),
              ("d2", "C", 0.0), ("d2", "D", 0.0)])
    assert C.lift(d, 1)["meets_bar"] is False


def test_two_carriers_on_one_day_collapse_to_one_carrier_day():
    d = _led([("d1", "A", 9.0), ("d1", "B", 8.0), ("d1", "C", 0.0),
              ("d2", "D", 0.0)])
    x = C.lift(d, 2)
    assert x["carrier_days"] == 1
    assert x["rest_trades"] == 1          # C only; A and B are both carriers


def test_every_day_being_a_carrier_day_leaves_no_comparison():
    d = _led([("d1", "A", 9.0), ("d1", "B", 1.0), ("d2", "C", 8.0), ("d2", "D", 1.0)])
    x = C.lift(d, 2)
    assert x["other_trades"] == 0
    assert np.isnan(x["other_mean"]) and np.isnan(x["lift"])
    assert x["meets_bar"] is False        # a nan comparison must not pass


# ------------------------------------------------------------------ G.3 bar

def test_the_bar_must_be_met_at_every_n():
    assert C.verdict([{"meets_bar": True}, {"meets_bar": True}])["register_gate"] is True


def test_a_split_reading_is_a_refusal_not_a_pass():
    v = C.verdict([{"meets_bar": True}, {"meets_bar": False}])
    assert v["split"] is True
    assert v["register_gate"] is False


def test_missing_the_bar_everywhere_retires_the_gate():
    v = C.verdict([{"meets_bar": False}, {"meets_bar": False}])
    assert v["register_gate"] is False and v["split"] is False


# ------------------------------------------------------------ G.4 clustering

def test_clustering_counts_the_distinct_days_the_carriers_fall_on():
    d = _led([("d1", "A", 9.0), ("d1", "B", 8.0), ("d2", "C", 7.0),
              ("d3", "D", 0.0), ("d4", "E", 0.0)])
    assert C.clustering(d, 3, draws=50)["observed"] == 2


def test_perfect_clustering_is_flagged_against_a_spread_null():
    # 6 carriers all on d1; 40 other trades spread over 40 days
    rows = [("d1", f"C{i}", 100.0 + i) for i in range(6)]
    rows += [(f"x{j:02d}", f"S{j:02d}", 0.0) for j in range(40)]
    c = C.clustering(_led(rows), 6, draws=500)
    assert c["observed"] == 1
    assert c["null_mean"] > 1.5
    assert c["clustered"] is True


def test_no_clustering_when_carriers_sit_on_separate_days():
    rows = [(f"d{i:02d}", f"C{i}", 100.0 - i) for i in range(6)]
    rows += [(f"d{i:02d}", f"S{i}", 0.0) for i in range(6, 46)]
    c = C.clustering(_led(rows), 6, draws=500)
    assert c["observed"] == 6
    assert c["clustered"] is False


def test_clustering_is_seeded_and_repeatable():
    rows = [(f"d{i%20:02d}", f"S{i}", float(i)) for i in range(60)]
    d = _led(rows)
    assert C.clustering(d, 10, draws=200)["p"] == C.clustering(d, 10, draws=200)["p"]


def test_the_null_inherits_the_real_trades_per_day_distribution():
    """A ledger where one day holds most trades must not be judged as if
    sessions were equally busy: the null draws from the ledger itself."""
    rows = [("busy", f"B{i}", float(i)) for i in range(30)]
    rows += [(f"q{j:02d}", f"Q{j}", -1.0) for j in range(10)]
    c = C.clustering(_led(rows), 5, draws=500)
    # drawing 5 of 40 trades, 30 of which share one day -> the null itself
    # expects heavy clustering, so an observed 1 is unremarkable
    assert c["null_mean"] < 3.0


def test_the_null_draws_without_replacement():
    """Drawing every trade must always yield every day.

    With replacement the null would report fewer distinct days than the
    ledger contains, making real clustering look ordinary.
    """
    d = _led([(f"d{i:02d}", f"S{i}", float(i)) for i in range(10)])
    c = C.clustering(d, 10, draws=200)
    assert c["observed"] == 10
    assert c["null_mean"] == pytest.approx(10.0)
    assert c["null_p05"] == pytest.approx(10.0)


def test_both_registered_carrier_sizes_are_reported():
    """G.2 fixes N at 20 and 50, both reported, neither chosen after the fact.

    Dropping one would let the reading be taken from whichever line happened
    to fall the convenient side of the bar -- which is the whole reason the
    amendment named two.
    """
    assert C.CARRIER_NS == (20, 50)
    assert C.LIFT_BAR == 0.10
    assert C.DRAWS == 2000
