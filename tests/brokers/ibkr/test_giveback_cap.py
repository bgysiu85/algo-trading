#!/usr/bin/env python3
"""H-S4 -- the session give-back cap, STRATEGY scope, MC5 only, 2026-09-24.

Registered in docs/research/REGISTERED_giveback_cap.md (research chat's
Sec.0-7, build chat's amendment A) before this code existed; the same rule
already lives in common/session_stop.py as a POST-PASS forward sweep over a
finished book (see tests/common/test_session_stop.py). This is the LIVE
version: the same three numbers (realised, peak, armed) computed incrementally
as trades close, gating brokers/ibkr/trader.py's entry path rather than
sweeping a CSV after the fact. Board: W02-0019. Ben's decision on the paper
cuts review (claude/paper_cuts_20260924_RESULT.md), in his own words: "Both,
give-back cap on MC5".

Mirrors tests/brokers/ibkr/test_stale_signal_bar.py and
tests/brokers/ibkr/test_spread_guard.py's own live-path harness (`one`,
`drive`, `rows_with`, `bought`) rather than building a new one.
"""
from __future__ import annotations

import asyncio
import csv
import dataclasses
import tempfile
from pathlib import Path

import pytest

from brokers.ibkr import trader as M
from common import strategy_adapter as SA

from tests.brokers.ibkr.test_live_paths import FakeIB, FakeTrade
from tests.brokers.ibkr.test_stale_signal_bar import (MCL, at, bought,
                                                      firing_frame, one,
                                                      retimed, rows_with)

ET = M.ET
MC5 = SA.mc5_adapter()


# --------------------------------------------------------------------------
# 1. the registered parameters -- fixed, not chosen after seeing results
# --------------------------------------------------------------------------

def test_the_registered_parameters():
    """REGISTERED_giveback_cap.md Sec.1: ARM is one average winner rounded to
    $40, not swept; Sec.3: GB-50 is the PRIMARY cell, the one both
    practitioner sources (Sec.0) agreed on and the one that passed."""
    assert M.GIVEBACK_ARM == 40.0
    assert M.GIVEBACK_RATIO == 0.50


def test_only_mc5_is_capped():
    """PROGRAM_INDEX / W02-0019: MC5 passes all six registered readings under
    both scopes at every friction level; MCL FAILS and is made WORSE under
    session scope. Ben's decision caps MC5 only. Strategy names in this
    codebase are uppercase -- the fill log's own "strategy" column reads
    MC5/MCL -- so a lowercase entry here would silently never match."""
    assert M.GIVEBACK_STRATEGIES == frozenset({"MC5"})
    assert "MCL" not in M.GIVEBACK_STRATEGIES


# --------------------------------------------------------------------------
# 2. _record_realised -- the accumulator and the trip condition
# --------------------------------------------------------------------------

def fresh_trader():
    tr, _st, _log, _out = one("giveback_unit", MC5)
    return tr


def test_untouched_strategy_reads_zero():
    tr = fresh_trader()
    assert tr.strategy_realised.get("MC5", 0.0) == 0.0
    assert tr.strategy_peak.get("MC5", 0.0) == 0.0
    assert tr.giveback_tripped == set()


def test_arm_must_be_reached_before_it_can_trip():
    """A peak under $40 can retreat to zero and still never trip -- ARM exists
    exactly to stop a one-cent peak from arming the rule (Sec.1)."""
    tr = fresh_trader()
    tr._record_realised("MC5", 30.0)     # peak 30, under ARM
    tr._record_realised("MC5", -100.0)   # realised -70 -- deep given-back,
                                         # but the peak never armed
    assert tr.strategy_peak["MC5"] == 30.0
    assert "MC5" not in tr.giveback_tripped


def test_trips_exactly_at_the_registered_boundary():
    """realised <= GIVEBACK * peak, Sec.1 -- AT the boundary trips."""
    tr = fresh_trader()
    tr._record_realised("MC5", 50.0)    # peak 50, armed (>= 40)
    tr._record_realised("MC5", -25.0)   # realised 25.0 == 50% of 50 exactly
    assert tr.strategy_peak["MC5"] == 50.0
    assert tr.strategy_realised["MC5"] == pytest.approx(25.0)
    assert "MC5" in tr.giveback_tripped


def test_does_not_trip_one_cent_above_the_boundary():
    tr = fresh_trader()
    tr._record_realised("MC5", 50.0)
    tr._record_realised("MC5", -24.99)  # realised 25.01, just above 50%
    assert "MC5" not in tr.giveback_tripped


def test_peak_is_a_running_max_survives_a_loss():
    """A session that goes +200 then back to +50 is still armed at 200's
    peak, not 50's -- session_stop.py's `peak = max(peak, realised)`, ported
    here incrementally rather than swept."""
    tr = fresh_trader()
    tr._record_realised("MC5", 200.0)
    tr._record_realised("MC5", -150.0)   # realised 50 -- 25% of 200, trips
    assert tr.strategy_peak["MC5"] == 200.0
    assert "MC5" in tr.giveback_tripped


