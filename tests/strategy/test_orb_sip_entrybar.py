#!/usr/bin/env python3
"""strategy/orb/sip_entrybar.py -- the order of two prints inside one minute.

The whole ORB stocks-in-play result turns on this: a stop touched in the entry
minute either fired (the entry came first) or could not have (the low came
first, when no position existed). These tests are about that ordering and
nothing else.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.orb import sip as S
from strategy.orb import sip_entrybar as E

ET = "America/New_York"
DAY = "2025-03-05"


def seconds(rows):
    """rows: (second, o, h, l, c) inside 09:35."""
    idx = pd.to_datetime([f"{DAY} 09:35:{s:02d}" for s, *_ in rows]).tz_localize(ET)
    return pd.DataFrame({"open": [r[1] for r in rows], "high": [r[2] for r in rows],
                         "low": [r[3] for r in rows], "close": [r[4] for r in rows]},
                        index=idx)


def test_the_low_that_came_first_could_not_have_stopped_a_trade_that_did_not_exist():
    """The stop price trades at :05, the entry trigger is reached at :20. The
    minute bar shows both and the pessimistic reading books a loss; the
    seconds show the position was not open when the low printed."""
    sec = seconds([(0, 10.40, 10.45, 10.40, 10.42),
                   (5, 10.42, 10.44, 10.38, 10.40),      # 10.38 <= the eventual stop
                   (20, 10.55, 10.62, 10.55, 10.60),     # trigger 10.60 reached
                   (40, 10.60, 10.65, 10.58, 10.62)])
    verdict, entry, exit_px = E.classify(sec, S.LONG, 10.60, 0.10)
    assert verdict == E.BEFORE and exit_px is None
    assert entry == pytest.approx(10.60)


def test_a_low_after_the_entry_did_stop_it():
    sec = seconds([(0, 10.55, 10.62, 10.55, 10.60),      # entry at 10.60
                   (30, 10.58, 10.59, 10.44, 10.46)])    # then through 10.50
    verdict, entry, exit_px = E.classify(sec, S.LONG, 10.60, 0.10)
    assert verdict == E.AFTER and entry == pytest.approx(10.60)
    assert exit_px == pytest.approx(10.50)


def test_both_inside_one_second_is_unresolved_and_says_so():
    """One second is the finest the data goes. A second holding the trigger
    and the stop cannot be ordered, and pretending otherwise would be the same
    assumption one level down."""
    sec = seconds([(12, 10.50, 10.70, 10.40, 10.45)])
    verdict, _entry, exit_px = E.classify(sec, S.LONG, 10.60, 0.10)
    assert verdict == E.SAME and exit_px == pytest.approx(10.50)


def test_a_second_that_gapped_past_the_stop_fills_at_its_open():
    sec = seconds([(0, 10.60, 10.62, 10.59, 10.61),
                   (10, 10.30, 10.31, 10.20, 10.25)])
    verdict, _e, exit_px = E.classify(sec, S.LONG, 10.60, 0.10)
    assert verdict == E.AFTER and exit_px == pytest.approx(10.30)


def test_the_entry_second_itself_never_gaps_the_stop():
    """Amendment D, one resolution down: within the entry second the open
    precedes the entry, so a stop hit in that same second fills at the stop."""
    sec = seconds([(7, 10.20, 10.70, 10.35, 10.40)])
    verdict, entry, exit_px = E.classify(sec, S.LONG, 10.60, 0.10)
    assert verdict == E.SAME and entry == pytest.approx(10.60)
    assert exit_px == pytest.approx(10.50), "not 10.20, the pre-entry open"


def test_a_short_is_the_mirror():
    sec = seconds([(0, 9.95, 9.97, 9.88, 9.90),          # trigger 9.90 reached
                   (20, 9.92, 10.05, 9.92, 10.02)])      # stop 10.00 taken out
    verdict, entry, exit_px = E.classify(sec, S.SHORT, 9.90, 0.10)
    assert verdict == E.AFTER and entry == pytest.approx(9.90)
    assert exit_px == pytest.approx(10.00)


def test_a_minute_with_no_seconds_is_counted_not_guessed():
    verdict, entry, exit_px = E.classify(seconds([]), S.LONG, 10.6, 0.1)
    assert verdict == E.NO_DATA and exit_px is None
    never = seconds([(0, 10.0, 10.1, 9.9, 10.0)])
    assert E.classify(never, S.LONG, 10.60, 0.10)[0] == E.NO_DATA


# --------------------------------------------------------------------------
# selecting the trades to price
# --------------------------------------------------------------------------

def ledger_rows(rows):
    out = []
    for i, r in enumerate(rows):
        base = {"date": DAY, "symbol": f"S{i:02d}", "range": 5, "side": 1,
                "rvol": 5.0, "rank": 1.0, "eligible": True, "atr": 1.0,
                "entry_min": 575, "entry_px": 10.6, "exit_min": 575,
                "exit_px": 10.5, "exit_reason": "stop", "r": 0.1,
                "bars_held": 0, "gapped_entry": False, "or_high": 10.6,
                "or_low": 10.0, "alt_exit_min": 959, "alt_exit_px": 10.9,
                "alt_exit_reason": "session_end"}
        base.update(r)
        out.append(base)
    return pd.DataFrame(out)


def test_only_top_twenty_five_minute_entry_bar_stops_are_selected():
    led = ledger_rows([
        {},                                             # the case
        {"exit_min": 600},                              # stopped later
        {"exit_reason": "session_end"},                 # not stopped
        {"rank": 25.0},                                 # outside the top 20
        {"range": 15},                                  # the secondary length
    ])
    got = E.entry_bar_stops(led)
    assert len(got) == 1 and got.iloc[0]["symbol"] == "S00"


def test_the_pairs_file_is_unique_symbol_days_in_fetch_format(tmp_path):
    led = ledger_rows([{"symbol": "AAA"}, {"symbol": "AAA"},
                       {"symbol": "BBB", "date": "2025-03-06"}])
    out = tmp_path / "p.json"
    n = E.write_pairs(E.entry_bar_stops(led), out)
    import json
    rows = json.loads(out.read_text(encoding="utf-8"))
    assert n == 2 and rows == [{"symbol": "AAA", "date": DAY},
                               {"symbol": "BBB", "date": "2025-03-06"}]


def test_counts_report_every_bucket():
    res = pd.DataFrame({"symbol": list("abcd"), "date": [DAY] * 4,
                        "verdict": [E.AFTER, E.BEFORE, E.SAME, E.NO_DATA],
                        "sec_entry_px": 1.0, "sec_exit_px": 1.0})
    c = E.counts(res)
    assert (c["entry_first"], c["stop_first"], c["same_second"], c["no_seconds"]) == (1, 1, 1, 1)
    assert c["share_entry_first"] == pytest.approx(0.25)
