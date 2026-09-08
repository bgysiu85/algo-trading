#!/usr/bin/env python3
"""What the portfolio book is allowed to buy.

common/portfolio.py decides every share count in the sizing study and had no
tests of its own. The three ceilings it applies -- the account, MAX_SHARES,
and the tape -- interact, and getting the order or the units wrong changes the
answer to task #11 without changing anything that looks wrong.
"""
from __future__ import annotations

from datetime import timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from common import portfolio as P

ET = ZoneInfo("America/New_York")


def book(**kw):
    kw.setdefault("capital", 10_000.0)
    kw.setdefault("per_trade_pct", 40.0)
    kw.setdefault("max_positions", 2)
    kw.setdefault("compound", False)
    return P.Book(**kw)


# --- the account ------------------------------------------------------------

def test_the_capital_rule_alone_is_unchanged():
    """Regression guard. 40% of $10,000 is $4,000; at $8 that is 500 shares."""
    assert book().size(8.0) == 500


def test_the_per_trade_cap_is_of_the_STARTING_capital_not_what_is_left():
    b = book()
    b.cash = 5_000.0            # a position is already open
    # min(40% x 10,000, 5,000) = 4,000 -> still 500 shares, not 250.
    assert b.size(8.0) == 500
    b.cash = 1_000.0            # now the remaining cash binds
    assert b.size(8.0) == 125


# --- MAX_SHARES -------------------------------------------------------------

def test_max_shares_is_a_ceiling_and_never_a_floor():
    assert book(max_shares=100).size(8.0) == 100
    # It must not top a small position UP to the ceiling.
    b = book(max_shares=100)
    b.cash = 100.0
    assert b.size(8.0) == 12


def test_max_shares_zero_means_no_ceiling():
    assert book(max_shares=0).size(8.0) == 500


# --- the tape ---------------------------------------------------------------

def test_the_tape_cap_is_a_percentage_of_the_minute_and_is_counted():
    """40% of $10,000 at $8 wants 500 shares. The minute printed 10,000, so a
    1% cap allows 100. The 400 shares it took away are counted, because
    'capacity cost $X' and 'capacity blocked N trades' are different findings.
    """
    b = book(participation_pct=1.0)
    assert b.size(8.0, 10_000) == 100
    assert b.capped_by_tape == 1
    assert b.shares_lost_to_tape == 400


def test_the_tape_cap_does_not_fire_when_the_minute_is_thick_enough():
    b = book(participation_pct=1.0)
    assert b.size(8.0, 10_000_000) == 500
    assert b.capped_by_tape == 0
    assert b.shares_lost_to_tape == 0


def test_no_tape_cap_leaves_the_size_alone():
    assert book(participation_pct=0.0).size(8.0, 10) == 500


@pytest.mark.parametrize("vol", [None, 0.0])
def test_a_minute_with_no_volume_is_exempted_and_counted_not_sized_to_zero(vol):
    """A bar reporting no volume is a minute with no print, and a percentage
    of nothing is nothing. Sizing it to zero would drop the trade entirely and
    make the capped run incomparable with the uncapped one on trade count --
    so it is exempted, and counted, because those are the thinnest minutes and
    the exemption flatters the capped run."""
    b = book(participation_pct=1.0)
    assert b.size(8.0, vol) == 500
    assert b.no_volume == 1
    assert b.capped_by_tape == 0


def test_the_tape_cap_binds_after_max_shares_not_before():
    """THE ORDER IS OBSERVABLE IN THE COUNTER, NOT IN THE SIZE.

    Capital wants 500 shares; MAX_SHARES is 100; the minute printed 20,000 so
    a 1% cap allows 200. Applied in the right order the tape never binds --
    100 is already under 200 -- and capped_by_tape stays 0. Applied the wrong
    way round the tape shrinks 500 to 200 and reports itself as the binding
    constraint before MAX_SHARES takes it to 100 anyway. Both orders return
    100 shares. Only the counter tells them apart, and the counter is what the
    sweep reports as the cost of capacity.
    """
    b = book(max_shares=100, participation_pct=1.0)
    assert b.size(8.0, 20_000) == 100
    assert b.capped_by_tape == 0
    assert b.shares_lost_to_tape == 0

    # And when the tape really is the tighter of the two, it says so.
    b2 = book(max_shares=100, participation_pct=1.0)
    assert b2.size(8.0, 5_000) == 50
    assert b2.capped_by_tape == 1
    assert b2.shares_lost_to_tape == 50


