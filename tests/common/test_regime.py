#!/usr/bin/env python3
"""The regime gate, and the three ways it could be fake.

`warrior_census_20260910.md` §4 puts a 16x spread on his mean day between hot
and cold. That is the largest effect measured anywhere in this project, which
is exactly why the failure modes matter more than the feature arithmetic:

  1. measuring Ben's trade count instead of the market,
  2. labelling a day with information from that same day, and
  3. reading a three-bucket ordering out of ninety sessions.

The headline tests here are `test_the_study_refuses_a_universe_that_is_not_a
_market` and `test_the_lagged_labelling_cannot_see_its_own_day`. The rest is
arithmetic.
"""
from __future__ import annotations

import pandas as pd
import pytest

from common import regime as RG
from common import regime_study as RS


def daily(rows) -> pd.DataFrame:
    """(symbol, date, close) -> a frame with high == close unless given."""
    out = []
    for r in rows:
        sym, d, close = r[0], r[1], r[2]
        high = r[3] if len(r) > 3 else close
        out.append({"symbol": sym, "date": d, "open": close, "high": high,
                    "low": min(close, high) * 0.9, "close": close,
                    "volume": 1e6})
    return pd.DataFrame(out)


# --- prior close, and the band test that must not select on the outcome -----

def test_the_first_session_of_each_symbol_is_dropped():
    """It has no prior close, so its gain is undefined. Filling it with the
    open would make every new listing look flat."""
    p = RG.prepare(daily([("A", "2026-01-02", 5.0), ("A", "2026-01-05", 6.0)]))
    assert list(p["date"]) == ["2026-01-05"]
    assert float(p["prior_close"].iloc[0]) == 5.0


def test_the_band_is_tested_on_the_prior_close_not_todays():
    """THE SELECTION TRAP. A name at $4 that runs to $40 is the hottest thing
    on the tape. Screening on today's price throws it out for being over $20 --
    which removes precisely the population the measure is about, and does it
    harder on hot days than cold ones."""
    p = RG.prepare(daily([("A", "2026-01-02", 4.0), ("A", "2026-01-05", 40.0)]))
    assert len(p) == 1, "the runner was dropped for the price it ran TO"


def test_a_name_that_starts_out_of_band_stays_out():
    p = RG.prepare(daily([("A", "2026-01-02", 50.0), ("A", "2026-01-05", 55.0)]))
    assert p.empty


# --- the day's reading ------------------------------------------------------

def rows(specs):
    """specs = [(prior_close, high, close)] for one session."""
    return pd.DataFrame([{"symbol": f"S{i}", "prior_close": pc,
                          "high": h, "close": c}
                         for i, (pc, h, c) in enumerate(specs)])


def test_movers_and_big_gainers_are_counted_separately():
    """He states a >100% count. That is 0 or 1 on most sessions even
    market-wide, so it cannot rank days by itself -- hence a lower MOVER_MIN
    for the breadth measure and his number kept as its own field."""
    f = RG.day_features(rows([(4.0, 4.4, 4.4),      # +10%, not a mover
                              (4.0, 5.4, 5.4),      # +35%, a mover
                              (4.0, 9.0, 9.0)]),    # +125%, mover AND big
                        "2026-01-05")
    assert f.n_movers == 2
    assert f.n_big == 1
    assert f.lead == pytest.approx(1.25)


def test_the_round_trip_rate_is_over_movers_only():
    """A name that never moved cannot give a move back. Including the flat
    names would dilute the rate toward zero on exactly the cold days where
    there are most of them."""
    f = RG.day_features(rows([(4.0, 4.0, 4.0),      # flat, not a mover
                              (4.0, 6.0, 4.1),      # ran +50%, gave it all back
                              (4.0, 6.0, 6.0)]),    # ran +50%, held
                        "2026-01-05")
    assert f.n_movers == 2
    assert f.round_trip == pytest.approx(0.5)


def test_retention_is_clipped_at_both_ends():
    """A close below the prior close is a NEGATIVE retention and a close above
    the high is impossible but has appeared in adjusted data. Neither should
    make the rate leave [0, 1]."""
    f = RG.day_features(rows([(4.0, 6.0, 2.0), (4.0, 6.0, 7.0),
                              (4.0, 6.0, 5.0), (4.0, 6.0, 5.5),
                              (4.0, 6.0, 5.9)]), "2026-01-05")
    assert 0.0 <= f.round_trip <= 1.0


