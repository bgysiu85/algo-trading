#!/usr/bin/env python3
"""The case-control weight is the whole thing that can go silently wrong here.

Take every run start and a sample of the rest, and the run rate in the sample
is inflated by exactly the sampling factor. A report that forgot to undo it
would print 40% for a 2% phenomenon -- a twentyfold error in the one number
that decides whether any of this is tradeable, and it would look entirely
plausible on the page.

So most of these tests are arithmetic on that weight, plus the usual refusals:
both halves, nothing ranked, nothing omitted, and no claim of P&L from a
measurement that has no exit in it.
"""
from __future__ import annotations

from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from common import run_signal as S
from common.entry_features import FEATURES

ET = ZoneInfo("America/New_York")


def rows_for(vals, cases, weights=None, dates=None):
    n = len(vals)
    weights = weights if weights is not None else [1.0] * n
    dates = dates or ["2026-09-11"] * n
    out = []
    for v, c, w, d in zip(vals, cases, weights, dates):
        r = {f: 0.0 for f in FEATURES}
        r.update({"vol_over_trail": v, "case": c, "weight": w,
                  "date": d, "symbol": "A"})
        out.append(r)
    return out


# --- the cell is named, never guessed -----------------------------------------

def test_the_cell_parses():
    assert S.parse_cell("8x15") == (8.0, 15)
    assert S.parse_cell("12X30") == (12.0, 30)


def test_a_malformed_cell_exits_rather_than_defaulting():
    """Silently falling back to a default cell would put one run definition in
    the header and a different one in the numbers."""
    with pytest.raises(SystemExit):
        S.parse_cell("8-15")


# --- the weight ---------------------------------------------------------------

def test_the_sample_rate_and_the_restored_rate_differ_as_the_weight_says():
    """10 cases at weight 1, 10 controls at weight 9: the sample looks 50% but
    the truth is 10/(10+90) = 10%."""
    rows = rows_for(list(range(20)), [1] * 10 + [0] * 10,
                    [1.0] * 10 + [9.0] * 10)
    bs = S.wbuckets(rows, "vol_over_trail", q=1, min_per_bucket=5)
    assert bs[0]["rate"] == pytest.approx(10.0)


def test_an_unweighted_population_is_unchanged_by_the_weighting():
    rows = rows_for(list(range(200)), [1] * 50 + [0] * 150)
    bs = S.wbuckets(rows, "vol_over_trail", q=1)
    assert bs[0]["rate"] == pytest.approx(25.0)


def test_the_rate_is_weighted_INSIDE_each_bucket_not_just_overall():
    """A bucket whose controls carry a heavier weight must show a lower rate,
    even when the raw counts match another bucket's."""
    vals = list(range(1, 25))
    cases = [1, 0] * 12
    # Identical case COUNTS in both halves; only the control weight differs.
    weights = [1.0] * 12 + [1.0 if c else 99.0 for c in cases[12:]]
    rows = rows_for(vals, cases, weights)
    bs = S.wbuckets(rows, "vol_over_trail", q=2, min_per_bucket=4)
    assert [b["cases"] for b in bs] == [6, 6], "the raw counts must match"
    assert bs[0]["rate"] == pytest.approx(50.0)
    assert bs[1]["rate"] == pytest.approx(1.0)


def test_bucket_edges_are_unweighted_but_rates_are_weighted():
    """Weighting the EDGES too would put the right number in the wrong bucket:
    the quartiles are of bars, the rate is of the population they represent."""
    rows = rows_for(list(range(200)), [1] * 100 + [0] * 100,
                    [1.0] * 100 + [50.0] * 100)
    bs = S.wbuckets(rows, "vol_over_trail")
    assert all(b["n"] == 50 for b in bs), [b["n"] for b in bs]


def test_a_constant_feature_is_refused_here_too():
    rows = rows_for([7.0] * 200, [1] * 40 + [0] * 160)
    assert S.wbuckets(rows, "vol_over_trail") == []


def test_too_few_bars_yields_no_buckets():
    assert S.wbuckets(rows_for([1, 2, 3], [1, 0, 0]), "vol_over_trail") == []


# --- the tier -----------------------------------------------------------------

def bs_rates(*rates):
    return [{"rate": r, "wcase": r, "wall": 100.0, "n": 50,
             "lo": i, "hi": i + 1, "cases": 1} for i, r in enumerate(rates)]


