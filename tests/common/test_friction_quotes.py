#!/usr/bin/env python3
"""Sign conventions and the stale-quote guard.

Every number this module produces is a small signed quantity, which is the
easiest kind to get backwards and the hardest to notice: a flipped sign turns
adverse slippage into price improvement and makes the strategy look better by
exactly the amount it is actually losing.
"""
from __future__ import annotations

import pandas as pd
import pytest

from common import friction_quotes as F


def fills(rows):
    """rows: (symbol, ts, side, price)"""
    return pd.DataFrame(
        [(s, "2026-08-04", pd.Timestamp(t, tz="UTC"), sd, p, 100, -1.0, 5 * 60)
         for s, t, sd, p in rows],
        columns=["symbol", "date", "ts", "side", "price", "qty",
                 "commission", "et_minute"])


def quotes(rows):
    """rows: (symbol, ts, bid, ask)"""
    return pd.DataFrame(
        [(s, pd.Timestamp(t, tz="UTC"), b, a, 100, 100)
         for s, t, b, a in rows],
        columns=["symbol", "ts", "bid", "ask", "bid_sz", "ask_sz"])


# --- signs ------------------------------------------------------------------

def test_a_buy_above_the_offer_is_adverse_and_positive():
    m = F.match(fills([("AAA", "2026-08-04 12:00:05", "BUY", 5.10)]),
                quotes([("AAA", "2026-08-04 12:00:00", 5.00, 5.05)]))
    r = m.iloc[0]
    assert r["slip_touch"] == pytest.approx(0.05)     # paid 5c through the ask
    assert r["slip_mid"] == pytest.approx(0.075)
    assert r["spread"] == pytest.approx(0.05)


def test_a_buy_inside_the_spread_is_price_improvement_and_negative():
    """2026-09-03 measured buys FAVOURABLE at -$0.0164/share. If this test
    fails, that finding would have been reported with the wrong sign."""
    m = F.match(fills([("AAA", "2026-08-04 12:00:05", "BUY", 5.01)]),
                quotes([("AAA", "2026-08-04 12:00:00", 5.00, 5.05)]))
    assert m.iloc[0]["slip_touch"] == pytest.approx(-0.04)


def test_a_sell_below_the_bid_is_adverse_and_positive():
    m = F.match(fills([("AAA", "2026-08-04 12:00:05", "SELL", 4.95)]),
                quotes([("AAA", "2026-08-04 12:00:00", 5.00, 5.05)]))
    r = m.iloc[0]
    assert r["slip_touch"] == pytest.approx(0.05)
    assert r["slip_mid"] == pytest.approx(0.075)


def test_a_sell_above_the_bid_is_price_improvement():
    m = F.match(fills([("AAA", "2026-08-04 12:00:05", "SELL", 5.04)]),
                quotes([("AAA", "2026-08-04 12:00:00", 5.00, 5.05)]))
    assert m.iloc[0]["slip_touch"] == pytest.approx(-0.04)


def test_both_sides_use_the_same_adverse_positive_convention():
    """A buy and a sell equally far through the touch must produce the SAME
    number. If one is negated, aggregating the two sides silently cancels
    real cost against itself."""
    m = F.match(
        fills([("AAA", "2026-08-04 12:00:05", "BUY", 5.10),
               ("BBB", "2026-08-04 12:00:05", "SELL", 4.95)]),
        quotes([("AAA", "2026-08-04 12:00:00", 5.00, 5.05),
                ("BBB", "2026-08-04 12:00:00", 5.00, 5.05)]))
    assert m["slip_touch"].nunique() == 1


# --- matching ---------------------------------------------------------------

def test_the_quote_used_is_the_last_one_before_the_fill():
    m = F.match(fills([("AAA", "2026-08-04 12:00:30", "BUY", 5.10)]),
                quotes([("AAA", "2026-08-04 12:00:00", 4.00, 4.05),
                        ("AAA", "2026-08-04 12:00:20", 5.00, 5.05),
                        ("AAA", "2026-08-04 12:00:40", 6.00, 6.05)]))
    assert m.iloc[0]["bid"] == pytest.approx(5.00)


def test_a_stale_quote_is_dropped_not_used():
    """On a thin pre-market name the previous print can be twenty minutes old.
    Pricing a fill against it yields a number that is precise and measures
    nothing -- worse than reporting no match, because it looks like data."""
    f = fills([("AAA", "2026-08-04 12:20:00", "BUY", 5.10)])
    q = quotes([("AAA", "2026-08-04 12:00:00", 5.00, 5.05)])
    assert F.match(f, q, tolerance_s=60).empty
    assert len(F.match(f, q, tolerance_s=3600)) == 1


def test_quotes_do_not_leak_between_symbols():
    """merge_asof without by="symbol" would price AAA's fill off BBB's quote
    and the frame would look entirely normal."""
    m = F.match(fills([("AAA", "2026-08-04 12:00:30", "BUY", 5.10)]),
                quotes([("BBB", "2026-08-04 12:00:20", 1.00, 1.05)]))
    assert m.empty


def test_a_fill_before_any_quote_is_dropped():
    m = F.match(fills([("AAA", "2026-08-04 12:00:00", "BUY", 5.10)]),
                quotes([("AAA", "2026-08-04 12:00:20", 5.00, 5.05)]))
    assert m.empty


# --- timezone ---------------------------------------------------------------

def test_fill_times_are_converted_from_the_report_zone_to_utc():
    """Flex stamps in the account's zone. Treating those as UTC would shift
    every fill by 10-16 hours and match it against quotes from a different
    session -- which would still produce numbers."""
    from datetime import datetime
    from common.flex import Execution

    e = Execution(symbol="AAA", trade_date="2026-08-04",
                  dt_raw=datetime(2026, 8, 4, 18, 0, 0), qty=100, price=5.0,
                  commission=-1.0, fifo_pnl=0.0, side="BUY", trade_id="1")
    df = F.fills_frame([e], "Australia/Sydney")
    # 18:00 Sydney (UTC+10) = 08:00 UTC = 04:00 ET, the pre-market open
    assert df.iloc[0]["ts"] == pd.Timestamp("2026-08-04 08:00:00", tz="UTC")


def test_executions_without_a_timestamp_are_excluded():
    """Three fills in the whole history carry a date and no time. They belong
    in the P/L and cannot be placed on a clock, so they cannot be priced."""
    from datetime import datetime
    from common.flex import Execution

    e = Execution(symbol="AAA", trade_date="2026-08-04",
                  dt_raw=datetime(2026, 8, 4), qty=100, price=5.0,
                  commission=-1.0, fifo_pnl=0.0, side="BUY", trade_id="1",
                  time_known=False)
    assert F.fills_frame([e], "Australia/Sydney").empty


def test_microsecond_and_nanosecond_timestamps_still_merge():
    """Flex times arrive as datetime64[us]; DBN timestamps are datetime64[ns].
    pandas refuses to merge_asof across the two -- 'incompatible merge keys' --
    and it only shows up against real data, not against fixtures built by the
    same helper."""
    f = fills([("AAA", "2026-08-04 12:00:05", "BUY", 5.10)])
    f["ts"] = f["ts"].astype("datetime64[us, UTC]")
    q = quotes([("AAA", "2026-08-04 12:00:00", 5.00, 5.05)])
    q["ts"] = q["ts"].astype("datetime64[ns, UTC]")
    assert len(F.match(f, q)) == 1
