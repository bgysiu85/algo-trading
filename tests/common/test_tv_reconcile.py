#!/usr/bin/env python3
"""Splitting TV-vs-broker price differences into parts that add up.

Ben, 2026-09-09: TV's BNC entry referenced $5.10, ours filled at $5.41. 31c on
a $5 name, against a 5% trail. The decomposition either sums exactly to that
difference or it is decoration, so most of what is tested here is the identity
and the signs.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from common import tv_reconcile as R

ET = ZoneInfo("America/New_York")


def ms(hh, mm, ss=0, day=9):
    return int(datetime(2026, 9, day, hh, mm, ss,
                        tzinfo=ET).timestamp() * 1000)


def alert(symbol="BNC", action="BUY", ref=5.10, close_h=6, close_m=22,
          reason="entry_signal", strategy="MCL"):
    close = ms(close_h, close_m)
    return {"v": 1, "strategy": strategy, "symbol": symbol, "action": action,
            "reason": reason, "bar_time_ms": close - 60_000,
            "bar_close_ms": close, "ref_close": ref, "qty": 100, "tf": "1"}


def fill(symbol="BNC", action="BUY", ref=5.22, bid=5.40, ask=5.42, px=5.41,
         hh=6, mm=23, ss=1, status="FILLED"):
    return {"ts_et": f"2026-09-09 {hh:02d}:{mm:02d}:{ss:02d}",
            "strategy": "MCL", "symbol": symbol, "action": action,
            "reason": "entry_signal", "ref_close": str(ref),
            "bid": str(bid), "ask": str(ask), "fill_price": str(px),
            "filled_qty": "100", "status": status,
            "_ts": datetime(2026, 9, 9, hh, mm, ss, tzinfo=ET)}


# --- reading the payload -----------------------------------------------------

def test_the_payload_survives_whatever_wraps_it():
    """The delivery path is not chosen yet and every candidate adds something
    around the JSON. Requiring a bare line would make the tool depend on a
    decision that has not been made."""
    body = ('{"v":1,"strategy":"MCL","symbol":"NASDAQ:BNC","action":"BUY",'
            '"reason":"entry_signal","bar_time_ms":1,"bar_close_ms":2,'
            '"ref_close":5.1,"qty":100,"tf":"1"}')
    for line in (body,
                 "2026-09-09T10:22:01Z webhook " + body,
                 "MCL alert fired: " + body + "  (delivered)"):
        got = R.parse_alert(line)
        assert got is not None and got["ref_close"] == 5.1


def test_the_exchange_prefix_is_stripped_so_symbols_join():
    """TradingView says NASDAQ:BNC, the fill log says BNC. Left alone, nothing
    would ever match and the report would read as 'TV disagreed with us on
    every trade'."""
    assert R.parse_alert('{"symbol":"NASDAQ:BNC","action":"BUY"}')["symbol"] \
        == "BNC"


def test_junk_is_skipped_rather_than_crashing_the_run():
    for line in ("", "   ", "heartbeat ok", "{not json}", '{"a":1}', "{}"):
        assert R.parse_alert(line) is None


def test_the_actionable_time_is_the_bar_close_not_the_bar_label():
    """A strategy that acts on a closed bar cannot act at the bar's label.
    Measuring latency from the label would charge us for the bar's own
    duration and make every entry look a minute worse than it is."""
    a = alert(close_h=6, close_m=22)
    t = R.alert_time(a)
    assert (t.hour, t.minute) == (6, 22)
    assert t != datetime.fromtimestamp(a["bar_time_ms"] / 1000, ET)


def test_an_alert_with_no_close_stamp_yields_no_time():
    assert R.alert_time({"symbol": "BNC", "action": "BUY"}) is None


# --- the decomposition -------------------------------------------------------

def test_the_parts_sum_exactly_to_the_difference():
    """The identity is the whole point. If the parts do not add up, each one
    is a guess with a label on it."""
    a, f = alert(ref=5.10), fill(ref=5.22, ask=5.42, px=5.41)
    d = R.decompose(f, a)
    assert d["bar_gap"] + d["drift"] + d["execution"] == pytest.approx(
        d["cost"])
    assert d["cost"] == pytest.approx(5.41 - 5.10)


