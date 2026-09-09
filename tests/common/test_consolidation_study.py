#!/usr/bin/env python3
"""The arithmetic behind the consolidation verdict.

Ben proposed a Bollinger-bandwidth gate on 2026-09-09. The study said no. What
is tested here is every place that answer could have been an artefact rather
than a measurement -- because a study that produces the wrong number produces
it silently, and this one is the basis for NOT building something.
"""
from __future__ import annotations

from datetime import timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from common import consolidation_study as C

ET = ZoneInfo("America/New_York")


def frame(closes, start="2026-03-01 04:00"):
    t0 = pd.Timestamp(start, tz=ET)
    idx = pd.DatetimeIndex(
        [t0 + timedelta(minutes=i) for i in range(len(closes))],
        tz=ET).tz_convert("UTC")
    return pd.DataFrame({"open": closes, "high": closes, "low": closes,
                         "close": closes, "volume": 1000.0}, index=idx)


def row(real, level=0.1, slope=0.0, hold=3, date="2026-01-01"):
    return dict(symbol="X", date=date, real=real, level=level, slope=slope,
                hold=hold)


# --- the indicator -----------------------------------------------------------

def test_a_flat_series_has_no_bandwidth():
    """The degenerate case, and the one a consolidation study most needs to
    get right: a name that does not move at all is maximally consolidated."""
    w = C.bbw(frame([5.0] * 40))
    assert w.iloc[-1] == pytest.approx(0.0)


def test_bandwidth_is_a_fraction_of_price_not_a_number_of_dollars():
    """A $2 name and a $9 name with the same PROPORTIONAL wobble must score
    the same. Without the division the study would rank by price and call it
    volatility -- and this universe is $1 to $10."""
    wobble = [1.0, 1.02, 0.98] * 20
    cheap = C.bbw(frame([2 * x for x in wobble])).iloc[-1]
    dear = C.bbw(frame([9 * x for x in wobble])).iloc[-1]
    assert cheap == pytest.approx(dear, rel=1e-9)


def test_bandwidth_is_the_full_width_of_the_band():
    """Two standard deviations either side of the basis, so 4 sd across. Half
    of that is a different indicator with the same name, and every threshold
    in the report would be off by two."""
    closes = [5.0 + (i % 7) * 0.1 for i in range(60)]
    df = frame(closes)
    c = df["close"]
    sd = c.rolling(C.BB_LEN).std(ddof=0).iloc[-1]
    basis = c.rolling(C.BB_LEN).mean().iloc[-1]
    assert C.bbw(df).iloc[-1] == pytest.approx(2 * C.BB_K * sd / basis)


def test_widening_and_narrowing_have_the_signs_the_report_claims():
    """The whole verdict is read off the sign of the slope. If it were
    inverted, the report would recommend the opposite of what it measured and
    every table would still look plausible."""
    # The regime change has to still be INSIDE the rolling window at the last
    # bar, or both ends of the slope see the same 20 bars and it reads 0 --
    # which is a fact about the lookback, not about the series.
    def loud(n):
        return [5.0 + (i % 2) * 0.5 for i in range(n)]
    widening = C.bbw(frame([5.0] * 30 + loud(22)))
    narrowing = C.bbw(frame(loud(30) + [5.0] * 22))
    assert widening.iloc[-1] - widening.iloc[-1 - C.SLOPE_BARS] > 0
    assert narrowing.iloc[-1] - narrowing.iloc[-1 - C.SLOPE_BARS] < 0


# --- reading the entry bar ---------------------------------------------------

def trade(ts, real=10.0, hold=3, symbol="X", reason="trailing_stop"):
    """Shaped like common.portfolio.simulate's trade dicts, keys included."""
    return {"symbol": symbol, "real": real, "reason": reason,
            "entry_ts": ts, "exit_ts": ts + timedelta(minutes=hold)}


def test_the_entry_bar_is_found_by_timestamp_not_by_counting_minutes():
    """THE ERROR THIS AVOIDS. A minute with no prints produces no row, so on a
    thin pre-market name bar position and clock time come apart. Counting
    minutes from the frame's start would read a DIFFERENT bar, and quietly."""
    closes = [5.0 + (i % 5) * 0.2 for i in range(60)]
    df = frame(closes)
    gappy = df.drop(df.index[5:25])          # twenty minutes never printed
    ts = df.index[50]
    frames = {("X", "2026-03-01"): gappy}
    got = C.entry_rows([trade(ts)], frames)
    assert got, "the entry bar is present in the gappy frame and must be found"
    w = C.bbw(gappy)
    assert got[0]["level"] == pytest.approx(
        float(w.iloc[w.index.get_loc(ts)]))


def test_a_trade_without_enough_prior_bars_is_dropped_not_zero_filled():
    """A NaN bandwidth scored as 0.0 would land every warm-up trade in the
    narrowest bucket -- inventing the exact result the study was testing."""
    df = frame([5.0 + (i % 3) * 0.1 for i in range(60)])
    early = trade(df.index[C.BB_LEN + C.SLOPE_BARS - 1])
    late = trade(df.index[50])
    frames = {("X", "2026-03-01"): df}
    assert C.entry_rows([early], frames) == []
    assert len(C.entry_rows([late], frames)) == 1


