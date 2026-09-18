#!/usr/bin/env python3
"""The qualifying set and the RVOL ranking (REGISTERED_orb_sip.md section 2).

THE FAILURE THIS FILE EXISTS FOR is the one that closed the last ORB line: a
universe that could only have been built after the fact. Every average here is
over PRIOR sessions, and `test_todays_value_never_enters_its_own_average` is
the test that says so. The rest guard the filters, the floor and the tie rule.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.orb import sip_universe as U

DATES = [f"2025-03-{d:02d}" for d in range(1, 26)]


def frame(symbol="AAA", n=20, *, or5=100_000.0, day_vol=5e6, open_=10.0,
          high=10.5, low=9.5, close=10.0, first_bar=570):
    """n consecutive sessions of one symbol, all identical unless overridden."""
    return pd.DataFrame({
        "symbol": symbol, "date": DATES[:n], "open": open_, "first_bar": first_bar,
        "rth_high": high, "rth_low": low, "rth_close": close,
        "or5_volume": or5, "or15_volume": or5 * 2.0, "day_volume": day_vol,
    })


def build(df, vol=None):
    """One tape unless a test supplies a second (amendment B)."""
    dvol = df[["symbol", "date", "day_volume"]]
    price = df.drop(columns=["day_volume"])
    return U.build_universe(price, vol if vol is not None else price, dvol)


def test_todays_value_never_enters_its_own_average():
    """A 10x volume day must read RVOL 10, not 10/(mean including itself).

    With the shift removed the spike lands in its own 14-day mean and the ratio
    collapses toward 1 -- the universe would then be chosen partly by the day
    it is trying to rank.
    """
    df = frame(n=20)
    df.loc[df.index[-1], "or5_volume"] = 1_000_000.0      # 10x the prior 14
    out = build(df)
    last = out.iloc[-1]
    assert last.avg_or5 == pytest.approx(100_000.0)
    assert last.rvol5 == pytest.approx(10.0)


def test_the_first_fourteen_sessions_have_no_ranking_at_all():
    out = build(frame(n=20))
    assert out.iloc[:14]["rvol5"].isna().all(), "a full 14-session window or nothing"
    assert out.iloc[14:]["rvol5"].notna().all()
    assert not out.iloc[:14]["qualifies"].any()


def test_each_registered_filter_can_refuse_on_its_own():
    base = build(frame(n=20)).iloc[-1]
    assert base.qualifies, "the control row must pass, or nothing below is a test"

    cheap = build(frame(n=20, open_=4.99)).iloc[-1]
    assert not cheap.qualifies and cheap.open == 4.99

    thin = build(frame(n=20, day_vol=999_999.0)).iloc[-1]
    assert not thin.qualifies

    quiet = build(frame(n=20, high=10.2, low=9.9, close=10.0)).iloc[-1]
    assert quiet.atr14 <= U.MIN_ATR and not quiet.qualifies

    # $5.00 exactly is not "above $5"
    at_five = build(frame(n=20, open_=5.00)).iloc[-1]
    assert not at_five.qualifies


def test_rvol_below_one_qualifies_but_is_not_eligible():
    """Two different gates: the universe filter, then the paper's RVOL floor."""
    df = frame(n=20)
    df.loc[df.index[-1], "or5_volume"] = 99_999.0
    out = build(df).iloc[-1]
    assert out.qualifies and out.rvol5 < 1.0
    assert not out.eligible5 and pd.isna(out.rank5)


def test_a_name_with_no_0930_bar_is_excluded_and_counted():
    out = build(frame(n=20, first_bar=9 * 60 + 47)).iloc[-1]
    assert not out.has_open and not out.qualifies
    assert U.counts(build(frame(n=20, first_bar=9 * 60 + 47)))["no_0930_bar"] == 20


def test_the_adjustment_guard_refuses_a_reverse_split_print():
    """Section 3.5. On a raw tape a 1-for-10 reverse split is a 10x gap, and it
    would otherwise arrive as the most active name of the day."""
    df = frame(n=20)
    df.loc[df.index[-1], ["open", "rth_high", "rth_low", "rth_close"]] = [100.0, 105.0, 95.0, 100.0]
    out = build(df).iloc[-1]
    assert not out.guard_ok and not out.qualifies
    df.loc[df.index[-1], ["open", "rth_high", "rth_low", "rth_close"]] = [40.0, 42.0, 38.0, 40.0]
    assert build(df).iloc[-1].guard_ok, "4x is inside the guard and must pass"


def test_the_top_twenty_is_by_rvol_descending_with_ties_by_symbol():
    syms = [f"S{i:02d}" for i in range(30)]
    parts = []
    for i, s in enumerate(syms):
        f = frame(symbol=s, n=20)
        # Distinct RVOL for the first ten, an exact tie for the rest.
        f.loc[f.index[-1], "or5_volume"] = 100_000.0 * (3.0 if i < 10 else 2.0)
        parts.append(f)
    out = build(pd.concat(parts, ignore_index=True))
    last = out[out["date"] == DATES[19]].dropna(subset=["rank5"])
    ranked = last.sort_values("rank5")
    assert list(ranked.head(10)["symbol"]) == syms[:10]
    tied = list(ranked.iloc[10:20]["symbol"])
    assert tied == sorted(tied) == syms[10:20], "ties break by symbol ascending"
    assert (last["rank5"] <= U.TOP_N).sum() == 20


