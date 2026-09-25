"""Tests for strategy/swing/alpaca_coverage_probe.py (W07-0012 subitem 2).
Offline: every Alpaca call is faked; no network, no real var/swing_pit needed."""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

import pytest

from strategy.swing import alpaca_coverage_probe as A
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
    return {"t": f"{day.isoformat()}T{hhmm_utc}:00Z", "o": close, "h": close,
           "l": close, "c": close, "v": 100}


# --------------------------------------------------------------------------
# self-test
# --------------------------------------------------------------------------

def test_self_test_passes():
    lines = A.self_test()
    assert lines and "passed" in lines[0]


# --------------------------------------------------------------------------
# keys
# --------------------------------------------------------------------------

def test_api_keys_missing():
    with pytest.raises(P.Refused, match="ALPACA_API_KEY_ID"):
        A.api_keys({})


def test_api_keys_op_reference_rejected():
    with pytest.raises(P.Refused, match="op://"):
        A.api_keys({"ALPACA_API_KEY_ID": "op://Trading/x/y",
                   "ALPACA_API_SECRET_KEY": "secret"})


def test_api_keys_resolved():
    key, secret = A.api_keys({"ALPACA_API_KEY_ID": "id123",
                              "ALPACA_API_SECRET_KEY": "sec456"})
    assert (key, secret) == ("id123", "sec456")


def test_scrub_removes_both_secrets():
    text = A.scrub("error near id123 and sec456", "id123", "sec456")
    assert "id123" not in text and "sec456" not in text


# --------------------------------------------------------------------------
# sampling
# --------------------------------------------------------------------------

def make_spells(n_current: int, n_delisted: int) -> list[P.Spell]:
    out = [P.Spell("sp500", f"C{i:03d}", "current", D(2016, 1, 1), None,
                   True, False) for i in range(n_current)]
    out += [P.Spell("sp500", f"X{i:03d}", "delisted", D(2016, 1, 1),
                    D(2020, 1, 1), False, True) for i in range(n_delisted)]
    return out


def test_pick_sample_symbols_stratifies_by_delisted():
    spells = make_spells(20, 20)
    chosen = A.pick_sample_symbols(spells, n=10, seed=1)
    assert len(chosen) == 10
    n_delisted = sum(1 for c in chosen if c.startswith("X"))
    assert n_delisted >= 5, chosen   # at least half, per min_delisted_frac=0.5


def test_pick_sample_symbols_returns_all_when_n_exceeds_universe():
    spells = make_spells(3, 2)
    chosen = A.pick_sample_symbols(spells, n=100, seed=1)
    assert sorted(chosen) == sorted({s.code for s in spells})


def test_pick_sample_dates_weekdays_only_and_deterministic():
    d1 = A.pick_sample_dates(D(2016, 5, 10), D(2018, 5, 10), n=10, seed=3)
    d2 = A.pick_sample_dates(D(2016, 5, 10), D(2018, 5, 10), n=10, seed=3)
    assert d1 == d2                       # seeded -> reproducible
    assert all(d.weekday() < 5 for d in d1)
    assert len(d1) == len(set(d1)) == 10


def test_pick_sample_dates_empty_window():
    assert A.pick_sample_dates(D(2020, 1, 1), D(2019, 1, 1), n=5, seed=1) == []


# --------------------------------------------------------------------------
# build_plan: membership + EOD gating
# --------------------------------------------------------------------------

def test_member_dates_with_eod_requires_both_membership_and_eod_row(tmp_path: Path):
    spells = [
        P.Spell("sp500", "AAA", "Alpha", D(2016, 1, 1), D(2018, 1, 1),
               False, True),
        P.Spell("sp500", "BBB", "Beta", D(2016, 1, 1), None, True, False),
    ]
    # AAA has an EOD row for a date OUTSIDE its membership spell -- must not
    # be paired for that date.
    write_eod(tmp_path / "eod" / "AAA.csv",
              {"2017-06-01": 10.0, "2019-06-01": 11.0})
    write_eod(tmp_path / "eod" / "BBB.csv", {"2017-06-01": 20.0})
    # no EOD file at all is the missing-file branch of load_eod_closes:
    assert A.load_eod_closes(tmp_path / "eod" / "NOPE.csv") == {}

    dates = [D(2017, 6, 1), D(2019, 6, 1)]
    by_code = {"AAA": [spells[0]], "BBB": [spells[1]]}
    aaa_eod = A.load_eod_closes(tmp_path / "eod" / "AAA.csv")
    bbb_eod = A.load_eod_closes(tmp_path / "eod" / "BBB.csv")
    aaa_dates = A.member_dates_with_eod(by_code["AAA"], dates, aaa_eod)
    bbb_dates = A.member_dates_with_eod(by_code["BBB"], dates, bbb_eod)
    assert aaa_dates == [D(2017, 6, 1)]     # 2019 row exists but AAA delisted 2018
    assert bbb_dates == [D(2017, 6, 1)]     # BBB has no EOD row for 2019-06-01