def test_latches_and_a_bounce_does_not_untrip_it():
    """Sec.1's "no further ENTRIES this session" is a latch, not a level: the
    registration is about a session-long state change, not a live gauge that
    could re-arm intra-session on a recovery."""
    tr = fresh_trader()
    tr._record_realised("MC5", 50.0)
    tr._record_realised("MC5", -25.0)    # trips
    assert "MC5" in tr.giveback_tripped
    tr._record_realised("MC5", 500.0)    # a big bounce, new all-time peak
    assert "MC5" in tr.giveback_tripped, "a bounce must not clear the trip"


def test_mcl_never_trips_at_the_same_numbers():
    """The exact sequence that trips MC5 above, fed to MCL instead: tracked
    for symmetry (strategy_peak/realised update), never gated -- MCL is not
    in GIVEBACK_STRATEGIES."""
    tr = fresh_trader()
    tr._record_realised("MCL", 50.0)
    tr._record_realised("MCL", -25.0)
    assert tr.strategy_realised["MCL"] == pytest.approx(25.0)
    assert tr.strategy_peak["MCL"] == 50.0
    assert "MCL" not in tr.giveback_tripped
    assert tr.giveback_tripped == set()


def test_strategies_do_not_share_an_accumulator():
    """STRATEGY scope (amendment A2): MC5's give-back must never be moved by
    MCL's trades or vice versa -- the one thing that would make this the
    SESSION-scope rule (which MCL fails) under the STRATEGY-scope name."""
    tr = fresh_trader()
    tr._record_realised("MC5", 50.0)
    tr._record_realised("MCL", -1000.0)   # a large MCL loss, same session
    assert tr.strategy_realised["MC5"] == 50.0
    assert tr.strategy_peak["MC5"] == 50.0
    assert "MC5" not in tr.giveback_tripped


# --------------------------------------------------------------------------
# 3. the live entry path
# --------------------------------------------------------------------------

def _forced_mc5_entry_frame():
    """A real MC5 evaluation, forced to long_entry=True, on a bar safely
    inside the session -- mirrors
    test_stale_signal_bar.test_mc5s_last_complete_bucket_can_be_before_the_session_opens,
    but timed so the last complete bucket falls INSIDE 04:00-09:30 rather
    than before it, so the frame actually reaches the gate under test."""
    import dataclasses as dc
    import pandas as pd
    from strategy.mc5 import mc5 as MC5MOD

    # MC5 needs MIN_BARS_REQUIRED (40) complete 5-min buckets, so the frame
    # has to start well before the session -- the overnight is where they
    # come from, same as test_stale_signal_bar's own MC5 fixture.
    idx = pd.date_range("2026-09-15 20:00", "2026-09-16 04:19",
                        freq="1min", tz=ET).tz_convert("UTC")
    px = [5.0 + 0.001 * i for i in range(len(idx))]
    df = pd.DataFrame({"open": px, "high": [p + .02 for p in px],
                       "low": [p - .02 for p in px], "close": px,
                       "volume": [10_000.0] * len(idx)}, index=idx)
    now = at("2026-09-16 04:20:11")
    real = MC5MOD.evaluate_last_bar(df, now)
    assert real is not None, "no complete bucket -- widen the frame"
    bar_et = pd.Timestamp(real.bar_ts).tz_convert(ET)
    assert at("2026-09-16 04:00:00") <= bar_et.to_pydatetime() < \
        at("2026-09-16 09:30:00"), (
            f"bucket {bar_et} is not inside the session -- this fixture is "
            "testing the wrong gate")
    forced = dc.replace(real, long_entry=True)
    return df, now, forced


def _drive_forced(tag, adapter, forced_sig, df, now, tripped=(),
                  peak=None, realised=None, fill_price=5.00):
    mc5_adapter = dataclasses.replace(adapter, _evaluate=lambda _d, _n: forced_sig)
    tr, st, log, out = one(tag, mc5_adapter, fill_price=fill_price)
    tr.giveback_tripped = set(tripped)
    if peak is not None:
        tr.strategy_peak[adapter.name] = peak
    if realised is not None:
        tr.strategy_realised[adapter.name] = realised
    tr.bars = lambda _s, _d=df: asyncio.sleep(0, result=_d)
    asyncio.run(tr.step_symbol(st, now))
    log.close()
    return tr, st, list(csv.DictReader(out.open(encoding="utf-8")))


def test_live_declines_a_tripped_strategys_entry_with_skipped_giveback():
    df, now, forced = _forced_mc5_entry_frame()
    tr, st, rows = _drive_forced("tripped", MC5, forced, df, now,
                                 tripped={"MC5"}, peak=50.0, realised=25.0)

    assert st.position is None
    assert not bought(rows)
    skipped = rows_with(rows, "SKIPPED_GIVEBACK")
    assert len(skipped) == 1
    reason = skipped[0]["reject_reason"]
    assert "MC5" in reason and "give-back cap" in reason
    assert "25.00" in reason and "50.00" in reason


