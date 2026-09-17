#!/usr/bin/env python3
"""The change-threshold study: the universe side, and the guard that keeps a
variant threshold out of the deciding universe file."""
from __future__ import annotations

import re

from datetime import date, datetime, time as dtime
from zoneinfo import ZoneInfo

import pytest

from common import change_threshold as C
from common import screen_sim as S
from common.screen_at import ScreenConfig
from common.tv_screener import PREMARKET_CHANGE_MIN

ET = ZoneInfo("America/New_York")
DAY = date(2026, 3, 2)
import pandas as pd


def rec(symbol, hhmm="04:00", day=DAY):
    hh, mm = map(int, hhmm.split(":"))
    fs = pd.Timestamp(datetime.combine(day, dtime(hh, mm), tzinfo=ET)).tz_convert("UTC").isoformat()
    return {"symbol": symbol, "date": day.isoformat(), "first_seen": fs}


def trade(symbol, net, day=DAY, ordinal=1, entry="04:30"):
    return {"symbol": symbol, "date": day.isoformat(), "ordinal": ordinal,
            "net": float(net), "entry_et": entry, "entry_px": 5.0,
            "exit_et": "05:00", "exit_px": 5.1, "reason": "trail", "bars_held": 3}


# --- the guard ----------------------------------------------------------------------

def test_variant_threshold_refuses_the_deciding_universe_file():
    msg = S.change_min_refusal(50.0, S.DECIDING_OUT)
    assert msg and "50" in msg and S.DECIDING_OUT in msg


def test_variant_threshold_allows_any_other_file():
    assert S.change_min_refusal(50.0, "var/state/screen_pairs_pit_chg50.json") is None


def test_the_shipped_threshold_is_not_refused():
    assert S.change_min_refusal(PREMARKET_CHANGE_MIN, S.DECIDING_OUT) is None
    assert S.change_min_refusal(None, S.DECIDING_OUT) is None


def test_windows_spelling_of_the_deciding_path_is_still_refused():
    win = S.DECIDING_OUT.replace("/", "\\")
    assert S.change_min_refusal(50.0, win) is not None


def test_cli_override_reaches_the_config_and_the_default_does_not_move():
    a = S.build_parser().parse_args(["--change-min", "50"])
    assert a.change_min == 50.0
    assert ScreenConfig().change_min is PREMARKET_CHANGE_MIN


# --- the universe side --------------------------------------------------------------

def test_floor_shift_is_minutes_later_and_signed():
    a, b = rec("AAA", "04:10"), rec("AAA", "07:40")
    assert C.floor_shift_minutes(a, b) == pytest.approx(210.0)
    assert C.floor_shift_minutes(b, a) == pytest.approx(-210.0)


def test_universe_block_counts_kept_dropped_and_flags_added():
    base = [rec("AAA"), rec("BBB"), rec("CCC")]
    var = [rec("AAA", "06:00"), rec("DDD")]
    out = "\n".join(C.universe_block("chg>=20%", "chg>=50%", base, var))
    assert "kept 1" in out
    assert "dropped 2" in out
    # DDD is in the variant and not the baseline, which a tighter screen
    # cannot do -- the block must say so rather than absorb it.
    assert "ADDED symbol-days" in out


def test_universe_block_is_silent_about_added_when_there_are_none():
    base = [rec("AAA"), rec("BBB")]
    var = [rec("AAA", "06:00")]
    out = "\n".join(C.universe_block("chg>=20%", "chg>=50%", base, var))
    assert "ADDED symbol-days" not in out
    assert "moved later 1 of 1" in out


def test_dropped_block_splits_losses_avoided_from_winners_lost():
    base_rows = [trade("AAA", 100.0), trade("BBB", -50.0), trade("CCC", 30.0)]
    out = "\n".join(C.dropped_block("MCL@20", "MCL@50", base_rows,
                                    [rec("AAA"), rec("BBB"), rec("CCC")],
                                    [rec("AAA")]))
    # BBB and CCC were dropped: one loser at -50, one winner at 30 - 4.26.
    squash = re.sub(r"[ \t]+", " ", out)
    assert "symbol-days removed 2" in squash
    assert "losses avoided 1 (54.26)" in squash
    assert "winners lost 1 25.74" in squash


def test_survivor_block_separates_shared_trades_from_new_ones():
    base_rows = [trade("AAA", 10.0), trade("BBB", -20.0)]
    var_rows = [trade("AAA", 10.0), trade("AAA", 5.0, ordinal=2, entry="06:00")]
    squash = re.sub(r"[ \t]+", " ", "\n".join(
        C.survivor_block("MCL@20", "MCL@50", base_rows, var_rows)))
    assert "shared 1 of 2" in squash
    assert "new 1 " in squash


def test_a_later_floor_makes_the_variant_not_a_subset():
    """The property the module exists for: same symbol-day, later floor, a
    trade the baseline does not contain."""
    base_rows = [trade("AAA", -10.0, entry="04:30")]
    var_rows = [trade("AAA", 7.0, entry="07:45")]
    squash = re.sub(r"[ \t]+", " ", "\n".join(
        C.survivor_block("MCL@20", "MCL@50", base_rows, var_rows)))
    assert "shared 0 of 1" in squash


# --- the decomposition --------------------------------------------------------------

def test_decomposition_partitions_the_baseline_and_lands_on_the_variant():
    """Every baseline trade is in exactly one of the two subtracted rows, and
    the arithmetic closes on the variant's book."""
    base = [trade("AAA", 10.0, entry="04:30"),      # kept name, kept by the floor
            trade("AAA", 50.0, entry="04:05", ordinal=2),   # kept name, lost to the floor
            trade("BBB", -30.0)]                    # dropped symbol-day
    var = [trade("AAA", 10.0, entry="04:30"),
           trade("AAA", -8.0, entry="07:50", ordinal=3)]    # new after the floor
    out = "\n".join(C.decomposition_block("MCL@20", "MCL@50", base, var, [rec("AAA")]))
    squash = re.sub(r"[ \t]+", " ", out)
    assert "MCL@20 whole book 3" in squash
    assert "- symbol-days dropped 1" in squash
    assert "= names the screen keeps 2" in squash
    assert "- lost to the floor 1" in squash
    assert "+ new after the floor 1" in squash
    assert "= MCL@50 whole book 2" in squash
    assert "NOT A TRADEABLE ARM" in out


def test_decomposition_names_the_look_ahead_it_prices():
    base = [trade("AAA", 1.0)]
    out = "\n".join(C.decomposition_block("MCL@20", "MCL@50", base, base, [rec("AAA")]))
    assert "SELECTION" in out and "COST OF WAITING" in out
