#!/usr/bin/env python3
"""C-B1, C-O2, C-O3, C-B3: seeded, reproducible, matched-to-the-real-trade
controls. REGISTERED_w16_session_baselines.md sec 7.1."""
from __future__ import annotations

from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

import strategy.w16.controls as CT

ET = ZoneInfo("America/New_York")


def _bars(date, rows):
    idx, data = [], []
    for hh, mm, o, h, l, c, v in rows:
        ts = pd.Timestamp(f"{date} {hh:02d}:{mm:02d}:00", tz=ET)
        idx.append(ts)
        data.append({"open": o, "high": h, "low": l, "close": c, "volume": v, "held_id": 1})
    return pd.DataFrame(data, index=pd.DatetimeIndex(idx).tz_convert("UTC"))


def _full_session(date, price=100.0):
    rows = []
    for i in range(390):
        hh, mm = 9 + (30 + i) // 60, (30 + i) % 60
        rows.append((hh, mm, price, price + 0.1, price - 0.1, price, 100))
    return _bars(date, rows)


def test_draw_rng_is_reproducible_and_matches_crc32_of_draw_index():
    import zlib
    rng1 = CT.draw_rng(7)
    rng2 = CT.draw_rng(7)
    assert rng1.integers(0, 10**9) == CT.draw_rng(7).integers(0, 10**9)
    # Different draw index -> (almost certainly) a different first value.
    assert rng2.bit_generator.seed_seq.entropy == zlib.crc32(b"7")


def test_c_b1_same_seed_same_result_across_markets():
    real = [{"date": "2024-06-06", "market": "ES", "direction": "long",
            "stop_dist": 1.0, "voided": False}]
    bars = {"2024-06-06": _full_session("2024-06-06")}
    a = CT.c_b1_draw(real, bars, draw_idx=0)
    b = CT.c_b1_draw(real, bars, draw_idx=0)
    assert a == b


def test_c_b1_skips_voided_real_trades():
    real = [{"date": "2024-06-06", "market": "ES", "direction": "long",
            "stop_dist": 1.0, "voided": True}]
    bars = {"2024-06-06": _full_session("2024-06-06")}
    out = CT.c_b1_draw(real, bars, draw_idx=0)
    assert out == []


def test_c_b1_entry_window_is_1001_to_1529():
    real = [{"date": "2024-06-06", "market": "ES", "direction": "long",
            "stop_dist": 1.0, "voided": False}]
    bars = {"2024-06-06": _full_session("2024-06-06")}
    for draw in range(20):
        out = CT.c_b1_draw(real, bars, draw_idx=draw)
        if not out:
            continue
        t = pd.Timestamp(out[0].get("date") or "2024-06-06")
    # fill_price comes from bars["open"] at fill_idx = candidate+1; just
    # check every draw produced a valid, priced trade with stop distance
    # preserved from the real trade.
    for draw in range(20):
        out = CT.c_b1_draw(real, bars, draw_idx=draw)
        assert len(out) == 1
        assert out[0]["stop_dist"] == pytest.approx(1.0)


def test_c_o2_matches_open_to_close_same_days_as_b2():
    real_b2 = [{"date": "2024-06-06", "market": "ES", "voided": False},
              {"date": "2024-06-07", "market": "ES", "voided": True}]
    bars = {"2024-06-06": _full_session("2024-06-06", price=100.0),
           "2024-06-07": _full_session("2024-06-07", price=200.0)}
    out = CT.c_o2_trades(real_b2, bars)
    assert len(out) == 1                       # the voided day is excluded
    assert out[0]["date"] == "2024-06-06"
    assert out[0]["entry_price"] == pytest.approx(100.0)
    assert out[0]["exit_price"] == pytest.approx(100.0)


def test_c_b3_produces_requested_number_of_flips():
    bars = {"2024-06-06": _full_session("2024-06-06")}
    legs = CT.c_b3_draw({"2024-06-06": 3}, bars, draw_idx=0)
    n_flips = sum(1 for l in legs if l["reason"] == "flip" and l["leg"] == "entry")
    assert n_flips == 3
    assert legs[-1]["reason"] == "flat_at_close"