def test_live_does_not_gate_an_untripped_strategy():
    """THE CONTROL. Without it, every assertion above would also be satisfied
    by a gate that declines every MC5 entry unconditionally."""
    df, now, forced = _forced_mc5_entry_frame()
    tr, st, rows = _drive_forced("untripped", MC5, forced, df, now,
                                 tripped=set())
    assert not rows_with(rows, "SKIPPED_GIVEBACK")
    assert bought(rows), "an untripped strategy's entry was declined"
    assert st.position is not None


def test_mcl_still_enters_when_only_mc5_has_tripped():
    """The board decision, checked directly: MCL is NOT capped. One trader,
    both strategies on the same symbol-shaped states, MC5 tripped, MCL not --
    MCL's entry must go through untouched."""
    out = Path(tempfile.gettempdir()) / "giveback_mcl_control.csv"
    if out.exists():
        out.unlink()
    log = M.FillLog(out)
    tr = M.MCLPaperTrader(FakeIB([FakeTrade(100, 5.00, "Filled")] * 8),
                          Path(tempfile.gettempdir()) / "wl.txt", log,
                          dry_run=False)
    tr.equity = 22290.96
    tr.giveback_tripped = {"MC5"}

    df = retimed(firing_frame(), "2026-09-16 04:05")
    st = M.SymbolState(symbol="TEST", strategy=MCL)
    from tests.brokers.ibkr.test_dryrun_roundtrip import FakeTicker
    st.contract = object()
    st.ticker = FakeTicker()
    tr.states[(MCL.name, "TEST")] = st
    tr.bars = lambda _s, _d=df: asyncio.sleep(0, result=_d)

    asyncio.run(tr.step_symbol(st, at("2026-09-16 04:06:05")))
    log.close()
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert not rows_with(rows, "SKIPPED_GIVEBACK")
    assert bought(rows), "MCL was gated by MC5's trip"
    assert st.position is not None


# --------------------------------------------------------------------------
# 4. an open position still rides its normal exit after the cap trips
# --------------------------------------------------------------------------

VEEA_SIGNAL_CLOSE = 5.8709
VEEA_FILL = 5.70


def test_an_open_position_still_exits_normally_after_its_strategy_trips():
    """Registration Sec.1, verbatim: "Open positions at the moment the cap
    fires ride their normal exits. Force-flattening them is a second,
    different rule and is not registered here." manage_position never reads
    giveback_tripped -- proved here rather than assumed, by forcing the flag
    on a strategy with an open position and confirming its trailing stop
    still fires and fills exactly as it would untripped."""
    df = retimed(firing_frame(scale_to=VEEA_SIGNAL_CLOSE), "2026-09-16 05:00")
    st, _rows = _drive_scale_entry(df)
    assert st.position is not None, "no entry -- the fixture never opened one"

    st.ticker.bid, st.ticker.ask = 5.30, 5.31   # below the 5.415 trail level
    out = Path(tempfile.gettempdir()) / "giveback_exit.csv"
    if out.exists():
        out.unlink()
    tr = M.MCLPaperTrader(FakeIB([FakeTrade(100, 5.30, "Filled")] * 4),
                          Path(tempfile.gettempdir()) / "wl.txt",
                          M.FillLog(out), dry_run=False)
    tr.states[(st.strategy.name, st.symbol)] = st
    tr.giveback_tripped = {st.strategy.name}    # forced, to prove the gate
                                                 # never reaches manage_position
    tr.ib.held = {"TEST": 100}       # what IB shows the account holding --
                                     # the exit path's own room check (S3)

    asyncio.run(tr.manage_position(st, at("2026-09-16 05:02:00"),
                                   bar_close=5.30, detail={}))
    tr.log.close()
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    sells = [r for r in rows if r["action"] == "SELL" and r["status"] == "FILLED"]
    assert sells, "the trailing stop should have fired and filled"
    assert st.position is None or st.position.exiting is not None
    # The CSV row rounds trade_pnl to the cent (FillLog's own round(pnl, 2));
    # the accumulator keeps full precision, exactly like self.session_pnl
    # does -- compare against THAT, not the rounded row, and use it to prove
    # the two never drift apart rather than re-deriving a tolerance.
    assert tr.strategy_realised[st.strategy.name] == pytest.approx(tr.session_pnl)
    assert tr.strategy_realised[st.strategy.name] == pytest.approx(
        float(sells[0]["trade_pnl"]), abs=0.01)


def _drive_scale_entry(df):
    tr, st, log, out = one("veea_giveback", MCL, fill_price=VEEA_FILL)
    tr.bars = lambda _s, _d=df: asyncio.sleep(0, result=_d)
    asyncio.run(tr.step_symbol(st, at("2026-09-16 05:01:00")))
    log.close()
    return st, list(csv.DictReader(out.open(encoding="utf-8")))
