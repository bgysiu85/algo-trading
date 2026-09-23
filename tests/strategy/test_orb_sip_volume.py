"""Amendment I: the break-volume rule, its ceiling, and the four controls."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.orb import sip_volume as V


# ------------------------------------------------------------ I.1 the rule

def test_the_break_bar_is_compared_to_the_five_minutes_before_it():
    m = [570, 571, 572, 573, 574, 575]
    v = [10, 10, 10, 10, 10, 99]
    b, pm, _lv, _lm = V.volumes(m, v, entry_min=575)
    assert b == 99
    assert pm == 10          # median of 570..574


def test_the_break_bar_itself_is_not_in_its_own_baseline():
    m = [573, 574, 575]
    v = [1.0, 3.0, 1000.0]
    b, pm, *_ = V.volumes(m, v, entry_min=575)
    assert b == 1000.0
    assert pm == 2.0         # median of 1 and 3, the 575 bar excluded


def test_the_lagged_reading_is_the_same_rule_one_minute_earlier():
    m = list(range(568, 576))
    v = [1, 1, 1, 1, 1, 1, 7, 500]
    b, pm, lv, lm = V.volumes(m, v, entry_min=575)
    assert (b, pm) == (500, 1)      # ceiling: 575 against 570-574
    assert (lv, lm) == (7, 1)       # tradeable: 574 against 569-573


def test_volumes_return_nan_rather_than_inventing_a_missing_bar():
    b, pm, *_ = V.volumes([570, 571], [5, 5], entry_min=575)
    assert np.isnan(b)
    assert not np.isnan(pm)


def test_bar_order_does_not_matter():
    """The window is cut by minute value, not by position, so an unsorted
    frame gives the same reading as a sorted one."""
    m = [574, 570, 575, 572]
    v = [3.0, 1.0, 50.0, 5.0]
    b, pm, *_ = V.volumes(m, v, entry_min=575)
    assert b == 50.0
    assert pm == 3.0         # median of 1, 5, 3
    assert V.volumes(sorted(m), [1.0, 5.0, 3.0, 50.0], entry_min=575)[:2] == (b, pm)


def test_a_break_above_its_baseline_is_confirmed():
    assert list(V.label([10.0], [9.0])) == [V.CONFIRMED]


def test_a_break_below_its_baseline_is_weak():
    assert list(V.label([8.0], [9.0])) == [V.WEAK]


def test_an_exact_tie_is_weak_not_confirmed():
    assert list(V.label([9.0], [9.0])) == [V.WEAK]


def test_a_missing_reading_is_no_data_never_guessed():
    got = list(V.label([np.nan, 5.0], [1.0, np.nan]))
    assert got == [V.NO_DATA, V.NO_DATA]


# -------------------------------------------------------- I.4(a) the null

def _frame(rows):
    """rows: (symbol, R, keep)"""
    d = pd.DataFrame(rows, columns=["symbol", "R_BASE", "keep"])
    return d


def test_the_null_permutes_labels_and_keeps_the_proportion():
    rows = [(f"S{i}", float(i), i < 3) for i in range(10)]
    out = V.shuffled_label_null(_frame(rows), "R_BASE", "keep", draws=200)
    assert out["valid_draws"] == 200            # 3 kept in every draw
    assert out["obs_mean"] == pytest.approx(1.0)  # 0,1,2


def test_a_label_with_no_information_does_not_beat_its_own_shuffle():
    rng = np.random.default_rng(3)
    rows = [(f"S{i%25:02d}", float(rng.normal()), bool(rng.random() > 0.4))
            for i in range(500)]
    out = V.shuffled_label_null(_frame(rows), "R_BASE", "keep", draws=300)
    assert out["mean_beats"] is False


def test_a_label_that_really_selects_winners_beats_the_shuffle():
    rows = [(f"S{i%25:02d}", 1.0 if i % 2 == 0 else -1.0, i % 2 == 0)
            for i in range(400)]
    out = V.shuffled_label_null(_frame(rows), "R_BASE", "keep", draws=300)
    assert out["obs_mean"] == pytest.approx(1.0)
    assert out["mean_beats"] is True


def test_a_tie_with_the_null_is_not_a_beat():
    rows = [(f"S{i}", float(i), True) for i in range(8)]
    out = V.shuffled_label_null(_frame(rows), "R_BASE", "keep", draws=40)
    assert out["mean_beats"] is False
    assert out["drop5_beats"] is False


def test_the_null_is_seeded_and_repeatable():
    rows = [(f"S{i%6}", float(i), i % 3 == 0) for i in range(40)]
    a = V.shuffled_label_null(_frame(rows), "R_BASE", "keep", draws=100)
    b = V.shuffled_label_null(_frame(rows), "R_BASE", "keep", draws=100)
    assert a["mean_p"] == b["mean_p"] and a["drop5_p"] == b["drop5_p"]


# ------------------------------------------------------- I.4(b)(c)(d) rest

def _labelled(rows):
    """rows: (symbol, date, entry_min, rank, R_BASE, vol_label)"""
    return pd.DataFrame(rows, columns=["symbol", "date", "entry_min", "rank",
                                       "R_BASE", "vol_label"])


def test_composition_reports_the_confirmed_share_by_entry_minute():
    rows = [("A", "d1", 575, 1, 0.0, V.CONFIRMED),
            ("B", "d1", 575, 2, 0.0, V.CONFIRMED),
            ("C", "d1", 900, 3, 0.0, V.WEAK)]
    c = V.composition(_labelled(rows))
    early = c[c["group"] == "when=<=575"].iloc[0]
    late = c[c["group"] == "when=781+"].iloc[0]
    assert early["confirmed_share"] == pytest.approx(1.0)
    assert late["confirmed_share"] == pytest.approx(0.0)


def test_composition_also_splits_by_rank_band():
    rows = [("A", "d1", 600, 2, 0.0, V.CONFIRMED),
            ("B", "d1", 600, 18, 0.0, V.WEAK)]
    c = V.composition(_labelled(rows))
    assert set(c[c["group"].str.startswith("rank_decile")]["group"]) == {
        "rank_decile=1-5", "rank_decile=16-20"}


def test_the_delta_is_confirmed_less_weak_per_symbol():
    rows = [("A", "d1", 600, 1, 5.0, V.CONFIRMED),
            ("A", "d2", 600, 1, 1.0, V.WEAK),
            ("B", "d1", 600, 2, 2.0, V.CONFIRMED),
            ("B", "d2", 600, 2, 3.0, V.WEAK)]
    got = V.delta_drop(_labelled(rows), "R_BASE")
    assert got["delta"] == pytest.approx(3.0)
    assert got["drop1"] == pytest.approx(-1.0)


def test_no_data_trades_are_excluded_from_the_delta():
    rows = [("A", "d1", 600, 1, 5.0, V.CONFIRMED),
            ("A", "d2", 600, 1, 1.0, V.WEAK),
            ("Z", "d1", 600, 3, 99.0, V.NO_DATA)]
    assert V.delta_drop(_labelled(rows), "R_BASE")["symbols"] == 1


def test_the_second_denominator_aggregates_per_symbol_day():
    rows = [("A", "d1", 600, 1, 2.0, V.CONFIRMED),
            ("A", "d1", 601, 1, 2.0, V.CONFIRMED),   # same symbol-day
            ("B", "d2", 600, 2, 1.0, V.WEAK)]
    sd = V.per_symbol_day(_labelled(rows), "R_BASE")
    assert sd[V.CONFIRMED] == pytest.approx(4.0)     # summed, not averaged
    assert sd[V.WEAK] == pytest.approx(1.0)
    assert sd["delta"] == pytest.approx(3.0)


def test_valid_draws_counts_the_draws_that_kept_anything():
    """A label that keeps nothing keeps nothing in every permutation too.

    Degenerate, but it is the only way to check that `valid_draws` counts
    rather than assumes -- which is what lets it detect a null that resamples
    instead of permuting.
    """
    rows = [(f"S{i}", float(i), False) for i in range(6)]
    out = V.shuffled_label_null(_frame(rows), "R_BASE", "keep", draws=30)
    assert np.isnan(out["obs_mean"])
    assert out["valid_draws"] == 0


def test_the_registered_constants_are_what_i_fixed():
    assert V.BASELINE == 5
    assert V.DRAWS == 2000
    assert V.NULL_PCT == 95
