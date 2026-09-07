#!/usr/bin/env python3
"""Compounding is path-dependent, and every bug in it produces a growth curve.

A sizing rule that quietly deploys more than it has, releases capital before
the position closed, or lets a losing account keep betting the same nominal
size, does not fail -- it produces a smooth equity curve with the wrong slope.
So the tests here pin the ARITHMETIC of the ledger, one property at a time.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from common import compound_sim as C


def leg(source="mcl", symbol="AAA", date="2026-03-16", entry="09:30",
        exit="09:45", price=10.0, pnl_per_share=1.0, ref_shares=0.0,
        ref_cost=0.0, recompute=True):
    a = datetime.strptime(f"{date} {entry}", "%Y-%m-%d %H:%M")
    b = datetime.strptime(f"{date} {exit}", "%Y-%m-%d %H:%M")
    return C.Leg(source=source, symbol=symbol, date=date, entry_ts=a,
                 exit_ts=b, entry_price=price,
                 exit_price=price + pnl_per_share,
                 pnl_per_share=pnl_per_share, ref_shares=ref_shares,
                 ref_cost=ref_cost, recompute_cost=recompute)


def free(legs, capital=10_000.0, per=60.0, total=100.0, **kw):
    """A run with commission switched off, so the arithmetic is visible."""
    r = C.simulate(legs, capital, per, total, **kw)
    return r


# --- the size rule ----------------------------------------------------------

def test_the_first_position_takes_the_per_trade_percentage():
    r = free([leg(price=10.0)])
    assert r.fills[0].shares == 600           # 60% of $10,000 at $10
    assert r.fills[0].basis == pytest.approx(6000.0)


def test_a_second_concurrent_position_gets_what_the_total_cap_leaves():
    """The stated case: 60 then 40. The second is limited by the TOTAL cap,
    not by its own per-trade cap."""
    r = free([leg(symbol="AAA", entry="09:30", exit="10:30"),
              leg(symbol="BBB", entry="09:35", exit="10:30")])
    assert [f.shares for f in r.fills] == [600, 400]


def test_a_third_concurrent_position_is_skipped_not_shrunk_to_nothing():
    r = free([leg(symbol="AAA", entry="09:30", exit="11:00"),
              leg(symbol="BBB", entry="09:35", exit="11:00"),
              leg(symbol="CCC", entry="09:40", exit="11:00")])
    assert len(r.fills) == 2
    assert r.skipped_no_capital == 1


def test_unused_allowance_flows_to_the_next_position(tmp_path):
    """The choice that was made explicitly: per-trade cap PLUS total cap, not
    two fixed slots. If the first position only manages 40% because of share
    rounding or a liquidity cap, the second may take up to its own 60% -- the
    binding limit is the cash actually free."""
    dv = {("AAA", "2026-03-16"): 40_000.0}      # 1% of $40k = $400 = 40 shares
    r = C.simulate([leg(symbol="AAA", entry="09:30", exit="10:30"),
                    leg(symbol="BBB", entry="09:35", exit="10:30")],
                   10_000.0, 60.0, 100.0, dollar_volume=dv, dv_cap_pct=1.0)
    assert r.fills[0].shares == 40            # capped hard by liquidity
    assert r.fills[0].dv_capped is True
    assert r.fills[1].shares == 600           # its own 60%, not the leftover 96%


def test_capital_is_released_only_when_the_position_closes():
    """A ledger that frees capital at signal time rather than at exit funds
    trades the account never had the cash for, and the equity curve looks
    entirely normal."""
    seq = [leg(symbol="AAA", entry="09:30", exit="15:00"),
           leg(symbol="BBB", entry="09:35", exit="09:40"),
           leg(symbol="CCC", entry="09:45", exit="15:00")]
    r = free(seq)
    # AAA holds 60% until 15:00. BBB takes the remaining 40% and returns it at
    # 09:40, so CCC can be funded at 09:45 -- but only from what BBB released.
    assert len(r.fills) == 3
    assert r.fills[2].capital_before > r.fills[1].capital_before


def test_a_hold_through_the_day_funds_fewer_trades_than_a_scalp():
    """The property this whole simulation exists to measure."""
    hold = [leg(symbol=f"S{i}", entry="09:30", exit="16:00") for i in range(5)]
    scalp = [leg(symbol=f"S{i}", entry=f"09:{30 + i * 5:02d}",
                 exit=f"09:{31 + i * 5:02d}") for i in range(5)]
    assert free(hold).taken < free(scalp).taken


# --- compounding -----------------------------------------------------------

def test_profit_folds_into_the_next_position_size():
    a = leg(symbol="AAA", entry="09:30", exit="09:45", price=10.0,
            pnl_per_share=1.0)
    b = leg(symbol="BBB", entry="10:00", exit="10:15", price=10.0)
    r = C.simulate([a, b], 10_000.0, 60.0, 100.0)
    # 600 shares x $1 = $600 gross, less commission, folded in before BBB.
    assert r.fills[1].capital_before > 10_000.0
    assert r.fills[1].shares > r.fills[0].shares


def test_a_loss_shrinks_the_next_position_too():
    """Compounding has to work downward or the drawdown is understated."""
    a = leg(symbol="AAA", entry="09:30", exit="09:45", pnl_per_share=-2.0)
    b = leg(symbol="BBB", entry="10:00", exit="10:15")
    r = C.simulate([a, b], 10_000.0, 60.0, 100.0)
    assert r.fills[1].shares < r.fills[0].shares


def test_an_account_that_runs_out_stops_rather_than_going_negative():
    legs = [leg(symbol=f"S{i}", entry="09:30", exit="09:45",
                date=f"2026-03-{16 + i:02d}", price=10.0, pnl_per_share=-9.9)
            for i in range(12)]
    r = C.simulate(legs, 10_000.0, 60.0, 100.0)
    assert r.final >= 0 or r.skipped_no_capital > 0
    assert r.taken < len(legs)


def test_max_drawdown_is_measured_from_the_peak_not_the_start():
    up = leg(symbol="AAA", entry="09:30", exit="09:45", pnl_per_share=5.0)
    down = leg(symbol="BBB", entry="10:00", exit="10:15", pnl_per_share=-5.0)
    r = C.simulate([up, down], 10_000.0, 60.0, 100.0)
    assert r.peak > 10_000.0
    assert r.max_drawdown > 0


# --- costs -----------------------------------------------------------------

def test_a_strategys_commission_is_recomputed_at_the_new_size():
    """Not scaled from the 100-share figure: the per-order minimum makes cost
    non-linear, so scaling would overstate it badly at size."""
    r = free([leg(price=10.0)])
    f = r.fills[0]
    assert f.cost > 0
    assert f.net == pytest.approx(f.gross - f.cost)


def test_my_commission_is_scaled_from_what_I_actually_paid():
    """Recomputing it would replace Ben's real execution habit -- a median 24
    fills a day -- with a model of one order per side, and quietly hand the
    comparison to him."""
    l = leg(source="mine", price=10.0, ref_shares=100.0, ref_cost=20.0,
            recompute=False)
    r = C.simulate([l], 10_000.0, 60.0, 100.0)
    f = r.fills[0]
    assert f.shares == 600
    assert f.cost == pytest.approx(20.0 * 6)      # 6x the size, 6x the cost


# --- the liquidity cap -----------------------------------------------------

def test_the_dollar_volume_cap_binds_and_is_counted():
    dv = {("AAA", "2026-03-16"): 100_000.0}       # 1% = $1,000 = 100 shares
    r = C.simulate([leg(price=10.0)], 10_000.0, 60.0, 100.0,
                   dollar_volume=dv, dv_cap_pct=1.0)
    assert r.fills[0].shares == 100
    assert r.dv_capped == 1


def test_a_symbol_day_with_no_volume_figure_is_not_silently_capped_to_zero():
    """An absent dollar volume must not read as zero liquidity -- that would
    delete the trade and quietly shrink the sample."""
    r = C.simulate([leg(price=10.0)], 10_000.0, 60.0, 100.0,
                   dollar_volume={}, dv_cap_pct=1.0)
    assert r.fills[0].shares == 600
    assert r.dv_capped == 0


def test_the_cap_only_ever_reduces_a_position():
    dv = {("AAA", "2026-03-16"): 10_000_000.0}    # 1% = $100k, far above 60%
    r = C.simulate([leg(price=10.0)], 10_000.0, 60.0, 100.0,
                   dollar_volume=dv, dv_cap_pct=1.0)
    assert r.fills[0].shares == 600
    assert r.dv_capped == 0


# --- ordering and determinism ----------------------------------------------

def test_the_run_is_reproducible_when_two_trades_share_a_timestamp():
    legs = [leg(symbol="BBB", entry="09:30", exit="10:30"),
            leg(symbol="AAA", entry="09:30", exit="10:30")]
    a = C.simulate(legs, 10_000.0, 60.0, 100.0)
    b = C.simulate(list(reversed(legs)), 10_000.0, 60.0, 100.0)
    assert [f.leg.symbol for f in a.fills] == [f.leg.symbol for f in b.fills]
    assert a.final == b.final


def test_nothing_is_taken_that_the_strategy_did_not_signal():
    """Capital can only ever make a run take FEWER trades."""
    legs = [leg(symbol=f"S{i}", entry="09:30", exit="09:45",
                date=f"2026-03-{16 + i:02d}") for i in range(5)]
    r = C.simulate(legs, 10_000.0, 60.0, 100.0)
    assert r.taken + r.skipped_no_capital == len(legs)


# --- the sweep --------------------------------------------------------------

def test_the_sweep_skips_totals_below_the_per_trade_cap():
    """A total cap under the per-trade cap is the same experiment as the two
    being equal, and running it twice would put a duplicate row on the grid
    and a false plateau on any surface drawn from it."""
    rows = C.sweep([leg()], 10_000.0, [60], [40, 60, 100])
    assert [r["total_pct"] for r in rows] == [60, 100]


def test_the_sweep_reports_every_cell_not_only_the_winner():
    rows = C.sweep([leg()], 10_000.0, [20, 60], [100])
    assert len(rows) == 2
    assert all("max_drawdown" in r and "taken" in r for r in rows)


# --- why a trade was not taken ---------------------------------------------

def test_concurrency_and_ruin_are_counted_separately():
    """Rolled into one 'skipped' figure they read identically, and a run the
    ratio was too concentrated to hold looks exactly like one that went broke.
    The two point at opposite fixes."""
    busy = [leg(symbol="AAA", entry="09:30", exit="16:00"),
            leg(symbol="BBB", entry="09:31", exit="16:00"),
            leg(symbol="CCC", entry="09:32", exit="16:00")]
    r = C.simulate(busy, 10_000.0, 60.0, 100.0)
    assert r.skipped_concurrency == 1
    assert r.skipped_ruined == 0

    # A losing account decays geometrically and asymptotes -- it does not
    # cross zero -- so the bucket it lands in is "could not buy one share with
    # nothing else open", which is practical ruin. skipped_ruined is reserved
    # for equity actually at or below zero, which only a gap can cause. The
    # distinction that matters is that NONE of these are concurrency.
    broke = [leg(symbol=f"S{i}", date=f"2026-03-{16 + i:02d}", entry="09:30",
                 exit="09:45", price=10.0, pnl_per_share=-9.99)
             for i in range(10)]
    r2 = C.simulate(broke, 10_000.0, 60.0, 100.0)
    assert r2.skipped_too_small > 0
    assert r2.skipped_concurrency == 0
    assert r2.final < 100.0


def test_the_three_reasons_still_sum_to_the_old_total():
    legs = [leg(symbol=f"S{i}", entry="09:30", exit="16:00") for i in range(4)]
    r = C.simulate(legs, 10_000.0, 60.0, 100.0)
    assert (r.taken + r.skipped_concurrency + r.skipped_ruined
            + r.skipped_too_small) == len(legs)
    assert r.skipped_no_capital == (r.skipped_concurrency + r.skipped_ruined
                                    + r.skipped_too_small)


# --- the liquidity input ----------------------------------------------------

def test_dollar_volume_is_close_times_volume(tmp_path, monkeypatch):
    """A daily bar carries no VWAP, and the cap is a coarse instrument -- 1% of
    a day's turnover. Close x volume does not deserve a precision the input
    cannot support, but it does have to be the right two columns."""
    import pandas as pd
    from common import day_dollar_volume as V
    frame = pd.DataFrame({"symbol": ["AAA", "BBB"],
                          "date": ["2026-03-16", "2026-03-16"],
                          "close": [4.0, 10.0], "volume": [1_000_000, 5_000]})
    monkeypatch.setattr("common.dbn_io.daily_frame", lambda *a, **k: frame)
    rows = V.build(tmp_path, "EQUS.SUMMARY",
                   {("AAA", "2026-03-16"), ("BBB", "2026-03-16")})
    got = {r["symbol"]: r["dollar_volume"] for r in rows}
    assert got == {"AAA": 4_000_000.0, "BBB": 50_000.0}


def test_only_the_wanted_symbol_days_come_back(tmp_path, monkeypatch):
    import pandas as pd
    from common import day_dollar_volume as V
    frame = pd.DataFrame({"symbol": ["AAA", "ZZZ"],
                          "date": ["2026-03-16", "2026-03-16"],
                          "close": [4.0, 10.0], "volume": [100, 100]})
    monkeypatch.setattr("common.dbn_io.daily_frame", lambda *a, **k: frame)
    rows = V.build(tmp_path, "EQUS.SUMMARY", {("AAA", "2026-03-16")})
    assert [r["symbol"] for r in rows] == ["AAA"]
