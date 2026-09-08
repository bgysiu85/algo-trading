#!/usr/bin/env python3
"""The capacity measurement says what it says it says.

Capacity is the number that decides whether any of this scales past 100
shares, and it is measured on volume the cache happens to carry. Two things
therefore have to be true and are asserted here: the arithmetic is right on a
frame worked by hand, and the report cannot print a capacity figure without
saying what share of the tape it was measured on.
"""
from __future__ import annotations

import csv
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from common import capacity as CAP

ET = ZoneInfo("America/New_York")


def bars(volumes, price=10.0, start="2026-01-07 04:00"):
    t0 = pd.Timestamp(start, tz=ET)
    idx = pd.DatetimeIndex(
        [t0 + timedelta(minutes=i) for i in range(len(volumes))]
    ).tz_convert("UTC")
    df = pd.DataFrame(
        {"open": price, "high": price, "low": price, "close": price,
         "volume": [float(v) for v in volumes]}, index=idx)
    return df


def trade(df, i_entry, i_exit, qty=100, price=10.0, net=-5.0, reason="trailing_stop"):
    return {"symbol": "T", "date": "2026-01-07",
            "entry_time": str(df.index[i_entry]),
            "exit_time": str(df.index[i_exit]),
            "entry_price": price, "exit_price": price, "qty": qty,
            "net": net, "reason": reason}


def test_one_minute_strategy_measures_the_trade_s_own_two_minutes():
    df = bars([1_000, 40_000, 5_000, 8_000])
    r = CAP.measure(trade(df, 1, 3), df, minutes=1)
    assert r.entry_minute_volume == 40_000
    assert r.exit_minute_volume == 8_000
    # The window equals the minute when the strategy's bar is one minute.
    assert r.entry_window_volume == 40_000


def test_the_binding_side_is_the_thinner_one_and_is_named():
    df = bars([1_000, 40_000, 5_000, 8_000])
    r = CAP.measure(trade(df, 1, 3), df, minutes=1)
    assert r.binding_volume == 8_000
    assert r.binding_side == "exit"

    # And the other way round, so the label is not a constant.
    df2 = bars([1_000, 8_000, 5_000, 40_000])
    r2 = CAP.measure(trade(df2, 1, 3), df2, minutes=1)
    assert r2.binding_volume == 8_000
    assert r2.binding_side == "entry"


def test_a_five_minute_bar_fills_in_its_last_printing_minute_not_its_first():
    """THE TRAP THIS TEST EXISTS FOR. A 5-minute strategy stamps entry_time
    with the bar's START and fills at its CLOSE. Measuring participation
    against the whole 5-minute window credits the order with liquidity from
    four minutes it was not present for -- here, 5x too much."""
    df = bars([100, 200, 300, 400, 9_000, 1_000])
    r = CAP.measure(trade(df, 0, 5), df, minutes=5)
    assert r.entry_minute_volume == 9_000        # the closing minute
    assert r.entry_window_volume == 10_000       # the optimistic reading
    assert r.entry_minute_volume < r.entry_window_volume


def test_minutes_that_did_not_print_are_skipped_not_counted_as_zero():
    """A zero-volume minute is a minute with no print. Taking it as the fill
    minute would report a capacity of zero shares for a trade that filled
    perfectly well one minute earlier."""
    df = bars([100, 5_000, 0, 0, 0])
    r = CAP.measure(trade(df, 0, 1), df, minutes=5)
    assert r.entry_minute_volume == 5_000


def test_a_trade_whose_minutes_are_absent_returns_none_and_is_counted():
    df = bars([1_000, 2_000])
    t = trade(df, 0, 1)
    t["entry_time"] = "2026-01-09 09:00:00+00:00"
    t["exit_time"] = "2026-01-09 09:05:00+00:00"
    assert CAP.measure(t, df, minutes=1) is None


def rows_for_report(n=10):
    df = bars([1_000] * (n + 2))
    return [CAP.measure(trade(df, 0, 1), df, minutes=1) for _ in range(n)]


