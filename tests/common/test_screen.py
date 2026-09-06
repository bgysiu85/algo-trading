#!/usr/bin/env python3
"""The look-ahead boundary, pinned.

A screen that peeks at today's bar to choose this morning's watchlist produces
a spectacular backtest and an untradeable strategy, and it does not look wrong
-- the P/L is simply large. These tests exist so that boundary cannot move
without a test going red.
"""
from __future__ import annotations

import pandas as pd
import pytest

from common import screen as S


def daily(rows):
    """rows: (symbol, date, open, high, low, close, volume)"""
    return pd.DataFrame(rows, columns=["symbol", "date", "open", "high",
                                       "low", "close", "volume"])


def series(symbol="AAA", n=15, close=5.0, vol=1_000_000, start=1):
    return [(symbol, f"2025-06-{start+i:02d}", close, close * 1.01,
             close * 0.99, close, vol) for i in range(n)]


# --- the boundary -----------------------------------------------------------

def test_prior_average_volume_excludes_today(tmp_path):
    """The bug that would be invisible.

    Rolling on the unshifted series includes today's volume in the baseline it
    is compared against, which mutes every spike: a 10x day divides by an
    average that already contains the 10x. The result is a lower, entirely
    plausible RVOL -- no error, just a different universe.
    """
    rows = series(n=11, vol=1_000_000)
    rows.append(("AAA", "2025-06-12", 5.0, 6.0, 4.9, 5.5, 10_000_000))
    df = S.features(daily(rows), S.Config())
    last = df.iloc[-1]
    assert last["prior_avg_vol"] == pytest.approx(1_000_000)
    assert last["rvol"] == pytest.approx(10.0)


def test_stage1_uses_no_column_from_todays_bar():
    """Stage 1 is the only part a live scanner could run at 03:59. If it ever
    starts reading today's close, high, low or volume, the whole separation is
    decorative."""
    import inspect
    src = inspect.getsource(S.stage1)
    for banned in ('"close"', '"high"', '"low"', '"volume"', '"open"',
                   '"rvol"', '"range_pct"', '"gap_pct"'):
        assert banned not in src, f"stage1 reads {banned} -- that is look-ahead"
    assert '"prior_close"' in src and '"prior_avg_dollar_vol"' in src


def test_price_band_is_judged_on_the_prior_close_not_todays():
    """A $1.80 stock that closes at $6 today is NOT in the band at 04:00. Using
    today's close would select it and no live scanner could."""
    rows = series(close=1.80, n=12)
    rows.append(("AAA", "2025-06-13", 1.85, 6.5, 1.8, 6.0, 50_000_000))
    df = S.features(daily(rows), S.Config())
    assert not S.stage1(df, S.Config()).iloc[-1]


# --- selection --------------------------------------------------------------

def test_a_quiet_day_on_a_qualifying_name_is_not_selected():
    df = S.features(daily(series(n=15)), S.Config())
    assert S.select(df, S.Config()).empty


def test_a_surge_on_a_qualifying_name_is_selected():
    rows = series(n=12, close=5.0, vol=500_000)
    rows.append(("AAA", "2025-06-13", 5.0, 7.0, 4.9, 6.8, 5_000_000))
    cfg = S.Config()
    sel = S.select(S.features(daily(rows), cfg), cfg)
    assert list(sel["symbol"]) == ["AAA"] and list(sel["date"]) == ["2025-06-13"]


def test_illiquid_names_are_excluded_before_anything_else():
    """A name that normally trades $2k/day can post a 50x RVOL on one print.
    Without the liquidity floor the universe fills with names no order can be
    worked in -- the failure the volume-floor study documented from the other
    direction."""
    rows = series(n=12, close=5.0, vol=400)          # ~$2k/day
    rows.append(("AAA", "2025-06-13", 5.0, 7.0, 4.9, 6.8, 20_000))
    cfg = S.Config()
    assert S.select(S.features(daily(rows), cfg), cfg).empty


def test_the_per_day_cap_keeps_the_highest_rvol():
    rows = []
    for i in range(10):
        s = f"S{i:02d}"
        rows += series(symbol=s, n=12, close=5.0, vol=500_000)
        rows.append((s, "2025-06-13", 5.0, 7.0, 4.9, 6.8, 500_000 * (i + 6)))
    cfg = S.Config(max_candidates_per_day=3)
    sel = S.select(S.features(daily(rows), cfg), cfg)
    assert len(sel) == 3
    assert set(sel["symbol"]) == {"S09", "S08", "S07"}


def test_pairs_output_matches_the_repo_pair_format():
    rows = series(n=12, close=5.0, vol=500_000)
    rows.append(("AAA", "2025-06-13", 5.0, 7.0, 4.9, 6.8, 5_000_000))
    cfg = S.Config()
    pl = S.pairs(S.select(S.features(daily(rows), cfg), cfg))
    assert pl == [{"symbol": "AAA", "date": "2025-06-13"}]


# --- warm-up ----------------------------------------------------------------

def test_a_name_with_too_little_history_yields_no_rvol_and_is_not_selected():
    """min_periods=3 means the first two sessions of any listing have no
    baseline. They must drop out rather than divide by NaN and slip through."""
    rows = [("NEW", "2025-06-01", 5.0, 9.0, 4.9, 8.0, 9_000_000)]
    cfg = S.Config()
    df = S.features(daily(rows), cfg)
    assert pd.isna(df.iloc[0]["rvol"])
    assert S.select(df, cfg).empty


def test_features_are_computed_per_symbol_not_across_the_whole_frame():
    """A groupby that leaks across symbols gives BBB's first day AAA's prior
    close. Sorted input makes this easy to get wrong and impossible to see."""
    rows = series("AAA", n=4, close=5.0) + series("BBB", n=4, close=50.0)
    df = S.features(daily(rows), S.Config())
    b0 = df[(df["symbol"] == "BBB")].iloc[0]
    assert pd.isna(b0["prior_close"])