def test_a_thin_session_is_marked_unusable_not_dropped():
    """A market with under five names moving 30% is the COLDEST reading
    available. Dropping those days would remove the coldest part of a cold
    sample and then report that cold days are rare."""
    f = RG.day_features(rows([(4.0, 6.0, 6.0)]), "2026-01-05")
    assert not f.usable
    assert f.n_movers == 1


def test_an_empty_session_does_not_raise():
    f = RG.day_features(rows([]), "2026-01-05")
    assert f.n_names == 0 and not f.usable


# --- the buckets ------------------------------------------------------------

def feats(spec):
    """spec = {date: (n_movers, lead, round_trip)}"""
    return {d: RG.DayFeatures(d, n, n, 0, lead, rt, 5.0)
            for d, (n, lead, rt) in spec.items()}


def test_the_round_trip_rate_alone_can_decide_the_bucket():
    """THE DISCRIMINATING VERSION. An earlier form of this test varied all
    three features together and would have passed with the round-trip rate
    ignored entirely -- the movers count alone reproduced the expected answer.

    So: movers and lead held CONSTANT, only the round-trip rate varies. A
    composite that ignored it would tie every day, every tercile boundary
    would land on the same value, and nothing could come out hot.
    """
    f = feats({f"2026-01-{i:02d}": (10, 0.5, i / 20.0) for i in range(2, 14)})
    lab = RG.classify(f)
    assert lab["2026-01-02"] == "hot", "least given back should be the hottest"
    assert lab["2026-01-13"] == "cold", "most given back should be the coldest"


def test_more_movers_is_hotter_with_the_other_two_held_constant():
    f = feats({f"2026-01-{i:02d}": (i, 0.5, 0.5) for i in range(2, 14)})
    lab = RG.classify(f)
    assert lab["2026-01-13"] == "hot" and lab["2026-01-02"] == "cold"


def test_a_bigger_leading_gainer_is_hotter_with_the_other_two_held_constant():
    f = feats({f"2026-01-{i:02d}": (10, i / 10.0, 0.5) for i in range(2, 14)})
    lab = RG.classify(f)
    assert lab["2026-01-13"] == "hot" and lab["2026-01-02"] == "cold"


def test_unusable_days_are_labelled_cold_and_not_dropped():
    f = feats({f"2026-01-{i:02d}": (10, 1.0, 0.1) for i in range(2, 12)})
    f["2026-02-02"] = RG.DayFeatures("2026-02-02", 3, 1, 0, 0.4, 0.0, 5.0)
    lab = RG.classify(f)
    assert lab["2026-02-02"] == "cold"
    assert len(lab) == len(f), "a session vanished"


def test_too_few_rated_days_gives_unrated_not_a_two_bucket_split():
    """Two buckets printed under three headings reads as a three-bucket
    result. It is not one."""
    f = feats({"2026-01-02": (10, 1.0, 0.1), "2026-01-05": (9, 0.9, 0.2)})
    assert set(RG.classify(f).values()) == {"unrated"}


def test_every_bucket_is_populated_on_a_spread_sample():
    f = feats({f"2026-01-{i:02d}": (i, i / 30.0, 0.5) for i in range(2, 32)})
    lab = RG.classify(f)
    assert {lab[d] for d in f} == {"cold", "mixed", "hot"}


# --- THE HEADLINE: the lag, and the universe refusal ------------------------

def test_the_lagged_labelling_cannot_see_its_own_day():
    """You decide at 04:00. You cannot know at 04:00 how many stocks will
    close up 100% today. Every entry in the lagged map must come from a
    STRICTLY EARLIER date, or the gate is a description of days that were
    already good and will look spectacular for that reason alone."""
    lab = {"2026-01-02": "hot", "2026-01-05": "cold", "2026-01-06": "mixed"}
    lag = RG.lagged(lab)
    assert lag == {"2026-01-05": "hot", "2026-01-06": "cold"}
    assert "2026-01-02" not in lag, "the first session has no predecessor"
    # And the property that matters, stated as a property rather than as one
    # hand-checked example: every lagged label equals SOME strictly earlier
    # session's label, and never its own day's.
    dates = sorted(lab)
    for i, d in enumerate(dates):
        if d in lag:
            assert lag[d] == lab[dates[i - 1]] and i >= 1


def test_the_first_session_is_dropped_rather_than_carried_from_itself():
    lab = {"2026-01-02": "hot"}
    assert RG.lagged(lab) == {}


