#!/usr/bin/env python3
"""Which condition blocked an entry.

The module's whole value is that it names a cause, so the failure that matters
is naming the WRONG one confidently. Two ways that happens, and both are
tested: a cold start where the volume floor is NaN and reads as False on every
early bar, and a bar failing four conditions being counted as evidence against
each of them.
"""
from __future__ import annotations

import math
from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from common import why_no_entry as W
from strategy.mcl import mcl as MCL

ET = ZoneInfo("America/New_York")
D = date(2026, 3, 2)


def frame(days=2, n=330, period=40, amp=0.30, drift=0.004,
          base_v=40_000.0, spike=130_000.0):
    idx = []
    for k in range(days, 0, -1):
        b = pd.Timestamp(datetime.combine(D - timedelta(days=k - 1),
                                          dtime(4, 0), tzinfo=ET))
        idx += [(b + timedelta(minutes=i)).tz_convert("UTC") for i in range(n)]
    idx = pd.DatetimeIndex(idx)
    close = [4.0 + drift * i + amp * math.sin(2 * math.pi * i / period)
             for i in range(len(idx))]
    vol = [spike if i % 3 == 0 else base_v for i in range(len(idx))]
    return pd.DataFrame({"symbol": "AAA", "open": close,
                         "high": [c + 0.02 for c in close],
                         "low": [c - 0.02 for c in close],
                         "close": close, "volume": vol}, index=idx)


def run(df, warmup=330, lo=dtime(4, 0), hi=dtime(9, 30)):
    sig = MCL.signals(df, require_macd_pos=True)
    conds = ("c_macd", "c_mfi", "c_rsi", "c_vol", "c_floor")
    recs = W.rows(sig, D.isoformat(), MCL, conds, lo, hi)
    return "\n".join(W.render("mcl", "AAA", D.isoformat(), recs, conds,
                              warmup, lo, hi, MCL)), recs


# --- the cold-start guard ---------------------------------------------------

def test_a_frame_with_no_warm_up_refuses_to_diagnose():
    """`c_floor` is a 60-bar shifted mean. Cold, it is NaN, renders as False,
    and would be named as the blocker on every early bar -- confidently and
    wrongly. Refusing is the only honest output."""
    out, _ = run(frame(days=1), warmup=0)
    assert "REFUSING TO DIAGNOSE" in out
    assert "cold start" in out
    assert "SOLE blocker" not in out


def test_the_threshold_is_the_longest_lookback():
    assert W.MIN_WARMUP_BARS >= MCL.FLOOR_AVG_LEN


def test_enough_warm_up_produces_a_diagnosis():
    out, _ = run(frame())
    assert "REFUSING TO DIAGNOSE" not in out
    assert "WHO BLOCKED IT" in out


def test_load_bars_counts_only_bars_BEFORE_the_session(tmp_path):
    df = frame()
    p = tmp_path / "b.csv"
    df.to_csv(p)
    _, warmup = W.load_bars("AAA", D.isoformat(), source="cache",
                            cache=tmp_path, archive=tmp_path,
                            dataset="XNAS.BASIC", csv=str(p))
    assert warmup == 330, "warm-up count included the session's own bars"


# --- sole blocker vs blocked-at-all -----------------------------------------

def test_a_bar_failing_four_conditions_is_not_charged_to_any_one_of_them():
    """Only the sole-blocker column is diagnostic. If a four-way failure
    incremented the sole count, the most fragile condition would look like the
    cause of every quiet minute in the session."""
    out, recs = run(frame())
    many = [r for r in recs if len(r["failed"]) > 1]
    assert many, "fixture has no multi-failure bars; the test proves nothing"
    sole_line = [ln for ln in out.splitlines() if ln.strip().startswith("c_")]
    assert sole_line
    total_sole = sum(int(ln.split()[1].replace(",", "")) for ln in sole_line)
    assert total_sole == sum(1 for r in recs
                             if not r["entry"] and len(r["failed"]) == 1)


def test_the_two_columns_are_reported_separately_and_explained():
    out, _ = run(frame())
    assert "SOLE blocker" in out and "blocked at all" in out
    assert "is not evidence against any one of them" in out


def test_each_condition_is_printed_with_the_rule_in_its_own_terms():
    out, _ = run(frame())
    for c in ("c_macd", "c_mfi", "c_rsi", "c_vol", "c_floor"):
        assert c in out
    assert f"{MCL.VOL_MULTIPLE:g}x the PREVIOUS" in out
    assert str(MCL.FLOOR_AVG_LEN) in out


# --- the window -------------------------------------------------------------

def test_the_window_lists_every_bar_with_its_blockers():
    out, _ = run(frame(), lo=dtime(7, 20), hi=dtime(7, 25))
    assert "07:20" in out and "07:25" in out
    assert "07:19" not in out


def test_an_empty_window_says_so_rather_than_printing_nothing():
    out, _ = run(frame(), lo=dtime(10, 0), hi=dtime(10, 5))
    assert "No in-session bars in that window" in out


