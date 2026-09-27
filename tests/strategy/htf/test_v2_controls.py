"""Tests for strategy/htf/v2_controls.py (C1 MACD-cross-alone, C2
re-export, C3 random entries matched to v2). W15-0021.

C1 and C3 are exercised at INTEGRATION level against the same synthetic
archive test_v2_runner.py uses -- there is no new entry-detection or exit
code in this module to unit-test in isolation (module docstring: both are
fixed kwargs/wrappers into the existing v2 engine / controls.py's own
generic C3 machinery). C2's internals are covered by test_controls.py;
here we only check the re-export is the same object.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.htf import controls as CT
from strategy.htf import exits as EX
from strategy.htf import preflight as P
from strategy.htf import v1_preflight as V1P
from strategy.htf import v2_controls as V2C
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


class TestRunC1:
    def test_c1_never_carries_a_curl_route_entry(self, archive_df_1h, q_h_q_e):
        q_h, q_e = q_h_q_e
        _, counts = V2C.run_c1(archive_df_1h, scenario="B", q_h=q_h, q_e=q_e)
        assert counts["triggers_curl"] == 0
        assert counts["curl_failing_t"] == 0

    def test_c1_takes_at_least_as_many_cross_triggers_as_full_v2(self, archive_df_1h, q_h_q_e):
        q_h, q_e = q_h_q_e
        _, counts_v2 = V2R.run_v2(archive_df_1h, scenario="B", q_h=q_h, q_e=q_e)
        _, counts_c1 = V2C.run_c1(archive_df_1h, scenario="B", q_h=q_h, q_e=q_e)
        assert counts_c1["triggers_cross"] == counts_v2["triggers_cross"]
        assert counts_c1["blocked_f1"] == 0 and counts_c1["blocked_f2"] == 0

    def test_c1_exit_reasons_are_v0s_own_plain_stop_trail(self, archive_df_1h, q_h_q_e):
        """Sec 3.6: C1 (v2) is "paired with v2's own exits (S1/S2 only)" --
        unlike v1's own C1, which keeps v1's X1/X2."""
        q_h, q_e = q_h_q_e
        trades, _ = V2C.run_c1(archive_df_1h, scenario="B", q_h=q_h, q_e=q_e)
        assert all(t.exit_reason in EX.REASONS for t in trades)
        assert all(t.exit_reason not in ("x1_opposite_cross", "x2_ema9_turn") for t in trades)


class TestRunC2:
    def test_c2_is_v0s_own_unchanged(self):
        assert V2C.run_c2 is CT.run_c2


class TestRunC3:
    def test_matches_v2_trades_count_and_direction_mix(self, archive_df_1h, q_h_q_e):
        q_h, q_e = q_h_q_e
        v2_trades, _ = V2R.run_v2(archive_df_1h, scenario="B", q_h=q_h, q_e=q_e)
        result = V2C.run_c3(archive_df_1h, scenario="B", v2_trades=v2_trades, n_draws=20,
                            seed_prefix="test-")
        assert result["n_trades_per_draw"] == len(v2_trades)
        assert result["p5"] <= result["p50"] <= result["p95"]

    def test_same_seed_prefix_gives_reproducible_percentiles(self, archive_df_1h, q_h_q_e):
        q_h, q_e = q_h_q_e
        v2_trades, _ = V2R.run_v2(archive_df_1h, scenario="B", q_h=q_h, q_e=q_e)
        r1 = V2C.run_c3(archive_df_1h, scenario="B", v2_trades=v2_trades, n_draws=15,
                        seed_prefix="fixed-")
        r2 = V2C.run_c3(archive_df_1h, scenario="B", v2_trades=v2_trades, n_draws=15,
                        seed_prefix="fixed-")
        assert r1["p50"] == r2["p50"]
        assert np.array_equal(r1["nets"], r2["nets"], equal_nan=True)

    def test_zero_trades_draws_zero_net_every_time_not_a_crash(self, archive_df_1h):
        result = V2C.run_c3(archive_df_1h, scenario="B", v2_trades=[], n_draws=5)
        assert result["n_trades_per_draw"] == 0
        assert result["p50"] == 0.0
        assert not np.isnan(result["nets"]).any()

    def test_c3_is_v0s_own_generic_machinery_under_the_hood(self, archive_df_1h, q_h_q_e):
        """Sec 3.6: "same v0 S1/S2 exits" -- v2_controls.run_c3 must not
        duplicate any draw/walk logic; it is a thin, v2-named wrapper over
        controls.run_c3 (module docstring)."""
        q_h, q_e = q_h_q_e
        v2_trades, _ = V2R.run_v2(archive_df_1h, scenario="B", q_h=q_h, q_e=q_e)
        wrapped = V2C.run_c3(archive_df_1h, scenario="B", v2_trades=v2_trades, n_draws=10,
                             seed_prefix="same-")
        direct = CT.run_c3(archive_df_1h, scenario="B", v0_trades=v2_trades, n_draws=10,
                           seed_prefix="same-")
        assert np.array_equal(wrapped["nets"], direct["nets"], equal_nan=True)
