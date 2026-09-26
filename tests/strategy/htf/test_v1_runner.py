"""Tests for strategy/htf/v1_runner.py. W15-0011.

TestSimulateV1NoSignal mirrors test_runner.py's own E5/roll tests almost
verbatim (same hand-built hourly frames), routed through v1_runner.simulate_v1
with a flat-price entry_adj so hist/EMA9 never cross -- X1/X2 stay silent
and the walk reduces to exactly v0's S1/S2/S4 behaviour, which is what these
tests check was not broken by threading the extra signal-exit machinery
through. TestRunV1Integration exercises the real wiring (run_v1,
run_v1_no_signal_exits) against the same large synthetic archive
test_v1_preflight.py already uses, to sanity-check X1/X2 actually fire in
practice and that v1-X's ledger never carries an x1/x2 exit reason.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.htf import costs as C
from strategy.htf import preflight as P
from strategy.htf import v1_exits as V1E
from strategy.htf import v1_preflight as V1P
from strategy.htf import v1_runner as V1R


def _hourly(rows):
    """rows: (session, bar, open, high, low, close, held_id, offset)."""
    idx = pd.date_range("2020-01-01", periods=len(rows), freq="h", tz="UTC")
    df = pd.DataFrame({
        "session": [r[0] for r in rows], "bar": [r[1] for r in rows],
        "open": [r[2] for r in rows], "high": [r[3] for r in rows],
        "low": [r[4] for r in rows], "close": [r[5] for r in rows],
        "held_id": [r[6] for r in rows], "adj_offset": [r[7] for r in rows],
    })
    for c in ("open", "high", "low", "close"):
        df[c + "_adj"] = df[c] + df["adj_offset"]
    df["t_open"] = idx
    return df


def _entry_adj_from_hourly(hourly: pd.DataFrame, bar_hours: int) -> pd.DataFrame:
    """One row per (session, bucket) present in `hourly`, with a flat
    close_adj (100.0 everywhere) -- guarantees hist/EMA9 never cross
    (either NaN, too few rows to seed, or perfectly flat), so X1/X2 stay
    False for every bucket and the walk reduces to v0's own S1/S2/S4."""
    seen = {}
    for _, row in hourly.iterrows():
        key = (row["session"], int(row["bar"]) // bar_hours)
        if key not in seen:
            seen[key] = row["t_open"]
    keys = list(seen.keys())
    return pd.DataFrame({
        "session": [k[0] for k in keys], "bar": [k[1] for k in keys],
        "t_open": [seen[k] for k in keys], "close_adj": [100.0] * len(keys),
    })


class TestSimulateV1NoSignal:
    """bar_hours=1 here (not v0's usual 4): every hourly row is then its
    own entry-chart bucket, so a candidate's t_open is always an exact
    entry_adj row -- matching how v1_preflight.detect_v1 actually builds
    fills (fill_idx indexes entry_adj directly) -- while keeping these
    hand-built frames identical in spirit to test_runner.py's own E5/roll
    tests. bar_hours only changes the trail-recompute cadence, which none
    of these three tests exercises (every exit here is a plain stop hit)."""

    def test_a_candidate_that_fires_inside_an_open_position_is_ignored(self):
        hourly = _hourly([
            ("d1", 0, 100.0, 100.1, 99.9, 100.0, 1, 0.0),
            ("d1", 1, 100.0, 100.1, 99.9, 100.0, 1, 0.0),
            ("d1", 2, 100.0, 100.1, 94.0, 95.0, 1, 0.0),
            ("d1", 3, 95.0, 95.5, 94.5, 95.0, 1, 0.0),
            ("d1", 4, 95.0, 95.2, 94.8, 95.0, 1, 0.0),
            ("d1", 5, 95.0, 95.2, 94.8, 95.0, 1, 0.0),
        ])
        entry_adj = _entry_adj_from_hourly(hourly, bar_hours=1)
        entries = [
            {"t_open": hourly["t_open"].iloc[0], "direction": "long", "stop_dist": 5.0, "session": "d1"},
            {"t_open": hourly["t_open"].iloc[1], "direction": "long", "stop_dist": 5.0, "session": "d1"},
            {"t_open": hourly["t_open"].iloc[3], "direction": "long", "stop_dist": 1.0, "session": "d1"},
        ]
        trades, n_ignored = V1R.simulate_v1(entries, hourly, entry_adj, bar_hours=1,
                                            session_flatten=False)
        assert n_ignored == 1
        assert len(trades) == 2
        assert trades[0].exit_pos == 2
        assert trades[0].exit_reason == "initial_stop"
        assert trades[1].entry_t == hourly["t_open"].iloc[3]

    def test_a_candidate_at_or_after_the_exit_bar_is_not_blocked(self):
        hourly = _hourly([
            ("d1", 0, 100.0, 100.1, 99.9, 100.0, 1, 0.0),
            ("d1", 1, 100.0, 100.1, 94.0, 95.0, 1, 0.0),
            ("d1", 2, 95.0, 95.5, 94.5, 95.0, 1, 0.0),
            ("d1", 3, 95.0, 95.2, 94.8, 95.0, 1, 0.0),
        ])
        entry_adj = _entry_adj_from_hourly(hourly, bar_hours=1)
        entries = [
            {"t_open": hourly["t_open"].iloc[0], "direction": "long", "stop_dist": 5.0, "session": "d1"},
            {"t_open": hourly["t_open"].iloc[2], "direction": "long", "stop_dist": 1.0, "session": "d1"},
        ]
        trades, n_ignored = V1R.simulate_v1(entries, hourly, entry_adj, bar_hours=1,
                                            session_flatten=False)
        assert n_ignored == 0
        assert len(trades) == 2

    def test_a_roll_between_fill_and_exit_is_counted_and_priced_in_raw_terms(self):
        hourly = _hourly([
            ("d1", 0, 100.0, 100.1, 99.9, 100.0, 1, 0.0),
            ("d1", 1, 100.0, 100.1, 99.9, 100.0, 2, -0.50),
            ("d1", 2, 94.5, 94.6, 89.0, 90.0, 2, -0.50),
        ])
        entry_adj = _entry_adj_from_hourly(hourly, bar_hours=1)
        entries = [{"t_open": hourly["t_open"].iloc[0], "direction": "long",
                   "stop_dist": 10.0, "session": "d1"}]
        trades, n_ignored = V1R.simulate_v1(entries, hourly, entry_adj, bar_hours=1,
                                            session_flatten=False)
        assert n_ignored == 0
        t = trades[0]
        assert t.n_rolls == 1
        assert t.fill_adj == pytest.approx(100.0)
        assert t.fill_raw == pytest.approx(100.0)
        assert t.exit_price_adj == pytest.approx(90.0)
        assert t.exit_price_raw == pytest.approx(90.0 - (-0.50))
        assert t.gross_pnl("MCL") == pytest.approx((t.exit_price_raw - t.fill_raw) * 100)
        assert t.cost("MCL", "mid") == pytest.approx(C.per_side("MCL", "mid") * 2 * 2)
        assert t.net_pnl("MCL", "mid") == pytest.approx(t.gross_pnl("MCL") - t.cost("MCL", "mid"))


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


class TestRunV1Integration:
    def test_trades_taken_never_exceeds_entries_and_reasons_are_valid(self, archive_df_1h, q_h_q_e):
        q_h, q_e = q_h_q_e
        trades, counts = V1R.run_v1(archive_df_1h, scenario="B", q_h=q_h, q_e=q_e)
        assert counts["trades_taken"] == len(trades)
        assert counts["trades_taken"] <= counts["entries"]
        assert all(t.exit_reason in V1E.REASONS for t in trades)
        assert all(t.direction in ("long", "short") for t in trades)

    def test_at_least_some_trades_exit_by_x1_or_x2_on_this_much_data(self, archive_df_1h, q_h_q_e):
        """Not a registered criterion -- just a sanity check that the
        signal-exit machinery is actually wired in, on a large enough
        synthetic run that never seeing X1/X2 would mean a bug, not luck."""
        q_h, q_e = q_h_q_e
        trades, _ = V1R.run_v1(archive_df_1h, scenario="B", q_h=q_h, q_e=q_e)
        reasons = {t.exit_reason for t in trades}
        assert reasons & {"x1_opposite_cross", "x2_ema9_turn"}

    def test_v1_x_never_carries_a_signal_exit_reason(self, archive_df_1h, q_h_q_e):
        q_h, q_e = q_h_q_e
        trades, _ = V1R.run_v1_no_signal_exits(archive_df_1h, scenario="B", q_h=q_h, q_e=q_e)
        assert all(t.exit_reason not in ("x1_opposite_cross", "x2_ema9_turn") for t in trades)

    def test_x2_bars_2_wired_through_simulate_v1_directly(self, archive_df_1h, q_h_q_e):
        """x2_bars is a plain pass-through from simulate_v1 into
        v1_exits.x_signal_series (that module's own tests cover the 1-vs-2
        semantics); this only checks the argument actually reaches the real
        wiring end-to-end (prepare_grids -> detect_v1 -> simulate_v1) and
        both settings run cleanly, without asserting a specific
        trade-by-trade outcome (too data-dependent on the synthetic seed)."""
        q_h, q_e = q_h_q_e
        grids, daily_adj = P.prepare_grids(archive_df_1h)
        hourly = grids["1H"]
        entry_adj = grids["4H"]
        four_h_adj = grids["4H"]
        entries, _ = V1P.detect_v1(entry_adj, daily_adj, four_h_adj, scenario="B",
                                   q_h=q_h, q_e=q_e)
        trades_1, _ = V1R.simulate_v1(entries, hourly, entry_adj, bar_hours=4,
                                      session_flatten=False, x2_bars=1)
        trades_2, _ = V1R.simulate_v1(entries, hourly, entry_adj, bar_hours=4,
                                      session_flatten=False, x2_bars=2)
        assert all(t.exit_reason in V1E.REASONS for t in trades_1)
        assert all(t.exit_reason in V1E.REASONS for t in trades_2)
        # not asserting they differ -- on some synthetic seeds they may
        # coincide -- only that both run cleanly through the real wiring.

    def test_v1_x_and_v1_use_the_same_entries_and_e5_walk_order(self, archive_df_1h, q_h_q_e):
        """v1-X changes only the exit rule, not entry detection -- the two
        runs must start from the same candidate list count (v1_preflight's
        own entries), though E5 can still take a different SUBSET of them
        once exits diverge."""
        q_h, q_e = q_h_q_e
        _, counts_v1 = V1R.run_v1(archive_df_1h, scenario="B", q_h=q_h, q_e=q_e)
        _, counts_x = V1R.run_v1_no_signal_exits(archive_df_1h, scenario="B", q_h=q_h, q_e=q_e)
        assert counts_v1["entries"] == counts_x["entries"]