def test_autocorr_is_a_third_on_an_uninformative_label():
    """The gate's ceiling. At chance, no lagged split can work whatever the
    same-day table shows -- which is why it prints before either verdict."""
    lab = {f"2026-01-{i:02d}": ["cold", "mixed", "hot"][i % 3]
           for i in range(2, 32)}
    assert RG.autocorr(lab) == 0.0          # a strict 3-cycle never repeats
    assert RG.autocorr({f"2026-01-{i:02d}": "hot" for i in range(2, 32)}) == 1.0


def test_the_study_refuses_a_universe_that_is_not_a_market():
    """THE ONE THAT MATTERS. bar_cache's universe is traded_pairs.json -- the
    symbol-days Ben traded, a median of THREE a day. Breadth over that measures
    his trade count, which the census showed tracks his outcome, and the table
    would look identical to a real one. So the study has to refuse, and the
    refusal has to name a number."""
    thin = daily([(f"S{i}", "2026-01-05", 5.0) for i in range(3)]
                 + [(f"S{i}", "2026-01-06", 5.0) for i in range(3)])
    med, refusal = RS.check_universe(thin)
    assert med == 3
    assert refusal and "market" in refusal


def test_a_real_market_is_accepted():
    wide = daily([(f"S{i}", d, 5.0)
                  for d in ("2026-01-05", "2026-01-06")
                  for i in range(RS.MIN_UNIVERSE + 10)])
    med, refusal = RS.check_universe(wide)
    assert refusal is None and med > RS.MIN_UNIVERSE


def test_an_empty_archive_is_refused_rather_than_scored_as_cold():
    med, refusal = RS.check_universe(pd.DataFrame())
    assert med == 0 and refusal


# --- the permutation null ---------------------------------------------------

class T:
    def __init__(self, net):
        self.net = net + 4.26          # so net - MEASURED_FRICTION == net


def trades(spec):
    """spec = {date: [pnl, ...]}"""
    return [("SYM", d, T(v)) for d, vs in spec.items() for v in vs]


def test_the_shuffle_is_over_dates_and_not_over_trades():
    """Trades on one session share a market and are not independent draws.
    Shuffling TRADES would break that clustering and produce a null far too
    tight -- every clustered effect would come out significant. Permuting the
    date labels preserves how many trades each session contributed."""
    import inspect
    src = inspect.getsource(RS.permutation_p)
    assert "rng.shuffle(vals)" in src
    assert "dict(zip(dates, vals))" in src


def test_a_label_with_no_relation_to_the_outcome_is_not_significant():
    """The null has to actually fire. If a random labelling came out
    significant, every result this gate ever produced would be noise wearing
    a p-value."""
    import random
    rng = random.Random(7)
    spec = {f"2026-{m:02d}-{d:02d}": [rng.gauss(0, 20) for _ in range(3)]
            for m in range(1, 7) for d in range(1, 16)}
    tr = trades(spec)
    lab = {d: ["cold", "mixed", "hot"][i % 3]
           for i, d in enumerate(sorted(spec))}
    obs = RS.spread(RS.group(tr, lab))
    p = RS.permutation_p(tr, lab, obs, n=300, seed=1)
    assert p > 0.05, f"a meaningless labelling came out at p={p:.3f}"


def test_a_planted_effect_is_detected():
    """And it has to fire the OTHER way, or a null result says nothing."""
    spec = {}
    for i in range(60):
        d = f"2026-{1 + i // 20:02d}-{1 + i % 20:02d}"
        spec[d] = [50.0] * 3 if i % 3 == 2 else [-50.0] * 3
    tr = trades(spec)
    lab = {d: ["cold", "mixed", "hot"][i % 3]
           for i, d in enumerate(sorted(spec))}
    obs = RS.spread(RS.group(tr, lab))
    assert obs > 0
    assert RS.permutation_p(tr, lab, obs, n=300, seed=1) < 0.05


def test_p_is_never_reported_as_zero():
    """With no resample beating it the honest statement is 'below 1/(n+1)'.
    A printed 0.0000 is a claim no finite number of shuffles can support."""
    spec = {f"2026-01-{i:02d}": [100.0 if i > 20 else -100.0] for i in range(2, 31)}
    tr = trades(spec)
    lab = {d: ("hot" if int(d[-2:]) > 20 else "cold") for d in spec}
    p = RS.permutation_p(tr, lab, RS.spread(RS.group(tr, lab)), n=50, seed=3)
    assert p > 0


