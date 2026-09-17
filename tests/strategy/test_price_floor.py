#!/usr/bin/env python3
"""H-S5: the $5 entry floor, on both engines.

Registered in docs/research/REGISTERED_price_floor.md before the parameter
existed. The universe does not move; only the price an entry may be taken at.
`price_min=None` is the shipped constant and must be bit-identical.

The floor is SIGNAL-ORDINAL, like skip_entries: a refused entry means the
position is never opened, so bars the baseline was in a trade for become live
signals and the floored book can hold entries the baseline never took. The
tests below pin that rather than assuming the floored book is a subset.
"""
from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from strategy.mc5 import mc5 as MC5
from strategy.mcl import mcl as MCL

ET = ZoneInfo("America/New_York")
DAY = date(2026, 9, 11)


def bars(prices, minutes=1):
    """Flat OHLC at each price; one bar per `minutes` from 07:00 ET."""
    t0 = datetime.combine(DAY, dtime(7, 0), tzinfo=ET)
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=minutes * i)
                            for i in range(len(prices))])
    return pd.DataFrame({"open": prices, "high": prices, "low": prices,
                         "close": prices, "volume": [10_000] * len(prices)},
                        index=idx)


def mcl_run(prices, signal_at, **kw):
    df = bars(prices)
    take = pd.Series(False, index=df.index)
    for i in signal_at:
        take.iloc[i] = True
    return MCL.backtest_session(df, DAY, ET, entry_bars=take, entry_shares=100,
                                use_apex=False, **kw)


def entry_prices(trades):
    return [round(t.entry_price, 2) for t in trades]


# --- the default is the shipped band ---------------------------------------

def test_none_is_bit_identical_on_both_engines():
    prices = [3.00] * 3 + [3.20] * 3 + [6.00] * 4
    a = [t.__dict__ for t in mcl_run(prices, [0, 6])]
    b = [t.__dict__ for t in mcl_run(prices, [0, 6], price_min=None)]
    assert a == b and len(a) >= 1
    # and the resolved default IS the constant, not a literal that happens to match
    c = [t.__dict__ for t in mcl_run(prices, [0, 6], price_min=MCL.PRICE_MIN)]
    assert a == c


def test_the_default_follows_the_constant_rather_than_a_literal(monkeypatch):
    """`price_min=None` must READ PRICE_MIN, not a 2.0 written beside it.
    Comparing None against PRICE_MIN cannot tell those apart while the
    constant is 2.0 -- a control indistinguishable from the failure it
    detects, which is the shape this project keeps catching. Move the
    constant and the default has to move with it."""
    prices = [3.00] * 10
    assert len(mcl_run(prices, [0])) == 1
    monkeypatch.setattr(MCL, "PRICE_MIN", 5.0)
    assert mcl_run(prices, [0]) == [], "the default is not reading PRICE_MIN"
    assert len(mcl_run(prices, [0], price_min=2.0)) == 1, "an explicit floor still wins"


def test_mc5s_default_follows_its_own_constant(monkeypatch):
    real = MC5.signals

    def fires(frame, *a, **k):
        out = real(frame, *a, **k).copy()
        out["entry"] = False
        out.iloc[20, out.columns.get_loc("entry")] = True
        return out
    monkeypatch.setattr(MC5, "signals", fires)
    assert len(mc5_run([3.00] * 40)) == 1
    monkeypatch.setattr(MC5, "PRICE_MIN", 5.0)
    assert mc5_run([3.00] * 40) == []


def test_the_shipped_floor_is_still_two_dollars():
    """If either constant moves, this file's arithmetic stops meaning what it
    says and the change should be deliberate."""
    assert MCL.PRICE_MIN == 2.0 and MCL.PRICE_MAX == 20.0
    assert MC5.PRICE_MIN == 2.0 and MC5.PRICE_MAX == 20.0


# --- the floor refuses, and only on the low side ---------------------------

def test_a_three_dollar_entry_is_refused_at_five_and_taken_at_two():
    prices = [3.00] * 10
    assert len(mcl_run(prices, [0])) == 1
    assert mcl_run(prices, [0], price_min=5.0) == []


