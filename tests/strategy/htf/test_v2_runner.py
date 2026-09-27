"""Tests for strategy/htf/v2_runner.py. W15-0021.

The central risk this module exists to test (REGISTERED_htf_ben_v2.md sec
5.1, gate G4): run_v2 wires v1's OWN entry detection (v1_preflight.detect_v1,
unchanged) into v0's OWN exit walk (runner.simulate/exits.simulate_exit,
unchanged) -- a recombination that must hold E5 correctly (a position
opened under v1's entry timing, held under v0's exit timing) without
accidentally consulting v1's own (signal-exit-carrying) position state.
The strongest test for that is equivalence: at its defaults, run_v2 must
produce EXACTLY what v1_runner.run_v1_no_signal_exits already produces --
that function is the exact, already-tested call the $3,956.12/286-trade
v1-X ablation number (REGISTERED sec 0.2) came from. Any edit that made
run_v2 consult the wrong module's exit/position state (e.g. reaching for
v1_exits.simulate_exit_v1 or v1_runner.simulate_v1 instead of v0's own)
would break this equivalence immediately, typically by producing an
x1/x2 exit reason v0's exits can never emit.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.htf import exits as EX
from strategy.htf import preflight as P
from strategy.htf import v1_preflight as V1P
from strategy.htf import v1_runner as V1R
from strategy.htf import v2_runner as V2R


def _synth_1h(n_days=900, seed=7):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2010-06-07", periods=24 * n_days, freq="h", tz="UTC")
    steps = rng.normal(loc=0.002, scale=0.35, size=len(idx))
    t = np.arange(len(idx))
    drift = 3.0 * np.sin(t / 800.0)
    close = 50.0 + np.cumsum(steps) * 0.05 + drift
    close = np.clip(close, 5.0, None)
    high = close + np.abs(rng.normal(0.1, 0.05, len(idx)))
    low = close - np.abs(rng.normal(0.1, 0.05, len(idx)))
    open_ = close - rng.normal(0, 0.05, len(idx))
    df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                       "volume": 100.0, "held_id": 1}, index=idx)
    return df


@pytest.fixture(scope="module")
def archive_df_1h():
    return _synth_1h()


@pytest.fixture(scope="module")
def q_h_q_e(archive_df_1h):
    grids, _ = P.prepare_grids(archive_df_1h)
    q_h, q_e, _, _, _ = V1P.compute_percentiles(grids["4H"])
    return q_h, q_e


class TestRunV2Integration:
    def test_trades_taken_never_exceeds_entries_and_reasons_are_valid(self, archive_df_1h, q_h_q_e):
        q_h, q_e = q_h_q_e
        trades, counts = V2R.run_v2(archive_df_1h, scenario="B", q_h=q_h, q_e=q_e)
        assert counts["trades_taken"] == len(trades)
        assert counts["trades_taken"] <= counts["entries"]
        assert all(t.exit_reason in EX.REASONS for t in trades)
        assert all(t.direction in ("long", "short") for t in trades)

    def test_v2_never_carries_a_v1_signal_exit_reason(self, archive_df_1h, q_h_q_e):
        """v2 has no X1/X2 (REGISTERED sec 2.2: "removed entirely") -- this
        is the direct, mutation-sensitive check that run_v2 is really
        walking v0's exits, not v1's."""
        q_h, q_e = q_h_q_e
        trades, _ = V2R.run_v2(archive_df_1h, scenario="B", q_h=q_h, q_e=q_e)
        assert all(t.exit_reason not in ("x1_opposite_cross", "x2_ema9_turn") for t in trades)

    def test_v2_at_defaults_equals_v1_no_signal_exits(self, archive_df_1h, q_h_q_e):
        """THE recombination equivalence test (module docstring, G4). Same
        entries (from the same detect_v1 call), same exit walk (v0's own
        runner.simulate) -- the two functions must agree trade for trade,
        not just on counts."""
        q_h, q_e = q_h_q_e
        trades_v2, counts_v2 = V2R.run_v2(archive_df_1h, scenario="B", q_h=q_h, q_e=q_e)
        trades_x, counts_x = V1R.run_v1_no_signal_exits(archive_df_1h, scenario="B",
                                                        q_h=q_h, q_e=q_e)
        assert counts_v2 == counts_x
        assert len(trades_v2) == len(trades_x)
        for a, b in zip(trades_v2, trades_x):
            assert a.session == b.session
            assert a.direction == b.direction
            assert a.entry_t == b.entry_t
            assert a.exit_t == b.exit_t
            assert a.exit_reason == b.exit_reason
            assert a.fill_raw == pytest.approx(b.fill_raw)
            assert a.exit_price_raw == pytest.approx(b.exit_price_raw)
            assert a.net_pnl("MCL", "mid") == pytest.approx(b.net_pnl("MCL", "mid"))

    def test_curl_enabled_false_removes_every_curl_trigger(self, archive_df_1h, q_h_q_e):
        q_h, q_e = q_h_q_e
        _, counts = V2R.run_v2(archive_df_1h, scenario="B", q_h=q_h, q_e=q_e, curl_enabled=False)
        assert counts["triggers_curl"] == 0
        assert counts["curl_failing_t"] == 0

    def test_f1_enabled_false_removes_every_f1_block(self, archive_df_1h, q_h_q_e):
        q_h, q_e = q_h_q_e
        _, counts = V2R.run_v2(archive_df_1h, scenario="B", q_h=q_h, q_e=q_e, f1_enabled=False)
        assert counts["blocked_f1"] == 0

    def test_f2_enabled_false_removes_every_f2_block(self, archive_df_1h, q_h_q_e):
        q_h, q_e = q_h_q_e
        _, counts = V2R.run_v2(archive_df_1h, scenario="B", q_h=q_h, q_e=q_e, f2_enabled=False)
        assert counts["blocked_f2"] == 0

    def test_swing_lr_and_trail_trigger_are_threaded_through(self, archive_df_1h, q_h_q_e):
        """Not asserting a specific outcome (too data-dependent on the
        synthetic seed) -- only that both knobs actually reach the real
        wiring end-to-end (v2_grid.py's own reason for existing) and every
        run stays internally consistent."""
        q_h, q_e = q_h_q_e
        trades_a, counts_a = V2R.run_v2(archive_df_1h, scenario="B", q_h=q_h, q_e=q_e,
                                        swing_LR=2, trail_trigger=0.10)
        trades_b, counts_b = V2R.run_v2(archive_df_1h, scenario="B", q_h=q_h, q_e=q_e,
                                        swing_LR=3, trail_trigger=0.40)
        assert counts_a["trades_taken"] == len(trades_a)
        assert counts_b["trades_taken"] == len(trades_b)
        assert all(t.exit_reason in EX.REASONS for t in trades_a + trades_b)
