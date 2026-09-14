#!/usr/bin/env python3
"""Is the profitable kind of trade visible at the entry bar?

Three properties carry this module:

1. **The bar is derived from the run's own data**, not pasted from the doc that
   motivated it. A threshold quoted from elsewhere while bucketing a different
   population is this project's recurring defect, one level out.
2. **The bucketing is `entry_features`', imported not copied.** A second
   implementation with its own quantile edges would make a result here
   incomparable with the 0-of-11 null recorded there -- and that null is the
   only thing this run is read against.
3. **Every tier branch is reachable.** A verdict only one branch can reach is a
   constant wearing a decision's clothes.
"""
from __future__ import annotations

import pytest

from common import entry_features as F
from common import entry_split as S


def rows(pairs, dates=None):
    """pairs = [(feature value, label 0/1, net)]"""
    dates = dates or ["2026-01-01"] * len(pairs)
    return [{"f": v, S.LABEL: float(lab), "net": net, "date": d,
             "adverse_first": bool(lab)}
            for (v, lab, net), d in zip(pairs, dates)]


# --- 1. the bar is derived ----------------------------------------------------

def test_break_even_comes_from_the_runs_own_group_means():
    """p * win = (1 - p) * |lose|. With +19.13 and -22.73 after friction that
    is 54.3% -- the figure the doc quotes, recomputed rather than trusted."""
    win = [{S.LABEL: 1.0, "net": 19.13 + 4.26}] * 30
    lose = [{S.LABEL: 0.0, "net": -22.73 + 4.26}] * 70
    be, st = S.break_even_rate(win + lose, 4.26)
    assert be == pytest.approx(22.73 / (19.13 + 22.73), abs=1e-4)
    assert be == pytest.approx(0.543, abs=0.001)
    assert st["base"] == pytest.approx(0.30)


def test_a_book_with_no_losing_group_has_no_break_even_rate():
    """There is no mix of two positives that trades one against the other.
    Returning a number would invent one."""
    both_up = [{S.LABEL: 1.0, "net": 20.0}] * 10 + [{S.LABEL: 0.0,
                                                     "net": 10.0}] * 10
    be, _ = S.break_even_rate(both_up, 4.26)
    assert be != be           # nan


def test_a_book_with_no_winning_group_has_no_break_even_rate():
    both_down = [{S.LABEL: 1.0, "net": -20.0}] * 10 + [{S.LABEL: 0.0,
                                                        "net": -10.0}] * 10
    be, _ = S.break_even_rate(both_down, 4.26)
    assert be != be


def test_the_report_says_no_filter_is_readable_without_a_break_even_rate():
    r = rows([(float(i), 1, 20.0) for i in range(400)])
    o = "\n".join(S.render(r, "mcl", 10, 1.0, 1))
    assert "NO BREAK-EVEN RATE EXISTS" in o
    assert "Nothing below is read as a filter" in o


# --- 2. the bucketing is entry_features' --------------------------------------

def test_the_buckets_are_entry_features_own_with_the_label_as_outcome():
    r = rows([(float(i), i % 2, 1.0) for i in range(80)])
    mine = F.buckets(r, "f", F.QUANTILES, outcome=S.LABEL)
    # the same split entry_features would make, with rates inside it
    edges = [(b["lo"], b["hi"], b["n"]) for b in F.buckets(r, "f")]
    assert [(b["lo"], b["hi"], b["n"]) for b in mine] == edges
    assert all(0.0 <= b["mean"] <= 1.0 for b in mine)


def test_a_constant_feature_is_refused_rather_than_bucketed():
    """`entry_features.why_not_bucketable` exists because a constant column was
    bucketed anyway once, and printed four identical ranges with a real-looking
    number beside them."""
    r = rows([(5.0, i % 2, 1.0) for i in range(80)])
    assert F.why_not_bucketable(r, "f", F.QUANTILES)
    assert F.buckets(r, "f", F.QUANTILES, outcome=S.LABEL) == []


# --- 3. the tiers -------------------------------------------------------------

def bs(means):
    return [{"mean": m, "n": 10, "lo": i, "hi": i} for i, m in enumerate(means)]


def test_reaching_break_even_in_both_halves_clears():
    t, why = S.tier(bs([.2, .3, .45, .60]), bs([.25, .35, .5, .58]), 0.29, 0.543)
    assert t == "CLEARS"
    assert "54.3%" in why


def test_monotone_and_lifted_but_short_of_break_even_only_separates():
    t, why = S.tier(bs([.20, .25, .30, .40]), bs([.22, .27, .32, .42]),
                    0.29, 0.543)
    assert t == "SEPARATES"
    assert "short of the" in why


