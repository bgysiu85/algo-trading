#!/usr/bin/env python3
"""The point-in-time screen, and the leak it exists to not have.

The headline test here is `test_future_bars_cannot_change_the_output`. Every
P/L figure in this project rests on a universe chosen with the day already
known; `screen_at` is the attempt to choose one at 03:59 instead, and a
look-ahead inside it would produce a BETTER number than the truth while looking
like vindication. `stage1`'s existing guard greps its own source, which catches
a named call and nothing else. This corrupts the future and demands the output
not move.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from common import screen_at as S
from common import tv_feed as F
from common import tv_screener as TV

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


def bar(sym, et_hhmm, close, volume, day="2026-08-04"):
    h, m = et_hhmm.split(":")
    ts = datetime.fromisoformat(f"{day}T{h}:{m}:00").replace(tzinfo=ET)
    return {"ts_event": pd.Timestamp(ts).tz_convert("UTC"), "symbol": sym,
            "close": close, "volume": volume}


def frame(rows) -> pd.DataFrame:
    return pd.DataFrame(rows).set_index("ts_event").sort_index()


def at(et_hhmm, day="2026-08-04") -> datetime:
    h, m = et_hhmm.split(":")
    return datetime.fromisoformat(f"{day}T{h}:{m}:00").replace(tzinfo=ET)


# A name that passes every clause comfortably: 100 -> 150 is +50%, price inside
# $2-25, volume well over the scaled floor.
def passing_rows(sym="AAA", day="2026-08-04"):
    return [bar(sym, "04:00", 3.00, 80_000, day),
            bar(sym, "04:01", 4.50, 80_000, day)]


PRIOR = pd.Series({"AAA": 3.00, "BBB": 3.00, "CCC": 3.00, "DDD": 3.00})


# --- the rules are imported, not restated ----------------------------------

def test_the_config_defaults_are_the_shipped_screen_not_a_copy():
    """The scope document found screen.py applying an RVOL clause the live
    screen does not have. A restated constant drifts silently; these must BE
    the live objects."""
    cfg = S.ScreenConfig()
    assert cfg.change_min is TV.PREMARKET_CHANGE_MIN
    assert cfg.price_range is TV.PREMARKET_PRICE_RANGE
    assert cfg.volume_min is TV.PREMARKET_VOLUME_MIN
    assert cfg.max_symbols is F.MAX_SYMBOLS


def test_the_screen_has_no_clause_the_live_screen_lacks():
    """If someone re-adds RVOL or float to the simulation without adding it to
    tv_screener, this fails. The reverse -- a clause added live and missing
    here -- is caught by the count."""
    assert len(TV.FILTERS) == 3, (
        "the live screen changed; screen_at applies exactly three clauses and "
        "must be updated deliberately, not discovered to be wrong in a report")
    assert {f["left"] for f in TV.FILTERS} == {
        "premarket_change", "premarket_close", "premarket_volume"}


# --- THE LEAK TEST ----------------------------------------------------------

def test_future_bars_cannot_change_the_output():
    """Corrupt the future and demand the answer does not move.

    The future here is not merely appended, it is made ENORMOUS: +567% on ten
    million shares, and priced INSIDE the $2-25 band on purpose. An earlier
    draft used $30, which the price clause rejected on its own -- so the test
    passed without the truncation doing anything, which is the same class of
    fault as a control that divides nothing. If any of the three columns reads
    past t, BBB now appears at rank 1 and this fails loudly.
    """
    t = at("05:00")
    base = frame(passing_rows("AAA"))
    honest = S.screen_at(base, PRIOR, t)

    poisoned = frame(passing_rows("AAA") + [
        bar("BBB", "05:30", 20.00, 10_000_000),
        bar("AAA", "06:00", 24.00, 10_000_000),
        bar("AAA", "09:29", 24.00, 10_000_000),
    ])
    after = S.screen_at(poisoned, PRIOR, t)

    pd.testing.assert_frame_equal(honest, after)
    assert "BBB" not in set(after["symbol"]), "a future-only name was screened"


def test_the_leak_test_can_actually_fail():
    """A test that cannot fail proves nothing. Screen at a LATER t and the same
    poisoned frame must produce a different answer -- which shows the assertion
    above is constraining something real rather than comparing two empties."""
    poisoned = frame(passing_rows("AAA") + [
        bar("BBB", "05:30", 20.00, 10_000_000)])
    early = S.screen_at(poisoned, PRIOR, at("05:00"))
    late = S.screen_at(poisoned, PRIOR, at("06:00"))
    assert set(early["symbol"]) == {"AAA"}
    assert "BBB" in set(late["symbol"])


# --- the bar-close boundary, which is the entry-latency lesson --------------

def test_a_bar_is_visible_only_after_it_closes():
    """ts_event is the interval START. The bar stamped 04:59 covers
    04:59:00-04:59:59 and is not knowable until 05:00:00. Including it at
    t=04:59 reads 59 seconds of the future on every symbol on every tick."""
    rows = frame([bar("AAA", "04:00", 3.00, 200_000),
                  bar("AAA", "04:59", 9.00, 200_000)])
    just_before = S.premarket_features(rows, PRIOR, at("04:59"))
    exactly_at = S.premarket_features(rows, PRIOR, at("05:00"))
    assert float(just_before["premarket_close"].iloc[0]) == 3.00
    assert float(exactly_at["premarket_close"].iloc[0]) == 9.00


def test_the_boundary_is_closed_not_open():
    """A bar closing exactly at t IS visible. Off-by-one in the safe direction
    is still off by one, and it would drop the most recent minute forever."""
    rows = frame([bar("AAA", "04:00", 3.00, 200_000)])
    assert len(S.visible_bars(rows, at("04:01"))) == 1
    assert len(S.visible_bars(rows, at("04:00"))) == 0


def test_bars_before_the_session_open_are_excluded():
    """premarket_volume accumulates from 04:00. An overnight print at 03:30 is
    not part of it."""
    rows = frame([bar("AAA", "03:30", 3.00, 5_000_000),
                  bar("AAA", "04:00", 4.50, 200_000)])
    f = S.premarket_features(rows, PRIOR, at("05:00"))
    assert int(f["premarket_volume"].iloc[0]) == 200_000


# --- the capture scaling, whose sign is the whole point ---------------------

def test_the_threshold_is_scaled_down_not_up():
    """Our tape shows ~55% of consolidated volume, so a name needs FEWER shares
    on our tape to represent 100k consolidated. Inverting this demands ~182k
    and empties the universe while reading as 'the screen is too tight'."""
    cfg = S.ScreenConfig()
    assert cfg.volume_min_on_tape < cfg.volume_min
    assert cfg.volume_min_on_tape == pytest.approx(100_000 * 0.552)


def test_capture_changes_which_names_pass():
    """If the sensitivity cannot move the answer it is decoration. 50k of tape
    volume clears p10 (45.8k) and fails p90 (65.6k)."""
    rows = frame([bar("AAA", "04:00", 4.50, 50_000)])
    lo = S.screen_at(rows, PRIOR, at("05:00"),
                     S.ScreenConfig(capture=S.CAPTURE_P10))
    hi = S.screen_at(rows, PRIOR, at("05:00"),
                     S.ScreenConfig(capture=S.CAPTURE_P90))
    assert len(lo) == 1 and len(hi) == 0

    sens = S.capture_sensitivity(rows, PRIOR, at("05:00"))
    assert list(sens["n"]) == [1, 0, 0]


# --- the three clauses, each at its boundary --------------------------------

@pytest.mark.parametrize("prior,close,volume,expect", [
    # change: prior 3.00 puts the threshold at exactly 3.60
    (3.00, 3.60, 200_000, True),    # +20.0% EXACTLY -- inclusive, and the case
                                    # binary float silently failed
    (3.00, 3.5999, 200_000, False),  # a hair under
    # price: prior chosen so every row is +100%, well clear of the change clause
    (1.00, 2.00, 200_000, True),     # floor, inclusive
    (0.99, 1.99, 200_000, False),    # below the floor
    (12.50, 25.00, 200_000, True),   # ceiling, inclusive
    (12.50, 25.01, 200_000, False),  # above it
    # volume: exactly the scaled floor, the other case float silently failed
    (3.00, 4.50, 55_200, True),
    (3.00, 4.50, 55_199, False),
])
def test_each_clause_at_its_boundary(prior, close, volume, expect):
    rows = frame([bar("AAA", "04:00", close, volume)])
    got = S.screen_at(rows, pd.Series({"AAA": prior}), at("05:00"))
    assert (len(got) == 1) is expect


# --- ranking ----------------------------------------------------------------

def test_ranked_by_change_and_capped():
    prior = pd.Series({c: 1.00 for c in "ABCDE"})
    rows = frame([bar(c, "04:00", px, 200_000)
                  for c, px in zip("ABCDE", [2.0, 5.0, 3.0, 4.0, 2.5])])
    got = S.screen_at(rows, prior, at("05:00"), S.ScreenConfig(max_symbols=3))
    assert list(got["symbol"]) == ["B", "D", "C"]
    assert list(got["rank"]) == [1, 2, 3]


def test_ties_break_by_symbol_so_the_cut_is_deterministic():
    """Two names at the same change is common on a 2-decimal figure. Without a
    tiebreak the top-N cut depends on row order, which changes with pandas and
    with how the archive was concatenated -- and the leak test above would then
    fail intermittently and be dismissed as flaky."""
    prior = pd.Series({"AAA": 1.00, "BBB": 1.00, "CCC": 1.00})
    rows = frame([bar(s, "04:00", 2.00, 200_000) for s in ("CCC", "AAA", "BBB")])
    cfg = S.ScreenConfig(max_symbols=2)
    first = S.screen_at(rows, prior, at("05:00"), cfg)
    shuffled = frame([bar(s, "04:00", 2.00, 200_000)
                      for s in ("BBB", "CCC", "AAA")])
    second = S.screen_at(shuffled, prior, at("05:00"), cfg)
    assert list(first["symbol"]) == ["AAA", "BBB"] == list(second["symbol"])


# --- DST, because the archive spans three changeovers -----------------------

@pytest.mark.parametrize("day,offset_h", [
    ("2026-08-04", 8),    # EDT, UTC-4 -> 04:00 ET = 08:00 UTC
    ("2026-01-14", 9),    # EST, UTC-5 -> 04:00 ET = 09:00 UTC
])
def test_the_session_open_follows_dst(day, offset_h):
    """A fixed -5 offset would move the window an hour for eight months of
    every year and quietly change what premarket_volume sums."""
    got = S.session_open_utc(at("06:00", day), S.ScreenConfig())
    assert got.hour == offset_h
    assert str(got.tz) == "UTC"


def test_the_window_is_built_from_ts_own_et_date():
    """At 00:30 UTC the ET date is the PREVIOUS calendar day. Taking the UTC
    date would open the window on the wrong session."""
    t = datetime(2026, 8, 5, 0, 30, tzinfo=UTC)      # = 2026-08-04 20:30 ET
    assert S.session_open_utc(t, S.ScreenConfig()).date().isoformat() \
        == "2026-08-04"


# --- inputs that are wrong rather than empty --------------------------------

def test_a_naive_timestamp_is_refused():
    rows = frame(passing_rows())
    with pytest.raises(ValueError, match="timezone-aware"):
        S.screen_at(rows, PRIOR, datetime(2026, 8, 4, 5, 0))


def test_a_naive_index_is_refused():
    rows = frame(passing_rows())
    rows.index = rows.index.tz_localize(None)
    with pytest.raises(ValueError, match="tz-aware"):
        S.screen_at(rows, PRIOR, at("05:00"))


def test_a_name_with_no_prior_close_is_dropped_not_treated_as_flat():
    """An unknown denominator is not a 0% move. Filling it would put every
    unmatched name at exactly the screen's boundary."""
    rows = frame([bar("ZZZ", "04:00", 4.50, 200_000)])
    assert S.premarket_features(rows, PRIOR, at("05:00")).empty


def test_a_zero_prior_close_does_not_divide():
    rows = frame([bar("AAA", "04:00", 4.50, 200_000)])
    assert S.premarket_features(rows, pd.Series({"AAA": 0.0}),
                                at("05:00")).empty


def test_an_empty_input_returns_an_empty_frame_with_the_columns():
    got = S.screen_at(frame(passing_rows()).iloc[:0], PRIOR, at("05:00"))
    assert got.empty
    assert "premarket_change" in got.columns and "rank" in got.columns
