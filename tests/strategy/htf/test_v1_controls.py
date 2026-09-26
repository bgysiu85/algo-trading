"""Tests for strategy/htf/v1_controls.py (C1 MACD-cross-alone, C2 re-export,
C3 random entries matched to v1). W15-0011.

C1 and C3 are exercised at INTEGRATION level against the same synthetic
archive test_v1_runner.py/test_v1_preflight.py already use -- there is no
new entry-detection or exit code in this module to unit-test in isolation
(module docstring: both are fixed kwargs into the existing v1 engine).
C2's own detect_c2/simulate_c2 internals are already covered by
test_controls.py; here we only check the re-export is the same object, so a
future edit that swaps it for a v1-flavoured copy is caught."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.htf import controls as CT
from strategy.htf import preflight as P
from strategy.htf import v1_controls as V1C
from strategy.htf import v1_exits as V1E
from strategy.htf import v1_preflight as V1P
from strategy.htf import v1_runner as V1R


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


class TestRunC1:
    def test_c1_never_carries_a_curl_route_entry(self, archive_df_1h, q_h_q_e):
        """C1 is cross-alone -- v1_preflight._entry_record tags each entry's
        own 'route', so a curl-tagged entry here would mean curl_enabled
        was not actually threaded through."""
        q_h, q_e = q_h_q_e
        _, counts = V1C.run_c1(archive_df_1h, scenario="B", q_h=q_h, q_e=q_e)
        assert counts["triggers_curl"] == 0
        assert counts["curl_failing_t"] == 0

    def test_c1_takes_at_least_as_many_cross_triggers_as_full_v1(self, archive_df_1h, q_h_q_e):
        """With F1/F2 both off, C1 blocks strictly fewer (never more)
        cross-route candidates than v1 itself does on the same cross
        triggers -- an equal-or-greater entry count on the cross route
        alone is the observable signature of the filters actually being
        disabled, not silently still active."""
        q_h, q_e = q_h_q_e
        _, counts_v1 = V1R.run_v1(archive_df_1h, scenario="B", q_h=q_h, q_e=q_e)
        _, counts_c1 = V1C.run_c1(archive_df_1h, scenario="B", q_h=q_h, q_e=q_e)
        assert counts_c1["triggers_cross"] == counts_v1["triggers_cross"]
        assert counts_c1["blocked_f1"] == 0 and counts_c1["blocked_f2"] == 0

    def test_c1_exit_reasons_are_v1s_own_including_signal_exits(self, archive_df_1h, q_h_q_e):
        """Sec 3: C1 uses 'v1's exits S1/S2/X1/X2' -- not v0's plain S1/S2,
        so C1's own trades must be able to carry an x1/x2 exit reason."""
        q_h, q_e = q_h_q_e
        trades, _ = V1C.run_c1(archive_df_1h, scenario="B", q_h=q_h, q_e=q_e)
        assert all(t.exit_reason in V1E.REASONS for t in trades)


class TestRunC2:
    def test_c2_is_v0s_own_unchanged(self):
        assert V1C.run_c2 is CT.run_c2


class TestRunC3:
    def test_matches_v1_trades_count_and_direction_mix(self, archive_df_1h, q_h_q_e):
        q_h, q_e = q_h_q_e
        v1_trades, _ = V1R.run_v1(archive_df_1h, scenario="B", q_h=q_h, q_e=q_e)
        result = V1C.run_c3(archive_df_1h, scenario="B", v1_trades=v1_trades, n_draws=20,
                            seed_prefix="test-")
        assert result["n_trades_per_draw"] == len(v1_trades)
        assert result["p5"] <= result["p50"] <= result["p95"]

    def test_same_seed_prefix_gives_reproducible_percentiles(self, archive_df_1h, q_h_q_e):
        q_h, q_e = q_h_q_e
        v1_trades, _ = V1R.run_v1(archive_df_1h, scenario="B", q_h=q_h, q_e=q_e)
        r1 = V1C.run_c3(archive_df_1h, scenario="B", v1_trades=v1_trades, n_draws=15,
                        seed_prefix="fixed-")
        r2 = V1C.run_c3(archive_df_1h, scenario="B", v1_trades=v1_trades, n_draws=15,
                        seed_prefix="fixed-")
        assert r1["p50"] == r2["p50"]
        assert np.array_equal(r1["nets"], r2["nets"], equal_nan=True)

    def test_zero_trades_draws_zero_net_every_time_not_a_crash(self, archive_df_1h):
        """An empty v1_trades list is a real (if degenerate) input -- 0
        directions means every draw places 0 trades, so every draw's net is
        the empty sum (0.0), not a crash and not NaN (nothing in the walk
        ever divides by n_trades_per_draw)."""
        result = V1C.run_c3(archive_df_1h, scenario="B", v1_trades=[], n_draws=5)
        assert result["n_trades_per_draw"] == 0
        assert result["p50"] == 0.0
        assert not np.isnan(result["nets"]).any()
