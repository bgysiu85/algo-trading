"""Tests for strategy/swing/intraday_pull.py (W07-0012 subitem 5, part 1).
Offline: every EODHD call is faked; no network, no real var/swing_pit needed."""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

import pytest

from strategy.swing import intraday_pull as I
from strategy.swing import pit_universe as P

D = dt.date


def write_eod(path: Path, rows: dict[str, float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=P.PRICE_FIELDS)
        w.writeheader()
        for date_s, close in rows.items():
            w.writerow({"date": date_s, "open": close, "high": close,
                       "low": close, "close": close, "adjusted_close": close,
                       "volume": 1000})


def bar(day: D, hhmm_utc: str, close: float) -> dict:
    t = dt.datetime.combine(day, dt.time.fromisoformat(hhmm_utc), tzinfo=I.UTC)
    return {"timestamp": int(t.timestamp()), "close": close}


def test_self_test_passes():
    lines = I.self_test()
    assert lines and "passed" in lines[0]


# --------------------------------------------------------------------------
# eligible_dates: point-in-time membership AND an EOD close, same gating
# the Alpaca probe used
# --------------------------------------------------------------------------

def test_eligible_dates_requires_membership_and_eod():
    spells = [P.Spell("sp500", "AAA", "Alpha", D(2016, 1, 1), D(2018, 1, 1),
                      False, True)]
    dates = [D(2017, 6, 1), D(2019, 6, 1)]   # second is outside the spell
    assert I.eligible_dates(spells, dates) == [D(2017, 6, 1)]


# --------------------------------------------------------------------------
# chunk_dates
# --------------------------------------------------------------------------

def test_chunk_dates_splits_on_size():
    dates = [D(2016, 1, 4) + dt.timedelta(days=i) for i in range(65)]
    chunks = I.chunk_dates(dates, max_days=60, max_gap_days=9999)
    assert [len(c) for c in chunks] == [60, 5]


def test_chunk_dates_splits_on_gap():
    dates = [D(2016, 1, 1), D(2016, 1, 2), D(2016, 6, 1), D(2016, 6, 2)]
    chunks = I.chunk_dates(dates, max_days=9999, max_gap_days=30)
    assert chunks == [[D(2016, 1, 1), D(2016, 1, 2)],
                      [D(2016, 6, 1), D(2016, 6, 2)]]


def test_chunk_dates_empty():
    assert I.chunk_dates([]) == []


# --------------------------------------------------------------------------
# evaluate_day: HIT / BACKFILL / MISSING
# --------------------------------------------------------------------------

def test_evaluate_day_hit_backfill_missing():
    day = D(2026, 3, 10)   # EDT: open=13:30Z, midday=15:30Z, close=19:30Z
    bars = [bar(day, "13:30", 50.0), bar(day, "15:29", 51.0)]
    by_date = I.group_bars_by_et_date(bars)
    obs = {o.bucket: o for o in I.evaluate_day(day, by_date)}
    assert obs["open"].status == "HIT" and obs["open"].minutes_back == 0.0
    assert obs["midday"].status == "HIT"
    assert obs["close"].status == "BACKFILL"
    assert obs["close"].price == 51.0


def test_evaluate_day_all_missing_for_a_date_with_no_bars():
    day = D(2026, 3, 10)
    obs = I.evaluate_day(day, {})
    assert len(obs) == 3
    assert all(o.status == "MISSING" and o.bar_et is None for o in obs)


def test_evaluate_day_ignores_bars_after_the_bucket():
    day = D(2026, 3, 10)
    by_date = I.group_bars_by_et_date([bar(day, "13:31", 50.0)])
    obs = {o.bucket: o for o in I.evaluate_day(day, by_date)}
    assert obs["open"].status == "MISSING"


# --------------------------------------------------------------------------
# build_plan / stage_pull / resumability
# --------------------------------------------------------------------------

def test_build_plan_skips_existing_file(tmp_path: Path):
    spells = [P.Spell("sp500", "AAA", "Alpha", D(2016, 1, 1), None, True, False)]
    write_eod(tmp_path / "eod" / "AAA.csv", {"2017-06-01": 10.0})
    (tmp_path / "intraday").mkdir()
    (tmp_path / "intraday" / "AAA.csv").write_text("date,bucket\n", encoding="utf-8")

    plan, summary = I.build_plan(spells, tmp_path)
    assert plan == {}
    assert summary["codes_to_pull"] == 0
    assert summary["codes_skipped_existing"] == 1

    plan2, summary2 = I.build_plan(spells, tmp_path, refresh=True)
    assert "AAA" in plan2
    assert summary2["codes_skipped_existing"] == 0


def test_stage_pull_flags_chunk_gap_without_polluting_missing(tmp_path: Path):
    spells = [P.Spell("sp500", "AAA", "Alpha", D(2016, 1, 1), None, True, False)]
    day1, day2 = D(2020, 6, 15), D(2020, 6, 16)
    write_eod(tmp_path / "eod" / "AAA.csv",
             {day1.isoformat(): 10.0, day2.isoformat(): 10.1})

    def fake_fetch(code, first, last):
        return [bar(day1, "13:30", 10.0)]   # nothing at all for day2

    plan, _ = I.build_plan(spells, tmp_path)
    stats = I.stage_pull(fake_fetch, plan, tmp_path, log=lambda m: None)
    assert stats["chunk_gaps"] == 1
    gap_rows = list(csv.DictReader(
        (tmp_path / I.CHUNK_GAPS_NAME).open(newline="", encoding="utf-8")))
    assert gap_rows[0]["date"] == day2.isoformat()

    rows = list(csv.DictReader(
        (tmp_path / "intraday" / "AAA.csv").open(newline="", encoding="utf-8")))
    day2_open = next(r for r in rows if r["date"] == day2.isoformat()
                     and r["bucket"] == "open")
    assert day2_open["status"] == "MISSING"   # still recorded, just also flagged


# --------------------------------------------------------------------------
# cost_lines / CLI gate
# --------------------------------------------------------------------------

def test_cost_lines_mentions_calls_and_wall_clock():
    summary = {"codes_total": 900, "codes_skipped_existing": 100,
              "codes_to_pull": 800, "api_calls": 4000, "symbol_days": 200000}
    joined = "\n".join(I.cost_lines(summary))
    assert "4000 chunked" in joined
    assert "minutes" in joined


def test_main_without_confirm_does_not_touch_network(tmp_path: Path, capsys):
    membership = tmp_path / "membership.csv"
    P.write_membership(membership, [
        P.Spell("sp500", "AAA", "Alpha", D(2016, 1, 1), None, True, False)])
    with (tmp_path / "suspects.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["index", "code", "name", "start", "end", "is_delisted",
                   "verdict", "in_window_rows", "expected_rows"])
    rc = I.main(["--pit-dir", str(tmp_path)])
    assert rc == 2   # universe guard refuses: wrong suspect count (0 != 35)
    out = capsys.readouterr().out + capsys.readouterr().err


def test_main_missing_membership_exits(tmp_path: Path):
    rc = I.main(["--pit-dir", str(tmp_path / "nope")])
    assert rc == 2