def test_monotone_lift_in_both_halves_is_a_CANDIDATE():
    tl, _ = S.tier(bs_rates(1.0, 2.0, 3.0, 4.0),
                   bs_rates(1.0, 1.5, 2.5, 3.5), 2.0, 2.0)
    assert tl == "CANDIDATE"


def test_ragged_middles_are_WEAK_not_CANDIDATE():
    ragged = bs_rates(1.0, 4.0, 0.5, 4.0)
    tl, _ = S.tier(ragged, ragged, 2.0, 2.0)
    assert tl == "WEAK"


def test_halves_disagreeing_is_NOTHING():
    tl, why = S.tier(bs_rates(1.0, 2.0, 3.0, 4.0),
                     bs_rates(4.0, 3.0, 2.0, 1.0), 2.0, 2.0)
    assert tl == "NOTHING"
    assert "DISAGREE" in why


def test_a_lift_under_the_floor_is_NOTHING_however_tidy():
    """A perfectly monotone 1.1x is still a condition that cannot pay for its
    own false positives."""
    tidy = bs_rates(2.00, 2.03, 2.06, 2.10)
    tl, why = S.tier(tidy, tidy, 2.0, 2.0)
    assert tl == "NOTHING"
    assert f"{S.MIN_LIFT:.2f}x" in why


def test_a_half_that_could_not_be_bucketed_is_NOTHING():
    assert S.tier([], bs_rates(1.0, 2.0, 3.0, 4.0), 2.0, 2.0)[0] == "NOTHING"


# --- labelling and sampling ---------------------------------------------------

def sig_frame(closes, start="04:00"):
    from strategy.mcl import mcl as MCL
    h, m = int(start[:2]), int(start[3:])
    t0 = pd.Timestamp(datetime.combine(pd.Timestamp("2026-09-11").date(),
                                       dtime(h, m), tzinfo=ET))
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=i)
                            for i in range(len(closes))])
    c = np.array(closes, dtype=float)
    df = pd.DataFrame({"open": c, "high": c * 1.002, "low": c * 0.998,
                       "close": c, "volume": np.full(len(c), 50_000.0)},
                      index=idx.tz_convert("UTC"))
    return MCL.signals(df)


def test_controls_never_include_a_run_start():
    """A case in the control group is a bar counted as both, which pushes the
    measured separation toward zero and looks like an honest null."""
    rng = np.random.default_rng(0)
    c = list(10.0 + np.cumsum(rng.normal(0.002, 0.05, 400)))
    sig = sig_frame(c)
    starts, controls, _ = S.label_and_sample(sig, (5.0, 15), 5.0, rng, 40, 1.0)
    assert not (set(starts) & set(controls))


def test_no_case_or_control_comes_from_the_warm_up_region():
    """Indicators are undefined there; a control drawn from it would differ
    from every case by the warm-up rather than by anything real."""
    rng = np.random.default_rng(1)
    c = list(10.0 + np.cumsum(rng.normal(0.002, 0.05, 400)))
    sig = sig_frame(c)
    warm = 60
    starts, controls, _ = S.label_and_sample(sig, (5.0, 15), 5.0, rng, warm, 1.0)
    assert all(i >= warm for i in starts + controls)


def test_no_bar_without_a_full_forward_window_is_eligible():
    """A bar near the end cannot be shown NOT to run -- its window is cut off,
    so calling it a control is an assertion the data does not support."""
    rng = np.random.default_rng(2)
    c = list(10.0 + np.cumsum(rng.normal(0.002, 0.05, 300)))
    sig = sig_frame(c)
    n = 15
    starts, controls, _ = S.label_and_sample(sig, (5.0, n), 5.0, rng, 40, 1.0)
    assert all(i < len(sig) - n for i in starts + controls)


def test_controls_are_sampled_at_a_FLAT_RATE_not_per_case():
    """The rate must not depend on how many runs this symbol-day happened to
    have. Tying it to the case count is what dropped every quiet day from the
    archive population and made the base rate 15.6x too high."""
    rng = np.random.default_rng(3)
    c = list(10.0 + np.cumsum(rng.normal(0.002, 0.05, 400)))
    sig = sig_frame(c)
    _, controls, elig = S.label_and_sample(sig, (5.0, 15), 5.0, rng, 40, 0.25)
    assert 0.15 * elig < len(controls) < 0.35 * elig, len(controls)