# --- bucketing ---------------------------------------------------------------

def test_a_trade_on_an_unlabelled_date_is_dropped_not_defaulted():
    """The lagged labelling has no entry for the first session by
    construction. Filing that day under 'cold' would put a real trading day in
    a bucket on the strength of an absent predecessor."""
    tr = trades({"2026-01-02": [10.0], "2026-01-05": [20.0]})
    by = RS.group(tr, {"2026-01-05": "hot"})
    assert [round(v) for v in by["hot"]] == [20]
    assert by["cold"] == [] and by["mixed"] == []


def test_the_spread_is_zero_when_a_bucket_is_empty():
    """Not a large number. An empty bucket compared against a full one is the
    shape a sign flip has, and the report refuses a verdict on it separately."""
    tr = trades({"2026-01-05": [20.0]})
    assert RS.spread(RS.group(tr, {"2026-01-05": "hot"})) == 0.0


def test_the_study_guards_the_holdout_like_every_other():
    import inspect
    src = inspect.getsource(RS)
    assert "split_sessions" in src and "--spend-holdout" in src


# --- the report renders, on both the verdict path and the refusal paths -----
#
# render() is where the index arithmetic lives (medians of possibly-empty
# lists, a halves split over the labelled dates, three quantile boundaries).
# None of that is exercised by the unit tests above, and a study that crashes
# after a twenty-minute backtest is a study nobody runs twice.

def render_args(spec, lab):
    feats = {d: RG.DayFeatures(d, 20, 12, 1, 1.5, 0.3, 5.0) for d in lab}
    return dict(trades=trades(spec), lab_same=lab, lab_lag=RG.lagged(lab),
                feats=feats, n_sessions=len(lab), med_universe=3000,
                side="training, before 2026-01-12")


def spread_sample():
    spec, lab = {}, {}
    for i in range(60):
        d = f"2026-{1 + i // 20:02d}-{1 + i % 20:02d}"
        k = ["cold", "mixed", "hot"][i % 3]
        lab[d] = k
        spec[d] = [{"cold": -40.0, "mixed": 0.0, "hot": 40.0}[k]] * 3
    return spec, lab


def test_the_report_renders_end_to_end():
    out = "\n".join(RS.render(**render_args(*spread_sample())))
    assert "THE GATE" in out and "THE CEILING" in out
    assert "permutation p" in out and "monotone" in out
    assert "PERSISTENCE" in out


def test_the_ceiling_is_never_labelled_a_result():
    """A same-day split will look spectacular by construction. If the header
    ever loses the word, the strongest number in the report becomes the one
    that cannot be acted on."""
    out = "\n".join(RS.render(**render_args(*spread_sample())))
    i = out.index("THE CEILING")
    assert "cannot know at 04:00" in out[i:i + 200]
    assert "NOT a result" in out


def test_an_empty_bucket_refuses_a_verdict():
    """A bucket with no trades reads exactly like a bucket that lost nothing.
    That is this project's recurring defect shape and it gets a refusal."""
    spec, lab = spread_sample()
    spec = {d: v for d, v in spec.items() if lab[d] != "hot"}
    out = "\n".join(RS.render(**render_args(spec, lab)))
    assert "NO VERDICT" in out


def test_a_low_persistence_warning_precedes_the_verdict():
    """At chance, no lagged gate can work whatever the same-day table shows."""
    spec, lab = spread_sample()          # a strict 3-cycle: autocorr 0
    out = "\n".join(RS.render(**render_args(spec, lab)))
    assert "THE LABEL BARELY PERSISTS" in out
    assert out.index("BARELY PERSISTS") < out.index("THE GATE")


def test_the_null_result_says_what_it_does_not_say():
    """His 16x is over HIS trading and his gate is discretionary -- he cuts
    size 5x rather than standing aside. A null here is about these features,
    not about the regime, and the report has to carry that distinction or the
    next reader retires the idea on the strength of it."""
    spec, lab = spread_sample()
    spec = {d: [-v for v in vs] for d, vs in spec.items()}   # invert: hot loses
    out = "\n".join(RS.render(**render_args(spec, lab)))
    assert "not adoptable" in out
    assert "does NOT say" in out and "cuts size" in out


# --- the reverse-split guard, and the two defects the first real run showed --

def dailyv(rows):
    """(symbol, date, close, high, volume)."""
    return pd.DataFrame([{"symbol": s, "date": d, "open": c, "high": h,
                          "low": min(c, h) * 0.9, "close": c, "volume": v}
                         for s, d, c, h, v in rows])


