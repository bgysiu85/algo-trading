"""Tests for strategy/swing/fill_engine.py (W07-0012 subitem 5, part 2).
Offline: synthetic calendar/picks/intraday store, no network, no real
var/swing_pit needed."""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

import pytest

from strategy.swing import fill_engine as F
from strategy.swing import pit_universe as P

D = dt.date


def test_self_test_passes():
    lines = F.self_test()
    assert lines and "passed" in lines[0]


# --------------------------------------------------------------------------
# load_intraday_store / bucket_price -- reading intraday_pull.py's own shape
# --------------------------------------------------------------------------

def write_intraday(path: Path, rows: list[tuple]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "bucket", "target_et", "bar_et", "minutes_back",
                   "price", "status"])
        for date_s, bucket, price, status in rows:
            w.writerow([date_s, bucket, "", "", "", price if price is not None else "",
                       status])


def test_load_intraday_store_and_bucket_price(tmp_path: Path):
    write_intraday(tmp_path / "AAA.csv", [
        ("2026-01-06", "midday", 10.0, "HIT"),
        ("2026-01-06", "close", None, "MISSING"),
    ])
    store = F.load_intraday_store(["AAA", "NOPE"], tmp_path)
    assert "NOPE" not in store   # no file -> absent, not an error
    px, status = F.bucket_price(store, "AAA", D(2026, 1, 6), "midday")
    assert px == 10.0 and status == "HIT"
    px2, status2 = F.bucket_price(store, "AAA", D(2026, 1, 6), "close")
    assert px2 is None and status2 == "MISSING"
    px3, status3 = F.bucket_price(store, "AAA", D(2026, 1, 7), "midday")
    assert px3 is None and status3 == "NO_ROW"
    px4, status4 = F.bucket_price(store, "NOPE", D(2026, 1, 6), "midday")
    assert px4 is None and status4 == "NO_FILE"


# --------------------------------------------------------------------------
# build_trades: entry timing, exit timing, unfilled reasons
# --------------------------------------------------------------------------

def make_calendar(n=10):
    return [D(2026, 1, 5) + dt.timedelta(days=i) for i in range(n)]


def test_build_trades_prices_entry_next_session_exit_n_later():
    cal = make_calendar()
    picks = {cal[2]: ["AAA"]}
    store = {"AAA": {(cal[3], "midday"): (10.0, "HIT"),
                     (cal[5], "midday"): (12.0, "HIT")}}
    trades, unfilled = F.build_trades(picks, cal, store, "midday", n=2)
    assert not unfilled
    assert len(trades) == 1
    t = trades[0]
    assert t.signal_date == cal[2] and t.entry_date == cal[3] and t.exit_date == cal[5]
    assert t.ret == pytest.approx(0.2)


def test_build_trades_no_next_session_is_unfilled_not_dropped():
    cal = make_calendar()
    picks = {cal[-1]: ["AAA"]}   # signal on the last day -- no next session
    trades, unfilled = F.build_trades(picks, cal, {}, "midday", n=2)
    assert not trades
    assert unfilled and unfilled[0].reason == "no_next_session"


def test_build_trades_insufficient_calendar_for_exit():
    cal = make_calendar()
    picks = {cal[-3]: ["AAA"]}   # entry at cal[-2], exit at cal[-2+5] out of range
    trades, unfilled = F.build_trades(picks, cal, {}, "midday", n=5)
    assert not trades
    assert unfilled[0].reason == "insufficient_calendar_for_exit"


def test_build_trades_missing_entry_and_exit_prices():
    cal = make_calendar()
    picks = {cal[2]: ["AAA", "BBB"]}
    store = {
        "BBB": {(cal[3], "midday"): (10.0, "HIT")},   # entry ok, exit missing
        # AAA: no file at all -> entry missing
    }
    trades, unfilled = F.build_trades(picks, cal, store, "midday", n=2)
    assert not trades
    reasons = {u.code: u.reason for u in unfilled}
    assert reasons["AAA"] == "entry_price_no_file"
    assert reasons["BBB"] == "exit_price_no_row"