def test_a_symbol_day_with_NO_run_still_contributes_controls():
    """A flat tape is a real observation: it is a day on which no bar ran, and
    excluding it makes the denominator the wrong population."""
    rng = np.random.default_rng(4)
    sig = sig_frame([10.0] * 300)
    starts, controls, elig = S.label_and_sample(sig, (8.0, 15), 5.0, rng,
                                                40, 0.5)
    assert starts == []
    assert controls and elig > 0


# --- what the report must and must not say ------------------------------------

def report_rows(n=600):
    rng = np.random.default_rng(7)
    out = []
    for k in range(n):
        d = "2026-09-01" if k < n // 2 else "2026-09-11"
        r = {f: float(rng.normal(0, 1)) for f in FEATURES}
        case = 1 if k % 7 == 0 else 0
        r.update(case=case, weight=1.0 if case else 6.0, date=d, symbol="A")
        out.append(r)
    return out


def text_of(rows=None):
    return "\n".join(S.render(rows or report_rows(), (8.0, 15), 5.0,
                              10_000, 2, 50, {}, "cache", 0.1))


def test_the_report_prints_BOTH_the_sample_rate_and_the_restored_rate():
    """Printing only the sample rate is the twentyfold error; printing only the
    restored one hides that a correction was applied at all."""
    t = text_of()
    assert "run rate IN THE SAMPLE" in t
    assert "run rate RESTORED" in t


def test_the_report_states_precision_and_recall_not_just_lift():
    t = text_of()
    assert "precision" in t and "recall" in t
    assert "lift" in t.lower()


def test_the_report_refuses_to_claim_a_PnL():
    """There is no exit in this measurement, so there is no P&L in it."""
    t = text_of()
    assert "Not a P&L" in t
    assert "needs an" in t and "exit" in t


def test_EVERY_feature_appears():
    t = text_of()
    for f in FEATURES:
        assert f in t, f"{f} omitted"


def test_nothing_is_ranked():
    low = text_of().lower()
    for banned in ("best feature", "strongest", "most predictive",
                   "top feature", "in order of"):
        assert banned not in low, f"the report ranks: {banned!r}"
    order = [low.index(f) for f in FEATURES]
    assert order == sorted(order), "features were re-ordered by result"


def test_both_halves_are_shown():
    t = text_of()
    assert t.count("early") >= len(FEATURES)
    assert t.count("late") >= len(FEATURES)


def test_the_cell_is_named_in_the_report():
    t = text_of()
    assert "8% within 15 bars" in t
    assert "named on the" in t


def test_the_holdout_is_named_as_untouched():
    assert "holdout.json" in text_of()


def test_a_population_with_no_runs_is_named_not_scored():
    rows = report_rows()
    for r in rows:
        r["case"] = 0
    t = "\n".join(S.render(rows, (8.0, 15), 5.0, 10, 1, 1, {}, "cache", 0.1))
    assert "NOTHING TO SEPARATE" in t


def test_the_lift_floor_is_declared_as_a_judgement():
    t = text_of()
    assert "judgement, stated so it can be argued with" in t


# --- is the finding just volatility wearing a hat? ----------------------------

def test_spearman_is_1_for_a_feature_against_itself():
    rows = report_rows()
    assert S.spearman(rows, S.VOL_PROXY, S.VOL_PROXY) == pytest.approx(1.0)


def test_spearman_is_rank_based_not_outlier_driven():
    """These features span orders of magnitude; one huge row must not set the
    correlation on its own."""
    n = 300
    rows = []
    for k in range(n):
        r = {f: 0.0 for f in FEATURES}
        r.update({S.VOL_PROXY: float(k), "vol_over_trail": float(k),
                  "case": 0, "weight": 1.0, "date": "2026-09-11", "symbol": "A"})
        rows.append(r)
    rows[-1]["vol_over_trail"] = 1e12          # one absurd value
    assert S.spearman(rows, "vol_over_trail", S.VOL_PROXY) == pytest.approx(1.0)


def test_spearman_is_zero_without_spread():
    rows = report_rows()
    for r in rows:
        r["vol_over_trail"] = 3.0
    assert S.spearman(rows, "vol_over_trail", S.VOL_PROXY) == 0.0