def test_the_report_refuses_to_look_measured_when_the_tape_share_is_unknown():
    """Capacity scales linearly with the cache's share of the tape. A report
    that prints share counts without saying which tape they came from is the
    ORB pre-flight's failure again: correct numbers, unreadable."""
    text = "\n".join(CAP.render(rows_for_report(), 0, "t.csv", 1, 40.0, None))
    assert "TAPE CAPTURE -- NOT MEASURED" in text
    assert "lower" in text and "bound" in text

    measured = "\n".join(
        CAP.render(rows_for_report(), 0, "t.csv", 1, 40.0, [0.8] * 20))
    assert "TAPE CAPTURE -- NOT MEASURED" not in measured
    assert "1.2x" in measured        # 1 / 0.8, printed for the reader to apply


def test_the_implied_account_follows_the_equity_percentage_it_was_given():
    """implied account = position dollars / (equity_pct/100). Doubling the
    percentage must halve the account the same position implies -- if it does
    not, the number is decorative."""
    rows = rows_for_report()
    a = "\n".join(CAP.render(rows, 0, "t.csv", 1, 40.0, [0.9] * 20))
    b = "\n".join(CAP.render(rows, 0, "t.csv", 1, 80.0, [0.9] * 20))
    assert a != b


def test_participation_caps_are_a_percentage_and_not_a_multiple():
    """Worked by hand. Binding minute 8,000 shares at $10, cap 1%, one
    position may take 40% of equity:

        shares   8,000 x 0.01           =     80
        dollars  80 x $10               =   $800
        account  $800 / 0.40            = $2,000

    A mutation dropping the /100 passed the whole suite when this arithmetic
    was only reachable through the report text.
    """
    df = bars([1_000, 40_000, 5_000, 8_000], price=10.0)
    r = CAP.measure(trade(df, 1, 3), df, minutes=1)
    shares, notional, equity = CAP.size_at(r, 1.0, 40.0)
    assert shares == pytest.approx(80.0)
    assert notional == pytest.approx(800.0)
    assert equity == pytest.approx(2_000.0)

    # 10% is exactly ten times 1%, and 80% of equity halves the account.
    assert CAP.size_at(r, 10.0, 40.0)[0] == pytest.approx(800.0)
    assert CAP.size_at(r, 1.0, 80.0)[2] == pytest.approx(1_000.0)


def test_the_caps_reach_the_report_unchanged():
    """The renderer must print size_at()'s numbers, not its own."""
    df = bars([1_000, 40_000, 5_000, 8_000], price=10.0)
    rows = [CAP.measure(trade(df, 1, 3), df, minutes=1)]
    text = "\n".join(CAP.render(rows, 0, "t.csv", 1, 40.0, [0.9] * 5))
    one = text.split("cap 1% of the minute")[1].split("cap 5%")[0]
    assert "80" in one          # shares
    assert "800" in one         # position dollars
    assert "2,000" in one       # implied account


def test_the_cli_writes_a_report_and_a_csv(tmp_path: Path):
    df = bars([1_000, 40_000, 5_000, 8_000])
    cache = tmp_path / "cache" / "3d_to_2000"
    cache.mkdir(parents=True)
    out = df.copy()
    out.index.name = "date"
    out.to_csv(cache / "T_2026-01-07.csv.gz", compression="gzip")

    trades = tmp_path / "trades.csv"
    with open(trades, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(trade(df, 1, 3).keys()))
        w.writeheader()
        w.writerow(trade(df, 1, 3))

    report = tmp_path / "cap.txt"
    csv_out = tmp_path / "cap.csv"
    rc = CAP.main(["--trades", str(trades), "--cache", str(cache),
                   "--out", str(report), "--csv", str(csv_out)])
    assert rc == 0
    text = report.read_text()
    assert "CAPACITY" in text
    assert "trades measured   1" in text
    with open(csv_out, newline="") as fh:
        got = list(csv.DictReader(fh))
    assert len(got) == 1
    assert float(got[0]["binding_volume"]) == 8_000