def test_a_trade_whose_session_is_not_cached_is_skipped_quietly():
    assert C.entry_rows([trade(pd.Timestamp("2026-03-01 05:00", tz=ET))],
                        {}) == []


def test_hold_is_measured_in_minutes_between_the_two_stamps():
    df = frame([5.0 + (i % 3) * 0.1 for i in range(60)])
    got = C.entry_rows([trade(df.index[50], hold=37)],
                       {("X", "2026-03-01"): df})
    assert got[0]["hold"] == 37


# --- the controls ------------------------------------------------------------

def test_drop_top_three_removes_this_groups_own_winners():
    """Computed WITHIN the bucket. A bucket judged by whether the sample's
    overall best trades happened to land in it is not being judged."""
    s = C.stats([row(100), row(50), row(20), row(-5), row(-5)])
    assert s["net"] == pytest.approx(160)
    assert s["dropped"] == pytest.approx(-10)


def test_drop_top_three_is_what_kills_the_narrowing_result():
    """The measured shape, kept as a regression: a bucket can be +$686 on the
    headline and +$1 once its own three best trades are removed. A study that
    reported only the headline would have recommended the rule."""
    s = C.stats([row(300), row(250), row(135), row(1)] + [row(0)] * 60)
    assert s["net"] > 600 and s["dropped"] == pytest.approx(1)


def test_the_halves_split_is_a_fixed_date_not_a_median_of_trades():
    """A split taken at the median of the TRADES moves when the entry rule
    moves, which makes the control a function of the thing under test."""
    early, late = C.halves([row(1, date="2020-01-01")] * 9
                           + [row(1, date="2030-01-01")])
    assert (len(early), len(late)) == (9, 1), (
        "the split must not rebalance itself to the sample")
    assert C.SPLIT == "2026-03-20"


def test_buckets_are_half_open_so_nothing_is_counted_twice():
    rows = [row(1, slope=-0.01), row(2, slope=0.0), row(4, slope=0.004),
            row(8, slope=0.005), row(16, slope=1.0)]
    got = dict(C.bucket(rows, "slope", [-0.005, 0.0, 0.005]))
    assert sum(s["n"] for s in got.values()) == len(rows)
    assert sum(s["net"] for s in got.values()) == 31
    assert got[">= 0.005"]["n"] == 2, "0.005 belongs to the bucket above it"


def test_an_empty_bucket_is_omitted_rather_than_shown_as_zero():
    """A row reading n=0 $0.00 invites a reader to compare it with the others
    as though it were a measurement."""
    assert [n for n, _ in C.bucket([row(1, slope=5.0)], "slope", [-1.0, 0.0])] \
        == [">= 0"]


# --- the report ---------------------------------------------------------------

def sample_report(**kw):
    df = frame([5.0 + (i % 4) * 0.15 for i in range(60)])
    frames = {("X", "2026-03-01"): df}
    trades = [trade(df.index[40 + i], real=(i - 2) * 3.0, hold=1 + i * 4)
              for i in range(8)]
    rows = C.entry_rows(trades, frames)
    return "\n".join(C.render(rows, trades, kw.get("uncapped", trades),
                              kw.get("rej_slot", 9), 0, 373))


def test_the_report_says_what_the_evidence_is_not():
    """The locked holdout splits the SCREENED universe, not this cache, and
    MCL was fitted over this whole period. A reader who took these tables for
    out-of-sample results would be badly wrong."""
    text = sample_report()
    assert "NOT out of sample" in text
    assert "screened universe" in text


def test_the_report_states_the_pinned_parameters():
    """Bandwidth has four free parameters. A table that does not say which
    were used is a table that could have been swept."""
    text = sample_report()
    assert "not swept" in text.lower()
    assert f"{C.BB_LEN}/{C.BB_K:g}" in text and str(C.SLOPE_BARS) in text
    assert C.SPLIT in text


def test_the_report_says_lifting_the_cap_is_worse_when_it_is():
    """The premise of the whole request is that a slot is scarce. When the
    uncapped run earns LESS, that has to be said in words -- a reader
    comparing two dollar figures in a row will not notice the sign."""
    df = frame([5.0 + (i % 4) * 0.15 for i in range(60)])
    good = [trade(df.index[40], real=100.0)]
    worse = good + [trade(df.index[41], real=-40.0)]
    text = "\n".join(C.render(C.entry_rows(good, {("X", "2026-03-01"): df}),
                              good, worse, 9, 0, 373))
    assert "worth nothing" in text


def test_the_report_does_not_say_that_when_the_cap_is_costing_money():
    df = frame([5.0 + (i % 4) * 0.15 for i in range(60)])
    good = [trade(df.index[40], real=10.0)]
    better = good + [trade(df.index[41], real=40.0)]
    text = "\n".join(C.render(C.entry_rows(good, {("X", "2026-03-01"): df}),
                              good, better, 9, 0, 373))
    assert "worth nothing" not in text


def test_the_report_says_hold_time_cannot_be_used_as_a_filter():
    """Section D is the most quotable table in the study and the easiest to
    misread: hold time is known only after the trade."""
    text = sample_report()
    assert "known only AFTER" in text
    assert "description and not a filter" in text


def test_the_report_states_both_controls_before_the_numbers_are_read():
    text = sample_report()
    assert "BOTH halves" in text and "drop-top-3" in text