def test_bens_bnc_trade_decomposes_the_way_the_fill_log_says():
    """The measured row. TV referenced 5.10, our signal bar closed at 5.22,
    the ask was 5.42 when the order went out, and we filled at 5.41 -- a cent
    INSIDE the ask. So execution is not the problem and the report must not
    let anyone conclude that it is."""
    d = R.decompose(fill(ref=5.22, bid=5.40, ask=5.42, px=5.41), alert(ref=5.10))
    assert d["bar_gap"] == pytest.approx(0.12)
    assert d["drift"] == pytest.approx(0.20)
    assert d["execution"] == pytest.approx(-0.01)
    assert d["cost"] == pytest.approx(0.31)
    assert d["cost_pct"] == pytest.approx(100 * 0.31 / 5.10, rel=1e-6)


def test_a_sell_is_signed_so_that_positive_is_still_money_lost():
    """Without the flip, buys and sells cannot be added or averaged: a report
    that mixed them would cancel real costs against each other and understate
    the total."""
    a = alert(action="SELL", ref=5.50)
    f = fill(action="SELL", ref=5.40, bid=5.20, ask=5.22, px=5.20)
    d = R.decompose(f, a)
    assert d["cost"] == pytest.approx(5.50 - 5.20)
    assert d["cost"] > 0, "receiving less than TV's reference is a LOSS"
    assert d["bar_gap"] + d["drift"] + d["execution"] == pytest.approx(
        d["cost"])


def test_a_sell_that_beat_the_reference_is_negative():
    d = R.decompose(fill(action="SELL", ref=5.60, bid=5.62, ask=5.64, px=5.62),
                    alert(action="SELL", ref=5.50))
    assert d["cost"] < 0


def test_a_buy_crosses_the_ask_and_a_sell_hits_the_bid():
    """Measuring execution against the wrong side of the book would report the
    spread as broker cost on every single trade."""
    buy = R.decompose(fill(ref=5.20, bid=5.40, ask=5.42, px=5.42),
                      alert(ref=5.20))
    assert buy["execution"] == pytest.approx(0.0), "filled AT the ask"
    sell = R.decompose(fill(action="SELL", ref=5.20, bid=5.00, ask=5.02,
                            px=5.00), alert(action="SELL", ref=5.20))
    assert sell["execution"] == pytest.approx(0.0), "filled AT the bid"


def test_latency_is_measured_from_the_bar_close():
    d = R.decompose(fill(hh=6, mm=23, ss=1), alert(close_h=6, close_m=22))
    assert d["latency_s"] == pytest.approx(61)


def test_a_fill_with_no_alert_decomposes_to_nothing():
    assert R.decompose(fill(), None) is None


def test_a_fill_missing_a_quote_is_not_silently_scored_as_zero():
    """A blank ask scored as 0.0 would report the entire price as execution
    cost -- a spectacular number that would send us to the wrong problem."""
    f = fill()
    f["ask"] = ""
    assert R.decompose(f, alert()) is None


# --- matching ----------------------------------------------------------------

def test_a_fill_matches_the_alert_that_preceded_it():
    m = R.match([alert()], [fill()])
    assert m[0]["alert"] is not None


def test_an_alert_after_the_fill_is_never_the_cause_of_it():
    m = R.match([alert(close_h=6, close_m=30)], [fill(hh=6, mm=23)])
    assert m[0]["alert"] is None


def test_a_stale_alert_is_not_matched_to_a_much_later_fill():
    m = R.match([alert(close_h=4, close_m=0)], [fill(hh=6, mm=23)])
    assert m[0]["alert"] is None


def test_each_alert_is_consumed_once():
    """On a name that signals twice in a morning, a greedy nearest-match would
    give both fills to whichever alert was closer and report a latency of
    seconds for a trade that took minutes."""
    a1 = alert(close_h=6, close_m=22, ref=5.10)
    a2 = alert(close_h=6, close_m=28, ref=5.60)
    m = R.match([a1, a2], [fill(hh=6, mm=23), fill(hh=6, mm=29)])
    assert [p["alert"]["ref_close"] for p in m] == [5.10, 5.60]


