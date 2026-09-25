"""Tests for strategy/htf/exits.py (S1-S5). W15-0004 step 7."""
from __future__ import annotations

import pandas as pd
import pytest

from strategy.htf import exits as E


def _hourly(rows):
    """rows: list of (session_str, bar, open, high, low, close). t_open is
    assigned as sequential UTC timestamps one hour apart -- exits.py never
    reads real wall-clock meaning from t_open, only equality, so a synthetic
    monotonic clock is fine and keeps fixtures short."""
    idx = pd.date_range("2020-01-01", periods=len(rows), freq="h", tz="UTC")
    df = pd.DataFrame({
        "session": [r[0] for r in rows],
        "bar": [r[1] for r in rows],
        "open_adj": [r[2] for r in rows],
        "high_adj": [r[3] for r in rows],
        "low_adj": [r[4] for r in rows],
        "close_adj": [r[5] for r in rows],
    })
    df["t_open"] = idx
    return df


class TestInitialStop:
    def test_hit_on_the_fill_hour_itself(self):
        hourly = _hourly([
            ("d1", 0, 100.0, 100.5, 94.0, 95.0),   # low undercuts the stop immediately
            ("d1", 1, 95.0, 96.0, 94.5, 95.5),
        ])
        out = E.simulate_exit(hourly, start_pos=0, direction="long", fill_price=100.0,
                              initial_stop=95.0, bar_hours=4, session_flatten=False)
        assert out.exit_pos == 0
        assert out.reason == E.R_INITIAL_STOP
        assert out.exit_price == pytest.approx(95.0)   # stop level, not the open (no gap)
        assert not out.trail_started

    def test_gap_through_fills_at_open_not_the_stop_level(self):
        hourly = _hourly([
            ("d1", 0, 100.0, 100.5, 99.5, 100.0),
            ("d1", 1, 90.0, 90.5, 88.0, 89.0),      # opens BELOW the stop (gap)
        ])
        out = E.simulate_exit(hourly, start_pos=0, direction="long", fill_price=100.0,
                              initial_stop=95.0, bar_hours=4, session_flatten=False)
        assert out.exit_pos == 1
        assert out.reason == E.R_INITIAL_STOP
        assert out.exit_price == pytest.approx(90.0)   # the gapped-through open

    def test_short_mirrors_long(self):
        hourly = _hourly([
            ("d1", 0, 100.0, 106.0, 99.5, 100.0),   # high breaches the stop
            ("d1", 1, 100.0, 100.5, 99.0, 100.0),
        ])
        out = E.simulate_exit(hourly, start_pos=0, direction="short", fill_price=100.0,
                              initial_stop=105.0, bar_hours=4, session_flatten=False)
        assert out.exit_pos == 0
        assert out.reason == E.R_INITIAL_STOP
        assert out.exit_price == pytest.approx(105.0)


