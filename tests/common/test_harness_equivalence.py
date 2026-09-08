#!/usr/bin/env python3
"""The harness must reproduce the engine that produced the published results.

CONTROL THE TOOL. PROGRAM_INDEX section 4: point a new analysis at an
already-published result and check it reproduces. A shared position-lifecycle
loop is exactly the kind of tool that can be subtly wrong and look right --
every result-inflating bug in this project's history lived in that loop.

So the harness is not validated against a fixture. It is validated against
strategy/mc5/mc5.py itself, on REAL cached bars, trade for trade and field for
field. MC5 is the strategy whose out-of-sample result the project currently
rests on; if the harness disagrees with it, the harness is wrong.

The bars are six symbol-days staged out of bar_cache_db. They are gitignored,
so this skips on a fresh clone rather than failing -- and the skip message says
how to get them, because a test that silently skips forever is not a test.

WHICH IS EXACTLY WHAT HAPPENED. Until 2026-09-08 BARS was a single hard-coded
path: the cloud sandbox's upload directory. That path exists in the sandbox and
nowhere else, so all 14 of these ran green where they were written and skipped
on Ben's machine -- on every run since. He noticed the skip COUNT; the tests
themselves said nothing. The suite reported "715 passed, 16 skipped" while the
only control on the shared position lifecycle had never once executed on the
machine that produces the results.

So the location is now a LIST, repo-relative first, and
test_the_bars_are_looked_for_where_this_repo_keeps_them asserts that list is
not sandbox-only. That assertion needs no bars and runs everywhere, which is
what makes this class of permanent skip loud instead of quiet.
"""
from __future__ import annotations

import os
from dataclasses import asdict
from datetime import date, time as dtime
from pathlib import Path

import pandas as pd
import pytest

from common import harness as H

REPO = Path(__file__).resolve().parents[2]
WINDOW = "3d_to_2000"

# Ordered by how much each one means. The repo-relative path is where the build
# writes on Ben's machine, so it goes first; the sandbox upload directory is
# last because it is real in exactly one place.
BARS_CANDIDATES = [
    p for p in (
        Path(os.environ["ALGO_TEST_BARS"]) if os.environ.get("ALGO_TEST_BARS")
        else None,
        REPO / "bar_cache_db" / WINDOW,
        REPO / "bar_cache_xnas" / WINDOW,
        Path("/mnt/user-data/uploads/Trading/bar_cache_db") / WINDOW,
    ) if p is not None
]


def bars_dir() -> Path:
    """The first candidate that exists, else the repo-relative one -- so a skip
    names where the bars BELONG rather than whatever happened to be last."""
    for c in BARS_CANDIDATES:
        if c.is_dir():
            return c
    return REPO / "bar_cache_db" / WINDOW


BARS = bars_dir()

CASES = [
    ("AAL", "2024-12-05"),
    ("AAOZ", "2026-08-06"),
    ("AAOZ", "2026-08-07"),
    ("ABAT", "2026-06-08"),
    ("ABCL", "2025-06-10"),
    ("ABCL", "2026-08-10"),
]


def test_the_bars_are_looked_for_where_this_repo_keeps_them():
    """The guard on the permanent silent skip.

    Needs no bars, so it runs on every machine, and it fails the moment the
    search list stops including a path relative to THIS repo. That is the whole
    defect: a list of absolute sandbox paths would let all 14 equivalence tests
    skip forever on the machine that matters while passing where they were
    written.
    """
    assert (REPO / "bar_cache_db" / WINDOW) in BARS_CANDIDATES
    assert any(c == REPO or REPO in c.parents for c in BARS_CANDIDATES), \
        f"no candidate is inside {REPO}: {BARS_CANDIDATES}"


