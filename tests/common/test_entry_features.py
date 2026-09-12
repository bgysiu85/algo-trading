#!/usr/bin/env python3
"""Does the feature study resist the thing it is most likely to do?

This module searches for something that separates outcomes already known. That
is overfitting by construction, and the failure is not a crash -- it is a
plausible report that makes a strategy worse. So most of these tests are about
what it must REFUSE to do:

  * no look-ahead: a feature that peeks at bars after the entry would separate
    winners from losers perfectly and mean nothing
  * no ranking, and no omission: printing only the features that separated is
    the selection the module exists to resist
  * both halves always, per feature, so a split that works on one and not the
    other cannot be pooled into a single flattering number
  * the holdout stays shut
"""
from __future__ import annotations

from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from common import entry_features as F
from strategy.mcl import mcl as MCL

ET = ZoneInfo("America/New_York")


def real_sig(n=200, seed=0):
    """signals() output on a real frame, so features are exercised against the
    columns the strategy actually emits."""
    t0 = pd.Timestamp(datetime.combine(pd.Timestamp("2026-09-11").date(),
                                       dtime(4, 0), tzinfo=ET))
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=i) for i in range(n)])
    rng = np.random.default_rng(seed)
    c = 7.0 + np.cumsum(rng.normal(0.004, 0.03, n))
    v = np.abs(np.full(n, 50_000.0) + rng.normal(0, 2000, n))
    v[117], v[118] = 7_000.0, 40_000.0
    df = pd.DataFrame({"open": c, "high": c * 1.004, "low": c * 0.996,
                       "close": c, "volume": v}, index=idx)
    return MCL.signals(df)


# --- no look-ahead ------------------------------------------------------------

def test_features_do_not_read_a_single_bar_after_the_entry():
    """The decisive test. Replace everything after the entry bar with noise;
    every feature must be bit-identical. A feature that peeked would separate
    winners from losers perfectly and mean nothing at all."""
    sig = real_sig()
    i = 150
    before = F.features_at(sig, i)

    tampered = sig.copy()
    rng = np.random.default_rng(99)
    for col in ("close", "high", "low", "volume", "macd", "macd_sig",
                "rsi", "mfi", "prev_vol", "trail_avg"):
        if col in tampered.columns:
            vals = tampered[col].to_numpy(dtype=float, copy=True)
            vals[i + 1:] = rng.normal(1000, 500, len(vals) - i - 1)
            tampered[col] = vals
    after = F.features_at(tampered, i)

    for k in before:
        assert before[k] == after[k] or (before[k] != before[k]
                                         and after[k] != after[k]), \
            f"feature {k} changed when the FUTURE changed -- it looks ahead"


def test_every_declared_feature_is_actually_produced():
    """A feature in the list but missing from the output would be silently
    dropped from the report."""
    got = F.features_at(real_sig(), 150)
    assert set(F.FEATURES) <= set(got)


def test_an_early_bar_yields_nan_slopes_rather_than_a_wrong_number():
    """Three bars are needed for a 3-bar slope. Inventing 0 would put a
    neutral-looking value in a bucket that has no measurement behind it."""
    got = F.features_at(real_sig(), 1)
    assert got["rsi_slope"] != got["rsi_slope"]
    assert got["mfi_slope"] != got["mfi_slope"]


def test_tape_density_measures_HOLES_not_rows():
    """The cache holds only the minutes that PRINTED -- a minute with no trade
    is an absent row, not a zero-volume one. An earlier version measured
    (volume > 0).mean(), which is 100% on a frame full of holes and 100% on a
    frame with none: a detector whose output is identical to the thing it is
    meant to detect."""
    full = real_sig()
    dense = F.features_at(full, 150)["tape_density"]
    assert dense == pytest.approx(100.0)

    holed = full.iloc[[k for k in range(len(full)) if k % 2 == 0 or k > 150]]
    i = list(holed.index).index(full.index[150])
    assert F.features_at(holed, i)["tape_density"] < 60.0


def test_tape_density_is_not_confused_by_the_PREVIOUS_session():
    """The frame is a 3-day superset. Elapsed minutes must be measured from
    this session's first bar, not the superset's."""
    one = real_sig(n=120)
    prior = one.copy()
    prior.index = prior.index - timedelta(days=1)
    both = pd.concat([prior, one])
    i = len(both) - 1
    assert F.features_at(both, i)["tape_density"] == pytest.approx(100.0)


# --- the buckets --------------------------------------------------------------

def rows_for(vals, nets, dates=None):
    dates = dates or ["2026-09-11"] * len(vals)
    return [{"vol_over_trail": v, "net": n, "date": d, "symbol": "A"}
            for v, n, d in zip(vals, nets, dates)]