def test_build_plan_end_to_end_gating(tmp_path: Path):
    spells = [
        P.Spell("sp500", "AAA", "Alpha", D(2016, 1, 1), D(2018, 1, 1),
               False, True),
        P.Spell("sp500", "BBB", "Beta", D(2016, 1, 1), None, True, False),
    ]
    write_eod(tmp_path / "eod" / "AAA.csv",
              {"2017-06-01": 10.0, "2019-06-01": 11.0})
    write_eod(tmp_path / "eod" / "BBB.csv", {"2017-06-01": 20.0})
    pairs, plan = A.build_plan(spells, tmp_path, sample_n=2, dates_n=5,
                               seed=1, window_start=D(2017, 6, 1),
                               window_end=D(2017, 6, 1))
    assert plan["symbols_sampled"] == 2
    codes_pulled = {sym for sym, _, _ in pairs}
    assert codes_pulled == {"AAA", "BBB"}   # both have an EOD row for the only sampled date
    for sym, day, eod_close in pairs:
        assert day == D(2017, 6, 1)


# --------------------------------------------------------------------------
# evaluate_day: HIT / BACKFILL / MISSING and the close-bucket gap
# --------------------------------------------------------------------------

def test_evaluate_day_hit_backfill_missing():
    day = D(2026, 3, 10)   # EDT: 09:30 ET = 13:30Z, 11:30 = 15:30Z, 15:30 = 19:30Z
    bars = [bar(day, "13:30", 50.0), bar(day, "15:29", 51.0)]
    obs = {o.bucket: o for o in A.evaluate_day("ZZZ", day, bars, eod_close=51.5)}
    assert obs["open"].status == "HIT"
    assert obs["open"].minutes_back == 0.0
    assert obs["midday"].status == "HIT"     # 1 minute back, within TOLERANCE_MIN
    assert obs["midday"].minutes_back == 1.0
    assert obs["close"].status == "BACKFILL"
    assert obs["close"].bar_et is not None
    # close bucket compares the LAST bar at/before it (51.0) against EOD (51.5)
    expected_bps = (51.0 - 51.5) / 51.5 * 10000.0
    assert obs["close"].gap_bps == pytest.approx(expected_bps)
    # open/midday buckets never carry a gap_bps (only "close" does)
    assert obs["open"].gap_bps is None and obs["midday"].gap_bps is None


def test_evaluate_day_all_missing_when_no_bars():
    day = D(2026, 3, 10)
    obs = A.evaluate_day("ZZZ", day, bars=[], eod_close=10.0)
    assert len(obs) == 3
    assert all(o.status == "MISSING" and o.bar_et is None and
              o.alpaca_price is None for o in obs)
    # eod_close is still carried through even on a MISSING row, for the report
    assert all(o.eod_close == 10.0 for o in obs)


def test_evaluate_day_ignores_bars_after_the_bucket():
    day = D(2026, 3, 10)
    # Only a bar AFTER the open bucket exists -- open must read MISSING, not
    # borrow a future price (would be look-ahead in the real fill engine).
    bars = [bar(day, "13:31", 50.0)]
    obs = {o.bucket: o for o in A.evaluate_day("ZZZ", day, bars, None)}
    assert obs["open"].status == "MISSING"


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------

