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
    assert "same direction in both halves" in text
    assert f"${F.FRICTION:.2f} in BOTH halves" in text
    assert "HYPOTHESIS, not a condition" in text


def test_a_disagreement_between_halves_is_LABELLED_as_such():
    rows = ([{**{f: 0.0 for f in F.FEATURES}, "vol_over_trail": float(i),
              "net": float(i) * 3, "date": "2026-09-01", "symbol": "A"}
             for i in range(60)]
            + [{**{f: 0.0 for f in F.FEATURES}, "vol_over_trail": float(i),
                "net": -float(i) * 3, "date": "2026-09-11", "symbol": "A"}
               for i in range(60)])
    text = "\n".join(F.render(rows, "entries", "p.json", 0, 0.1))
    assert "DISAGREES between halves" in text


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