class TestTrail:
    def test_a_new_level_takes_effect_only_from_the_next_entry_chart_bar(self):
        """bar_hours=4: bucket 0 is bar 0-3, bucket 1 is bar 4-7. The high
        that triggers the trail happens INSIDE bucket 0 (bar 2); S3 says that
        recomputed level must not apply until bucket 1 -- so a low in bucket
        0's own remaining hours that would have hit the NEW (raised) stop but
        not the OLD one must NOT exit."""
        hourly = _hourly([
            ("d1", 0, 100.0, 100.2, 99.8, 100.0),          # fill hour
            ("d1", 1, 100.0, 100.1, 99.9, 100.0),
            ("d1", 2, 100.0, 100.30, 99.9, 100.2),          # peak-fill=0.30 >= 0.20 trigger
            ("d1", 3, 100.2, 100.25, 100.05, 100.2),        # low 100.05: below the WOULD-BE new stop (100.15) but bucket 0 hasn't closed
            ("d1", 4, 100.2, 100.3, 100.16, 100.25),        # bucket 1's first hour: NOW the new stop (100.15) is live; low 100.16 doesn't hit it
            ("d1", 5, 100.2, 100.3, 100.10, 100.20),        # low 100.10 <= 100.15: hits the now-live trailed stop
        ])
        out = E.simulate_exit(hourly, start_pos=0, direction="long", fill_price=100.0,
                              initial_stop=90.0, bar_hours=4, session_flatten=False)
        # new_stop = fill + (peak-fill)/2 = 100.0 + 0.30/2 = 100.15
        assert out.trail_started
        assert out.reason == E.R_TRAILED_STOP
        assert out.exit_pos == 5
        assert out.exit_price == pytest.approx(100.15)

    def test_the_stop_never_loosens(self):
        """A lower high in a LATER bucket must not pull a already-raised
        trail back down."""
        hourly = _hourly([
            ("d1", 0, 100.0, 100.0, 99.9, 100.0),
            ("d1", 1, 100.0, 100.0, 99.9, 100.0),
            ("d1", 2, 100.0, 100.50, 99.9, 100.3),   # big peak: trail -> 100.25
            ("d1", 3, 100.3, 100.3, 100.2, 100.3),
            ("d1", 4, 100.3, 100.31, 100.26, 100.30),  # bucket 1: a SMALLER high than bucket 0's
            ("d1", 5, 100.3, 100.31, 100.26, 100.30),
            ("d1", 6, 100.3, 100.31, 100.26, 100.30),
            ("d1", 7, 100.3, 100.31, 100.20, 100.30),
            ("d1", 8, 100.3, 100.31, 100.24, 100.30),  # bucket 2 first hour: stop must still be 100.25, not lower
        ])
        out = E.simulate_exit(hourly, start_pos=0, direction="long", fill_price=100.0,
                              initial_stop=90.0, bar_hours=4, session_flatten=False)
        assert out.reason == E.R_TRAILED_STOP
        assert out.exit_price == pytest.approx(100.25)

    def test_short_trail_mirrors_long(self):
        hourly = _hourly([
            ("d1", 0, 100.0, 100.1, 99.8, 100.0),
            ("d1", 1, 100.0, 100.1, 99.8, 100.0),
            ("d1", 2, 100.0, 100.1, 99.70, 99.8),    # fill-low = 0.30 >= 0.20 trigger
            ("d1", 3, 99.8, 99.95, 99.85, 99.9),
            ("d1", 4, 99.8, 99.95, 99.85, 99.9),      # bucket 1: new stop = 100 - 0.15 = 99.85 now live
            ("d1", 5, 99.9, 99.95, 99.80, 99.9),      # high 99.95 doesn't hit 99.85 for a short (need high>=stop)... adjust
        ])
        out = E.simulate_exit(hourly, start_pos=0, direction="short", fill_price=100.0,
                              initial_stop=110.0, bar_hours=4, session_flatten=False)
        assert out.trail_started
        # new_stop = 100 - (100-99.70)/2 = 99.85; none of the highs above reach
        # it (all < 99.85 is false... 99.95 >= 99.85 IS a hit) -- so it exits
        # in bucket 1's first hour (pos 4) at 99.85
        assert out.reason == E.R_TRAILED_STOP
        assert out.exit_price == pytest.approx(99.85)


class TestTrailTriggerParam:
    """REGISTERED sec 3 item 8: trail trigger in {$0.10, $0.20, $0.40}, for
    the neighbour grid -- simulate_exit's `trail_trigger` param, default
    E.TRAIL_TRIGGER ($0.20)."""

    def test_a_smaller_trigger_starts_the_trail_where_the_default_would_not(self):
        hourly = _hourly([
            ("d1", 0, 100.0, 100.1, 99.9, 100.0),
            ("d1", 1, 100.0, 100.1, 99.9, 100.0),
            ("d1", 2, 100.0, 100.12, 99.9, 100.1),
            ("d1", 3, 100.1, 100.15, 100.05, 100.1),   # bucket 0's extreme high = 100.15 (bars 0-3), peak-fill = 0.15
            ("d1", 4, 100.1, 100.15, 100.02, 100.1),  # bucket 1: with trail_trigger=0.10, new stop=100.075 -> low 100.02 hits it
        ])
        default_out = E.simulate_exit(hourly, start_pos=0, direction="long", fill_price=100.0,
                                      initial_stop=90.0, bar_hours=4, session_flatten=False)
        assert not default_out.trail_started   # 0.15 < the registered $0.20 trigger

        tight_out = E.simulate_exit(hourly, start_pos=0, direction="long", fill_price=100.0,
                                    initial_stop=90.0, bar_hours=4, session_flatten=False,
                                    trail_trigger=0.10)
        assert tight_out.trail_started
        assert tight_out.exit_price == pytest.approx(100.075)   # 100.0 + 0.15/2

    def test_default_matches_the_module_constant(self):
        hourly = _hourly([
            ("d1", 0, 100.0, 100.1, 99.9, 100.0),
            ("d1", 1, 100.0, 100.1, 99.9, 100.0),
            ("d1", 2, 100.0, 100.30, 99.9, 100.2),
            ("d1", 3, 100.2, 100.25, 100.05, 100.2),
        ])
        a = E.simulate_exit(hourly, start_pos=0, direction="long", fill_price=100.0,
                            initial_stop=90.0, bar_hours=4, session_flatten=False)
        b = E.simulate_exit(hourly, start_pos=0, direction="long", fill_price=100.0,
                            initial_stop=90.0, bar_hours=4, session_flatten=False,
                            trail_trigger=E.TRAIL_TRIGGER)
        assert a == b