def test_a_six_dollar_entry_is_taken_at_both():
    prices = [6.00] * 10
    assert len(mcl_run(prices, [0])) == 1
    assert len(mcl_run(prices, [0], price_min=5.0)) == 1


def test_the_ceiling_is_untouched():
    """A floor is a RESTRICTION on the low side. Raising it must not admit
    anything above PRICE_MAX that the shipped band refused."""
    prices = [25.00] * 10
    assert mcl_run(prices, [0]) == []
    assert mcl_run(prices, [0], price_min=5.0) == []


def test_the_floor_is_read_at_the_price_actually_paid_not_the_bar_close():
    """The band sits after the slippage tick, so a bar closing a tick under the
    floor still enters. Pinning the side it is applied on."""
    tick = MCL.SLIPPAGE_TICKS * MCL.TICK
    just_under = 5.00 - tick
    assert entry_prices(mcl_run([just_under] * 10, [0], price_min=5.0)) == [5.00]
    assert mcl_run([just_under - 0.01] * 10, [0], price_min=5.0) == []


def test_the_floor_is_inclusive_at_the_threshold():
    assert len(mcl_run([5.00 - MCL.SLIPPAGE_TICKS * MCL.TICK] * 10, [0],
                       price_min=5.0)) == 1


# --- signal-ordinal, not a filter on a finished book -----------------------

def test_the_floored_book_can_hold_an_entry_the_baseline_never_took():
    """THE PROPERTY THAT MAKES THIS A RULE AND NOT A DELETION. The baseline
    enters at $3 on bar 0 and is still holding on bar 2; the floored book
    refuses bar 0, so bar 2's signal finds it flat and it enters at $6 -- a
    trade that does not exist in the baseline at all."""
    prices = [3.00, 3.00, 6.00, 6.00, 6.00, 6.00]
    base = mcl_run(prices, [0, 2])
    floored = mcl_run(prices, [0, 2], price_min=5.0)
    assert entry_prices(base) == [3.00 + MCL.SLIPPAGE_TICKS * MCL.TICK]
    assert entry_prices(floored) == [6.00 + MCL.SLIPPAGE_TICKS * MCL.TICK]
    assert floored[0].entry_time not in {t.entry_time for t in base}


def test_the_floored_book_is_not_the_baseline_minus_its_cheap_trades():
    """The accounting form and the signal-ordinal form differ, and the study
    prints both for exactly this reason."""
    prices = [3.00, 3.00, 6.00, 6.00, 6.00, 6.00]
    base = mcl_run(prices, [0, 2])
    floored = mcl_run(prices, [0, 2], price_min=5.0)
    accounting = [t for t in base if t.entry_price >= 5.0]
    assert accounting == []
    assert len(floored) == 1, "signal-ordinal and accounting agree here, so the test is vacuous"


# --- MC5 carries the same parameter ----------------------------------------

def mc5_run(prices, **kw):
    """MC5 reads 5-minute buckets; feed it 5-minute bars directly."""
    df = bars(prices, minutes=5)
    return MC5.backtest_session(df, DAY, ET, entry_shares=100, **kw)


def test_mc5_takes_price_min_and_none_is_bit_identical(monkeypatch):
    prices = [3.00] * 40
    sig = MC5.signals(bars(prices, minutes=5))
    a = [t.__dict__ for t in mc5_run(prices)]
    b = [t.__dict__ for t in mc5_run(prices, price_min=None)]
    assert a == b


def test_mc5_refuses_a_cheap_entry_at_five(monkeypatch):
    """Drive MC5's entry directly so the test is about the band and not about
    whether a synthetic frame happens to fire."""
    import pandas as pd

    df = bars([3.00] * 40, minutes=5)
    real = MC5.signals

    def fires(frame, *a, **k):
        out = real(frame, *a, **k)
        out = out.copy()
        out["entry"] = False
        out.iloc[20, out.columns.get_loc("entry")] = True
        return out
    monkeypatch.setattr(MC5, "signals", fires)
    assert len(mc5_run([3.00] * 40)) == 1
    assert mc5_run([3.00] * 40, price_min=5.0) == []
    assert len(mc5_run([6.00] * 40, price_min=5.0)) == 1
