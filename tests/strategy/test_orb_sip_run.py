#!/usr/bin/env python3
"""strategy/orb/sip_run.py -- the trade ledger, before any arm exists.

What matters here: every QUALIFYING name is traded (the unfiltered arm is a
registered control, so the ledger cannot be pre-filtered to the top 20), the
rank and RVOL that travel with a row are the ones for that row's range length,
the holdout is withheld by default, and the price tape is refused if it is not
the registered one.
"""
from __future__ import annotations

import pandas as pd
import pytest

from strategy.orb import sip as S
from strategy.orb import sip_run as R

ET = "America/New_York"
DAY = "2025-03-05"


def bars(rows, symbol="AAA"):
    idx = pd.to_datetime([f"{DAY} {t}" for t, *_ in rows]).tz_localize(ET).tz_convert("UTC")
    return pd.DataFrame({"open": [r[1] for r in rows], "high": [r[2] for r in rows],
                         "low": [r[3] for r in rows], "close": [r[4] for r in rows],
                         "symbol": symbol}, index=idx)


RISE = [("09:30", 10.0, 10.2, 9.9, 10.1), ("09:31", 10.1, 10.3, 10.0, 10.2),
        ("09:32", 10.2, 10.4, 10.1, 10.3), ("09:33", 10.3, 10.5, 10.2, 10.4),
        ("09:34", 10.4, 10.6, 10.3, 10.5), ("09:35", 10.6, 10.8, 10.6, 10.7),
        ("09:44", 10.7, 10.9, 10.65, 10.85), ("09:45", 11.0, 11.2, 11.0, 11.1),
        ("15:59", 11.1, 11.2, 11.0, 11.05)]


def univ_row(symbol="AAA", **kw):
    row = {"symbol": symbol, "date": DAY, "open": 10.0, "atr14": 1.0,
           "advol14": 5e6, "rvol5": 9.0, "rank5": 1.0, "eligible5": True,
           "rvol15": 3.0, "rank15": 7.0, "eligible15": True, "qualifies": True}
    row.update(kw)
    return row


def test_a_qualifying_name_is_traded_at_both_registered_range_lengths():
    rows, status = R.trade_session(bars(RISE), pd.DataFrame([univ_row()]), DAY)
    led = pd.DataFrame(rows, columns=R.LEDGER_COLS)
    assert sorted(led["range"]) == [5, 15]
    assert set(led["symbol"]) == {"AAA"} and (led["side"] == S.LONG).all()
    assert any(k.startswith("5:") for k in status)


def test_the_rank_and_rvol_on_a_row_belong_to_that_rows_range_length():
    """A 15-minute row carrying the 5-minute rank would put the wrong names in
    the top 20 of the secondary reading, and nothing downstream could tell."""
    rows, _ = R.trade_session(bars(RISE), pd.DataFrame([univ_row()]), DAY)
    led = pd.DataFrame(rows, columns=R.LEDGER_COLS).set_index("range")
    assert (led.loc[5, "rvol"], led.loc[5, "rank"]) == (9.0, 1.0)
    assert (led.loc[15, "rvol"], led.loc[15, "rank"]) == (3.0, 7.0)


def test_a_name_outside_the_top_twenty_is_still_in_the_ledger():
    """Section 4's unfiltered arm and the random-20 control both draw from the
    whole qualifying set, so the ledger must not be pre-filtered by rank."""
    rows, _ = R.trade_session(bars(RISE),
                              pd.DataFrame([univ_row(rank5=417.0, rvol5=1.1)]), DAY)
    led = pd.DataFrame(rows, columns=R.LEDGER_COLS)
    assert (led["rank"] == 417.0).any()


def test_a_name_with_rvol_below_one_is_traded_and_marked_not_eligible():
    rows, _ = R.trade_session(
        bars(RISE), pd.DataFrame([univ_row(rvol5=0.4, rank5=float("nan"),
                                           eligible5=False)]), DAY)
    led = pd.DataFrame(rows, columns=R.LEDGER_COLS)
    r5 = led[led["range"] == 5].iloc[0]
    assert not bool(r5.eligible) and pd.isna(r5["rank"])