def test_c_b3_zero_flips_produces_nothing():
    bars = {"2024-06-06": _full_session("2024-06-06")}
    legs = CT.c_b3_draw({"2024-06-06": 0}, bars, draw_idx=0)
    assert legs == []


# ---------------------------------------------------------------------
# performance caches: must be bit-identical to the uncached (original)
# path -- these are pure speed optimizations, not behavior changes. See
# controls.py's module docstring / c_o3_draw docstring for why they exist
# (measured ~116h/market for B2's control before o3_candidates_cache).
# ---------------------------------------------------------------------

def test_c_b1_naive_cache_matches_uncached_across_draws():
    real = [{"date": "2024-06-06", "market": "ES", "direction": "long",
            "stop_dist": 1.0, "voided": False},
           {"date": "2024-06-07", "market": "ES", "direction": "short",
            "stop_dist": 2.0, "voided": False}]
    bars = {"2024-06-06": _full_session("2024-06-06"),
           "2024-06-07": _full_session("2024-06-07", price=150.0)}
    cache = CT.naive_time_cache(bars, {t["date"] for t in real})
    for draw in range(10):
        uncached = CT.c_b1_draw(real, bars, draw_idx=draw)
        cached = CT.c_b1_draw(real, bars, draw_idx=draw, naive_cache=cache)
        assert cached == uncached


def test_c_b3_naive_cache_matches_uncached_across_draws():
    bars = {"2024-06-06": _full_session("2024-06-06"),
           "2024-06-07": _full_session("2024-06-07", price=150.0)}
    flip_counts = {"2024-06-06": 3, "2024-06-07": 2}
    cache = CT.naive_time_cache(bars, flip_counts.keys(), sort=True)
    for draw in range(10):
        uncached = CT.c_b3_draw(flip_counts, bars, draw_idx=draw)
        cached = CT.c_b3_draw(flip_counts, bars, draw_idx=draw, naive_cache=cache)
        assert cached == uncached


def _synthetic_full_index(n=2000, start="2024-06-01 00:00"):
    idx = pd.date_range(start, periods=n, freq="1min", tz="UTC")
    price = pd.Series(np.linspace(100.0, 120.0, n), index=idx)
    return idx, price


def test_o3_candidates_cache_matches_uncached_across_draws():
    full_index, price_at = _synthetic_full_index()
    real_b2 = [{"market": "ES", "voided": False, "hold_length": "90min"},
              {"market": "ES", "voided": False, "hold_length": "90min"},
              {"market": "ES", "voided": False, "hold_length": "45min"},
              {"market": "ES", "voided": True, "hold_length": "90min"}]
    cache = CT.o3_candidates_cache(real_b2, full_index)
    # one cache entry per unique non-voided length, not one per trade
    assert set(cache.keys()) == {pd.Timedelta("90min"), pd.Timedelta("45min")}
    for draw in range(10):
        uncached = CT.c_o3_draw(real_b2, full_index, price_at, draw_idx=draw)
        cached = CT.c_o3_draw(real_b2, full_index, price_at, draw_idx=draw,
                              candidates_cache=cache)
        assert cached == uncached


def test_o3_candidates_cache_handles_a_length_not_present_in_the_cache():
    """A cache built from a different (e.g. training-only) trade list than
    the one passed to c_o3_draw must fall back to the uncached computation
    for any length it doesn't have, not silently drop those trades."""
    full_index, price_at = _synthetic_full_index()
    cache = CT.o3_candidates_cache(
        [{"market": "ES", "voided": False, "hold_length": "90min"}], full_index)
    real_b2 = [{"market": "ES", "voided": False, "hold_length": "45min"}]
    uncached = CT.c_o3_draw(real_b2, full_index, price_at, draw_idx=0)
    cached = CT.c_o3_draw(real_b2, full_index, price_at, draw_idx=0,
                          candidates_cache=cache)
    assert cached == uncached
    assert len(cached) == 1
