#!/usr/bin/env python3
r"""Pricing the backtest's fills against the real quote, and the traps in it.

A STALE QUOTE PRICED AS A FRESH ONE. `tcbbo` carries a quote only where a TRADE
printed, and on a dead pre-market minute the last print can be twenty minutes
old. Pricing a fill against it yields a figure that is precise and meaningless.
Fresh and stale are separate strata here, a disagreement between them refuses a
verdict, and neither is dropped -- "no recent quote" is evidence about how thin
these bars are, and dropping it would restrict the check to the liquid half of
a population whose thinness is the thing being examined.

A TRADE PRICED ON ONE LEG. A buy repriced at the ask and a sell left at the
modelled close is two price bases in one number. Such trades are excluded and
counted, never half-repriced.

A SIGN READ BACKWARDS. `shortfall` is positive when the MODEL got the better
price. The convention is chosen so the flattering direction is the positive one
and cannot be mistaken for a cost.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from common import quote_fill as Q


def leg(side="BUY", model_px=5.00, bid=4.95, ask=5.05, age_s=1.0,
        symbol="AAA", date="2026-01-02", trade=0, gross=10.0, covered=True):
    r = {"symbol": symbol, "date": date, "trade": trade, "side": side,
         "model_px": model_px, "gross": gross, "covered": covered}
    if covered:
        r.update(bid=bid, ask=ask, bid_sz=100.0, ask_sz=100.0, age_s=age_s)
    return r


def both(entry=(5.00, 4.95, 5.05), exit_=(5.20, 5.15, 5.25), age=1.0,
         date="2026-01-02", trade=0, symbol="AAA"):
    e_px, e_bid, e_ask = entry
    x_px, x_bid, x_ask = exit_
    gross = (x_px - e_px) * Q.QTY
    return [leg("BUY", e_px, e_bid, e_ask, age, symbol, date, trade, gross),
            leg("SELL", x_px, x_bid, x_ask, age, symbol, date, trade, gross)]


# --- derived quantities -----------------------------------------------------

def test_the_spread_and_its_basis_points_come_off_the_quote():
    r = Q.enrich([leg(bid=4.95, ask=5.05)])[0]
    assert r["spread"] == pytest.approx(0.10)
    assert r["mid"] == pytest.approx(5.00)
    assert r["spread_bps"] == pytest.approx(200.0)


def test_a_buy_is_priced_against_the_ask_and_a_sell_against_the_bid():
    b, s = Q.enrich([leg("BUY"), leg("SELL")])
    assert b["book_px"] == b["ask"]
    assert s["book_px"] == s["bid"]


def test_shortfall_is_positive_when_the_model_got_the_better_price():
    """The sign convention. A buy below the ask and a sell above the bid are
    both money the model gave itself, and both must read positive."""
    b = Q.enrich([leg("BUY", model_px=5.00, bid=4.95, ask=5.05)])[0]
    s = Q.enrich([leg("SELL", model_px=5.00, bid=4.95, ask=5.05)])[0]
    assert b["shortfall"] == pytest.approx(0.05)
    assert s["shortfall"] == pytest.approx(0.05)


def test_a_model_price_worse_than_the_book_reads_negative():
    b = Q.enrich([leg("BUY", model_px=5.10, bid=4.95, ask=5.05)])[0]
    assert b["shortfall"] == pytest.approx(-0.05)


def test_freshness_is_decided_by_the_quotes_age():
    fresh = Q.enrich([leg(age_s=Q.FRESH_S - 1)])[0]
    stale = Q.enrich([leg(age_s=Q.FRESH_S + 1)])[0]
    assert fresh["fresh"] and not stale["fresh"]


def test_an_uncovered_leg_is_left_alone_rather_than_given_a_zero_spread():
    r = Q.enrich([leg(covered=False)])[0]
    assert "spread" not in r and r["covered"] is False


# --- folding legs back into trades ------------------------------------------

def test_a_trade_needs_both_legs_priced():
    """One leg at the book and one at the modelled close is two price bases in
    one number."""
    rows = Q.enrich(both())
    rows[1]["covered"] = False
    assert Q.pairs(rows) == []


def test_a_trade_with_only_one_leg_at_all_is_dropped():
    rows = Q.enrich([leg("BUY")])
    assert Q.pairs(rows) == []


def test_the_book_price_buys_the_offer_and_sells_the_bid():
    t = Q.pairs(Q.enrich(both(entry=(5.00, 4.95, 5.05),
                              exit_=(5.20, 5.15, 5.25))))[0]
    assert t["gross"] == pytest.approx(20.0)          # (5.20-5.00)*100
    assert t["book_gross"] == pytest.approx(10.0)     # (5.15-5.05)*100
    assert t["give_up"] == pytest.approx(10.0)


def test_two_trades_on_one_symbol_day_do_not_collide():
    rows = Q.enrich(both(trade=0) + both(trade=1))
    assert len(Q.pairs(rows)) == 2


def test_a_trade_is_fresh_only_when_both_legs_are():
    rows = Q.enrich(both(age=1.0))
    rows[1]["age_s"] = Q.FRESH_S + 10
    Q.enrich(rows)
    assert Q.pairs(rows)[0]["fresh"] is False


# --- the sections -----------------------------------------------------------

def test_a_spread_wider_than_the_friction_allowance_is_called_out():
    """The finding this module exists for. $4.26 per round trip is charged for
    spread, commission and slippage together; if one crossing costs more than
    that, every net in the project is optimistic."""
    trades = Q.pairs(Q.enrich(both(entry=(5.00, 4.90, 5.10),
                                   exit_=(5.20, 5.10, 5.30))))
    out = "\n".join(Q.spread_section(trades))
    assert "COSTS MORE THAN THE WHOLE" in out
    assert "optimistic" in out


def test_a_narrow_spread_is_not_called_adequate():
    """Covering the median spread does not make the allowance right -- it has
    to cover commission and slippage too."""
    trades = Q.pairs(Q.enrich(both(entry=(5.00, 4.999, 5.001),
                                   exit_=(5.20, 5.199, 5.201))))
    out = "\n".join(Q.spread_section(trades))
    assert "COSTS MORE THAN THE WHOLE" not in out
    assert "does not make it" in out


def test_the_reachable_section_reports_both_sides_separately():
    out = "\n".join(Q.reachable_section(Q.enrich(both())))
    assert "BUY" in out and "SELL" in out
    assert "model better" in out


def test_the_repriced_section_moves_only_the_fill():
    trades = Q.pairs(Q.enrich(both()))
    out = "\n".join(Q.repriced_section(trades))
    assert "same exits" in out
    assert f"${Q.MEASURED_FRICTION:.2f} charged on top" in out


def test_fresh_and_stale_are_separate_strata():
    trades = (Q.pairs(Q.enrich(both(age=1.0, trade=0)))
              + Q.pairs(Q.enrich(both(age=Q.FRESH_S + 100, trade=1))))
    out = "\n".join(Q.repriced_section(trades))
    assert "fresh quotes" in out and "stale quotes" in out


def test_a_stratum_disagreement_refuses_a_verdict():
    """A stale quote is not evidence about this fill. While the two populations
    point opposite ways, no correction is issued -- the same rule a halves
    disagreement gets."""
    fresh = Q.pairs(Q.enrich(both(entry=(5.00, 4.90, 5.10),
                                  exit_=(5.20, 5.10, 5.30), age=1.0, trade=0)))
    stale = Q.pairs(Q.enrich(both(entry=(5.00, 5.10, 4.90),
                                  exit_=(5.20, 5.30, 5.10),
                                  age=Q.FRESH_S + 100, trade=1)))
    out = "\n".join(Q.repriced_section(fresh + stale))
    assert "DISAGREE ON THE SIGN" in out


def test_agreement_is_stated_as_agreement_not_as_proof():
    fresh = Q.pairs(Q.enrich(both(age=1.0, trade=0)))
    stale = Q.pairs(Q.enrich(both(age=Q.FRESH_S + 100, trade=1)))
    out = "\n".join(Q.repriced_section(fresh + stale))
    assert "not an artefact of pricing dead minutes" in out


def test_coverage_counts_legs_and_both_leg_trades_apart():
    rows = Q.enrich(both() + [leg(covered=False, trade=9)])
    out = "\n".join(Q.coverage(rows, Q.pairs(rows), 10, 8))
    assert "legs with a quote" in out
    assert "priced on BOTH legs" in out
    assert "the whole book and is not claimed to be" in out


def test_the_correction_is_named_a_floor_not_an_estimate():
    """Paying the ask assumes the offer was big enough for 100 shares. Where it
    was not, the true cost is worse -- never better."""
    rows = Q.enrich(both())
    out = "\n".join(Q.render(rows, Q.pairs(rows), 10, 8, 1.0, 1))
    assert "FLOOR on the correction" in out


def test_nothing_priced_is_reported_as_a_fact_about_the_archive():
    out = "\n".join(Q.render([], [], 10, 0, 1.0, 1))
    assert "NOTHING COULD BE PRICED" in out
    assert "a fact about" in out and "the archive" in out


def test_the_report_says_it_is_a_validity_check_not_a_new_edge():
    rows = Q.enrich(both())
    out = "\n".join(Q.render(rows, Q.pairs(rows), 10, 8, 1.0, 1))
    assert "VALIDITY CHECK" in out


# --- the pipeline -----------------------------------------------------------

def test_a_session_with_no_quote_file_is_uncovered_not_unpriceable(monkeypatch):
    """NO QUOTE FILE IS NOT NO QUOTES. A session the archive never covered must
    not read as one whose fills all happened to be unmatchable."""
    import math
    from datetime import date, datetime, time as dtime, timedelta
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
    D = date(2026, 3, 2)
    idx = []
    for d in (D - timedelta(days=1), D):
        b = pd.Timestamp(datetime.combine(d, dtime(4, 0), tzinfo=ET))
        idx += [(b + timedelta(minutes=i)).tz_convert("UTC") for i in range(330)]
    close = [4.0 + 0.004 * i + 0.30 * math.sin(2 * math.pi * i / 40)
             for i in range(len(idx))]
    vol = [130_000.0 if i % 3 == 0 else 40_000.0 for i in range(len(idx))]
    df = pd.DataFrame({"symbol": "AAA", "open": close,
                       "high": [c + 0.02 for c in close],
                       "low": [c - 0.02 for c in close],
                       "close": close, "volume": vol},
                      index=pd.DatetimeIndex(idx))
    monkeypatch.setattr("common.dbn_io.read_dbn", lambda p: df)
    monkeypatch.setattr("common.friction_quotes.quotes_for_date",
                        lambda *a, **k: pd.DataFrame())
    fs = pd.Timestamp(f"{D.isoformat()}T04:00:00-05:00").tz_convert(
        "UTC").isoformat()
    _day, rows, err = Q.run_day(([f"{D.isoformat()}.dbn"], D.isoformat(),
                                 [{"symbol": "AAA", "date": D.isoformat(),
                                   "first_seen": fs}], "/archive"))
    assert err == ""
    assert rows, "the fixture produced no legs; the test proves nothing"
    assert all(r["covered"] is False for r in rows)
    assert len(rows) % 2 == 0, "legs must come in pairs"
    assert Q.pairs(Q.enrich(rows)) == []


def test_every_trade_contributes_exactly_two_legs(monkeypatch):
    """One row per LEG, not per trade: the two sides are priced against
    different sides of the book and folding them would force a choice."""
    import math
    from datetime import date, datetime, time as dtime, timedelta
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
    D = date(2026, 3, 2)
    idx = []
    for d in (D - timedelta(days=1), D):
        b = pd.Timestamp(datetime.combine(d, dtime(4, 0), tzinfo=ET))
        idx += [(b + timedelta(minutes=i)).tz_convert("UTC") for i in range(330)]
    close = [4.0 + 0.004 * i + 0.30 * math.sin(2 * math.pi * i / 40)
             for i in range(len(idx))]
    vol = [130_000.0 if i % 3 == 0 else 40_000.0 for i in range(len(idx))]
    df = pd.DataFrame({"symbol": "AAA", "open": close,
                       "high": [c + 0.02 for c in close],
                       "low": [c - 0.02 for c in close],
                       "close": close, "volume": vol},
                      index=pd.DatetimeIndex(idx))
    monkeypatch.setattr("common.dbn_io.read_dbn", lambda p: df)
    monkeypatch.setattr("common.friction_quotes.quotes_for_date",
                        lambda *a, **k: pd.DataFrame())
    fs = pd.Timestamp(f"{D.isoformat()}T04:00:00-05:00").tz_convert(
        "UTC").isoformat()
    _day, rows, _err = Q.run_day(([f"{D.isoformat()}.dbn"], D.isoformat(),
                                  [{"symbol": "AAA", "date": D.isoformat(),
                                    "first_seen": fs}], "/archive"))
    sides = {}
    for r in rows:
        sides.setdefault((r["date"], r["symbol"], r["trade"]), set()).add(r["side"])
    assert sides and all(v == {"BUY", "SELL"} for v in sides.values())


# --- the price probe --------------------------------------------------------

def test_the_probe_can_scope_a_price_to_the_watchlist(tmp_path):
    """ALL_SYMBOLS on a depth schema prices ~11,000 names to answer a question
    about forty, and a figure that large kills an idea that was never that
    expensive."""
    import json
    from common import databento_probe as P
    p = tmp_path / "pairs.json"
    p.write_text(json.dumps(
        [{"date": "2026-01-02", "symbol": s} for s in ("CCC", "AAA", "BBB")]
        + [{"date": "2026-01-05", "symbol": "ZZZ"}]), encoding="utf-8")
    assert P.universe_symbols(p, "2026-01-02") == ["AAA", "BBB", "CCC"]
    assert P.universe_symbols(p, "2026-01-05") == ["ZZZ"]


def test_the_busiest_session_is_used_when_no_day_is_named(tmp_path):
    """A quiet day would understate every other one."""
    import json
    from common import databento_probe as P
    p = tmp_path / "pairs.json"
    p.write_text(json.dumps(
        [{"date": "2026-01-05", "symbol": "ZZZ"}]
        + [{"date": "2026-01-02", "symbol": s} for s in ("AAA", "BBB")]), encoding="utf-8")
    assert P.universe_symbols(p) == ["AAA", "BBB"]


def test_the_scope_limit_matches_the_live_watchlist_cap(tmp_path):
    import json
    from common import databento_probe as P
    from common.tv_feed import MAX_SYMBOLS
    p = tmp_path / "pairs.json"
    p.write_text(json.dumps([{"date": "d", "symbol": f"S{i:03d}"}
                             for i in range(100)]), encoding="utf-8")
    assert len(P.universe_symbols(p, limit=MAX_SYMBOLS)) == MAX_SYMBOLS
    assert P.build_parser_default_scope_limit() == MAX_SYMBOLS


def test_the_scoped_price_is_printed_beside_the_universe_one():
    """Both, because each hides the other's failure: the scoped number looks
    affordable while hiding what a wider universe would cost later."""
    from common import databento_probe as P

    class FakeClient:
        class metadata:
            @staticmethod
            def get_billable_size(**kw):
                return 1_000_000 if kw["symbols"] == "ALL_SYMBOLS" else 50_000

            @staticmethod
            def get_cost(**kw):
                return 10.0 if kw["symbols"] == "ALL_SYMBOLS" else 0.5

    lines = []
    P.emit = lambda text, out=None, **k: lines.append(text)      # noqa: E731
    P.probe_sizes(FakeClient(), "2026-08-04", [("XNAS.BASIC", "mbp-10")],
                  out=None, window="04:00-09:30", symbols=["AAA", "BBB"])
    text = lines[0]
    assert "10.0000" in text and "0.5000" in text
    assert "scoped to watchlist" in text
    assert "5.0% of the universe cost" in text


# --- the defect this module shipped with ------------------------------------

def test_the_quote_is_matched_at_the_END_of_the_bar():
    """THE BUG THIS MODULE SHIPPED WITH, AND THE MOST DANGEROUS SHAPE AN ERROR
    CAN TAKE HERE.

    dbn_io's own first paragraph: "ts_event is the interval START. A bar
    stamped 09:30 covers 09:30:00-09:30:59." The fill is at the CLOSE. The
    first version matched the prevailing quote at the bar's STAMP -- a minute
    early, on bars the rule selects for HAVING MOVED -- so the model appeared
    to pay 12c above the offer and sell 5.75c below the bid, and repricing at
    the book invented +$30.54 per trade. A correction that turns a losing
    strategy profitable is exactly what nobody checks twice.
    """
    t = pd.Timestamp("2026-03-02 09:30:00", tz="UTC")
    got = Q.fill_instant(t, "mcl")
    assert got > t, "the quote is being matched before the fill happened"
    assert got < t + pd.Timedelta(seconds=60), (
        "the match instant reaches into the NEXT bar, which is the same "
        "off-by-one in the other direction")
    assert got == t + pd.Timedelta(seconds=60) - pd.Timedelta(nanoseconds=1)


def test_the_bar_length_follows_the_strategys_own():
    from strategy.mc5 import mc5 as MC5
    assert Q.BAR_SECONDS["mc5"] == MC5.BAR_MINUTES * 60
    assert Q.BAR_SECONDS["mcl"] == 60
    t = pd.Timestamp("2026-03-02 09:30:00", tz="UTC")
    assert Q.fill_instant(t, "mc5") - t == pd.Timedelta(
        minutes=MC5.BAR_MINUTES) - pd.Timedelta(nanoseconds=1)


def test_a_quote_inside_the_bar_is_preferred_to_one_at_its_stamp(monkeypatch):
    """THE BEHAVIOURAL VERSION. Two quotes, one at the bar's stamp and one just
    before its close at a different price: the fill must be priced against the
    later one."""
    import math
    from datetime import date, datetime, time as dtime, timedelta
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
    D = date(2026, 3, 2)
    idx = []
    for d in (D - timedelta(days=1), D):
        b = pd.Timestamp(datetime.combine(d, dtime(4, 0), tzinfo=ET))
        idx += [(b + timedelta(minutes=i)).tz_convert("UTC") for i in range(330)]
    close = [4.0 + 0.004 * i + 0.30 * math.sin(2 * math.pi * i / 40)
             for i in range(len(idx))]
    vol = [130_000.0 if i % 3 == 0 else 40_000.0 for i in range(len(idx))]
    df = pd.DataFrame({"symbol": "AAA", "open": close,
                       "high": [c + 0.02 for c in close],
                       "low": [c - 0.02 for c in close],
                       "close": close, "volume": vol},
                      index=pd.DatetimeIndex(idx))
    monkeypatch.setattr("common.dbn_io.read_dbn", lambda p: df)

    # A quote at every bar's stamp priced at 1.00/1.02, and one 59s later at
    # 9.00/9.02. Matching at the stamp picks the first; matching at the close
    # picks the second, and the two are not confusable.
    rows = []
    for ts in idx:
        rows.append({"ts": ts, "symbol": "AAA", "bid": 1.00, "ask": 1.02,
                     "bid_sz": 100.0, "ask_sz": 100.0})
        rows.append({"ts": ts + pd.Timedelta(seconds=59), "symbol": "AAA",
                     "bid": 9.00, "ask": 9.02, "bid_sz": 100.0,
                     "ask_sz": 100.0})
    quotes = pd.DataFrame(rows).sort_values("ts").reset_index(drop=True)
    monkeypatch.setattr("common.friction_quotes.quotes_for_date",
                        lambda *a, **k: quotes)

    fs = pd.Timestamp(f"{D.isoformat()}T04:00:00-05:00").tz_convert(
        "UTC").isoformat()
    _day, out, _err = Q.run_day(([f"{D.isoformat()}.dbn"], D.isoformat(),
                                 [{"symbol": "AAA", "date": D.isoformat(),
                                   "first_seen": fs}], "/archive"))
    priced = [r for r in out if r.get("covered")]
    assert priced, "nothing was priced; the test proves nothing"
    assert all(r["bid"] == 9.00 for r in priced), (
        "the fill was priced against the quote at the bar's STAMP, one bar "
        "before the close it is meant to price")


def test_the_report_states_where_in_the_bar_the_quote_is_taken():
    rows = Q.enrich(both())
    out = "\n".join(Q.render(rows, Q.pairs(rows), 10, 8, 1.0, 1))
    assert "LAST NANOSECOND" in out and "stamped at its START" in out
