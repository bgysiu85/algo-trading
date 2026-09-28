"""Tests for `strategy.orb.tensec_hq1` -- W05-0003 step 7 (G5, then H-Q1).

Every test here uses hand-built frames -- no MBP-1 record is read from disk
(G4's real archive lives on E:\\Databento, outside this bridge's reach; Ben
runs the real thing per the commands on board item W05-0003 subitem 7). The
one test that matters most (`test_g5_reads_the_signal_in_the_trades_own_frame`)
is mutation-checked by hand: run it against the "naive" version that compares
`I_s` to the RAW (unsigned) mid change instead of the side-adjusted one, and
it fails -- the short-trade case flips from "right" to "wrong". That is
exactly the bug the module docstring's "A NOTE ON SIGNING" section explains.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from strategy.orb import tensec_g4 as G4
from strategy.orb import tensec_hq1 as H

UTC = ZoneInfo("UTC")
ET = ZoneInfo("America/New_York")

DAY = "2026-01-05"
TRIGGER_SEC = 34520          # 09:35:20 ET -- matches tensec_g4's own test fixture


def qrow(bid_px, ask_px, bid_sz, ask_sz):
    return {"bid_px_00": bid_px, "ask_px_00": ask_px,
            "bid_sz_00": bid_sz, "ask_sz_00": ask_sz,
            "action": "M", "side": "N", "price": float("nan"), "size": 0.0}


def qframe(rows: dict[datetime, dict]) -> pd.DataFrame:
    idx = pd.DatetimeIndex(sorted(rows.keys()), tz="UTC")
    return pd.DataFrame([rows[k] for k in sorted(rows.keys())], index=idx)


class FakeWindows:
    """Duck-types `tensec_hq1.Windows` without touching a filesystem."""

    def __init__(self, frames: dict[tuple, pd.DataFrame | None]):
        self._frames = frames

    def get(self, symbol, day):
        return self._frames.get((symbol, day))


def trade_row(symbol="AAA", day=DAY, side=1, r=0.10, trigger_sec=TRIGGER_SEC,
             entry_px=10.00, entry_sec=None, exit_px=None, exit_reason="stop"):
    if entry_sec is None:
        entry_sec = trigger_sec + 10
    if exit_px is None:
        exit_px = entry_px - side * r      # a scratch-ish stop-out by default
    return dict(symbol=symbol, date=day, side=side, r=r,
               t1_why="OK", t1_trigger_sec=trigger_sec,
               t1_entry_px=entry_px, t1_entry_sec=entry_sec,
               t1_exit_px=exit_px, t1_exit_reason=exit_reason)


def pop_df(rows):
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# log_binom_sf
# --------------------------------------------------------------------------

def test_log_binom_sf_all_right_is_tiny():
    import math
    p = math.exp(H.log_binom_sf(20, 20))
    assert p == pytest.approx(0.5 ** 20, rel=1e-6)


def test_log_binom_sf_half_right_is_about_half():
    import math
    p = math.exp(H.log_binom_sf(50, 100))
    assert 0.4 < p < 0.6


def test_log_binom_sf_k_greater_than_n_is_impossible():
    assert H.log_binom_sf(5, 3) == float("-inf")


# --------------------------------------------------------------------------
# in_window_population -- must be the exact G4 population, not a re-filter
# --------------------------------------------------------------------------

def test_in_window_population_matches_g4_windows_exactly(monkeypatch):
    df = pop_df([
        trade_row(symbol="AAA", day="2026-01-05"),
        trade_row(symbol="BBB", day="2026-01-05"),
        trade_row(symbol="CCC", day="2025-01-01"),      # before the plan edge
    ])
    df.loc[df["symbol"] == "BBB", "t1_why"] = "NO_TRIGGER"   # not OK

    from datetime import date
    got = H.in_window_population(df, date(2026, 1, 1), date(2030, 1, 1))
    assert sorted(got["symbol"]) == ["AAA"]


# --------------------------------------------------------------------------
# G5 -- the sign-equivalence this module's docstring is built to get right
# --------------------------------------------------------------------------

def _bar_end():
    _, t = G4.bar_bounds(DAY, TRIGGER_SEC)
    return t


def test_g5_reads_the_signal_in_the_trades_own_frame():
    """Long, bid-heavy book, mid goes UP -> correctly favourable -> 'right'.
    Short, ASK-heavy book, mid goes DOWN -> also correctly favourable (a
    falling mid is what a short wants) -> also 'right'. A naive
    `i_s > 0` vs `raw m1 > m0` comparison would score the short case
    'wrong' (ask-heavy predicting a raw *rise* is backwards) -- this test
    fails under that version, which is the point."""
    t = _bar_end()
    long_df = qframe({
        t - timedelta(seconds=60): qrow(10.00, 10.02, 300, 100),   # bid-heavy, I=+0.5
        t + timedelta(seconds=5): qrow(10.04, 10.06, 300, 100),    # mid rises
    })
    short_df = qframe({
        t - timedelta(seconds=60): qrow(10.02, 10.04, 100, 300),   # ask-heavy, I=-0.5
        t + timedelta(seconds=5): qrow(9.97, 9.99, 100, 300),      # mid falls
    })
    pop = pop_df([
        trade_row(symbol="LONG", side=1),
        trade_row(symbol="SHORT", side=-1),
    ])
    wins = FakeWindows({("LONG", DAY): long_df, ("SHORT", DAY): short_df})
    g5 = H.g5_positive_control(pop, wins)
    assert g5["right"] == 2
    assert g5["wrong"] == 0


def test_g5_skips_a_missing_window():
    pop = pop_df([trade_row(symbol="NOPE")])
    g5 = H.g5_positive_control(pop, FakeWindows({}))
    assert g5["n"] == 0
    assert g5["skipped_no_window"] == 1
    assert g5["passes"] is False


def test_g5_skips_a_flat_mid():
    t = _bar_end()
    df = qframe({
        t - timedelta(seconds=60): qrow(10.00, 10.02, 300, 100),
        t + timedelta(seconds=5): qrow(10.00, 10.02, 300, 100),   # unchanged
    })
    pop = pop_df([trade_row(symbol="AAA", side=1)])
    g5 = H.g5_positive_control(pop, FakeWindows({("AAA", DAY): df}))
    assert g5["n"] == 0
    assert g5["skipped_flat_mid"] == 1


# --------------------------------------------------------------------------
# add_signal -- the bucket assignment (section 3.3)
# --------------------------------------------------------------------------

def test_add_signal_buckets_kept_discarded_flat_no_book():
    t = _bar_end()
    bid_heavy = qframe({t - timedelta(seconds=60): qrow(10.00, 10.02, 300, 100)})
    ask_heavy = qframe({t - timedelta(seconds=60): qrow(10.00, 10.02, 100, 300)})
    balanced = qframe({t - timedelta(seconds=60): qrow(10.00, 10.02, 100, 100)})

    pop = pop_df([
        trade_row(symbol="KEEPME", side=1),      # bid-heavy, long -> I_s > 0 -> KEPT
        trade_row(symbol="DUMPME", side=1),      # ask-heavy, long -> I_s < 0 -> DISCARDED
        trade_row(symbol="EVEN", side=1),        # balanced -> FLAT
        trade_row(symbol="MISSING", side=1),     # no window -> NO_BOOK
    ])
    wins = FakeWindows({("KEEPME", DAY): bid_heavy, ("DUMPME", DAY): ask_heavy,
                        ("EVEN", DAY): balanced})
    out = H.add_signal(pop, wins)
    b = dict(zip(out["symbol"], out["bucket"]))
    assert b["KEEPME"] == H.KEPT
    assert b["DUMPME"] == H.DISCARDED
    assert b["EVEN"] == H.FLAT
    assert b["MISSING"] == H.NO_BOOK


def test_add_signal_flips_sign_for_a_short():
    """The same ask-heavy book that DISCARDS a long must KEEP a short --
    I_s = -I, and a short wants the book leaning toward a fall."""
    t = _bar_end()
    ask_heavy = qframe({t - timedelta(seconds=60): qrow(10.00, 10.02, 100, 300)})
    pop = pop_df([trade_row(symbol="SHORT", side=-1)])
    out = H.add_signal(pop, FakeWindows({("SHORT", DAY): ask_heavy}))
    assert out.iloc[0]["bucket"] == H.KEPT
    assert out.iloc[0]["i_s"] > 0


# --------------------------------------------------------------------------
# section 4 -- the fill check
# --------------------------------------------------------------------------

def test_fill_check_flags_a_worse_long_and_a_worse_short():
    entry_t = datetime(2026, 1, 5, tzinfo=ET) + timedelta(seconds=TRIGGER_SEC + 10)
    entry_utc = entry_t.astimezone(UTC)
    long_df = qframe({entry_utc - timedelta(seconds=5):
                      qrow(10.03, 10.05, 100, 100)})    # ask 10.05 > modelled 10.00
    short_df = qframe({entry_utc - timedelta(seconds=5):
                       qrow(9.95, 9.97, 100, 100)})      # bid 9.95 < modelled 10.00
    pop = pop_df([
        trade_row(symbol="L", side=1, entry_px=10.00, entry_sec=TRIGGER_SEC + 10),
        trade_row(symbol="S", side=-1, entry_px=10.00, entry_sec=TRIGGER_SEC + 10),
    ])
    wins = FakeWindows({("L", DAY): long_df, ("S", DAY): short_df})
    fc = H.fill_check(pop, wins)
    assert fc["n"] == 2
    assert fc["median_diff"] > 0
    assert fc["understated"] is True


def test_fill_check_does_not_flag_a_better_fill():
    entry_t = datetime(2026, 1, 5, tzinfo=ET) + timedelta(seconds=TRIGGER_SEC + 10)
    entry_utc = entry_t.astimezone(UTC)
    long_df = qframe({entry_utc - timedelta(seconds=5):
                      qrow(9.97, 9.99, 100, 100)})       # ask 9.99 < modelled 10.00 -- better
    pop = pop_df([trade_row(symbol="L", side=1, entry_px=10.00,
                            entry_sec=TRIGGER_SEC + 10)])
    fc = H.fill_check(pop, FakeWindows({("L", DAY): long_df}))
    assert fc["median_diff"] < 0
    assert fc["understated"] is False


# --------------------------------------------------------------------------
# two_denominators -- sign agreement
# --------------------------------------------------------------------------

def test_two_denominators_agree_when_kept_beats_discarded_everywhere():
    d = pd.DataFrame({
        "symbol": ["A", "A", "B", "B"],
        "bucket": [H.KEPT, H.DISCARDED, H.KEPT, H.DISCARDED],
        "R_BASE": [0.5, -0.5, 0.3, -0.2],
    })
    out = H.two_denominators(d)
    assert out["sign_agree"] is True
    assert out["per_trade_delta"] > 0
    assert out["per_symday_delta"] > 0


def test_two_denominators_flags_a_refusal():
    """A small, high-mean KEPT book against a large, lower-mean DISCARDED
    book: per-trade favours KEPT (1.0 > 0.5) but per-symday favours
    DISCARDED (2.0/10 < 4.0/10, because DISCARDED's much bigger count wins
    on the shared-population denominator) -- the two denominators disagree
    in sign, exactly the H-N1-style refusal `docs/research/REGISTERED_10sec.md`
    section 5.2.3 exists to catch."""
    d = pd.DataFrame({
        "symbol": ["A"] * 10,
        "bucket": [H.KEPT] * 2 + [H.DISCARDED] * 8,
        "R_BASE": [1.0, 1.0] + [0.5] * 8,
    })
    out = H.two_denominators(d)
    assert out["per_trade_delta"] > 0
    assert out["per_symday_delta"] < 0
    assert out["sign_agree"] is False