def test_bucket_edges_come_from_the_data_not_round_numbers():
    """A hand-chosen threshold is already a fitted parameter."""
    bs = F.buckets(rows_for(list(range(40)), [1.0] * 40), "vol_over_trail")
    assert len(bs) == F.QUANTILES
    assert bs[0]["lo"] == 0 and bs[-1]["hi"] == 39


def test_too_few_trades_yields_no_buckets_rather_than_thin_ones():
    assert F.buckets(rows_for([1, 2, 3], [1.0, 2.0, 3.0]), "vol_over_trail") == []


def test_nan_values_are_excluded_not_bucketed_as_zero():
    vals = [float("nan")] * 10 + list(range(30))
    bs = F.buckets(rows_for(vals, [1.0] * 40), "vol_over_trail")
    assert sum(b["n"] for b in bs) == 30


def test_each_bucket_reports_its_own_n():
    bs = F.buckets(rows_for(list(range(40)), [1.0] * 40), "vol_over_trail")
    assert all(b["n"] > 0 for b in bs)
    assert sum(b["n"] for b in bs) == 40


# --- what the report must and must not do -------------------------------------

def full_rows(n=200):
    rng = np.random.default_rng(1)
    out = []
    for k in range(n):
        d = "2026-09-01" if k < n // 2 else "2026-09-11"
        r = {f: float(rng.normal(0, 1)) for f in F.FEATURES}
        r.update(net=float(rng.normal(-1, 20)), date=d, symbol="A")
        out.append(r)
    return out


def test_EVERY_feature_appears_in_the_report():
    """Printing only what separated is the selection this module exists to
    resist."""
    text = "\n".join(F.render(full_rows(), "entries", "p.json", 0, 0.1))
    for f in F.FEATURES:
        assert f in text, f"{f} was omitted from the report"


def test_nothing_is_ranked():
    """A 'best feature' line hands the reader the overfit answer in the one
    place they will look.

    Checked as BEHAVIOUR, not as vocabulary: an earlier version banned the
    word "ranked" and tripped on the report's own "nothing is ranked"
    disclaimer -- a test that fails on the promise rather than the breach.
    """
    text = "\n".join(F.render(full_rows(), "entries", "p.json", 0, 0.1))
    low = text.lower()
    for banned in ("best feature", "strongest", "most predictive",
                   "top feature", "best separator", "in order of"):
        assert banned not in low, f"the report ranks: {banned!r}"
    # and the denial is actually made
    assert "nothing is ranked" in low

    # Features appear in their DECLARED order, not sorted by effect.
    order = [low.index(f) for f in F.FEATURES]
    assert order == sorted(order), "features were re-ordered by result"


def test_both_halves_are_shown_for_every_feature():
    text = "\n".join(F.render(full_rows(), "entries", "p.json", 0, 0.1))
    assert text.count("early") >= len(F.FEATURES)
    assert text.count("late") >= len(F.FEATURES)


def test_the_comparison_count_is_stated():
    """Multiplicity is the whole hazard; it must be on the page, not implied."""
    text = "\n".join(F.render(full_rows(), "entries", "p.json", 0, 0.1))
    assert f"{len(F.FEATURES) * F.QUANTILES * 2} comparisons" in text
    assert "by chance" in text


def test_the_base_rate_is_stated_before_any_feature():
    """A bucket at 40% means nothing until the reader knows the base is 34%."""
    text = "\n".join(F.render(full_rows(), "entries", "p.json", 0, 0.1))
    i_base = text.index("THE BASE RATE")
    i_feat = text.index("EVERY FEATURE")
    assert i_base < i_feat


def test_the_three_conditions_for_a_second_look_are_stated():
    text = "\n".join(F.render(full_rows(), "entries", "p.json", 0, 0.1))
    assert "MONOTONE across the buckets, the same way in both halves" in text
    assert f"${F.FRICTION:.2f} in BOTH halves" in text
    assert "HYPOTHESIS, not a condition" in text


def halves_disagreeing_rows():
    """Rising feature, rising net in the early half and falling in the late
    one. The two halves cannot both be right about it."""
    return ([{**{f: 0.0 for f in F.FEATURES}, "vol_over_trail": float(i),
              "net": float(i) * 3, "date": "2026-09-01", "symbol": "A"}
             for i in range(60)]
            + [{**{f: 0.0 for f in F.FEATURES}, "vol_over_trail": float(i),
                "net": -float(i) * 3, "date": "2026-09-11", "symbol": "A"}
               for i in range(60)])


def test_a_disagreement_between_halves_is_LABELLED_as_such():
    text = "\n".join(F.render(halves_disagreeing_rows(),
                              "entries", "p.json", 0, 0.1))
    assert "the halves DISAGREE in direction" in text


def test_a_disagreement_between_halves_can_never_be_a_candidate():
    """The label is cosmetic; the tier is what a reader acts on."""
    rows = halves_disagreeing_rows()
    a, b = F.split(rows)
    tl, _ = F.tier(F.buckets(a, "vol_over_trail"),
                   F.buckets(b, "vol_over_trail"))
    assert tl == "NOTHING"