def test_both_readings_of_amendment_a_travel_on_the_same_row():
    rows = [("09:30", 10.0, 10.2, 9.9, 10.1), ("09:31", 10.1, 10.3, 10.0, 10.2),
            ("09:32", 10.2, 10.4, 10.1, 10.3), ("09:33", 10.3, 10.5, 10.2, 10.4),
            ("09:34", 10.4, 10.6, 10.3, 10.5),
            ("09:35", 10.6, 10.75, 10.4, 10.7),      # entry bar dips to the stop
            ("15:59", 10.9, 11.0, 10.8, 10.95)]
    led = pd.DataFrame(R.trade_session(bars(rows), pd.DataFrame([univ_row()]), DAY)[0],
                       columns=R.LEDGER_COLS)
    r5 = led[led["range"] == 5].iloc[0]
    assert r5.exit_reason == "stop" and r5.exit_px == pytest.approx(10.5)
    assert r5.alt_exit_reason == "session_end" and r5.alt_exit_px == pytest.approx(10.95)


def test_a_gapped_entry_is_flagged():
    rows = RISE[:5] + [("09:35", 12.0, 12.1, 11.9, 12.05), ("15:59", 12.0, 12.1, 11.9, 12.0)]
    led = pd.DataFrame(R.trade_session(bars(rows), pd.DataFrame([univ_row()]), DAY)[0],
                       columns=R.LEDGER_COLS)
    assert bool(led[led["range"] == 5].iloc[0].gapped_entry)
    clean = pd.DataFrame(R.trade_session(bars(RISE), pd.DataFrame([univ_row()]), DAY)[0],
                         columns=R.LEDGER_COLS)
    assert not bool(clean[clean["range"] == 5].iloc[0].gapped_entry)


def test_a_symbol_in_the_universe_with_no_bars_is_counted_not_dropped_silently():
    _, status = R.trade_session(bars(RISE), pd.DataFrame([univ_row(symbol="ZZZ")]), DAY)
    assert status.get("NO_BARS") == 1


def test_only_symbols_in_the_universe_are_traded():
    frame = pd.concat([bars(RISE, "AAA"), bars(RISE, "BBB")])
    rows, _ = R.trade_session(frame, pd.DataFrame([univ_row("AAA")]), DAY)
    led = pd.DataFrame(rows, columns=R.LEDGER_COLS)
    assert set(led["symbol"]) == {"AAA"}


def test_load_universe_keeps_only_qualifying_rows_and_honours_the_window(tmp_path):
    df = pd.DataFrame([univ_row(), univ_row(symbol="BBB", qualifies=False),
                       {**univ_row(symbol="CCC"), "date": "2026-06-01"}])
    p = tmp_path / "u.csv.gz"
    df.to_csv(p, index=False, compression="gzip", encoding="utf-8")
    out = R.load_universe(p, None, None)
    assert set(out["symbol"]) == {"AAA", "CCC"}
    assert set(R.load_universe(p, None, "2025-12-31")["symbol"]) == {"AAA"}


def test_the_holdout_is_withheld_unless_it_is_explicitly_spent(tmp_path, monkeypatch, capsys):
    df = pd.DataFrame([univ_row(), {**univ_row(symbol="CCC"), "date": "2026-06-01"}])
    p = tmp_path / "u.csv.gz"
    df.to_csv(p, index=False, compression="gzip", encoding="utf-8")
    seen = {}
    monkeypatch.setattr(R, "build",
                        lambda *a, **k: seen.setdefault("dates", sorted(a[2]["date"].unique()))
                        and {"sessions": 0, "already": 0, "trades": 0, "status": {}, "failed": []}
                        or {"sessions": 0, "already": 0, "trades": 0, "status": {}, "failed": []})
    args = ["--universe", str(p), "--archive", str(tmp_path), "--out", str(tmp_path / "t")]
    R.main(args)
    assert seen["dates"] == [DAY], "2026-06-01 is inside the locked holdout"
    seen.clear()
    R.main(args + ["--spend-holdout"])
    assert seen["dates"] == [DAY, "2026-06-01"]
    assert R.HOLDOUT_FROM == "2026-05-01"


def test_an_unregistered_price_dataset_is_refused_and_says_why(tmp_path):
    with pytest.raises(SystemExit) as e:
        R.main(["--dataset", "XNAS.BASIC", "--universe", str(tmp_path / "x.csv.gz")])
    msg = str(e.value)
    assert "REFUSING TO RUN" in msg and "XNAS.ITCH" in msg and "209.27" in msg
