#!/usr/bin/env python3
"""Does the churn count pair trades correctly, and refuse to overstate?

Two failure modes matter here.

The first is MECHANICAL: the rows under investigation are a sell and a buy in
the SAME SECOND, so anything that re-sorts on the timestamp can swap them and
silently destroy the evidence. `round_trips` walks file order for that reason
and these tests pin it.

The second is RHETORICAL. Three overlapping measures of the same behaviour
invite a headline that adds them. A trade that is reused AND instant AND
sub-minute would then be counted three times, producing a loss larger than the
session it came from.
"""
from __future__ import annotations

import pandas as pd
import pytest

from common import churn_count as C

COLS = ["ts_et", "strategy", "symbol", "action", "status", "trade_pnl",
        "hold_minutes", "ref_close", "macd", "macd_sig", "rsi", "vol"]


def f(rows):
    d = pd.DataFrame(rows, columns=COLS)
    d["ts_et"] = pd.to_datetime(d["ts_et"])
    return d


def buy(ts, ref=7.5, sym="AAA", st="MC5"):
    return [ts, st, sym, "BUY", "FILLED", None, None, ref, 0.1, 0.05, 70.0,
            1000]


def sell(ts, pnl, hold, sym="AAA", st="MC5"):
    return [ts, st, sym, "SELL", "FILLED", pnl, hold, 7.4, 0.1, 0.05, 70.0,
            1000]


# --- pairing ----------------------------------------------------------------

def test_a_simple_round_trip_is_paired():
    t = C.round_trips(f([buy("2026-09-11 04:00:00"),
                         sell("2026-09-11 04:10:00", 25.0, 10.0)]))
    assert len(t) == 1
    assert t.pnl.iloc[0] == 25.0


def test_a_sell_and_a_buy_in_the_SAME_SECOND_keep_their_file_order():
    """The TNON 07:47:25 shape. If these swap, the re-entry disappears and so
    does the finding."""
    t = C.round_trips(f([
        buy("2026-09-11 07:41:00", ref=7.82),
        sell("2026-09-11 07:47:25", 90.62, 6.4),
        buy("2026-09-11 07:47:25", ref=7.90),
        sell("2026-09-11 07:48:23", -59.38, 1.0)]))
    assert len(t) == 2
    assert list(t.pnl) == [90.62, -59.38]
    assert t.since_prev_exit_s.iloc[1] == 0.0
    assert bool(t.instant.iloc[1]) is True


def test_the_first_trade_in_a_name_has_no_previous_exit():
    t = C.round_trips(f([buy("2026-09-11 04:00:00"),
                         sell("2026-09-11 04:10:00", 1.0, 10.0)]))
    assert t.since_prev_exit_s.iloc[0] is None
    assert bool(t.instant.iloc[0]) is False


def test_an_unclosed_position_is_not_invented_as_a_trade():
    t = C.round_trips(f([buy("2026-09-11 04:00:00")]))
    assert t.empty


def test_trades_in_different_names_do_not_pair_with_each_other():
    t = C.round_trips(f([buy("2026-09-11 04:00:00", sym="AAA"),
                         buy("2026-09-11 04:00:30", sym="BBB"),
                         sell("2026-09-11 04:05:00", 5.0, 5.0, sym="BBB"),
                         sell("2026-09-11 04:09:00", 9.0, 9.0, sym="AAA")]))
    assert set(zip(t.symbol, t.pnl)) == {("AAA", 9.0), ("BBB", 5.0)}


# --- the fingerprint ---------------------------------------------------------

def test_the_same_signal_bar_twice_is_flagged_reused():
    t = C.round_trips(f([
        buy("2026-09-11 05:41:00", ref=7.51),
        sell("2026-09-11 05:41:30", -5.0, 0.5),
        buy("2026-09-11 05:42:00", ref=7.51),        # same bar
        sell("2026-09-11 05:42:30", -8.0, 0.5)]))
    assert list(t.reused) == [False, True], "the FIRST use is not a reuse"


def test_a_different_signal_bar_is_not_reuse():
    t = C.round_trips(f([
        buy("2026-09-11 05:41:00", ref=7.51),
        sell("2026-09-11 05:41:30", -5.0, 0.5),
        buy("2026-09-11 05:46:00", ref=7.62),
        sell("2026-09-11 05:46:30", -8.0, 0.5)]))
    assert list(t.reused) == [False, False]


def test_the_same_close_in_a_DIFFERENT_name_is_not_reuse():
    t = C.round_trips(f([
        buy("2026-09-11 05:41:00", ref=7.51, sym="AAA"),
        sell("2026-09-11 05:41:30", -5.0, 0.5, sym="AAA"),
        buy("2026-09-11 05:41:40", ref=7.51, sym="BBB"),
        sell("2026-09-11 05:42:30", -8.0, 0.5, sym="BBB")]))
    assert list(t.reused) == [False, False]


# --- the refusal -------------------------------------------------------------

def test_the_report_says_the_measures_are_never_summed():
    t = C.round_trips(f([
        buy("2026-09-11 05:41:00", ref=7.51),
        sell("2026-09-11 05:41:30", -5.0, 0.5),
        buy("2026-09-11 05:41:31", ref=7.51),
        sell("2026-09-11 05:41:50", -8.0, 0.3)]))
    # this second trade is reused AND instant AND sub-minute
    assert bool(t.reused.iloc[1]) and bool(t.instant.iloc[1]) \
        and bool(t.sub_minute.iloc[1])
    text = "\n".join(C.render([], t, ["2026-09-11"], 0.1))
    assert "NEVER summed" in text
    assert "count it three times" in text


def test_the_report_refuses_to_estimate_what_the_fix_earns():
    t = C.round_trips(f([buy("2026-09-11 04:00:00"),
                         sell("2026-09-11 04:10:00", 1.0, 10.0)]))
    text = "\n".join(C.render([], t, ["2026-09-11"], 0.1))
    assert "Not an estimate of what the fix earns" in text
    assert "counterfactual" in text


def test_unfilled_rows_are_excluded(tmp_path):
    p = tmp_path / "mcl_fills_20260911.csv"
    d = f([buy("2026-09-11 04:00:00"),
           sell("2026-09-11 04:10:00", 1.0, 10.0)])
    d.loc[len(d)] = ["2026-09-11 08:21:00", "MC5", "AAA", "BUY",
                     "SKIPPED_CONCURRENCY_CAP", None, None, 8.0, 0.1, 0.05,
                     70.0, 1000]
    d.to_csv(p, index=False)
    out = C.load(p)
    assert len(out) == 2
    assert (out.status == "FILLED").all()
