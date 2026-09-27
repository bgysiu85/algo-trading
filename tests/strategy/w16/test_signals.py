#!/usr/bin/env python3
"""B1 (ORB), B2 (overnight), B3 (VWAP flip) rule logic, and gate G4's
look-ahead guards: each proven not to use a bar before it closes, by a test
a one-bar shift (in timing, or in which bar a value is read from) breaks.
REGISTERED_w16_session_baselines.md sec 3 (the rules) and sec 6.3 (G4)."""
from __future__ import annotations

from zoneinfo import ZoneInfo

import pandas as pd
import pytest

import strategy.w16.signals as SIG

ET = ZoneInfo("America/New_York")


def _bars(date: str, rows, held_id=1):
    """rows: list of (hh, mm, open, high, low, close, volume)."""
    idx, data = [], []
    for hh, mm, o, h, l, c, v in rows:
        ts = pd.Timestamp(f"{date} {hh:02d}:{mm:02d}:00", tz=ET)
        idx.append(ts)
        data.append({"open": o, "high": h, "low": l, "close": c, "volume": v,
                    "held_id": held_id})
    df = pd.DataFrame(data, index=pd.DatetimeIndex(idx).tz_convert("UTC"))
    return df


def _opening_range(date, *, h=100.0, l=99.0, minute_open=99.5):
    """30 bars, 09:30..09:59, high=h, low=l, everything else tame."""
    rows = []
    for i, m in enumerate(range(30, 60)):
        rows.append((9, m, minute_open, h if i == 0 else minute_open + 0.01,
                    l if i == 1 else minute_open - 0.01, minute_open, 100))
    return rows


# ---------------------------------------------------------------------
# B1 -- basic outcomes
# ---------------------------------------------------------------------

