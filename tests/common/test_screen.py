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


def test_the_screen_does_not_apply_mcls_price_band():
    """A $1.80 stock that gaps to $6 pre-market is a legitimate MCL candidate.

    The live scanner screens on premarket_close -- the price at 04:00 -- so
    that name passes live. Applying MCL's $2-20 to the PRIOR close rejected 39%
    of the 587 symbol-days Ben actually traded, whose median prior close was
    $2.60. MCL enforces the real band at entry, on the price at the time, which
    is both the right place and not look-ahead. The screen must not do it here
    and must not do it on the wrong day's price.
    """
    rows = series(close=1.80, n=12)
    rows.append(("AAA", "2025-06-13", 1.85, 6.5, 1.8, 6.0, 50_000_000))
    df = S.features(daily(rows), S.Config())
    assert S.stage1(df, S.Config()).iloc[-1], (
        "a sub-$2 prior close must survive the screen -- the band belongs at entry")


def test_the_sanity_band_still_excludes_the_obviously_untradeable():
    """Dropping MCL's band is not dropping all price sense. A $0.02 shell and a
    $900 name are not candidates for this strategy at any hour."""
    cfg = S.Config()
    for px in (0.02, 900.0):
        rows = series(close=px, n=12, vol=5_000_000)
        rows.append(("AAA", "2025-06-13", px, px * 1.5, px, px * 1.4, 50_000_000))
        df = S.features(daily(rows), cfg)
        assert not S.stage1(df, cfg).iloc[-1], f"${px} should fail the sanity band"


def test_stage1_still_reads_the_prior_close_not_todays():
    """Whatever the band's width, it must be judged on data known at 03:59."""
    rows = series(close=0.10, n=12, vol=5_000_000)
    rows.append(("AAA", "2025-06-13", 0.10, 9.0, 0.10, 8.0, 90_000_000))
    cfg = S.Config()
    df = S.features(daily(rows), cfg)
    # today's close is $8 (inside any band); the prior close is $0.10 (outside)
    assert not S.stage1(df, cfg).iloc[-1]


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


# --- the symbology trap -----------------------------------------------------

def test_an_unsymbolised_archive_raises_instead_of_reporting_zeroes(tmp_path):
    """The failure that produced a clean report full of structural zeroes.

    An ALL_SYMBOLS pull embeds no symbol mapping, so to_df(map_symbols=True)
    returns symbol=None on every row without failing. Downstream the frame
    de-duplicated on (symbol, date), collapsed 206,362 rows per month to one
    per session, and the screen reported "864 symbol-days, 0 distinct symbols"
    and exited 0. Nothing raised anywhere.

    daily_frame must refuse that frame rather than pass it on.
    """
    import pandas as pd
    from common import dbn_io

    df = pd.DataFrame({
        "ts_event": pd.to_datetime(["2026-08-03", "2026-08-04"], utc=True),
        "symbol": [None, None],
        "open": [1.0, 1.0], "high": [1.0, 1.0], "low": [1.0, 1.0],
        "close": [1.0, 1.0], "volume": [10, 10],
    }).set_index("ts_event")

    d = tmp_path / "EQUS.MINI" / "ohlcv-1d"
    d.mkdir(parents=True)
    (d / "2026-08.dbn.zst").write_bytes(b"")

    import unittest.mock as mock
    with mock.patch.object(dbn_io, "read_many", return_value=df):
        with pytest.raises(ValueError, match="resolved no tickers"):
            dbn_io.daily_frame(tmp_path, "EQUS.MINI")


def test_symbology_sits_next_to_its_data_file():
    from common.dbn_io import symbology_path
    from pathlib import Path
    p = symbology_path(Path("databento/EQUS.MINI/ohlcv-1d/2026-08.dbn.zst"))
    assert p == Path("databento/EQUS.MINI/ohlcv-1d/2026-08.symbology.json")


# --- exchange test symbols --------------------------------------------------

def test_exchange_test_symbols_are_recognised():
    """ZVZZT was the second most frequent name in the first candidate list --
    30 of 864 sessions. It is Nasdaq's connectivity test instrument, not a
    security. Its prints are arbitrary, so any P/L it produced would be noise
    presented as a symbol-level result."""
    for s in ("ZVZZT", "ZWZZT", "ZXZZT", "ZBZZT", "ZVZZC", "ATEST", "NTEST",
              "ZTEST", "zvzzt"):
        assert S.is_test_symbol(s), s
    for s in ("HOLO", "VCIG", "WHLR", "MLGO", "AAPL", "ZM", "TSLA", "ZI"):
        assert not S.is_test_symbol(s), s


def test_test_symbols_never_reach_the_candidate_list():
    rows = []
    for sym in ("ZVZZT", "REAL"):
        rows += series(symbol=sym, n=12, close=5.0, vol=500_000)
        rows.append((sym, "2025-06-13", 5.0, 7.0, 4.9, 6.8, 5_000_000))
    cfg = S.Config()
    sel = S.select(S.features(daily(rows), cfg), cfg)
    assert list(sel["symbol"]) == ["REAL"]