def test_bars_that_fired_are_marked_ENTRY_not_blamed_on_a_condition():
    out, recs = run(frame())
    fired = [r for r in recs if r["entry"]]
    assert fired, "fixture never enters"
    assert "entry signal fired on" in out
    for r in fired:
        assert r["failed"] == []


# --- the caveats ------------------------------------------------------------

def test_the_report_refuses_to_claim_a_trade_would_have_happened():
    """A near miss is not a foregone trade: position state, the shared cap and
    the broker all sit between a signal and a fill."""
    out, _ = run(frame())
    assert "does not say a trade would have happened" in out
    assert "position cap" in out and "29%" in out


def test_only_session_bars_are_examined():
    """A blocker counted on a warm-up day's bar would be attributed to a
    session the strategy never traded."""
    _, recs = run(frame())
    for r in recs:
        assert r["t"].date() == D
        assert MCL.SESSION_START <= r["t"].time() < MCL.SESSION_END


def test_an_unknown_strategy_exits_rather_than_guessing():
    with pytest.raises(SystemExit):
        W.engine("vw9")


# --- the Databento source ---------------------------------------------------

def test_the_archive_source_prepends_the_prior_session_for_warm_up(monkeypatch,
                                                                   tmp_path):
    """A 04:00 session has nothing behind it, so the prior slice is what makes
    the 60-bar volume floor computable at all."""
    import common.dbn_io as DIO
    import common.screen_sim as SS
    from pathlib import Path

    df = frame(days=2)
    day0, day1 = sorted(set(df.index.tz_convert(ET).date))
    by = {str(d): df[df.index.tz_convert(ET).date == d] for d in (day0, day1)}
    paths = [Path(f"{d}_0400_0930.dbn.zst") for d in by]
    monkeypatch.setattr(SS, "window_slices", lambda a, ds: paths)
    monkeypatch.setattr(SS, "date_of", lambda p: p.name[:10])
    monkeypatch.setattr(DIO, "read_dbn", lambda p: by[p.name[:10]])

    got = W.from_archive("AAA", str(day1), tmp_path, "XNAS.BASIC")
    local = got.index.tz_convert(ET)
    assert set(local.date) == {day0, day1}, "prior session was not prepended"
    assert (local.date < day1).sum() >= W.MIN_WARMUP_BARS


def test_a_date_outside_the_archive_names_the_pull_command(monkeypatch,
                                                          tmp_path):
    import common.screen_sim as SS
    from pathlib import Path
    monkeypatch.setattr(SS, "window_slices",
                        lambda a, ds: [Path("2026-09-03_0400_0930.dbn.zst")])
    monkeypatch.setattr(SS, "date_of", lambda p: p.name[:10])
    with pytest.raises(SystemExit) as e:
        W.from_archive("AAA", "2026-09-11", tmp_path, "XNAS.BASIC")
    assert "databento_universe" in str(e.value)


def test_a_symbol_absent_from_the_tape_is_not_read_as_untraded(monkeypatch,
                                                               tmp_path):
    import common.dbn_io as DIO
    import common.screen_sim as SS
    from pathlib import Path
    df = frame(days=1)
    monkeypatch.setattr(SS, "window_slices",
                        lambda a, ds: [Path(f"{D}_0400_0930.dbn.zst")])
    monkeypatch.setattr(SS, "date_of", lambda p: p.name[:10])
    monkeypatch.setattr(DIO, "read_dbn", lambda p: df)
    with pytest.raises(SystemExit) as e:
        W.from_archive("ZZZ", D.isoformat(), tmp_path, "XNAS.BASIC")
    assert "not the same as a name that did not trade" in str(e.value)


def test_the_archive_report_says_these_are_not_the_live_traders_bars():
    """IB's feed against XNAS.BASIC at 55.2% capture. The report must say so,
    and say why a RATIO condition survives it where an absolute one would not."""
    out, _ = run(frame())
    out = "\n".join(W.render("mcl", "AAA", D.isoformat(),
                             W.rows(MCL.signals(frame(), require_macd_pos=True),
                                    D.isoformat(), MCL,
                                    ("c_macd", "c_mfi", "c_rsi", "c_vol",
                                     "c_floor"), dtime(4, 0), dtime(9, 30)),
                             ("c_macd", "c_mfi", "c_rsi", "c_vol", "c_floor"),
                             330, dtime(4, 0), dtime(9, 30), MCL,
                             source="archive"))
    assert "NOT THE BARS THE LIVE TRADER SAW" in out
    assert "RATIOS" in out and "1.8x" in out


def test_the_cache_source_does_not_carry_the_tape_caveat():
    out = "\n".join(W.render("mcl", "AAA", D.isoformat(), [],
                             ("c_macd",), 330, dtime(4, 0), dtime(9, 30), MCL,
                             source="cache"))
    assert "NOT THE BARS THE LIVE TRADER SAW" not in out
    assert "bars from: cache" in out