# --- monotonicity, added after the first run ----------------------------------

def bs(*means):
    return [{"mean": m, "n": 10, "lo": i, "hi": i + 1, "win": 30.0}
            for i, m in enumerate(means)]


def test_monotone_reports_rising_falling_and_neither():
    assert F.monotone(bs(1.0, 2.0, 3.0, 4.0)) == 1
    assert F.monotone(bs(4.0, 3.0, 2.0, 1.0)) == -1
    assert F.monotone(bs(1.0, 5.0, 2.0, 9.0)) == 0


def test_the_macd_level_shape_that_prompted_monotonicity_is_not_monotone():
    """The first run passed `macd_level` on ends alone while its middles ran
    (6.58) / 7.40 / (10.11) / 3.27. That shape must not clear the bar now."""
    assert F.monotone(bs(-6.58, 7.40, -10.11, 3.27)) == 0


def test_big_ends_with_ragged_middles_are_WEAK_not_CANDIDATE():
    ragged = bs(-6.58, 7.40, -10.11, 3.27)     # ends +9.85, middles disordered
    tl, why = F.tier(ragged, ragged)
    assert tl == "WEAK"
    assert "do not line up" in why


def test_monotone_in_both_halves_and_past_friction_is_a_CANDIDATE():
    tl, _ = F.tier(bs(0.0, 4.0, 8.0, 12.0), bs(1.0, 3.0, 6.0, 9.0))
    assert tl == "CANDIDATE"


def test_monotone_the_OTHER_way_in_the_second_half_is_not_a_candidate():
    tl, _ = F.tier(bs(0.0, 4.0, 8.0, 12.0), bs(12.0, 8.0, 4.0, 0.0))
    assert tl != "CANDIDATE"


def test_an_effect_under_friction_is_never_a_candidate():
    """A separation smaller than the cost of trading it is not a finding."""
    small = bs(0.0, 0.5, 1.0, 1.5)             # ends differ by 1.50 < 4.26
    tl, why = F.tier(small, small)
    assert tl == "NOTHING"
    assert f"${F.FRICTION:.2f}" in why


def test_too_few_trades_to_bucket_is_NOTHING_not_a_silent_pass():
    assert F.tier([], bs(1.0, 2.0, 3.0, 4.0))[0] == "NOTHING"
    assert F.tier(bs(1.0, 2.0, 3.0, 4.0), [])[0] == "NOTHING"


# --- multiplicity is counted by family, not by column -------------------------

def test_every_feature_belongs_to_exactly_one_family():
    """A column outside FAMILIES would clear the bar and be counted by
    nothing; a family naming a column that does not exist would be counted
    as evidence that cannot arrive."""
    claimed = [c for cols in F.FAMILIES.values() for c in cols]
    assert sorted(claimed) == sorted(F.FEATURES), "family map and FEATURES differ"
    assert len(claimed) == len(set(claimed)), "a column is in two families"


def test_the_family_count_is_in_the_report():
    text = "\n".join(F.render(full_rows(), "entries", "p.json", 0, 0.1))
    assert "TIERS, COUNTED BY FAMILY" in text
    assert f"{len(F.FAMILIES)} families over {len(F.FEATURES)} columns" in text


def test_no_candidate_is_reported_as_a_result_not_a_failure():
    """Noise in, nothing out -- and the report has to say so out loud, or a
    reader will go looking for the finding that is not there."""
    text = "\n".join(F.render(full_rows(), "entries", "p.json", 0, 0.1))
    assert "CANDIDATE  0" in text
    assert "NO family cleared the bar" in text


def test_the_holdout_is_named_as_untouched():
    text = "\n".join(F.render(full_rows(), "entries", "p.json", 0, 0.1))
    assert "holdout.json" in text
    assert "NOT touched" in text


def test_the_report_says_it_is_not_a_model():
    text = "\n".join(F.render(full_rows(), "entries", "p.json", 0, 0.1))
    assert "Not a model" in text
    assert "Not causal" in text


def test_an_empty_population_is_named_not_scored():
    text = "\n".join(F.render([], "entries", "p.json", 0, 0.1))
    assert "NOTHING TO DESCRIBE" in text


# --- the population default ---------------------------------------------------

def test_the_default_population_is_the_rules_OWN_entries():
    """Ben's question is about bars that passed the IDENTICAL conditions and
    then diverged. That is the rule's own entries, not the refused ones."""
    assert F.build_parser().parse_args([]).population == "entries"


def test_the_feature_list_is_a_module_constant():
    """Fixed in the file before any outcome was examined. If it were built at
    runtime from whatever separated, the pre-registration would be a fiction."""
    import inspect
    src = inspect.getsource(F)
    assert "FEATURES = {" in src
    assert src.index("FEATURES = {") < src.index("def features_at")
