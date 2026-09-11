#!/usr/bin/env python3
"""The tape comparison, and the two things that would make it meaningless.

Two measurements of MCL disagree by 10x — -$0.53/trade on the screened run,
-$5.22 on bar_cache_xnas. This module exists to attribute that, and it has
exactly two ways to produce a confident wrong answer:

  1. comparing two different UNIVERSES and calling the difference a tape, and
  2. comparing SPLIT-ADJUSTED IB prices against raw Databento prices, where
     every split shows up as an enormous coverage effect.

`test_the_comparison_is_the_intersection_never_the_union` and
`test_a_split_adjusted_day_is_excluded_and_counted` are the headline tests.
"""
from __future__ import annotations

from datetime import timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from common import tape_compare as TC

ET = ZoneInfo("America/New_York")


def frame(n=30, close=4.0, vol=1000.0, rng=0.01, start="2026-03-02 04:00",
          step=1):
    idx = pd.DatetimeIndex(
        [pd.Timestamp(start, tz=ET) + timedelta(minutes=i * step)
         for i in range(n)], tz=ET).tz_convert("UTC")
    return pd.DataFrame({
        "open": [close] * n,
        "high": [close * (1 + rng)] * n,
        "low": [close * (1 - rng)] * n,
        "close": [close] * n,
        "volume": [vol] * n,
    }, index=idx)


def sess(pairs):
    """[(symbol, date, frame)] from {(sym, date): frame}."""
    return [(s, d, f) for (s, d), f in pairs.items()]


# --- THE HEADLINE: the universe confound ------------------------------------

def test_the_comparison_is_the_intersection_never_the_union():
    """bar_cache_xnas holds 27,776 symbol-days; the screened run covered
    21,407. Comparing those two POPULATIONS would measure the universe and
    report it as the tape — and it would look exactly like a tape effect,
    because a bigger universe takes more trades and the extra ones are
    different.
    """
    a = sess({("AAA", "2026-03-02"): frame(), ("BBB", "2026-03-02"): frame()})
    b = sess({("AAA", "2026-03-02"): frame(), ("CCC", "2026-03-02"): frame()})
    g = TC.collect(a, b)
    assert g["n_a"] == 2 and g["n_b"] == 2
    assert g["n_matched"] == 1, "a symbol present on one side only was scored"
    assert g["scored"] == 1


def test_the_unmatched_counts_are_reported_not_silently_dropped():
    """Dropping 6,000 symbol-days quietly and printing a clean table is how a
    universe difference becomes a tape finding."""
    a = sess({("AAA", "2026-03-02"): frame()})
    b = sess({("AAA", "2026-03-02"): frame(), ("CCC", "2026-03-02"): frame()})
    out = "\n".join(TC.render(TC.collect(a, b), "xnas", "db"))
    assert "MATCHED" in out and "SCORED" in out


def test_too_few_matched_days_refuses_a_comparison():
    a = b = sess({("AAA", "2026-03-02"): frame()})
    out = "\n".join(TC.render(TC.collect(a, list(b)), "xnas", "db"))
    assert "NO COMPARISON" in out


# --- THE SECOND HEADLINE: split adjustment ----------------------------------

def test_a_split_adjusted_day_is_excluded_and_counted():
    """`bar_cache` is IB data and SPLIT-ADJUSTED; the Databento caches are RAW.
    On any name that split, every price differs by the split factor. That is a
    UNITS difference, not a tape difference, and left in it would swamp the
    coverage measurement while looking like an enormous one.
    """
    a = sess({("AAA", "2026-03-02"): frame(close=4.0),
              ("SPL", "2026-03-02"): frame(close=40.0)})
    b = sess({("AAA", "2026-03-02"): frame(close=4.0),
              ("SPL", "2026-03-02"): frame(close=4.0)})
    g = TC.collect(a, b)
    assert g["splits"] == 1
    assert g["scored"] == 1, "the 10x price day was scored as a tape effect"


def test_an_ordinary_tape_difference_is_not_called_a_split():
    """Real venue differences in a minute's close are sub-1%. A band that
    excluded those would throw away the measurement itself."""
    a = sess({("AAA", "2026-03-02"): frame(close=4.00)})
    b = sess({("AAA", "2026-03-02"): frame(close=4.01)})
    assert TC.collect(a, b)["splits"] == 0


def test_the_split_band_is_wide_enough_to_only_catch_units():
    """It has to separate 'different venues' from 'different units', and
    nothing in between needs deciding."""
    lo, hi = TC.SPLIT_BAND
    assert lo <= 0.95 and hi >= 1.05, "a real tape difference would be excluded"
    assert lo > 0.5 and hi < 2.0, "a 2:1 split would be scored"