def test_ranks_restart_every_session():
    parts = [frame(symbol=s, n=20) for s in ("AAA", "BBB")]
    out = build(pd.concat(parts, ignore_index=True))
    per_day = out.dropna(subset=["rank5"]).groupby("date")["rank5"]
    assert per_day.min().eq(1).all() and per_day.max().le(2).all()


def test_the_fifteen_minute_ranking_is_computed_from_its_own_volume():
    df = frame(n=20)
    df.loc[df.index[-1], "or15_volume"] = 200_000.0 * 4          # 4x prior
    out = build(df).iloc[-1]
    assert out.rvol15 == pytest.approx(4.0) and out.rvol5 == pytest.approx(1.0)


def test_true_range_uses_the_prior_close():
    df = frame(n=3, high=11.0, low=10.5, close=10.8)
    df.loc[df.index[0], ["rth_high", "rth_low", "rth_close"]] = [10.0, 9.0, 9.5]
    tr = U.true_range(df.sort_values(["symbol", "date"]).reset_index(drop=True))
    # Session 2: high 11.0, low 10.5, prior close 9.5 -> 11.0 - 9.5 = 1.5
    assert tr.iloc[1] == pytest.approx(1.5)


def test_counts_report_what_was_excluded_and_why():
    parts = [frame(symbol=s, n=20) for s in ("AAA", "BBB")]
    bad = frame(symbol="CCC", n=20, first_bar=600)
    c = U.counts(build(pd.concat(parts + [bad], ignore_index=True)))
    assert c["sessions"] == 20 and c["no_0930_bar"] == 20
    assert c["qualify"] == 12 and c["eligible5"] == 12
    assert c["sessions_short_of_top_n"] == 6


# --------------------------------------------------------------------------
# amendment B -- prices from one tape, opening-range volume from another
# --------------------------------------------------------------------------

def test_the_ranking_reads_the_volume_tape_and_the_filters_read_the_price_tape():
    """XNAS.BASIC carries off-exchange prints that put AAPL's low 4.8% below
    the real session low; XNAS.ITCH matches the consolidated daily high and
    low. So prices come from ITCH and the opening-range volume, where BASIC
    sees 56% of the market against ITCH's 12%, comes from BASIC."""
    price = frame(n=20)                      # clean tape, or5_volume flat
    vol = frame(n=20)
    vol.loc[vol.index[-1], "or5_volume"] = 400_000.0        # 4x on the volume tape
    out = U.build_universe(price.drop(columns=["day_volume"]), vol,
                           price[["symbol", "date", "day_volume"]])
    last = out.iloc[-1]
    assert last.rvol5 == pytest.approx(4.0), "the ranking must read the volume tape"
    assert last.open == 10.0 and last.qualifies

    # And a corrupt low on the volume tape must not reach ATR or the filters.
    vol.loc[vol.index[-1], "rth_low"] = 1.0
    out2 = U.build_universe(price.drop(columns=["day_volume"]), vol,
                            price[["symbol", "date", "day_volume"]])
    assert out2.iloc[-1].atr14 == pytest.approx(out.iloc[-1].atr14)


def test_a_symbol_day_missing_from_the_volume_tape_cannot_be_ranked():
    price = frame(n=20)
    vol = frame(n=20).iloc[:-1]              # today's OR volume absent
    out = U.build_universe(price.drop(columns=["day_volume"]), vol,
                           price[["symbol", "date", "day_volume"]])
    last = out.iloc[-1]
    assert pd.isna(last.rvol5) and not last.eligible5
    assert last.qualifies, "the universe filters do not depend on the volume tape"


def test_the_daily_volume_date_is_the_sessions_own_date(tmp_path, monkeypatch):
    """A daily bar is stamped 00:00 UTC on its session date. Converted to ET
    it becomes the previous evening, and every session's volume then merges
    onto the day before -- silently, because most rows still match."""
    idx = pd.to_datetime(["2025-03-03", "2025-03-04"]).tz_localize("UTC")
    df = pd.DataFrame({"symbol": ["AAA", "AAA"], "volume": [1.0, 2.0],
                       "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0}, index=idx)
    monkeypatch.setattr(U, "load_daily_volume", U.load_daily_volume)
    import common.dbn_io as dbn
    monkeypatch.setattr(dbn, "read_dbn", lambda *a, **k: df)
    monkeypatch.setattr("common.dbn_io.read_dbn", lambda *a, **k: df)
    arch = tmp_path / "A" / "EQUS.SUMMARY" / "ohlcv-1d"
    arch.mkdir(parents=True)
    (arch / "2025-03.dbn.zst").write_bytes(b"x")
    out = U.load_daily_volume(tmp_path / "A", "EQUS.SUMMARY", tmp_path / "c.csv.gz")
    assert sorted(out["date"]) == ["2025-03-03", "2025-03-04"]