def load(symbol: str, day: str):
    p = BARS / f"{symbol}_{day}.csv.gz"
    if not p.exists():
        pytest.skip(
            f"{p} absent -- bar_cache_db is gitignored and machine-local, so "
            f"the harness equivalence control is NOT running here. Build it "
            f"({', '.join(sorted({s for s, _ in CASES}))} are enough) or point "
            "ALGO_TEST_BARS at a directory of SYMBOL_DATE.csv.gz files.")
    df = pd.read_csv(p, index_col=0, parse_dates=True)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df


def mc5_rules(mod):
    """MC5's own constants, read off the module rather than retyped -- a copy
    here would drift and the test would pass against the wrong thing."""
    return H.Rules(
        session_start=mod.SESSION_START,
        session_end=mod.SESSION_END,
        exits=H.Exits(trail_pct=mod.TRAIL_PCT, use_exit_signal=True,
                      flat_at_session_end=True),
        price_min=mod.PRICE_MIN, price_max=mod.PRICE_MAX,
        enforce_price_band=mod.ENFORCE_PRICE_BAND,
        commission_plan=mod.COMMISSION_PLAN,
        slippage_ticks=mod.SLIPPAGE_TICKS,
        max_shares=mod.MAX_SHARES, max_equity_pct=mod.MAX_EQUITY_PCT,
        equity=mod.EQUITY)


def via_harness(mod, df, day):
    """MC5's signals, the harness's lifecycle."""
    df5 = df if mod._looks_5m(df) else mod.to_5m(df)
    sig = mod.signals(df5).copy()
    # MC5 names its exit column exit_sig, which is what the harness reads.
    return H.run_session(sig, date.fromisoformat(day), "America/New_York", mc5_rules(mod))


COMPARED = ("entry_time", "exit_time", "entry_price", "exit_price", "qty",
            "bars_held", "gross", "commission", "net")


@pytest.mark.parametrize("symbol,day", CASES)
def test_the_harness_reproduces_mc5_trade_for_trade(symbol, day):
    from strategy.mc5 import mc5

    df = load(symbol, day)
    d = date.fromisoformat(day)
    theirs = mc5.backtest_session(df, d, "America/New_York")
    ours = via_harness(mc5, df, day)

    assert len(ours) == len(theirs), (
        f"{symbol} {day}: harness produced {len(ours)} trades, mc5 produced "
        f"{len(theirs)}. A trade-count difference is never rounding.")
    for a, b in zip(ours, theirs):
        ad, bd = asdict(a), asdict(b)
        for f in COMPARED:
            assert ad[f] == bd[f], (
                f"{symbol} {day}: field {f!r} differs -- harness {ad[f]!r}, "
                f"mc5 {bd[f]!r}")


def test_the_control_actually_exercises_some_trades():
    """A control that compares two empty lists passes forever and proves
    nothing. This asserts the sample contains real trades."""
    from strategy.mc5 import mc5

    total = 0
    for symbol, day in CASES:
        df = load(symbol, day)
        total += len(mc5.backtest_session(df, date.fromisoformat(day), "America/New_York"))
    assert total >= 3, (
        f"only {total} trades across the sample -- the equivalence test is "
        "comparing mostly-empty lists. Stage symbol-days that traded.")


# --- the fill model, on hand-built bars -------------------------------------

def frame(bars, entry_on=0, stop_level=None):
    """bars: list of (open, high, low, close). One-minute, inside the window."""
    idx = pd.date_range("2026-03-16 13:00", periods=len(bars), freq="1min",
                        tz="UTC")
    df = pd.DataFrame(bars, columns=["open", "high", "low", "close"], index=idx)
    df["entry"] = [i == entry_on for i in range(len(bars))]
    if stop_level is not None:
        df["stop_level"] = stop_level
    return df


RULES = H.Rules(session_start=dtime(9, 0), session_end=dtime(16, 0),
                enforce_price_band=False, slippage_ticks=0,
                max_shares=100, max_equity_pct=100.0, equity=100_000.0)


def run(df, **kw):
    r = kw.pop("rules", RULES)
    return H.run_session(df, date(2026, 3, 16), "America/New_York", rules=r,
                         **kw)


