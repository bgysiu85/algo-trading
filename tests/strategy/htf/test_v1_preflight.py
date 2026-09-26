"""Tests for strategy/htf/v1_preflight.py (G2, no P&L). W15-0011."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.htf import preflight as P
from strategy.htf import v1_lines as V1L
from strategy.htf import v1_preflight as V1P
from strategy.htf import v1_signals as V1S


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
def grids_and_daily():
    df_1h = _synth_1h()
    return P.prepare_grids(df_1h)


@pytest.fixture(scope="module")
def percentiles(grids_and_daily):
    grids, _ = grids_and_daily
    four_h_adj = grids["4H"]
    return V1P.compute_percentiles(four_h_adj)


class TestTrainingMask4h:
    def test_mask_matches_the_registered_training_window(self, grids_and_daily):
        grids, _ = grids_and_daily
        four_h_adj = grids["4H"]
        mask = V1P.training_mask_4h(four_h_adj)
        sessions = pd.Series(four_h_adj["session"])
        expected = (sessions >= V1P.TRAIN_START) & (sessions <= V1P.TRAIN_END)
        assert mask.tolist() == expected.tolist()


class TestComputePercentiles:
    def test_percentiles_are_finite_and_between_zero_and_the_max_ratio(self, percentiles):
        q_h, q_e, ratio_h, ratio_e, atr = percentiles
        assert np.isfinite(q_h)
        assert np.isfinite(q_e)
        finite_h = ratio_h[np.isfinite(ratio_h)]
        finite_e = ratio_e[np.isfinite(ratio_e)]
        assert 0 <= q_h <= finite_h.max()
        assert 0 <= q_e <= finite_e.max()

    def test_percentile_is_computed_only_over_training_side_bars(self, grids_and_daily):
        """Blowing up ratios strictly in the holdout tail (post-2021) must
        not move q_h/q_e -- sec 5.2/G4: percentiles computed on training
        bars only."""
        grids, _ = grids_and_daily
        four_h_adj = grids["4H"].copy()
        q_h_before, q_e_before, _, _, _ = V1P.compute_percentiles(four_h_adj)

        mutated = four_h_adj.copy()
        holdout_mask = ~V1P.training_mask_4h(mutated)
        mutated.loc[holdout_mask, ["high_adj", "low_adj", "close_adj"]] *= 5
        q_h_after, q_e_after, _, _, _ = V1P.compute_percentiles(mutated)

        assert q_h_before == pytest.approx(q_h_after)
        assert q_e_before == pytest.approx(q_e_after)


class TestDetectV1Invariants:
    @pytest.mark.parametrize("scenario", list(V1P.SCENARIOS))
    def test_counts_partition_every_trigger(self, grids_and_daily, percentiles, scenario):
        grids, daily_adj = grids_and_daily
        q_h, q_e, ratio_h, ratio_e, atr = percentiles
        entry_adj = grids[P.SCENARIO_GRID[scenario]]
        four_h_adj = grids["4H"]
        entries, counts = V1P.detect_v1(entry_adj, daily_adj, four_h_adj, scenario=scenario,
                                        q_h=q_h, q_e=q_e, ratio_h=ratio_h, ratio_e=ratio_e)
        triggers = counts["triggers_cross"] + counts["triggers_curl"]
        accounted = (counts["curl_failing_t"] + counts["lapsed"] + counts["blocked_f1"]
                    + counts["blocked_f2"] + counts["blocked_e3"]
                    + counts["blocked_end_of_session"] + counts["voided"] + counts["entries"])
        assert accounted == triggers
        assert len(entries) == counts["entries"]

    @pytest.mark.parametrize("scenario", list(V1P.SCENARIOS))
    def test_entries_have_positive_stop_distance_and_a_route(self, grids_and_daily,
                                                              percentiles, scenario):
        grids, daily_adj = grids_and_daily
        q_h, q_e, ratio_h, ratio_e, atr = percentiles
        entry_adj = grids[P.SCENARIO_GRID[scenario]]
        four_h_adj = grids["4H"]
        entries, _ = V1P.detect_v1(entry_adj, daily_adj, four_h_adj, scenario=scenario,
                                   q_h=q_h, q_e=q_e, ratio_h=ratio_h, ratio_e=ratio_e)
        assert all(e["stop_dist"] > 0 for e in entries)
        assert all(e["route"] in ("cross", "curl") for e in entries)

    def test_curl_disabled_never_produces_curl_route_entries(self, grids_and_daily, percentiles):
        grids, daily_adj = grids_and_daily
        q_h, q_e, ratio_h, ratio_e, atr = percentiles
        entry_adj = grids["4H"]
        four_h_adj = grids["4H"]
        entries, counts = V1P.detect_v1(entry_adj, daily_adj, four_h_adj, scenario="B",
                                        q_h=q_h, q_e=q_e, ratio_h=ratio_h, ratio_e=ratio_e,
                                        curl_enabled=False)
        assert counts["triggers_curl"] == 0
        assert counts["curl_failing_t"] == 0
        assert all(e["route"] == "cross" for e in entries)

    def test_disabling_f1_never_loses_an_entry_v1_would_have_kept(self, grids_and_daily,
                                                                   percentiles):
        """Removing a filter can only ADD entries relative to the full
        rule set, never remove one v1 itself would have taken -- same
        subset logic as test_tl_variant.py's v0-TL-is-a-subset-of-v0 test,
        mirrored the other way (v1 is a subset of v1-F1-disabled)."""
        grids, daily_adj = grids_and_daily
        q_h, q_e, ratio_h, ratio_e, atr = percentiles
        entry_adj = grids["4H"]
        four_h_adj = grids["4H"]
        v1_entries, _ = V1P.detect_v1(entry_adj, daily_adj, four_h_adj, scenario="B",
                                      q_h=q_h, q_e=q_e, ratio_h=ratio_h, ratio_e=ratio_e)
        no_f1_entries, _ = V1P.detect_v1(entry_adj, daily_adj, four_h_adj, scenario="B",
                                         q_h=q_h, q_e=q_e, ratio_h=ratio_h, ratio_e=ratio_e,
                                         f1_enabled=False)
        no_f1_fills = {(e["t_open"], e["direction"]) for e in no_f1_entries}
        for e in v1_entries:
            assert (e["t_open"], e["direction"]) in no_f1_fills

    def test_disabling_f2_never_loses_an_entry_v1_would_have_kept(self, grids_and_daily,
                                                                   percentiles):
        grids, daily_adj = grids_and_daily
        q_h, q_e, ratio_h, ratio_e, atr = percentiles
        entry_adj = grids["4H"]
        four_h_adj = grids["4H"]
        v1_entries, _ = V1P.detect_v1(entry_adj, daily_adj, four_h_adj, scenario="B",
                                      q_h=q_h, q_e=q_e, ratio_h=ratio_h, ratio_e=ratio_e)
        no_f2_entries, _ = V1P.detect_v1(entry_adj, daily_adj, four_h_adj, scenario="B",
                                         q_h=q_h, q_e=q_e, ratio_h=ratio_h, ratio_e=ratio_e,
                                         f2_enabled=False)
        no_f2_fills = {(e["t_open"], e["direction"]) for e in no_f2_entries}
        for e in v1_entries:
            assert (e["t_open"], e["direction"]) in no_f2_fills

    def test_no_lookahead_a_bar_far_after_c_does_not_change_the_decision_at_c(self,
                                                                              grids_and_daily,
                                                                              percentiles):
        """G4-style guard: mutating price data strictly after a trigger's
        own confirmation bar must not change whether that trigger becomes
        an entry."""
        grids, daily_adj = grids_and_daily
        q_h, q_e, ratio_h, ratio_e, atr = percentiles
        entry_adj = grids["4H"]
        four_h_adj = grids["4H"]
        entries_before, _ = V1P.detect_v1(entry_adj, daily_adj, four_h_adj, scenario="B",
                                          q_h=q_h, q_e=q_e, ratio_h=ratio_h, ratio_e=ratio_e)

        mutated_entry = entry_adj.copy()
        mutated_four_h = four_h_adj.copy()
        n = len(entry_adj)
        tail = 30
        for df in (mutated_entry, mutated_four_h):
            df.loc[df.index[-tail:], ["high_adj", "low_adj", "close_adj", "open_adj"]] *= 3
        entries_after, _ = V1P.detect_v1(mutated_entry, daily_adj, mutated_four_h,
                                         scenario="B", q_h=q_h, q_e=q_e)

        cutoff = n - tail - max(V1P.CROSS_CONFIRM_WINDOW, max(V1P.T_OFFSETS)) - 10
        early_before = [e for e in entries_before
                        if pd.Timestamp(e["t_open"]) < entry_adj["t_open"].iloc[cutoff]]
        early_after = [e for e in entries_after
                      if pd.Timestamp(e["t_open"]) < entry_adj["t_open"].iloc[cutoff]]
        assert early_before == early_after


class TestStopRule:
    def test_below_min_is_underpowered(self):
        r = V1P.stop_rule(149)
        assert r["underpowered"]

    def test_at_min_is_not_underpowered(self):
        r = V1P.stop_rule(150)
        assert not r["underpowered"]