def test_fixed_qty_ignores_every_ceiling():
    """Equivalence mode reproduces the per-session engine, which knows nothing
    about capital or the tape. If a ceiling leaked into it, --verify would
    stop being a control and start being another opinion."""
    b = book(fixed_qty=100, max_shares=10, participation_pct=0.001)
    assert b.size(8.0, 10) == 100
    assert b.capped_by_tape == 0


# --- the prepared-signals cache ---------------------------------------------

def synth_session(symbol: str, date: str, n: int = 40):
    t0 = pd.Timestamp(f"{date} 04:00", tz=ET)
    idx = pd.DatetimeIndex(
        [t0 + timedelta(minutes=i) for i in range(n)]).tz_convert("UTC")
    px = [5.0 + 0.01 * i for i in range(n)]
    df = pd.DataFrame({"open": px, "high": [p + 0.02 for p in px],
                       "low": [p - 0.02 for p in px], "close": px,
                       "volume": [50_000.0] * n}, index=idx)
    return (symbol, date, df)


def test_sharing_a_prepared_cache_changes_nothing_about_the_answer():
    """The cache exists so a 40-cell sweep does not recompute the signals 40
    times. It is only sound if the walk never mutates what it reads -- so two
    runs sharing one cache must agree with two runs that build their own.
    """
    from strategy.mcl import mcl as MCL
    sessions = [synth_session("AAA", "2026-01-07"),
                synth_session("BBB", "2026-01-07")]

    cold_a, *_ = P.simulate(sessions, MCL, 10_000, 40.0, 2)
    cold_b, *_ = P.simulate(sessions, MCL, 10_000, 40.0, 2)
    shared: dict = {}
    warm_a, *_ = P.simulate(sessions, MCL, 10_000, 40.0, 2, prepared=shared)
    warm_b, *_ = P.simulate(sessions, MCL, 10_000, 40.0, 2, prepared=shared)

    def key(ts):
        return [(t["symbol"], t["qty"], round(t["real"], 6)) for t in ts]

    assert key(cold_a) == key(cold_b) == key(warm_a) == key(warm_b)


# --- the boundary check -----------------------------------------------------

def sweep_row(max_shares, pct, drop5):
    return dict(max_shares=max_shares, per_trade_pct=pct, trades=10,
                net=drop5, per_trade=0.0, drop5=drop5, max_qty=max_shares,
                capped=0, rejected_capital=0, rejected_slots=0)


def test_the_boundary_check_fires_when_the_best_cell_is_on_the_edge():
    grid_s, grid_p = (100, 200, 400), (20.0, 40.0, 60.0)
    rows = [sweep_row(100, 20.0, -100.0), sweep_row(200, 40.0, -500.0)]
    text = "\n".join(P.report_sweep(rows, grid_s, grid_p, "t"))
    assert "ON THE BOUNDARY" in text
    assert "MAX_SHARES" in text and "per-trade %" in text


def test_the_boundary_check_stays_quiet_on_an_interior_optimum():
    grid_s, grid_p = (100, 200, 400), (20.0, 40.0, 60.0)
    rows = [sweep_row(100, 20.0, -500.0), sweep_row(200, 40.0, -100.0)]
    text = "\n".join(P.report_sweep(rows, grid_s, grid_p, "t"))
    assert "ON THE BOUNDARY" not in text


def test_the_sweep_is_ranked_on_drop_top_5_and_not_on_net():
    """Net picks the cell whose best five symbols were kindest. drop-top-5 is
    the column this project ranks on, and the header line has to agree with
    the column the code actually maximises."""
    grid_s, grid_p = (100, 200, 400), (20.0, 40.0, 60.0)
    rows = [dict(sweep_row(200, 40.0, -100.0), net=10.0),
            dict(sweep_row(400, 40.0, -900.0), net=9_999.0)]
    text = "\n".join(P.report_sweep(rows, grid_s, grid_p, "t"))
    assert "best on drop-top-5: max_shares 200" in text
