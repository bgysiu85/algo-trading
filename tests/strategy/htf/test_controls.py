"""Tests for strategy/htf/controls.py (C2 Donchian). W15-0004 step 7
checkpoint 4. detect_c2/simulate_c2 are tested directly against small
hand-built entry-chart frames, same approach as test_exits.py/test_runner.py."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.htf import controls as CT


def _entry_adj(rows):
    """rows: (session, bar, open, high, low, close, held_id, offset).
    *_adj = raw + offset (bars.back_adjust's own convention)."""
    idx = pd.date_range("2020-01-01", periods=len(rows), freq="4h", tz="UTC")
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


def _flat_history(n, base=50.0, held_id=1, offset=0.0):
    """n quiet bars (tight, no breakout) to satisfy the 20-bar entry lookback
    and 10-bar exit lookback without triggering anything themselves."""
    return [("warm", i, base, base + 0.1, base - 0.1, base, held_id, offset) for i in range(n)]


class TestDetectC2:
    def test_a_close_above_the_prior_20_bar_high_triggers_long_next_bar(self):
        rows = _flat_history(20) + [
            ("d1", 20, 50.0, 60.0, 49.9, 55.0, 1, 0.0),   # breakout close (55 > prior 20-bar high 50.1)
            ("d1", 21, 55.0, 55.5, 54.5, 55.0, 1, 0.0),   # fill bar
        ]
        entry_adj = _entry_adj(rows)
        entries, counts = CT.detect_c2(entry_adj, scenario="B", bar_hours=4)
        assert counts["triggers"] == 1
        assert counts["entries"] == 1
        assert entries[0]["direction"] == "long"
        assert entries[0]["fill_idx"] == 21

    def test_a_close_below_the_prior_20_bar_low_triggers_short(self):
        rows = _flat_history(20) + [
            ("d1", 20, 50.0, 50.1, 40.0, 45.0, 1, 0.0),
            ("d1", 21, 45.0, 45.5, 44.5, 45.0, 1, 0.0),
        ]
        entry_adj = _entry_adj(rows)
        entries, counts = CT.detect_c2(entry_adj, scenario="B", bar_hours=4)
        assert entries[0]["direction"] == "short"

    def test_trigger_on_the_last_bar_of_the_series_lapses(self):
        rows = _flat_history(20) + [("d1", 20, 50.0, 60.0, 49.9, 55.0, 1, 0.0)]
        entry_adj = _entry_adj(rows)
        entries, counts = CT.detect_c2(entry_adj, scenario="B", bar_hours=4)
        assert counts["lapsed"] == 1
        assert len(entries) == 0

    def test_intraday_scenario_blocks_a_fill_on_the_sessions_last_bar(self):
        rows = _flat_history(20) + [
            ("d1", 20, 50.0, 60.0, 49.9, 55.0, 1, 0.0),
            ("d1", 22, 55.0, 55.5, 54.5, 55.0, 1, 0.0),   # bar 22 == last bucket for bar_hours=4 (22//4=5... )
        ]
        # last_bucket = 22 // bar_hours; use bar_hours=4 -> last_bucket=5, so
        # the fill bar's own 'bar' column must equal 5 to be blocked
        rows[-1] = ("d1", 5, 55.0, 55.5, 54.5, 55.0, 1, 0.0)
        entry_adj = _entry_adj(rows)
        entries, counts = CT.detect_c2(entry_adj, scenario="A-4H", bar_hours=4)
        assert counts["blocked_end_of_session"] == 1
        assert len(entries) == 0


class TestSimulateC2:
    def test_long_exits_on_the_opposite_10_bar_channel(self):
        rows = _flat_history(20, base=50.0) + [
            ("d1", 20, 50.0, 60.0, 49.9, 55.0, 1, 0.0),    # trigger
            ("d1", 21, 55.0, 55.2, 54.8, 55.0, 1, 0.0),    # fill_idx=21
        ] + [("d1", 22 + i, 55.0, 55.2, 54.8, 55.0, 1, 0.0) for i in range(9)]  # 9 more quiet bars (10-bar exit lookback fills)
        rows.append(("d1", 31, 55.0, 55.2, 44.0, 50.0, 1, 0.0))   # breaches the 10-bar low channel
        entry_adj = _entry_adj(rows)
        entries, _ = CT.detect_c2(entry_adj, scenario="B", bar_hours=4)
        trades, n_ignored = CT.simulate_c2(entries, entry_adj, bar_hours=4, session_flatten=False)
        assert n_ignored == 0
        assert len(trades) == 1
        t = trades[0]
        assert t.direction == "long"
        assert t.exit_reason == "channel_exit"

    def test_a_second_trigger_while_in_a_position_is_ignored(self):
        rows = _flat_history(20, base=50.0) + [
            ("d1", 20, 50.0, 60.0, 49.9, 55.0, 1, 0.0),    # trigger 1
            ("d1", 21, 55.0, 55.2, 54.8, 55.0, 1, 0.0),    # fill 1
            ("d1", 22, 55.0, 65.0, 54.8, 60.0, 1, 0.0),    # itself a fresh breakout (ignored: still in position)
        ] + [("d1", 23 + i, 55.0, 55.2, 54.8, 55.0, 1, 0.0) for i in range(9)]
        entry_adj = _entry_adj(rows)
        entries = [
            {"fill_idx": 21, "direction": "long", "session": "d1"},
            {"fill_idx": 22, "direction": "long", "session": "d1"},
        ]
        trades, n_ignored = CT.simulate_c2(entries, entry_adj, bar_hours=4, session_flatten=False)
        assert n_ignored == 1
        assert len(trades) == 1

    def test_raw_conversion_and_roll_counting_via_entry_adj_own_columns(self):
        rows = [
            ("d1", 0, 50.0, 50.1, 49.9, 50.0, 1, 0.0),      # fill row, offset 0
            ("d1", 1, 50.0, 50.1, 49.9, 50.0, 2, -1.0),     # roll leg (held_id changes)
            ("d1", 2, 49.0, 49.1, 30.0, 35.0, 2, -1.0),     # exit row, post-roll offset
        ]
        entry_adj = _entry_adj(rows)
        # force a channel level that isn't NaN by monkeypatching via a tiny
        # DONCHIAN_EXIT_N-independent trade: directly call simulate_c2 with a
        # single manual entry and a pre-set low low enough to trigger even
        # with a NaN exit-channel level (falls through to data_end/last bar,
        # which still exercises raw conversion + roll counting identically)
        entries = [{"fill_idx": 0, "direction": "long", "session": "d1"}]
        trades, _ = CT.simulate_c2(entries, entry_adj, bar_hours=4, session_flatten=False)
        t = trades[0]
        assert t.n_rolls == 1
        assert t.fill_raw == pytest.approx(50.0)             # offset 0 at the fill row
        assert t.exit_price_adj == pytest.approx(34.0)        # data_end -> close_adj of the last row (raw 35.0 + offset -1.0)
        assert t.exit_price_raw == pytest.approx(35.0)         # adj - that row's own offset -> back to raw close