def test_a_gap_through_the_stop_fills_at_the_open_not_the_level():
    """The assumption that moved MC5 from +$20,156 to -$400. Selling AT a level
    the market never offered."""
    r = H.Rules(**{**RULES.__dict__, "exits": H.Exits(stop_pct=5.0)})
    # entry at 10.00, stop at 9.50, next bar OPENS at 9.00 -- the level was
    # never available.
    df = frame([(10, 10, 10, 10), (9.0, 9.1, 8.8, 8.9)])
    t = run(df, rules=r)[0]
    assert t.exit_price == 9.0, "filled at the stop level, not at the open"


def test_turning_gap_fills_off_restores_the_optimistic_price():
    """Kept only so an old result can be reproduced deliberately."""
    r = H.Rules(**{**RULES.__dict__, "exits": H.Exits(stop_pct=5.0),
                   "gap_fills": False})
    df = frame([(10, 10, 10, 10), (9.0, 9.1, 8.8, 8.9)])
    assert run(df, rules=r)[0].exit_price == 9.5


def test_the_trail_is_seeded_from_the_entry_price_not_the_bar_high():
    """The entry bar's high happened BEFORE the close that was bought. Seeding
    from it put the trail above the market at the instant of entry in 53% of
    MC5's stop exits."""
    r = H.Rules(**{**RULES.__dict__, "exits": H.Exits(trail_pct=5.0)})
    # Entry bar closes at 10 but printed a high of 12. A trail seeded from 12
    # sits at 11.40 -- already above the entry, so the next bar stops out.
    df = frame([(10, 12, 10, 10), (10, 10.2, 9.9, 10.1),
                (10, 10, 9.4, 9.4)])
    ts = run(df, rules=r)
    assert ts, "position stopped out immediately -- peak seeded from the high"
    assert ts[0].reason == "stop" and ts[0].exit_price < 10


def test_when_one_bar_holds_both_stop_and_target_the_stop_wins():
    r = H.Rules(**{**RULES.__dict__,
                   "exits": H.Exits(stop_pct=5.0, target_r=2.0)})
    # entry 10.00, stop 9.50, target 11.00; one bar spans both.
    df = frame([(10, 10, 10, 10), (10, 11.5, 9.2, 10)])
    assert run(df, rules=r)[0].reason == "stop"


def test_the_optimistic_tie_break_is_available_and_is_not_the_default():
    r = H.Rules(**{**RULES.__dict__,
                   "exits": H.Exits(stop_pct=5.0, target_r=2.0),
                   "stop_wins_ties": False})
    df = frame([(10, 10, 10, 10), (10, 11.5, 9.2, 10)])
    assert run(df, rules=r)[0].reason == "target"
    assert H.Rules(session_start=dtime(9, 0),
                   session_end=dtime(16, 0)).stop_wins_ties is True


def test_a_target_without_a_stop_is_refused_rather_than_guessed():
    """R is the distance to the stop. With no stop there is no denominator,
    and inventing one is how an uncalibrated parameter gets into a result."""
    r = H.Rules(**{**RULES.__dict__, "exits": H.Exits(target_r=2.0)})
    with pytest.raises(ValueError, match="target_r needs a stop"):
        run(frame([(10, 10, 10, 10)]), rules=r)


def test_a_structure_stop_comes_from_the_strategys_own_column():
    r = H.Rules(**{**RULES.__dict__,
                   "exits": H.Exits(use_stop_column=True)})
    df = frame([(10, 10, 10, 10), (10, 10, 9.0, 9.1)], stop_level=9.6)
    t = run(df, rules=r)[0]
    assert t.reason == "stop" and t.exit_price == 9.6


def test_the_tighter_of_a_structure_stop_and_a_trail_is_used():
    """Running both must not let one silently cancel the other."""
    r = H.Rules(**{**RULES.__dict__,
                   "exits": H.Exits(trail_pct=50.0, use_stop_column=True)})
    df = frame([(10, 10, 10, 10), (10, 10, 9.7, 9.8)], stop_level=9.9)
    assert run(df, rules=r)[0].reason == "stop"      # 9.90 beats the 5.00 trail