# --- coverage ---------------------------------------------------------------

def test_a_minute_present_on_one_tape_only_is_counted_not_filled():
    """A minute with no print is not a minute with zero volume. Filling a
    fabricated zero into the volume ratio would understate the thinner tape's
    coverage — in the direction that flatters the conclusion."""
    a = sess({("AAA", "2026-03-02"): frame(n=30)})
    b = sess({("AAA", "2026-03-02"): frame(n=20)})
    g = TC.collect(a, b)
    assert g["minutes_shared"] == 20
    assert g["minutes_a_only"] == 10 and g["minutes_b_only"] == 0


def test_the_volume_ratio_reads_the_right_way_round():
    a = sess({("AAA", "2026-03-02"): frame(vol=550.0)})
    b = sess({("AAA", "2026-03-02"): frame(vol=1000.0)})
    g = TC.collect(a, b)
    assert g["bars"][0]["vol_ratio"] == pytest.approx(0.55)


def test_a_zero_volume_minute_does_not_produce_an_infinity():
    """It happens on a thin tape, which is exactly the case being measured."""
    a = sess({("AAA", "2026-03-02"): frame(vol=100.0)})
    b = sess({("AAA", "2026-03-02"): frame(vol=0.0)})
    r = TC.collect(a, b)["bars"][0]["vol_ratio"]
    assert r != r or r < float("inf")          # NaN or finite, never inf


def test_the_range_is_normalised_by_price():
    """So a $2 name and a $19 one are comparable. An absolute range would make
    the measurement a function of which names happened to match.

    Tested on `bar_stats` directly and NOT through `collect`: a $2 frame joined
    against a $19 one is a 9.5x price ratio, which is precisely what
    `split_suspect` exists to exclude. The first version of this test went
    through collect and failed on its own split guard — correctly.
    """
    cheap = TC.bar_stats(TC.aligned(frame(close=2.0, rng=0.01),
                                    frame(close=2.0, rng=0.01)))
    dear = TC.bar_stats(TC.aligned(frame(close=19.0, rng=0.01),
                                   frame(close=19.0, rng=0.01)))
    assert cheap["range_a"] == pytest.approx(dear["range_a"], rel=1e-9)
    assert cheap["range_a"] == pytest.approx(0.02, rel=1e-9)


# --- trade pairing ----------------------------------------------------------

class T:
    def __init__(self, ts, net=10.0, reason="trailing_stop", bars=5):
        self.entry_time, self.net = ts, net + TC.MEASURED_FRICTION
        self.reason, self.bars_held = reason, bars


def ts(minute):
    return str(pd.Timestamp(f"2026-03-02 07:{minute:02d}", tz=ET))


def test_trades_within_the_window_pair_and_the_gap_is_reported():
    p, ao, bo = TC.pair_trades([T(ts(10))], [T(ts(12))])
    assert len(p) == 1 and not ao and not bo
    assert p[0][2] == pytest.approx(2.0)


def test_a_trade_outside_the_window_is_tape_only_not_paired():
    """An unpaired trade is the most interesting kind: one tape took it and the
    other did not. Forcing a pair would hide exactly that."""
    p, ao, bo = TC.pair_trades([T(ts(10))], [T(ts(40))])
    assert not p and len(ao) == 1 and len(bo) == 1


def test_each_trade_pairs_at_most_once():
    """Two entries a minute apart on one tape and one on the other must not
    both claim the same partner — that would invent a trade."""
    p, ao, bo = TC.pair_trades([T(ts(10)), T(ts(11))], [T(ts(10))])
    assert len(p) == 1 and len(ao) == 1 and not bo


def test_pairing_takes_the_nearest_entry():
    p, _, _ = TC.pair_trades([T(ts(20))], [T(ts(30)), T(ts(21))])
    assert p[0][2] == pytest.approx(1.0)


# --- the verdict ------------------------------------------------------------

def matched(n=60, **kw):
    a = {("S%03d" % i, "2026-03-02"): frame(**kw) for i in range(n)}
    b = {("S%03d" % i, "2026-03-02"): frame() for i in range(n)}
    return sess(a), sess(b)


