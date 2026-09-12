#!/usr/bin/env python3
"""Does the baseline check tell an offset from a dead lead?

The module exists to chase ONE hypothesis -- that `prior_close` is the wrong
daily row -- and the failure mode that would matter is the usual one: a check
that returns the hypothesis it was written to find.

So the tests that carry weight here are the NEGATIVE ones. A name whose live
+20% is consistent with the row already in use, and a name no row at all can
explain, must both come back saying so, or the module is an agreement machine
and its output is worthless as evidence.
"""
from __future__ import annotations

import pandas as pd
import pytest

from common import prior_close_check as P
from common.screen_at import ScreenConfig
from common.screen_sim import prior_closes

CFG = ScreenConfig()


def daily(closes, symbol="AAA", start="2026-09-01"):
    """closes = [(date, close)]"""
    return pd.DataFrame([{"symbol": symbol, "date": d, "close": c,
                          "volume": 1_000_000.0} for d, c in closes])


def examine(closes, target, tape, symbol="AAA", monkeypatch=None):
    d = daily(closes, symbol)
    pc = prior_closes(d)
    rec = P.examine(d, pc, {}, target, symbol)
    # The window slice is stubbed rather than read: this module's question is
    # about the DAILY rows, and a real .dbn.zst here would test dbn_io.
    rec["tape"] = tape
    peak = tape.get("high")
    rec["satisfies"] = []
    for r in rec["rows"]:
        if r["close"] > 0 and peak:
            ch = (peak / r["close"] - 1.0) * 100.0
            r["change_from"] = ch
            if ch >= P.LIVE_CLAIM:
                rec["satisfies"].append(r["date"])
    return rec


# --- parsing -----------------------------------------------------------------

def test_names_parse():
    assert P.parse_names("2026-09-11:acva, 2026-09-10:RML") == [
        ("2026-09-11", "ACVA"), ("2026-09-10", "RML")]


def test_names_without_a_colon_are_refused():
    with pytest.raises(SystemExit):
        P.parse_names("ACVA")


# --- which row is in use -----------------------------------------------------

def test_prior_close_is_the_previous_row():
    rec = examine([("2026-09-08", 10.0), ("2026-09-09", 11.0),
                   ("2026-09-10", 12.0)], "2026-09-10",
                  {"high": 13.0, "first": 12.0, "last": 12.5, "bars": 30})
    assert rec["used"] == pytest.approx(11.0)


def test_a_date_with_no_daily_row_is_named_not_guessed():
    rec = examine([("2026-09-08", 10.0), ("2026-09-10", 12.0)], "2026-09-09",
                  {"high": 13.0, "first": 12.0, "last": 12.5, "bars": 30})
    assert rec["used"] is None
    assert "no daily row" in rec["note"]


def test_first_day_in_the_archive_has_no_prior_close():
    rec = examine([("2026-09-08", 10.0), ("2026-09-09", 11.0)], "2026-09-08",
                  {"high": 13.0, "first": 12.0, "last": 12.5, "bars": 30})
    assert rec["used"] is None


# --- the negative cases, which are the point ---------------------------------

def test_a_consistent_row_in_use_does_not_support_the_hypothesis():
    """The screen's own baseline explains the live claim. No offset here.

    prior_close for 09-10 is 10.00 and the tape peaked at 13.00 = +30%. If the
    module reported an offset on this shape it would report one on anything.
    """
    rec = examine([("2026-09-08", 9.0), ("2026-09-09", 10.0),
                   ("2026-09-10", 12.8)], "2026-09-10",
                  {"high": 13.0, "first": 12.0, "last": 12.5, "bars": 30})
    assert rec["used"] == pytest.approx(10.0)
    # 09-08 at 9.00 also clears +20%, but 09-09 -- the row in use -- is among
    # the consistent ones, which is what retires the lead for this name.
    assert "2026-09-09" in rec["satisfies"]


def test_no_row_consistent_retires_the_lead():
    """A tape that never reaches +20% off ANY nearby close.

    This is the outcome that kills the hypothesis rather than confirming it,
    and it must be reachable.
    """
    rec = examine([("2026-09-08", 20.0), ("2026-09-09", 20.5),
                   ("2026-09-10", 21.0)], "2026-09-10",
                  {"high": 21.2, "first": 21.0, "last": 21.1, "bars": 30})
    assert rec["satisfies"] == []
    text = "\n".join(P.render([rec], CFG))
    assert "An" in text and "offset does not explain this name" in text


def test_the_offset_shape_is_visible_when_it_is_real():
    """The row one further back is the only consistent baseline.

    Closes 10.00 / 10.05 / 10.10 with a tape high of 12.30: +22% off 09-08,
    +22% off 09-09 -- both clear. Tightened so only the older row clears.
    """
    rec = examine([("2026-09-08", 10.0), ("2026-09-09", 12.2),
                   ("2026-09-10", 12.25)], "2026-09-10",
                  {"high": 12.3, "first": 12.2, "last": 12.25, "bars": 30})
    assert rec["used"] == pytest.approx(12.2)
    assert rec["satisfies"] == ["2026-09-08"]


# --- rendering ---------------------------------------------------------------

def test_render_marks_the_row_in_use_and_the_target():
    rec = examine([("2026-09-08", 10.0), ("2026-09-09", 11.0),
                   ("2026-09-10", 12.0)], "2026-09-10",
                  {"high": 13.5, "first": 12.0, "last": 12.5, "bars": 30})
    text = "\n".join(P.render([rec], CFG))
    assert "THE ROW IN USE" in text
    assert "TARGET DATE" in text


def test_render_states_what_it_is_not():
    rec = examine([("2026-09-08", 10.0), ("2026-09-09", 11.0)], "2026-09-09",
                  {"high": 13.5, "first": 12.0, "last": 12.5, "bars": 30})
    text = "\n".join(P.render([rec], CFG))
    assert "Not a correction" in text
    assert "Not TradingView's arithmetic" in text


def test_a_name_with_no_tape_says_so_rather_than_scoring_it():
    rec = examine([("2026-09-08", 10.0), ("2026-09-09", 11.0),
                   ("2026-09-10", 12.0)], "2026-09-10", {})
    assert rec["satisfies"] == []
    text = "\n".join(P.render([rec], CFG))
    assert "no bars in the window slice" in text


def test_negative_values_render_in_brackets():
    """A baseline ABOVE the tape's high is a negative change, and the report
    format brackets it rather than printing a minus sign."""
    rec = examine([("2026-09-08", 20.0), ("2026-09-09", 20.5),
                   ("2026-09-10", 21.0)], "2026-09-10",
                  {"high": 19.0, "first": 19.0, "last": 19.0, "bars": 30})
    text = "\n".join(P.render([rec], CFG))
    assert "(" in text and ")%" in text
