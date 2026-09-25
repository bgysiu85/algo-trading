"""Tests for strategy/htf/runner.py -- E5 enforcement, roll counting, raw
P&L conversion. W15-0004 step 7 checkpoint 3. simulate() is tested directly
against small hand-built hourly frames (mirrors test_exits.py's approach);
run_v0/run_c1 (archive-level wiring) are exercised for real on Ben's machine."""
from __future__ import annotations

import pandas as pd
import pytest

from strategy.htf import costs as C
from strategy.htf import exits as E
from strategy.htf import runner as R


def _hourly(rows):
    """rows: (session, bar, open, high, low, close, held_id, offset).
    open_adj etc = raw + offset (mirrors bars.back_adjust's own convention:
    adj = raw + adj_offset)."""
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


class TestE5Enforcement:
    def test_a_candidate_that_fires_inside_an_open_position_is_ignored(self):
        hourly = _hourly([
            ("d1", 0, 100.0, 100.1, 99.9, 100.0, 1, 0.0),   # e1 fill
            ("d1", 1, 100.0, 100.1, 99.9, 100.0, 1, 0.0),   # e2 candidate -- must be ignored
            ("d1", 2, 100.0, 100.1, 94.0, 95.0, 1, 0.0),    # e1's stop hit here
            ("d1", 3, 95.0, 95.5, 94.5, 95.0, 1, 0.0),      # e3 candidate -- allowed (after e1's exit)
            ("d1", 4, 95.0, 95.2, 94.8, 95.0, 1, 0.0),
            ("d1", 5, 95.0, 95.2, 94.8, 95.0, 1, 0.0),
        ])
        entries = [
            {"t_open": hourly["t_open"].iloc[0], "direction": "long", "stop_dist": 5.0, "session": "d1"},
            {"t_open": hourly["t_open"].iloc[1], "direction": "long", "stop_dist": 5.0, "session": "d1"},
            {"t_open": hourly["t_open"].iloc[3], "direction": "long", "stop_dist": 1.0, "session": "d1"},
        ]
        trades, n_ignored = R.simulate(entries, hourly, bar_hours=4, session_flatten=False)
        assert n_ignored == 1
        assert len(trades) == 2
        assert trades[0].exit_pos == 2
        assert trades[0].exit_reason == "initial_stop"
        assert trades[1].entry_t == hourly["t_open"].iloc[3]

    def test_a_candidate_at_or_after_the_exit_bar_is_not_blocked(self):
        """blocked_until is the exit t_open itself -- a new trigger fills
        the SAME bar the previous exit happened on (or later) is allowed,
        matching E5's 'a new trigger may fire on any bar after the exit
        bar' read together with E4's next-bar-open fill (the candidate's
        own fill_idx is already c+1, one past its trigger)."""
        hourly = _hourly([
            ("d1", 0, 100.0, 100.1, 99.9, 100.0, 1, 0.0),
            ("d1", 1, 100.0, 100.1, 94.0, 95.0, 1, 0.0),     # e1 exits here
            ("d1", 2, 95.0, 95.5, 94.5, 95.0, 1, 0.0),       # e2 candidate, same t_open as exit -- allowed
            ("d1", 3, 95.0, 95.2, 94.8, 95.0, 1, 0.0),
        ])
        entries = [
            {"t_open": hourly["t_open"].iloc[0], "direction": "long", "stop_dist": 5.0, "session": "d1"},
            {"t_open": hourly["t_open"].iloc[2], "direction": "long", "stop_dist": 1.0, "session": "d1"},
        ]
        trades, n_ignored = R.simulate(entries, hourly, bar_hours=4, session_flatten=False)
        assert n_ignored == 0
        assert len(trades) == 2