def test_a_small_lift_is_nothing_even_when_monotone():
    t, why = S.tier(bs([.28, .29, .30, .31]), bs([.28, .29, .30, .31]),
                    0.29, 0.543)
    assert t == "NOTHING"
    assert "ends differ by only" in why


def test_halves_that_run_opposite_ways_are_nothing():
    t, why = S.tier(bs([.2, .3, .4, .6]), bs([.6, .4, .3, .2]), 0.29, 0.543)
    assert t == "NOTHING"
    assert "no single direction" in why


def test_a_falling_feature_is_read_at_the_end_it_points_at():
    """A feature that predicts the label by being LOW must be judged on its
    bottom bucket. Reading the top would call a real separator nothing."""
    t, _ = S.tier(bs([.60, .45, .30, .20]), bs([.58, .5, .35, .25]), 0.29, 0.543)
    assert t == "CLEARS"


def test_non_monotone_middles_are_not_rescued_by_the_ends():
    """Top-minus-bottom is the weak test that let `macd_level` through once:
    two ends that happen to differ is what noise looks like."""
    t, _ = S.tier(bs([.20, .55, .18, .60]), bs([.22, .50, .20, .58]),
                  0.29, 0.543)
    assert t == "NOTHING"


def test_every_tier_branch_is_reachable():
    got = {S.tier(a, b, 0.29, 0.543)[0] for a, b in (
        (bs([.2, .3, .45, .60]), bs([.25, .35, .5, .58])),
        (bs([.20, .25, .30, .40]), bs([.22, .27, .32, .42])),
        (bs([.28, .29, .30, .31]), bs([.28, .29, .30, .31])),
        ([], []))}
    assert got == {"CLEARS", "SEPARATES", "NOTHING"}


# --- 4. the report ------------------------------------------------------------

def mixed(n=800):
    """A feature that genuinely separates, in both halves."""
    out = []
    for i in range(n):
        v = float(i % 100)
        lab = 1 if (v > 70 and i % 3) else 0
        out.append({"f": v, S.LABEL: float(lab),
                    "net": (19.13 + 4.26) if lab else (-22.73 + 4.26),
                    "date": f"2026-0{1 + (i // (n // 2))}-01",
                    "adverse_first": bool(lab)})
    return out


def test_every_feature_is_printed_and_nothing_is_ranked():
    o = "\n".join(S.render(mixed(), "mcl", 10, 1.0, 1))
    for fam in F.FAMILIES:
        assert fam.upper() in o
    assert "Nothing is ranked and nothing is omitted" in o


def test_tiers_are_counted_by_family_not_by_column():
    o = "\n".join(S.render(mixed(), "mcl", 10, 1.0, 1))
    assert "22 columns is 22 chances; 11 families is 11" in o
    assert f"of {len(F.FAMILIES)} families" in o


def test_a_thin_book_refuses_to_bucket_at_all():
    o = "\n".join(S.render(mixed(50), "mcl", 10, 1.0, 1))
    assert "TOO FEW TRADES" in o
    assert "EVERY FEATURE" not in o


def test_a_null_result_says_what_it_closes_and_what_it_does_not():
    """The value of this run is that a negative is as informative as a
    positive, so the null has to say so rather than trailing off."""
    r = rows([(float(i), i % 2, (19.13 + 4.26) if i % 2 else (-22.73 + 4.26))
              for i in range(800)],
             dates=["2026-01-01"] * 400 + ["2026-02-01"] * 400)
    o = "\n".join(S.render(r, "mcl", 10, 1.0, 1))
    assert "NOTHING AT THE ENTRY BAR SEES IT" in o
    assert "closes the entry question for minute OHLCV" in o
    assert "float, short interest" in o


def test_the_base_rate_is_recomputed_not_quoted():
    """29.3% belongs to the population entry_excursion measured. Quoting it
    while bucketing a different one is the defect, one level out."""
    r = rows([(float(i), 1 if i < 100 else 0,
               (19.13 + 4.26) if i < 100 else (-22.73 + 4.26))
              for i in range(400)])
    o = "\n".join(S.render(r, "mcl", 10, 1.0, 1))
    assert "base rate" in o and "25.0%" in o
    assert "29.3" not in o


def test_the_label_is_one_for_a_drawdown_that_came_first():
    got = S.label_rows([{"adverse_first": True}, {"adverse_first": False},
                        {}])
    assert [r[S.LABEL] for r in got] == [1.0, 0.0, 0.0]