def history(sym, n=25, close=4.0, vol=1e6, start=1):
    return [(sym, f"2026-01-{start + i:02d}", close, close, vol)
            for i in range(n)]


def test_a_price_jump_with_no_volume_is_not_a_mover():
    """THE REVERSE-SPLIT GUARD. Daily bars are not split-adjusted, so a
    1-for-10 prints as a ~900% overnight gain with no volume behind it, and
    across ~9,000 names in the band there are several every session. The first
    real run reported a MEDIAN leading gainer of 195% and a >=100% gainer on
    729 of 863 sessions — that is not a description of the market.
    """
    rows = history("SPLIT") + [("SPLIT", "2026-02-01", 40.0, 40.0, 1e6)]
    f = RG.series(dailyv(rows))["2026-02-01"]
    assert f.n_big == 0, "a 900% move on ordinary volume counted as a gainer"
    assert f.n_suspect == 1, "and it was not counted as rejected"
    assert f.lead <= 0.0


def test_a_real_runner_brings_volume_and_still_counts():
    """The guard has to let the thing it is about through, or it is just a
    filter that makes every day look cold."""
    rows = history("RUN") + [("RUN", "2026-02-01", 12.0, 12.0, 1e6 * 20)]
    f = RG.series(dailyv(rows))["2026-02-01"]
    assert f.n_big == 1 and f.n_suspect == 0
    assert f.lead == pytest.approx(2.0)


def test_todays_volume_is_not_in_its_own_baseline():
    """Otherwise a huge day raises the bar it has to clear, and the biggest
    movers filter themselves out — the guard would remove exactly the sessions
    it exists to measure."""
    rows = history("RUN") + [("RUN", "2026-02-01", 12.0, 12.0, 1e6 * 8)]
    p = RG.prepare(dailyv(rows))
    last = p[p["date"] == "2026-02-01"].iloc[0]
    assert float(last["rel_volume"]) == pytest.approx(8.0)


def test_a_name_with_no_volume_history_gets_the_benefit_of_the_doubt():
    """The guard is aimed at one artefact, not at thinning the universe. A
    recent listing has no baseline, and these are a large part of this market."""
    rows = [("NEW", "2026-02-01", 4.0, 4.0, 1e6),
            ("NEW", "2026-02-02", 12.0, 12.0, 1e6)]
    f = RG.series(dailyv(rows))["2026-02-02"]
    assert f.n_big == 1, "a new listing was filtered out for being new"


def test_the_relative_volume_floor_is_the_screens_own():
    """One threshold, not a new one."""
    import inspect
    from common.tv_screener import RELATIVE_VOLUME_MIN
    assert RG.RELATIVE_VOLUME_MIN == RELATIVE_VOLUME_MIN
    assert "RELATIVE_VOLUME_MIN" in inspect.getsource(RG.live_volume)


def test_the_sessions_column_counts_sessions_scored_not_labelled():
    """The archive carries ~860 daily sessions and the cache carried 66 of
    them. The first run printed 297 in a column the eye reads as sample size,
    next to nine trades."""
    spec, lab = spread_sample()
    # Label a year of dates, but only score a handful.
    for i in range(300):
        lab[f"2025-{1 + i // 28:02d}-{1 + i % 28:02d}"] = "cold"
    out = "\n".join(RS.render(**render_args(spec, lab)))
    gate = out[out.index("THE GATE"):out.index("THE CEILING")]
    counts = [int(line.split()[1]) for line in gate.splitlines()
              if line.strip().startswith(("cold", "mixed", "hot"))]
    assert sum(counts) <= len(spec), (
        f"{sum(counts)} sessions reported against {len(spec)} scored")