def test_orb_long_hits_target():
    date = "2024-06-06"
    rows = _opening_range(date)                                   # H=100, L=99
    rows += [(10, 0, 99.5, 100.5, 99.4, 100.2, 50)]                # trigger: close 100.2 > H
    rows += [(10, 1, 100.3, 100.4, 100.2, 100.35, 50)]             # fill bar: open=100.3
    # stop = L = 99, dist = 100.3-99 = 1.3, target = 100.3 + 2*1.3 = 102.9
    rows += [(10, 2, 100.4, 101.0, 100.3, 100.9, 50)]
    rows += [(10, 3, 100.9, 103.2, 100.8, 101.0, 50)]              # high clears target+tick (target=102.9, tick=0.25)
    for m in range(4, 350):
        rows.append((10 + (30 + m) // 60, (30 + m) % 60, 101, 101, 101, 101, 10))
    df = _bars(date, rows)
    res = SIG.orb_session(df, date, market="ES")
    assert not res["skipped"]
    assert res["range_high"] == pytest.approx(100.0)
    assert res["range_low"] == pytest.approx(99.0)
    trade = res["trade"]
    assert trade is not None and not trade["voided"]
    assert trade["direction"] == "long"
    assert trade["fill_price"] == pytest.approx(100.3)
    assert trade["stop"] == pytest.approx(99.0)
    assert trade["target"] == pytest.approx(100.3 + 2 * 1.3)
    assert trade["exit_reason"] == "target"
    assert trade["exit_price"] == pytest.approx(trade["target"])
    assert trade["exit_fill_kind"] == "target"


def test_orb_short_hits_stop_with_gap_fill():
    date = "2024-06-06"
    rows = _opening_range(date)                                   # H=100, L=99
    rows += [(10, 0, 99.5, 99.6, 98.9, 98.8, 50)]                  # trigger: close 98.8 < L
    rows += [(10, 1, 98.7, 98.8, 98.5, 98.6, 50)]                  # fill bar: open=98.7 (short)
    # stop = H = 100, so short stop at 100; next bar gaps OPEN through 100
    rows += [(10, 2, 100.5, 100.6, 98.6, 98.6, 50)]                # opens beyond stop (>=100)
    for m in range(3, 350):
        rows.append((10 + (30 + m) // 60, (30 + m) % 60, 101, 101, 101, 101, 10))
    df = _bars(date, rows)
    res = SIG.orb_session(df, date, market="ES")
    trade = res["trade"]
    assert trade["direction"] == "short"
    assert trade["exit_reason"] == "stop"
    assert trade["exit_price"] == pytest.approx(100.5)             # gap fill at bar's OPEN, not the stop level
    assert trade["exit_fill_kind"] == "market_or_stop"


def test_orb_stop_without_gap_fills_at_stop_level():
    date = "2024-06-06"
    rows = _opening_range(date)
    rows += [(10, 0, 99.5, 99.6, 98.9, 98.8, 50)]
    rows += [(10, 1, 98.7, 98.8, 98.5, 98.6, 50)]                  # short fill at 98.7
    rows += [(10, 2, 99.0, 100.2, 98.9, 100.1, 50)]                # opens below stop(100), high pierces it
    for m in range(3, 350):
        rows.append((10 + (30 + m) // 60, (30 + m) % 60, 101, 101, 101, 101, 10))
    df = _bars(date, rows)
    res = SIG.orb_session(df, date, market="ES")
    trade = res["trade"]
    assert trade["exit_reason"] == "stop"
    assert trade["exit_price"] == pytest.approx(100.0)             # exact stop level, no gap


def test_orb_time_exit_when_neither_stop_nor_target_hit():
    date = "2024-06-06"
    rows = _opening_range(date)
    rows += [(10, 0, 99.5, 100.5, 99.4, 100.2, 50)]
    rows += [(10, 1, 100.3, 100.4, 100.2, 100.35, 50)]             # long fill at 100.3
    m = 2
    while True:
        hh, mm = 10 + (30 + m) // 60, (30 + m) % 60
        if (hh, mm) == (15, 30):
            rows.append((hh, mm, 100.6, 100.7, 100.5, 100.6, 40))  # time-exit bar: open=100.6
            break
        rows.append((hh, mm, 100.3, 100.31, 100.29, 100.3, 40))    # flat, no stop/target hit
        m += 1
    df = _bars(date, rows)
    res = SIG.orb_session(df, date, market="ES")
    trade = res["trade"]
    assert trade["exit_reason"] == "time_exit"
    assert trade["exit_price"] == pytest.approx(100.6)


def test_orb_void_when_fill_gaps_beyond_stop():
    date = "2024-06-06"
    rows = _opening_range(date)                                   # H=100, L=99
    rows += [(10, 0, 99.5, 100.5, 99.4, 100.2, 50)]                # trigger long
    rows += [(10, 1, 98.5, 100.4, 98.4, 99.0, 50)]                 # fill bar opens BELOW stop(99)
    df = _bars(date, rows)
    res = SIG.orb_session(df, date, market="ES")
    trade = res["trade"]
    assert trade["voided"] and "beyond stop" in trade["void_reason"]


def test_orb_no_trigger_in_entry_window():
    date = "2024-06-06"
    rows = _opening_range(date)
    for m in range(0, 350):
        rows.append((10 + m // 60, m % 60, 99.5, 99.6, 99.4, 99.5, 10))  # never breaks out
    df = _bars(date, rows)
    res = SIG.orb_session(df, date, market="ES")
    assert res["trade"] is None
    assert res["range_high"] == pytest.approx(100.0)


def test_orb_skipped_on_invalid_open():
    date = "2024-06-06"
    rows = [(9, m, 100, 100, 100, 100, 10) for m in range(35, 60)]  # missing 09:30
    df = _bars(date, rows)
    res = SIG.orb_session(df, date, market="ES")
    assert res["skipped"]
    assert res["trade"] is None


def test_orb_stop_wins_over_target_on_same_bar():
    date = "2024-06-06"
    rows = _opening_range(date)
    rows += [(10, 0, 99.5, 100.5, 99.4, 100.2, 50)]
    rows += [(10, 1, 100.3, 100.4, 100.2, 100.35, 50)]             # long fill 100.3, stop=99, target=102.9
    rows += [(10, 2, 100.4, 103.0, 98.9, 99.5, 50)]                # same bar: high clears target AND low breaches stop
    for m in range(3, 350):
        rows.append((10 + (30 + m) // 60, (30 + m) % 60, 101, 101, 101, 101, 10))
    df = _bars(date, rows)
    res = SIG.orb_session(df, date, market="ES")
    trade = res["trade"]
    assert trade["exit_reason"] == "stop"


# ---------------------------------------------------------------------
# B1 -- G4 look-ahead guards
# ---------------------------------------------------------------------

def test_orb_range_ignores_bars_at_or_after_1000():
    """A bar at 10:00 with an extreme high must NOT enlarge the opening
    range -- if it did, this extreme high would sit inside H and no
    breakout could trigger off a modest close; the assertion that a trigger
    DOES fire, and at the modest H, is only possible if the 10:00 bar was
    excluded from the range calc."""
    date = "2024-06-06"
    rows = _opening_range(date, h=100.0, l=99.0)
    rows += [(10, 0, 99.5, 500.0, 99.4, 100.2, 50)]   # huge high at 10:00 -- must not move H
    rows += [(10, 1, 100.3, 100.4, 100.2, 100.35, 50)]
    for m in range(2, 350):
        rows.append((10 + (30 + m) // 60, (30 + m) % 60, 101, 101, 101, 101, 10))
    df = _bars(date, rows)
    res = SIG.orb_session(df, date, market="ES")
    assert res["range_high"] == pytest.approx(100.0)          # NOT 500.0
    assert res["trade"]["direction"] == "long"


def test_orb_fills_at_next_bar_open_not_trigger_close():
    """The fill price must be the NEXT bar's open, not the trigger bar's own
    close -- a one-bar shift in fill timing would produce fill_price ==
    100.2 (the trigger's close) instead of 100.3 (the next bar's open)."""
    date = "2024-06-06"
    rows = _opening_range(date, h=100.0, l=99.0)
    rows += [(10, 0, 99.5, 100.5, 99.4, 100.2, 50)]    # trigger, close=100.2
    rows += [(10, 1, 100.3, 100.4, 100.2, 100.35, 50)]  # next bar, open=100.3
    for m in range(2, 350):
        rows.append((10 + (30 + m) // 60, (30 + m) % 60, 101, 101, 101, 101, 10))
    df = _bars(date, rows)
    trade = SIG.orb_session(df, date, market="ES")["trade"]
    assert trade["fill_price"] == pytest.approx(100.3)
    assert trade["fill_price"] != pytest.approx(100.2)


def test_orb_stop_target_never_read_from_a_bar_before_the_fill():
    """The trigger bar itself (index fill_idx - 1) has a low that breaches
    the eventual stop level; if the exit walk incorrectly started one bar
    early, it would report an immediate stop exit. It must instead reach
    the target on a later bar."""
    date = "2024-06-06"
    rows = _opening_range(date, h=100.0, l=99.0)
    rows += [(10, 0, 99.5, 100.5, 98.0, 100.2, 50)]      # trigger bar: low=98.0, BELOW the stop(99)
    rows += [(10, 1, 100.3, 100.4, 100.2, 100.35, 50)]   # fill bar, stop=99, target=100.3+2*1.3=102.9
    rows += [(10, 2, 100.4, 103.2, 100.3, 102.0, 50)]    # clears target (target=102.9, tick=0.25)
    for m in range(3, 350):
        rows.append((10 + (30 + m) // 60, (30 + m) % 60, 101, 101, 101, 101, 10))
    df = _bars(date, rows)
    trade = SIG.orb_session(df, date, market="ES")["trade"]
    assert trade["exit_reason"] == "target"


# ---------------------------------------------------------------------
# B2 -- overnight hold
# ---------------------------------------------------------------------

def _one_bar(date, hh, mm, price, held_id=1):
    return _bars(date, [(hh, mm, price, price, price, price, 10)], held_id=held_id)


def test_overnight_trade_basic():
    day = _one_bar("2024-06-06", 15, 59, 100.0)
    next_day = pd.concat([_one_bar("2024-06-07", 9, 30, 101.0),
                         _one_bar("2024-06-07", 9, 31, 101.5)])
    res = SIG.overnight_trade(day, next_day, "2024-06-06", "2024-06-07", market="ES")
    trade = res["trade"]
    assert not trade["voided"]
    assert trade["entry_price"] == pytest.approx(100.0)
    assert trade["exit_price"] == pytest.approx(101.0)   # the 09:30 OPEN, not a later bar


def test_overnight_trade_voided_on_roll():
    day = _one_bar("2024-06-06", 15, 59, 100.0, held_id=1)
    next_day = _one_bar("2024-06-07", 9, 30, 101.0, held_id=2)
    res = SIG.overnight_trade(day, next_day, "2024-06-06", "2024-06-07", market="ES")
    assert res["trade"]["voided"]
    assert "roll" in res["trade"]["void_reason"]


def test_overnight_trade_skipped_on_missing_session():
    empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume", "held_id"])
    next_day = _one_bar("2024-06-07", 9, 30, 101.0)
    res = SIG.overnight_trade(empty, next_day, "2024-06-06", "2024-06-07", market="ES")
    assert res["skipped"]


# ---------------------------------------------------------------------
# B3 -- VWAP flip
# ---------------------------------------------------------------------

def test_vwap_flip_basic_sequence_and_flat_at_close():
    date = "2024-06-06"
    rows = []
    # First 5 bars: price well above a low VWAP anchor -> should flip long
    rows.append((9, 30, 100.0, 100.0, 100.0, 100.0, 100))
    rows.append((9, 31, 110.0, 110.0, 110.0, 110.0, 100))   # close(110) > vwap(~105) -> signal long at bar 1
    rows.append((9, 32, 111.0, 111.0, 111.0, 111.0, 100))   # fill bar for the long entry (open=111)
    for m in range(33, 60):
        rows.append((9, m, 111.0, 111.0, 111.0, 111.0, 100))
    for h in range(10, 16):
        for m in range(0, 60):
            if h == 15 and m > 59:
                continue
            rows.append((h, m, 111.0, 111.0, 111.0, 111.0, 100))
    df = _bars(date, rows)
    res = SIG.vwap_flip_session(df, date, market="ES")
    assert not res["skipped"]
    assert res["n_flips"] == 1
    trades = SIG.pair_b3_legs(res["legs"])
    assert len(trades) == 1
    t = trades[0]
    assert t["direction"] == "long"
    assert t["entry_price"] == pytest.approx(111.0)
    assert t["exit_reason"] == "flat_at_close"
    assert t["exit_price"] == pytest.approx(111.0)


def test_vwap_signal_uses_only_bars_up_to_and_including_t():
    """A later bar's price must not affect an earlier bar's VWAP-cross
    decision -- change bar 300 (mid-afternoon) drastically and the FIRST
    flip's timing/direction must be identical."""
    date = "2024-06-06"

    def build(late_price):
        rows = [(9, 30, 100.0, 100.0, 100.0, 100.0, 100)]
        rows.append((9, 31, 110.0, 110.0, 110.0, 110.0, 100))
        for i in range(2, 389):
            hh, mm = 9 + (30 + i) // 60, (30 + i) % 60
            price = late_price if i == 300 else 110.0
            rows.append((hh, mm, price, price, price, price, 100))
        return _bars(date, rows)

    res_a = SIG.vwap_flip_session(build(110.0), date, market="ES")
    res_b = SIG.vwap_flip_session(build(9999.0), date, market="ES")
    first_a = SIG.pair_b3_legs(res_a["legs"])[0]
    first_b = SIG.pair_b3_legs(res_b["legs"])[0]
    assert first_a["entry_time"] == first_b["entry_time"]
    assert first_a["direction"] == first_b["direction"]