def test_build_report_sections_present():
    day = D(2026, 3, 10)
    obs = A.evaluate_day("AAA", day, [bar(day, "13:30", 10.0)], eod_close=10.0)
    obs += A.evaluate_day("XXX", day, [], eod_close=None)
    plan = {"symbols_sampled": 2, "symbols_ever_delisted": 1,
           "dates_sampled": 1, "pairs_to_pull": 2,
           "pairs_skipped_no_eod_or_not_member": 0}
    report = A.build_report(obs, delisted_symbols={"XXX"}, plan=plan)
    assert "COVERAGE BY BUCKET" in report
    assert "ever delisted from the index" in report
    assert "still current" in report
    assert "XXX" in report            # the all-MISSING symbol is called out
    assert "does not decide" in report


def test_build_report_invalid_symbol_excluded_from_coverage_tables():
    day = D(2026, 3, 10)
    obs = A.evaluate_day("AAA", day, [bar(day, "13:30", 10.0)], eod_close=10.0)
    obs += A.invalid_symbol_observations("NFX_OLD", day, eod_close=None)
    plan = {"symbols_sampled": 2, "symbols_ever_delisted": 1,
           "dates_sampled": 1, "pairs_to_pull": 2,
           "pairs_skipped_no_eod_or_not_member": 0}
    report = A.build_report(obs, delisted_symbols={"NFX_OLD"}, plan=plan,
                            invalid_symbols={"NFX_OLD"})
    assert "REJECTED OUTRIGHT" in report
    assert "NFX_OLD" in report
    # not folded into the missing-buckets table as a genuine coverage gap
    assert "NFX_OLD" not in report.split("MOST MISSING BUCKETS")[1]


def test_write_obs_csv_roundtrip(tmp_path: Path):
    day = D(2026, 3, 10)
    obs = A.evaluate_day("AAA", day, [bar(day, "13:30", 10.0)], eod_close=10.0)
    path = tmp_path / "obs.csv"
    A.write_obs_csv(path, obs)
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 3
    assert set(rows[0]) == set(A.OBS_FIELDS)
    assert rows[0]["symbol"] == "AAA"


# --------------------------------------------------------------------------
# run_pairs: a rejected symbol (HTTP 400) must not abort the run
# --------------------------------------------------------------------------

def test_run_pairs_skips_invalid_symbol_instead_of_aborting():
    day = D(2026, 3, 10)

    def fetch(symbol: str, d: D) -> list[dict]:
        if symbol == "NFX_OLD":
            raise A.InvalidSymbol(symbol)
        return [bar(d, "13:30", 10.0)]

    pairs = [("AAA", day, 10.0), ("NFX_OLD", day, 20.0), ("BBB", day, 30.0)]
    obs, invalid_symbols = A.run_pairs(fetch, pairs, log=lambda m: None)
    assert invalid_symbols == {"NFX_OLD"}
    assert len(obs) == 9   # 3 symbols x 3 buckets, run continued past NFX_OLD
    bad = [o for o in obs if o.symbol == "NFX_OLD"]
    assert all(o.status == "INVALID_SYMBOL" for o in bad)
    good = [o for o in obs if o.symbol == "AAA"]
    assert any(o.status == "HIT" for o in good)   # AAA/BBB still processed normally


# --------------------------------------------------------------------------
# cost_lines / CLI gate
# --------------------------------------------------------------------------

def test_cost_lines_states_zero_dollars_and_wall_clock():
    plan = {"symbols_sampled": 40, "symbols_ever_delisted": 20,
           "dates_sampled": 20, "pairs_to_pull": 800,
           "pairs_skipped_no_eod_or_not_member": 0}
    lines = A.cost_lines(plan)
    joined = "\n".join(lines)
    assert "800 Alpaca requests" in joined
    assert "cost: $0" in joined
    assert "minutes" in joined


def test_main_without_confirm_does_not_touch_network(tmp_path: Path, capsys):
    membership = tmp_path / "membership.csv"
    P.write_membership(membership, [
        P.Spell("sp500", "AAA", "Alpha", D(2016, 1, 1), None, True, False),
    ])
    rc = A.main(["--out-dir", str(tmp_path), "--sample", "1", "--dates", "1"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "stopped: pass --confirm" in out


def test_main_missing_membership_exits(tmp_path: Path):
    with pytest.raises(SystemExit):
        A.main(["--out-dir", str(tmp_path / "nope")])