def test_build_trades_empty_pick_list_produces_nothing():
    cal = make_calendar()
    picks = {cal[2]: []}
    trades, unfilled = F.build_trades(picks, cal, {}, "midday", n=2)
    assert not trades and not unfilled


# --------------------------------------------------------------------------
# check_no_lookahead -- the mutation-tested guard
# --------------------------------------------------------------------------

def test_check_no_lookahead_passes_for_correctly_built_trades():
    cal = make_calendar()
    t = F.Trade("AAA", cal[2], cal[3], cal[5], "midday", 2, 10.0, 11.0, "HIT", "HIT")
    assert F.check_no_lookahead([t], cal, n=2) == 1


def test_check_no_lookahead_catches_same_day_entry():
    cal = make_calendar()
    bad = F.Trade("AAA", cal[2], cal[2], cal[4], "midday", 2, 10.0, 11.0, "HIT", "HIT")
    with pytest.raises(F.LookaheadError):
        F.check_no_lookahead([bad], cal, n=2)


def test_check_no_lookahead_catches_wrong_n():
    cal = make_calendar()
    bad = F.Trade("AAA", cal[2], cal[3], cal[4], "midday", 2, 10.0, 11.0, "HIT", "HIT")
    with pytest.raises(F.LookaheadError):
        F.check_no_lookahead([bad], cal, n=2)


def test_check_no_lookahead_catches_date_not_in_calendar():
    cal = make_calendar()
    bad = F.Trade("AAA", cal[2], cal[3], D(2099, 1, 1), "midday", 2, 10.0, 11.0,
                  "HIT", "HIT")
    with pytest.raises(F.LookaheadError):
        F.check_no_lookahead([bad], cal, n=2)


# --------------------------------------------------------------------------
# summarize / CSV writers
# --------------------------------------------------------------------------

def test_summarize_counts_fill_rate_and_reasons():
    cal = make_calendar()
    trades = [F.Trade("AAA", cal[2], cal[3], cal[5], "midday", 2, 10.0, 11.0,
                      "HIT", "HIT")]
    unfilled = [F.Unfilled("BBB", cal[2], "midday", 2, "exit_price_no_row"),
               F.Unfilled("CCC", cal[2], "midday", 2, "exit_price_no_row")]
    summary = F.summarize(trades, unfilled)
    assert summary == {
        "picks": 3, "filled": 1, "unfilled": 2, "fill_rate_pct": 33.33,
        "unfilled_by_reason": {"exit_price_no_row": 2},
    }


def test_summarize_empty():
    assert F.summarize([], [])["fill_rate_pct"] is None


def test_write_trades_and_unfilled_csv_roundtrip(tmp_path: Path):
    cal = make_calendar()
    trades = [F.Trade("AAA", cal[2], cal[3], cal[5], "midday", 2, 10.0, 11.0,
                      "HIT", "HIT")]
    unfilled = [F.Unfilled("BBB", cal[2], "midday", 2, "no_next_session")]
    F.write_trades_csv(tmp_path / "trades.csv", trades)
    F.write_unfilled_csv(tmp_path / "unfilled.csv", unfilled)
    trows = list(csv.DictReader((tmp_path / "trades.csv").open(
        newline="", encoding="utf-8")))
    urows = list(csv.DictReader((tmp_path / "unfilled.csv").open(
        newline="", encoding="utf-8")))
    assert trows[0]["code"] == "AAA" and trows[0]["ret"] == "0.1"
    assert urows[0]["code"] == "BBB" and urows[0]["reason"] == "no_next_session"


# --------------------------------------------------------------------------
# CLI gate
# --------------------------------------------------------------------------

def test_main_missing_membership_exits(tmp_path: Path):
    rc = F.main(["run", "--pit-dir", str(tmp_path / "nope")])
    assert rc == 2