def test_the_price_band_is_enforced_at_entry():
    r = H.Rules(**{**RULES.__dict__, "enforce_price_band": True,
                   "price_min": 2.0, "price_max": 20.0})
    assert run(frame([(50, 50, 50, 50), (51, 51, 51, 51)]), rules=r) == []


def test_a_position_still_open_at_the_session_end_is_closed():
    r = H.Rules(**{**RULES.__dict__, "exits": H.Exits()})
    ts = run(frame([(10, 10, 10, 10), (10, 10.5, 10, 10.4)]), rules=r)
    assert len(ts) == 1 and ts[0].reason == "session_end"


def test_max_entries_per_session_is_honoured():
    r = H.Rules(**{**RULES.__dict__, "exits": H.Exits(stop_pct=1.0),
                   "max_entries_per_session": 1})
    df = frame([(10, 10, 10, 10), (10, 10, 9.5, 9.6), (10, 10, 10, 10),
                (10, 10, 9.5, 9.6)])
    df["entry"] = [True, False, True, False]
    assert len(run(df, rules=r)) == 1


def test_commission_is_charged_on_both_legs():
    from common.commissions import round_trip
    r = H.Rules(**{**RULES.__dict__, "exits": H.Exits(), "max_shares": 100})
    t = run(frame([(10, 10, 10, 10), (10, 10, 10, 10)]), rules=r)[0]
    assert t.qty == 100
    assert abs(t.commission - round(round_trip(100, 10.0, "ibkr_tiered"), 2)) < 0.01


# --- the one field that legitimately differs ---------------------------------

REASON_MAP = {"stop": "trailing_stop", "signal": "gradient_reversal",
              "session_end": "window_close"}


@pytest.mark.parametrize("symbol,day", CASES)
def test_the_exit_reasons_correspond_one_to_one(symbol, day):
    """`reason` is the one compared field that differs by design: the harness
    names exits generically ('stop') because six strategies cannot share
    MC5's vocabulary ('gradient_reversal').

    That is a rename, not a behaviour change -- but per-exit-reason breakdowns
    are load-bearing here (friction is measured per exit reason, and the
    scale-out study was caught by one). So the correspondence is pinned: if a
    harness 'stop' ever lines up against an mc5 'window_close', the two engines
    have diverged on WHY they exited even where they agree on the price.
    """
    from strategy.mc5 import mc5

    df = load(symbol, day)
    theirs = mc5.backtest_session(df, date.fromisoformat(day),
                                  "America/New_York")
    ours = via_harness(mc5, df, day)
    for a, b in zip(ours, theirs):
        assert REASON_MAP[a.reason] == b.reason, (
            f"{symbol} {day}: harness said {a.reason!r} where mc5 said "
            f"{b.reason!r} -- same fill, different reason")


def test_the_map_covers_every_reason_the_harness_can_emit():
    """A map that silently lacks an entry would KeyError in the test above
    rather than reporting a mismatch -- which is fine, but only if the map is
    known to be complete. 'target' and 'time_stop' have no mc5 equivalent
    because mc5 has neither mechanic."""
    import inspect
    src = inspect.getsource(H.run_session)
    emitted = {r for r in ("stop", "target", "time_stop", "signal",
                           "session_end") if f'"{r}"' in src}
    assert emitted == {"stop", "target", "time_stop", "signal", "session_end"}
    assert set(REASON_MAP) == emitted - {"target", "time_stop"}


def test_the_mc5_calibration_aid_can_actually_be_called():
    """It raised NameError on every call for as long as it has existed, because
    a line was copied from backtest_session where the name is a parameter.
    Nothing called it, so nothing caught it."""
    from strategy.mc5 import mc5

    df = load("ABAT", "2026-06-08")
    out = mc5.slope_distribution(df, "America/New_York")
    assert isinstance(out, dict)
    if out:
        assert "p50" in out and out["bars"] > 0