class TestSessionFlatten:
    def test_scenario_a_flattens_at_the_last_hour_of_the_session(self):
        hourly = _hourly([
            ("d1", 0, 100.0, 100.1, 99.9, 100.0),
            ("d1", 22, 100.0, 100.2, 99.95, 100.10),   # last hour of the session
            ("d2", 0, 100.10, 100.2, 100.0, 100.15),   # next session -- must not be reached
        ])
        out = E.simulate_exit(hourly, start_pos=0, direction="long", fill_price=100.0,
                              initial_stop=90.0, bar_hours=4, session_flatten=True)
        assert out.exit_pos == 1
        assert out.reason == E.R_SESSION_FLAT
        assert out.exit_price == pytest.approx(100.10)   # the close, not the high

    def test_scenario_b_does_not_flatten_and_holds_into_the_next_session(self):
        hourly = _hourly([
            ("d1", 0, 100.0, 100.05, 99.9, 100.0),
            ("d1", 22, 100.0, 100.05, 99.95, 100.02),
            ("d2", 0, 100.02, 100.05, 94.0, 100.03),     # stop finally hit here; highs stay below the trail trigger throughout
        ])
        out = E.simulate_exit(hourly, start_pos=0, direction="long", fill_price=100.0,
                              initial_stop=95.0, bar_hours=4, session_flatten=False)
        assert out.exit_pos == 2
        assert out.reason == E.R_INITIAL_STOP


class TestDataEnd:
    def test_runs_off_the_end_of_the_archive(self):
        hourly = _hourly([
            ("d1", 0, 100.0, 100.1, 99.9, 100.0),
            ("d1", 1, 100.0, 100.1, 99.9, 100.05),
        ])
        out = E.simulate_exit(hourly, start_pos=0, direction="long", fill_price=100.0,
                              initial_stop=90.0, bar_hours=4, session_flatten=False)
        assert out.exit_pos == 1
        assert out.reason == E.R_DATA_END
        assert out.exit_price == pytest.approx(100.05)


class TestStartPosBounds:
    def test_start_pos_at_the_end_raises(self):
        hourly = _hourly([("d1", 0, 100.0, 100.1, 99.9, 100.0)])
        with pytest.raises(IndexError):
            E.simulate_exit(hourly, start_pos=5, direction="long", fill_price=100.0,
                            initial_stop=90.0, bar_hours=4, session_flatten=False)

    def test_bad_direction_raises(self):
        hourly = _hourly([("d1", 0, 100.0, 100.1, 99.9, 100.0)])
        with pytest.raises(ValueError):
            E.simulate_exit(hourly, start_pos=0, direction="sideways", fill_price=100.0,
                            initial_stop=90.0, bar_hours=4, session_flatten=False)


class TestFindStartPos:
    def test_matches_by_t_open_exactly(self):
        hourly = _hourly([("d1", 0, 100.0, 100.1, 99.9, 100.0),
                          ("d1", 1, 100.0, 100.1, 99.9, 100.0)])
        pos = E.find_start_pos(hourly, hourly["t_open"].iloc[1])
        assert pos == 1

    def test_raises_when_not_found(self):
        hourly = _hourly([("d1", 0, 100.0, 100.1, 99.9, 100.0)])
        with pytest.raises(KeyError):
            E.find_start_pos(hourly, pd.Timestamp("2099-01-01", tz="UTC"))
