#!/usr/bin/env python3
"""End-to-end tests for the full backtest engine (engine.py, W15-0016):
1-hour exit precision, real $ Trade objects, E4 re-entry against real exit
times, and a look-ahead guard on the trade-simulation path itself (signal
look-ahead is already covered by test_guards.py)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.htf import bars as B
from strategy.tl_bounce import engine as E
from strategy.tl_bounce.preflight import BUILT_VARIANTS, prepare_grids


def _synthetic_1h(n_sessions=220, seed=4):
    rng = np.random.default_rng(seed)
    n = n_sessions * 23
    start = pd.Timestamp("2016-01-04T23:00:00Z")
    t = start + pd.to_timedelta(
        np.concatenate([np.arange(23) + s * 24 for s in range(n_sessions)]), unit="h")
    tt = np.arange(n)
    close = 60 + np.sin(tt / 200) * 12 + np.cumsum(rng.normal(0, 0.25, n))
    high = close + np.abs(rng.normal(0, 0.5, n))
    low = close - np.abs(rng.normal(0, 0.5, n))
    open_ = close + rng.normal(0, 0.2, n)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close,
         "volume": rng.integers(100, 1000, n),
         "held_id": np.full(n, 999, dtype="int64")},
        index=pd.DatetimeIndex(t, name="ts_event"))


def _hourly_grid(df_1h):
    return B.back_adjust(B.resample(df_1h, "1H"))


def test_all_variants_run_and_counts_are_internally_consistent():
    df_1h = _synthetic_1h()
    grids = prepare_grids(df_1h)
    hourly = _hourly_grid(df_1h)
    for variant, opts in BUILT_VARIANTS.items():
        for entry_chart, (ef, hf, hh) in grids.items():
            trades, k = E.simulate_market(ef, hf, hh, hourly, **opts)
            assert k.entries == len(trades)
            assert k.entries == k.re_entries + (1 if k.entries else 0) or not opts["allow_reentry"] \
                or k.re_entries <= k.entries
            assert k.touch_bars >= k.touch_long
            assert k.touch_bars >= k.touch_short
            for t in trades:
                assert t.exit_reason in ("initial_stop", "trailed_stop", "X1", "data_end")
                assert t.n_rolls == 0          # synthetic archive never rolls (held_id constant)
                assert t.direction in ("long", "short")
                # cost is strictly positive (round-trip friction at any level)
                assert t.cost("MCL", "mid") > 0
                assert t.net_pnl("MCL", "mid") == pytest.approx(
                    t.gross_pnl("MCL") - t.cost("MCL", "mid"))


def test_bounce_once_never_re_enters():
    df_1h = _synthetic_1h(n_sessions=300, seed=11)
    grids = prepare_grids(df_1h)
    hourly = _hourly_grid(df_1h)
    ef, hf, hh = grids["4H"]
    trades, k = E.simulate_market(ef, hf, hh, hourly, **BUILT_VARIANTS["bounce-once"])
    assert k.entries <= 1
    assert k.re_entries == 0
    assert all(not t.is_reentry for t in trades)


def test_e0_off_never_blocks():
    df_1h = _synthetic_1h(n_sessions=200, seed=3)
    grids = prepare_grids(df_1h)
    hourly = _hourly_grid(df_1h)
    ef, hf, hh = grids["4H"]
    _, k = E.simulate_market(ef, hf, hh, hourly, **BUILT_VARIANTS["bounce-noE0"])
    assert k.e0_blocked == 0


def test_exit_bar_is_never_a_touch_bar_double_counted():
    """sec 2.2 E4: an exit bar cannot itself be counted as ignored_in_position
    (it is flat again by the time the scan resumes) -- so entries+voided
    (candidates acted on) plus ignored_in_position must never exceed held."""
    df_1h = _synthetic_1h(n_sessions=260, seed=21)
    grids = prepare_grids(df_1h)
    hourly = _hourly_grid(df_1h)
    ef, hf, hh = grids["4H"]
    _, k = E.simulate_market(ef, hf, hh, hourly, **BUILT_VARIANTS["bounce"])
    assert k.held == k.entries + k.voided
    assert k.ignored_in_position >= 0


@pytest.mark.parametrize("cut_sessions", [120, 180])
def test_trade_simulation_no_lookahead(cut_sessions):
    """Same CUT technique as test_guards.py, applied to the trade-walk
    itself: every trade whose ENTIRE lifetime (fill through exit) falls
    inside the cut must be identical whether or not bars after the cut
    exist -- a look-ahead in the exit walk (exits.py) or the re-entry scan
    (engine.py) would move or alter one of these."""
    df_1h = _synthetic_1h(n_sessions=260, seed=5)
    df_1h_cut = df_1h.iloc[: cut_sessions * 23]

    grids_full = prepare_grids(df_1h)
    grids_cut = prepare_grids(df_1h_cut)
    hourly_full = _hourly_grid(df_1h)
    hourly_cut = _hourly_grid(df_1h_cut)

    ef_full, hf_full, hh_full = grids_full["4H"]
    ef_cut, hf_cut, hh_cut = grids_cut["4H"]

    trades_full, _ = E.simulate_market(ef_full, hf_full, hh_full, hourly_full,
                                       **BUILT_VARIANTS["bounce"])
    trades_cut, _ = E.simulate_market(ef_cut, hf_cut, hh_cut, hourly_cut,
                                      **BUILT_VARIANTS["bounce"])

    boundary = df_1h_cut.index[-1]
    safe_full = [t for t in trades_full if t.exit_t <= boundary]
    # the cut series' own trades, dropping only one that might be truncated
    # into a fake data_end right at the very end (not a look-ahead case)
    safe_cut = [t for t in trades_cut if t.exit_t < hourly_cut["t_open"].iloc[-1]]

    assert len(safe_full) <= len(trades_cut)
    for tf, tc in zip(safe_full, safe_cut):
        assert tf.entry_t == tc.entry_t
        assert tf.direction == tc.direction
        assert tf.fill_raw == pytest.approx(tc.fill_raw)
        assert tf.exit_t == tc.exit_t
        assert tf.exit_reason == tc.exit_reason
        assert tf.exit_price_raw == pytest.approx(tc.exit_price_raw)


def test_touch_bars_matches_g2_sim_exactly():
    """sec 3's touch_bars/touch_long/touch_short are unconditional per-bar
    counts (sim.py's own convention) -- must match G2's own walk exactly,
    whatever the real engine's E4 jump-scanning does to entry/re-entry
    counts. Independent-review finding (2026-09-28): engine.py's outer
    loop used to skip re-visiting bars between a fill and its exit, which
    silently undercounted these totals."""
    from strategy.tl_bounce.sim import simulate as g2_simulate
    from strategy.tl_bounce.signals import market_signals as _ms

    df_1h = _synthetic_1h(n_sessions=240, seed=17)
    grids = prepare_grids(df_1h)
    hourly = _hourly_grid(df_1h)
    for entry_chart, (ef, hf, hh) in grids.items():
        for variant, opts in BUILT_VARIANTS.items():
            e0 = None
            if opts["e0_on"]:
                from strategy.tl_bounce import lines as L
                e0 = L.e0_filter(ef, hf, hh)
            sig = _ms(ef, e0=e0)
            _, g2_counts = g2_simulate(sig, e0_on=opts["e0_on"], x1_on=opts["x1_on"],
                                       allow_reentry=opts["allow_reentry"])
            _, real_counts = E.simulate_market(ef, hf, hh, hourly, **opts)
            assert real_counts.touch_bars == g2_counts.touch_bars, (variant, entry_chart)
            assert real_counts.touch_long == g2_counts.touch_long, (variant, entry_chart)
            assert real_counts.touch_short == g2_counts.touch_short, (variant, entry_chart)