def test_one_alert_cannot_explain_two_fills():
    """The case consumption actually exists for. With two alerts and two fills
    the nearest-preceding rule already pairs them correctly, so it proves
    nothing; ONE alert and two fills is where a non-consuming matcher credits
    the same signal twice and reports a second trade that TV never called."""
    m = R.match([alert(close_h=6, close_m=22, ref=5.10)],
                [fill(hh=6, mm=23), fill(hh=6, mm=25)])
    assert [p["alert"] is not None for p in m] == [True, False]


def test_the_nearest_preceding_alert_wins():
    a_old = alert(close_h=6, close_m=15, ref=5.00)
    a_new = alert(close_h=6, close_m=22, ref=5.10)
    m = R.match([a_old, a_new], [fill(hh=6, mm=23)])
    assert m[0]["alert"]["ref_close"] == 5.10


def test_a_buy_is_never_matched_to_a_sell_alert():
    m = R.match([alert(action="SELL")], [fill(action="BUY")])
    assert m[0]["alert"] is None


def test_a_different_symbol_is_never_matched():
    m = R.match([alert(symbol="ACCL")], [fill(symbol="BNC")])
    assert m[0]["alert"] is None


def test_unfilled_rows_are_not_treated_as_trades(tmp_path):
    """The fill log records rejects and cancels too. Scoring a cancel as an
    execution cost of its whole limit price would swamp every real number."""
    p = tmp_path / "f.csv"
    rows = [fill(), fill(symbol="ZZZ", status="CANCELLED")]
    import csv
    with open(p, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=[k for k in rows[0] if k != "_ts"])
        w.writeheader()
        for r in rows:
            w.writerow({k: v for k, v in r.items() if k != "_ts"})
    got = R.load_fills(p)
    assert [r["symbol"] for r in got] == ["BNC"]


# --- the report --------------------------------------------------------------

def report(alerts, fills):
    return "\n".join(R.render(R.match(alerts, fills), "f.csv", "a.jsonl"))


def test_the_report_names_the_largest_component_and_what_it_means():
    """A table of three numbers invites the reader to act on whichever looks
    biggest without knowing which are even fixable."""
    text = report([alert(ref=5.10)], [fill(ref=5.22, ask=5.42, px=5.41)])
    assert "LARGEST COMPONENT: drift" in text
    assert "reaching the book" in text


def test_the_report_does_not_blame_the_broker_when_execution_is_clean():
    text = report([alert(ref=5.10)], [fill(ref=5.22, ask=5.42, px=5.41)])
    assert "LARGEST COMPONENT: execution" not in text


def test_the_report_calls_out_bar_alignment_when_that_dominates():
    """The case where no order type helps, and the one most likely to be
    misread as slippage."""
    text = report([alert(ref=5.00)], [fill(ref=5.40, bid=5.40, ask=5.41,
                                           px=5.41)])
    assert "LARGEST COMPONENT: bar_gap" in text
    assert "timing defect, not an execution one" in text


def test_an_empty_alert_file_says_why_rather_than_showing_zero_trades():
    """A silent empty report would be read as 'no difference found', which is
    the opposite of what it means."""
    text = report([], [fill()])
    assert "NOTHING MATCHED" in text
    assert "alert() function calls only" in text, (
        "the most likely cause is the alert's event type, and it must say so")


def test_unmatched_fills_are_not_presented_as_disagreement():
    text = report([], [fill()])
    assert "no matching alert" in text
    assert "NOT evidence" in text


def test_the_report_states_the_identity_it_relies_on():
    text = report([alert()], [fill()])
    assert "bar_gap + drift + execution" in text
    assert "Positive is money" in text


def test_the_report_sends_a_long_latency_to_the_freshness_probe():
    text = report([alert(ref=5.10)], [fill(ref=5.22, ask=5.42, px=5.41)])
    assert "bar_freshness" in text