def test_an_empty_bucket_in_a_half_is_not_reported_as_a_sign_flip():
    """`spread` returns 0.0 for an empty bucket, and 0.0 fails the
    both-halves test for exactly the same reason a genuine reversal does. The
    first run printed 'late +0.00' and concluded 'the sign flips between
    halves' when the late half simply had no hot trades."""
    spec, lab = spread_sample()
    # Strip every hot trade from the late half. Bucketing uses the LAGGED
    # labelling, so the strip has to as well -- stripping by the same-day
    # label leaves the lagged hot bucket full and the test passes vacuously.
    lag = RG.lagged(lab)
    dates = sorted(d for d in spec if d in lag)
    # Cut at a THIRD, not at the half. Removing dates moves the derived split
    # point earlier, so a cut at the half leaves hot trades sitting between
    # the new split and the old one -- which is how the first version of this
    # test passed vacuously. A quarter empties the late half too but starves
    # the hot bucket below MIN_SESSIONS_PER_BUCKET, and then the session floor
    # answers first and this test stops being about the halves at all.
    cut = dates[len(dates) // 3]
    spec = {d: v for d, v in spec.items()
            if not (d >= cut and lag.get(d) == "hot")}
    out = "\n".join(RS.render(**render_args(spec, lab)))
    assert "a bucket is EMPTY" in out
    assert "halves control did not divide" in out
    assert "the sign flips between halves" not in out


def test_a_genuine_reversal_is_still_called_a_sign_flip():
    """Or the new branch would absorb the real finding too."""
    spec, lab = spread_sample()
    mid = sorted(spec)[len(spec) // 2]
    spec = {d: ([-v for v in vs] if d >= mid else vs)
            for d, vs in spec.items()}
    out = "\n".join(RS.render(**render_args(spec, lab)))
    assert "the sign flips between halves" in out
    assert "did not divide" not in out


def test_a_bucket_of_one_session_cannot_carry_a_verdict():
    """THE FOURTH DEFECT, from the 2026-09-11 run. The table showed 9 / 9 / 53
    trades — which reads as a sample — and the corrected sessions column showed
    cold=1, mixed=2, hot=11. The cold bucket's -$16.96 per trade was a SINGLE
    MORNING.

    Trades inside one session share a market and are not independent draws:
    that is the whole reason the permutation test shuffles dates rather than
    trades. So the effective sample is the session count, and a thin bucket
    must refuse a verdict however many trades sit in it.
    """
    spec, lab = spread_sample()
    lag = RG.lagged(lab)
    # One cold session, carrying plenty of trades.
    cold = [d for d in sorted(spec) if lag.get(d) == "cold"]
    spec = {d: (v * 12 if d == cold[0] else v)
            for d, v in spec.items() if d not in cold[1:]}
    out = "\n".join(RS.render(**render_args(spec, lab)))
    assert "NO VERDICT" in out and "sessions, not trades" in out
    assert "cold = 1 session(s)" in out
    assert "not adoptable" not in out and "the gate separates" not in out


def test_the_session_floor_does_not_fire_on_a_real_sample():
    """Or every run refuses and the study never answers anything."""
    out = "\n".join(RS.render(**render_args(*spread_sample())))
    assert "sessions, not trades" not in out
    assert "VERDICT" in out


def test_the_floor_is_set_from_what_the_controls_need():
    """drop-top-N removes DROP trades, so a bucket has to carry more sessions
    than that for the check to mean anything."""
    assert RS.MIN_SESSIONS_PER_BUCKET > RS.DROP


def test_the_ceiling_gets_its_own_permutation_test():
    """WHAT THE WHOLE THREAD TURNS ON. "The lagged gate is null" has two very
    different causes: the breadth features do not separate these trades at
    all, or they DO and yesterday cannot predict today. Only the second leaves
    anything to build on. Without a p-value on the same-day split the two are
    indistinguishable, and the 2026-09-11 xnas run had a same-day spread more
    than twice the lagged one — monotone, where the lagged split was not.
    """
    out = "\n".join(RS.render(**render_args(*spread_sample())))
    ceiling = out[out.index("THE CEILING"):]
    assert "permutation p" in ceiling
    assert "not recoverable from" in ceiling


def test_the_ceiling_is_still_labelled_unusable_alongside_its_p_value():
    """A significant ceiling is the most tempting number in the report and it
    cannot be read at 04:00. The p-value must not launder it into a result."""
    out = "\n".join(RS.render(**render_args(*spread_sample())))
    i = out.index("THE CEILING")
    assert "cannot know at 04:00" in out[i:i + 200]
    assert "NOT a result" in out[i:]


def test_the_ceiling_test_is_skipped_when_a_bucket_is_empty():
    """permutation_p on an empty bucket compares against a spread of 0.0 and
    returns a meaningless 1.0. Absent beats wrong."""
    spec, lab = spread_sample()
    spec = {d: v for d, v in spec.items() if lab[d] != "cold"}
    out = "\n".join(RS.render(**render_args(spec, lab)))
    ceiling = out[out.index("THE CEILING"):]
    assert "permutation p" not in ceiling.split("CONTROLS")[0]