def test_the_report_warns_that_a_volatility_proxy_predicts_by_construction():
    """The likeliest wrong conclusion from this page is that a 4x lift on a
    volatility measure is a discovery. It is the run definition looking at
    itself, and the page has to say so next to the number."""
    t = text_of()
    assert "|r| vol" in t
    assert "definition looking at itself" in t


def test_the_report_disowns_its_own_family_count():
    """FAMILIES came from entry_features, where the question was different. It
    does not collapse volatility proxies, so the count overstates."""
    t = text_of()
    assert "OVERSTATES the number of" in t


def test_no_case_or_control_starts_after_the_premarket_window():
    """The cache frames run to 20:00. Without an explicit upper bound this
    drew cases and controls from the regular session and after hours while
    the report's header said 04:00-09:30 -- a window claim the numbers did
    not honour."""
    rng = np.random.default_rng(8)
    c = list(10.0 + np.cumsum(rng.normal(0.002, 0.05, 500)))
    sig = sig_frame(c)
    hi = 200
    starts, controls, elig = S.label_and_sample(sig, (5.0, 15), 5.0, rng,
                                                40, 1.0, hi)
    assert all(i < hi for i in starts + controls)
    assert elig == hi - 40


def test_the_forward_window_may_still_read_past_that_bound():
    """A run beginning at 09:28 finishes when it finishes; bounding the START
    is not the same as truncating the move."""
    c = [10.0] * 60 + [10.0] * 5 + [11.0] * 40
    sig = sig_frame(c)
    rng = np.random.default_rng(9)
    starts, _, _ = S.label_and_sample(sig, (5.0, 15), 5.0, rng, 40, 1.0, 66)
    assert starts, "a run starting inside the bound was dropped"


# --- parallelism must not change the answer -----------------------------------

def test_rng_for_depends_only_on_its_key_not_on_call_order():
    """The first version threaded ONE generator through every symbol-day, so
    which bars became controls depended on the order they were reached -- and
    therefore on the worker count."""
    a1 = S.rng_for(0, "2026-09-11", "TNON").integers(0, 10_000, 5).tolist()
    _ = S.rng_for(0, "2026-01-02", "AAAA").integers(0, 10_000, 99)
    a2 = S.rng_for(0, "2026-09-11", "TNON").integers(0, 10_000, 5).tolist()
    assert a1 == a2


def test_rng_for_separates_symbols_and_days_and_seeds():
    draw = lambda *k: S.rng_for(*k).integers(0, 10_000, 5).tolist()
    base = draw(0, "2026-09-11", "TNON")
    assert draw(0, "2026-09-11", "ACVA") != base
    assert draw(0, "2026-09-10", "TNON") != base
    assert draw(1, "2026-09-11", "TNON") != base


def test_rng_for_is_stable_ACROSS_PROCESSES():
    """Python salts hash() per process, so a hash-keyed seed would give a pool
    worker a different sample from the parent -- silently, and only when
    --jobs > 1."""
    import subprocess
    import sys as _sys
    code = ("from common.run_signal import rng_for;"
            "print(rng_for(0,'2026-09-11','TNON').integers(0,10_000,5).tolist())")
    out = subprocess.run([_sys.executable, "-c", code], capture_output=True,
                         text=True, cwd=".")
    assert out.returncode == 0, out.stderr
    here = S.rng_for(0, "2026-09-11", "TNON").integers(0, 10_000, 5).tolist()
    assert out.stdout.strip() == str(here)


def test_the_report_is_invariant_to_ROW_ORDER():
    """Workers finish in whatever order they finish. If bucket membership
    could turn on list order, --jobs would quietly change the findings."""
    import random
    rows = report_rows(800)
    a = "\n".join(S.render(rows, (8.0, 15), 5.0, 10_000, 2, 50, {}, "cache", 0.1))
    shuffled = rows[:]
    random.Random(3).shuffle(shuffled)
    b = "\n".join(S.render(shuffled, (8.0, 15), 5.0, 10_000, 2, 50, {},
                           "cache", 0.1))
    assert a == b


def test_jobs_zero_means_one_per_core():
    assert S.build_parser().parse_args(["--jobs", "0"]).jobs == 0
    assert S.build_parser().parse_args([]).jobs == 1