class TestRollAndRawConversion:
    def test_a_roll_between_fill_and_exit_is_counted_and_priced_in_raw_terms(self):
        hourly = _hourly([
            ("d1", 0, 100.0, 100.1, 99.9, 100.0, 1, 0.0),      # fill: raw==adj (offset 0)
            ("d1", 1, 100.0, 100.1, 99.9, 100.0, 2, -0.50),    # roll leg: held_id changes here
            ("d1", 2, 94.5, 94.6, 89.0, 90.0, 2, -0.50),       # stop hit here (post-roll)
        ])
        entries = [{"t_open": hourly["t_open"].iloc[0], "direction": "long",
                   "stop_dist": 10.0, "session": "d1"}]
        trades, n_ignored = R.simulate(entries, hourly, bar_hours=4, session_flatten=False)
        assert n_ignored == 0
        t = trades[0]
        assert t.n_rolls == 1
        assert t.fill_adj == pytest.approx(100.0)
        assert t.fill_raw == pytest.approx(100.0)          # offset 0 at the fill row
        assert t.exit_price_adj == pytest.approx(90.0)     # stop level (94.5 > 90, not gapped)
        assert t.exit_price_raw == pytest.approx(90.0 - (-0.50))  # adj - that row's own offset

        assert t.gross_pnl("MCL") == pytest.approx((t.exit_price_raw - t.fill_raw) * 100)
        assert t.cost("MCL", "mid") == pytest.approx(C.per_side("MCL", "mid") * 2 * 2)  # 1 trade + 1 roll = 2 round trips
        assert t.net_pnl("MCL", "mid") == pytest.approx(t.gross_pnl("MCL") - t.cost("MCL", "mid"))

    def test_no_roll_crossed_is_one_round_trip(self):
        hourly = _hourly([
            ("d1", 0, 100.0, 100.1, 99.9, 100.0, 1, 0.0),
            ("d1", 1, 100.0, 100.1, 94.0, 95.0, 1, 0.0),
        ])
        entries = [{"t_open": hourly["t_open"].iloc[0], "direction": "long",
                   "stop_dist": 5.0, "session": "d1"}]
        trades, _ = R.simulate(entries, hourly, bar_hours=4, session_flatten=False)
        assert trades[0].n_rolls == 0
        assert trades[0].cost("MCL", "low") == pytest.approx(C.per_side("MCL", "low") * 2)


class TestShortMirrorsLong:
    def test_short_gross_pnl_sign(self):
        hourly = _hourly([
            ("d1", 0, 100.0, 100.1, 99.9, 100.0, 1, 0.0),
            ("d1", 1, 105.5, 106.0, 99.9, 105.0, 1, 0.0),   # gaps through the stop (open >= stop)
        ])
        entries = [{"t_open": hourly["t_open"].iloc[0], "direction": "short",
                   "stop_dist": 5.0, "session": "d1"}]
        trades, _ = R.simulate(entries, hourly, bar_hours=4, session_flatten=False)
        t = trades[0]
        assert t.direction == "short"
        assert t.exit_price_adj == pytest.approx(105.5)   # gapped open, not the 105.0 stop level
        assert t.gross_pnl("MCL") < 0    # price rose against the short


class TestTrailTriggerPassthrough:
    """REGISTERED sec 3 item 8: runner.simulate's trail_trigger param must
    actually reach exits.simulate_exit, not just be accepted and ignored."""

    def test_a_tighter_trigger_starts_the_trail_where_the_default_would_not(self):
        hourly = _hourly([
            ("d1", 0, 100.0, 100.1, 99.9, 100.0, 1, 0.0),
            ("d1", 1, 100.0, 100.1, 99.9, 100.0, 1, 0.0),
            ("d1", 2, 100.0, 100.12, 99.9, 100.1, 1, 0.0),
            ("d1", 3, 100.1, 100.15, 100.05, 100.1, 1, 0.0),
            ("d1", 4, 100.1, 100.15, 100.02, 100.1, 1, 0.0),
        ])
        entries = [{"t_open": hourly["t_open"].iloc[0], "direction": "long",
                   "stop_dist": 10.0, "session": "d1"}]
        default_trades, _ = R.simulate(entries, hourly, bar_hours=4, session_flatten=False)
        tight_trades, _ = R.simulate(entries, hourly, bar_hours=4, session_flatten=False,
                                     trail_trigger=0.10)
        assert not default_trades[0].trail_started
        assert tight_trades[0].trail_started