def g_with(paired, a_only, b_only, pa=0.0, pb=0.0, trades=100):
    return {"n_a": 100, "n_b": 100, "n_matched": 100, "splits": 0,
            "scored": 100, "minutes_shared": 1000, "minutes_a_only": 0,
            "minutes_b_only": 0,
            "bars": [{"minutes": 10, "vol_ratio": 0.55,
                      "range_a": 0.01, "range_b": 0.02}],
            "paired": [("A", "2026-03-02", T(ts(10), pa), T(ts(10), pb), 0.0)]
                      * paired,
            "a_only": [("A", "2026-03-02", T(ts(10)))] * a_only,
            "b_only": [("A", "2026-03-02", T(ts(10)))] * b_only,
            "trades_a": trades, "trades_b": trades,
            "net_a": pa * trades, "net_b": pb * trades,
            "days_a": 50, "days_b": 50}


def test_mostly_unpaired_trades_reads_as_a_tape_artefact():
    """If the two tapes select different trades, a per-trade P/L measured on
    one does not describe the other — which is the whole question."""
    out = "\n".join(TC.render(g_with(10, 60, 60), "xnas", "db"))
    assert "FEWER THAN HALF THE TRADES PAIR" in out
    assert "TAPE artefact" in out


def test_paired_trades_with_a_large_gap_points_at_the_exits():
    out = "\n".join(TC.render(g_with(90, 5, 5, pa=-5.22, pb=-0.53),
                              "xnas", "db"))
    assert "That is the EXITS" in out
    assert "FEWER THAN HALF" not in out


def test_agreement_sends_the_reader_to_the_universe():
    """The outcome that would refute my own tape hypothesis has to be one the
    report states plainly, or the module only knows how to confirm."""
    out = "\n".join(TC.render(g_with(90, 5, 5, pa=-1.0, pb=-0.6),
                              "xnas", "db"))
    assert "it is NOT the tape" in out
    assert "universe and the date range" in out


def test_the_report_never_rescales_anything():
    """`sizing_and_capacity.md` §3's rule: a correction applied silently is a
    correction nobody can check. The ratios are printed; the arithmetic is the
    reader's."""
    out = "\n".join(TC.render(g_with(90, 5, 5), "xnas", "db"))
    assert "Not a correction" in out
    assert "left to the reader" in out


def test_the_report_says_neither_tape_is_the_live_one():
    """IBKR fills against the consolidated tape. A reader who concludes 'use
    the other cache' from this has drawn the wrong lesson."""
    out = "\n".join(TC.render(g_with(90, 5, 5), "xnas", "db"))
    assert "IBKR fills against the" in out and "consolidated tape" in out
    assert "0.831" in out, "the closest cache is named with its measured figure"


def test_comparing_a_cache_with_itself_is_refused():
    with pytest.raises(SystemExit):
        TC.main(["--a", "bar_cache", "--b", "bar_cache"])


# --- the identity case: the strongest smoke test there is -------------------

def test_a_cache_compared_with_itself_agrees_exactly():
    """THE CALIBRATION. Run the same bars down both sides and every difference
    must vanish: all trades pair, the entry gap is zero, the exit reasons match
    and the per-trade delta is exactly $0.00.

    If this ever shows a difference, the module is manufacturing one — and a
    manufactured difference in THIS study would be read as a tape effect and
    used to explain away a 10x P/L gap.

    Run on real cached bars rather than a fixture, because the fixture cannot
    exercise the join, the split guard and the pairing against real timestamps
    at once.
    """
    from pathlib import Path
    from common.analysis import load_sessions

    sessions = load_sessions(Path("bar_cache"))[:40]
    if len(sessions) < 10:
        pytest.skip("bar_cache is not populated in this environment")
    g = TC.collect(sessions, sessions)
    assert g["splits"] == 0, "a cache is not a split of itself"
    assert g["scored"] == g["n_matched"] == len(sessions)
    assert g["minutes_a_only"] == 0 and g["minutes_b_only"] == 0
    assert g["trades_a"] == g["trades_b"] > 0, "vacuous with no trades"
    assert not g["a_only"] and not g["b_only"], "a trade failed to pair"
    assert g["net_a"] == pytest.approx(g["net_b"])
    gaps = [gap for _, _, _, _, gap in g["paired"]]
    assert max(gaps) == 0.0
    for _, _, x, y, _ in g["paired"]:
        assert x.reason == y.reason and x.bars_held == y.bars_held


def test_the_identity_case_reaches_the_agreement_verdict():
    """And the report has to say so, rather than finding an effect in noise."""
    from pathlib import Path
    from common.analysis import load_sessions

    sessions = load_sessions(Path("bar_cache"))[:40]
    if len(sessions) < 10:
        pytest.skip("bar_cache is not populated in this environment")
    out = "\n".join(TC.render(TC.collect(sessions, sessions), "x", "y"))
    assert "it is NOT the tape" in out
