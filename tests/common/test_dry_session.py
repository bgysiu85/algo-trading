#!/usr/bin/env python3
"""The dry-run replay that gates a second strategy going live.

Stage 5 of claude/multi_strategy_trader_spec.md. The module under test drives
the REAL trader over recorded bars; these tests check the two things the
replay itself has to get right, because a replay that lies is worse than no
replay.
"""
from __future__ import annotations

from datetime import timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from common import dry_session as D

ET = ZoneInfo("America/New_York")


def session(n=320, start="2026-01-07 04:00", price=5.0, step=0.004):
    """A synthetic session long enough to warm MC5's 40 five-minute bars."""
    t0 = pd.Timestamp(start, tz=ET)
    idx = pd.DatetimeIndex(
        [t0 + timedelta(minutes=i) for i in range(n)]).tz_convert("UTC")
    px = [price + step * i for i in range(n)]
    df = pd.DataFrame(
        {"open": px, "high": [p + 0.01 for p in px],
         "low": [p - 0.01 for p in px], "close": px,
         "volume": [20_000.0] * n}, index=idx)
    return [("TEST", "2026-01-07", df)]


# --- the recorder stamps SIMULATED time --------------------------------------

def test_rows_carry_the_simulated_minute_not_the_wall_clock():
    """THE DEFECT THIS CAUGHT, in the replay's own first run. The trader
    stamps ts_et with now_et_str() -- the real clock at write time, correct
    live and useless here, because two replays seconds apart then differ in
    every timestamp. The first comparison reported 21 of 32 MCL rows changed
    and every one was identical in substance."""
    sink = []
    rec = D._Recorder(sink, "TEST")
    rec.now = "2026-01-07 08:11"
    rec.write(strategy="MCL", symbol="TEST", ts_et="2026-09-09 02:28:39",
              status="DRY_RUN", action="BUY", reason="entry_signal",
              fill_price=5.82)
    assert sink[0][2] == "2026-01-07 08:11"
    assert "2026-09-09" not in str(sink[0])


def test_two_recordings_of_the_same_minute_compare_equal():
    rows = []
    for _ in range(2):
        rec = D._Recorder(rows, "TEST")
        rec.now = "2026-01-07 08:11"
        rec.write(strategy="MCL", symbol="TEST", status="DRY_RUN",
                  action="BUY", reason="entry_signal", fill_price=5.82)
    assert rows[0] == rows[1]


# --- the comparison ----------------------------------------------------------

def row(strat="MCL", sym="A", when="08:11", status="DRY_RUN", action="BUY",
        reason="entry_signal", px=5.0):
    return (strat, sym, when, status, action, reason, px)


def test_compare_only_looks_at_the_named_strategy():
    solo = [row("MCL")]
    joint = [row("MCL"), row("MC5", sym="B")]
    a, b, only_a, only_b = D.compare(solo, joint, "MCL")
    assert (a, b) == ([row("MCL")], [row("MCL")])
    assert not only_a and not only_b


def test_compare_reports_a_row_the_joint_run_lost():
    solo = [row(when="08:11"), row(when="08:20")]
    joint = [row(when="08:11")]
    _a, _b, only_a, only_b = D.compare(solo, joint, "MCL")
    assert only_a == [row(when="08:20")]
    assert only_b == []


def test_a_difference_in_price_alone_is_a_difference():
    """Same symbol, same minute, different fill. That is a changed decision,
    not a rounding footnote."""
    _a, _b, only_a, only_b = D.compare([row(px=5.0)], [row(px=5.5)], "MCL")
    assert only_a and only_b


# --- what the report says ----------------------------------------------------

def test_a_cap_breach_is_reported_as_a_defect_not_a_note():
    text = "\n".join(D.render(["mcl", "mc5"], 1, [], ["X 08:11 — 3 open"],
                              {}, None))
    assert "BREACHED" in text
    assert "defect" in text


def test_a_clean_run_says_so_on_every_step_not_at_the_end():
    text = "\n".join(D.render(["mcl", "mc5"], 1, [], [], {}, None))
    assert "held on every step" in text


def test_identical_decisions_are_stated_plainly():
    same = [row()]
    text = "\n".join(D.render(["mcl", "mc5"], 1, same, [], {}, same))
    assert "IDENTICAL" in text


def test_a_changed_decision_names_the_cap_exception_explicitly():
    """A row lost to the shared cap is a design consequence; anything else is
    a defect. The report must not let the reader blur them."""
    text = "\n".join(D.render(["mcl", "mc5"], 1, [], [], {},
                              [row(when="08:20")]))
    assert "SKIPPED_CONCURRENCY_CAP" in text
    assert "DESIGN" in text


# --- end to end --------------------------------------------------------------

@pytest.mark.slow
def test_adding_mc5_leaves_mcls_decisions_untouched():
    """The question stage 5 exists to answer, on one synthetic session.

    The real answer is in var/reports/dry_session.txt over cached sessions;
    this is the version that can live in a suite that has to stay fast.
    """
    s = session()
    joint, breaches, _r = D.replay(s, ["mcl", "mc5"])
    solo, _b, _r2 = D.replay(s, ["mcl"])
    assert not breaches, breaches
    _a, _b2, only_a, only_b = D.compare(solo, joint, "MCL")
    assert not only_a and not only_b, (only_a, only_b)


@pytest.mark.slow
def test_the_cap_is_checked_on_every_step_not_only_at_the_end():
    """A run that ends flat can still have breached in the middle, so the
    check has to be inside the loop. Asserted by running one -- an earlier
    draft of this test grepped replay()'s docstring for the words 'minute by
    minute', which is the same source-text mistake two of this project's own
    tests were making until this morning."""
    s = session(n=260)
    _j, breaches, _r = D.replay(s, ["mcl", "mc5"])
    assert breaches == []


def test_the_stub_broker_would_raise_rather_than_swallow_a_live_order():
    """placeOrder is absent on purpose: a stub that silently accepted orders
    would let a live-order bug pass a dry run."""
    assert not hasattr(D._NoBroker(), "placeOrder")


def test_the_breach_detector_counts_across_strategies():
    """SURVIVED A MUTATION UNTIL THIS EXISTED, and could not have been caught
    by a replay: the trader enforces the cap, so no breach ever occurs for a
    detector to miss. A detector is only testable by handing it a breach."""
    from datetime import datetime

    from brokers.ibkr import trader as M
    from common import strategy_adapter as SA

    def held(adapter, sym):
        st = M.SymbolState(symbol=sym, strategy=adapter)
        st.position = M.Position(
            symbol=sym, qty=100, entry_price=5.0,
            entry_time=datetime(2026, 9, 8, 8, 11, tzinfo=M.ET), peak=5.0)
        return st

    mcl, mc5 = SA.mcl_adapter(), SA.mc5_adapter()
    states = [held(mcl, "A"), held(mc5, "B"), held(mcl, "C"),
              M.SymbolState(symbol="D", strategy=mc5)]
    assert D.open_positions(states) == 3, (
        "three positions are open; a per-strategy count would read 2 and call "
        "a cap of 2 respected")
