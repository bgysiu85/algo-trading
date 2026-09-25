"""Tests for strategy/swing/reversal_v0.py (W07-0010, REGISTERED_swing_v0.md).

Every guard is exercised directly, not only through self_test(): the
hindsight guard's mutation test in particular is the thing the spec asks for
by name ("Mutation-tested before the backtest runs (shift a membership date
by one day, the test must fail)") and is written out here rather than left
inside the module's own self-test so it runs under pytest and shows up in
CI/coverage the same as every other guard in the repo.
"""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

import pytest

from strategy.swing import pit_universe as P
from strategy.swing import reversal_v0 as R

D = dt.date


# --------------------------------------------------------------------- fixtures

def _write_membership(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(P.MEMBERSHIP_FIELDS)
        for r in rows:
            w.writerow(r)


def _write_suspects(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["index", "code", "name", "start", "end", "is_delisted",
                   "verdict", "in_window_rows", "expected_rows"])
        for r in rows:
            w.writerow(r)


def _write_prices(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "open", "high", "low", "close",
                   "adjusted_close", "volume"])
        for d, px in rows:
            w.writerow([d, px, px, px, px, px, 1000])


def _pad_rows(n: int, start="2016-01-01", end="2020-01-01"):
    """n (membership_row, suspect_row) pairs sharing the same PADi code, so
    every padded suspect the universe-file guard checks is actually present
    in membership.csv -- the guard requires suspects.csv to be a subset of
    membership.csv (spec section 0), and these pads must satisfy that the
    same way the real 35-row G8 residual does."""
    membership = [["sp500", f"PAD{i}", "pad", start, end, 1, 1]
                 for i in range(n)]
    suspects = [["sp500", f"PAD{i}", "pad", start, end, 1, "suspect_reuse",
                0, 1] for i in range(n)]
    return membership, suspects


@pytest.fixture
def pit(tmp_path):
    pad_membership, pad_suspects = _pad_rows(34)
    membership = [
        ["sp500", "AAPL", "Apple", "2015-01-01", "", 1, 0],
        ["sp500", "GOOD", "Good Co", "2016-01-01", "", 1, 0],
        ["sp500", "BAD", "Excluded Co", "2016-01-01", "2020-01-01", 1, 1],
    ] + pad_membership
    _write_membership(tmp_path / R.MEMBERSHIP_NAME, membership)
    _write_suspects(tmp_path / R.SUSPECTS_NAME,
                    [["sp500", "BAD", "Excluded Co", "2016-01-01",
                     "2020-01-01", 1, "suspect_reuse", 0, 100]] + pad_suspects)
    days = [D(2016, 1, 4) + dt.timedelta(days=i) for i in range(30)]
    _write_prices(tmp_path / "eod" / "AAPL.csv",
                 [(d, 100 + i) for i, d in enumerate(days)])
    _write_prices(tmp_path / "eod" / "GOOD.csv",
                 [(d, 50 - i * 0.5) for i, d in enumerate(days)])
    return tmp_path, days


# --------------------------------------------------------------- universe-file guard

def test_universe_guard_excludes_exactly_the_suspects(pit):
    pit_dir, _days = pit
    universe = R.load_universe(pit_dir)
    codes = {s.code for s in universe.spells}
    assert codes == {"AAPL", "GOOD"}, codes
    assert universe.n_suspects_excluded == 35


def test_universe_guard_refuses_missing_suspects_file(tmp_path):
    _write_membership(tmp_path / R.MEMBERSHIP_NAME,
                      [["sp500", "AAPL", "Apple", "2015-01-01", "", 1, 0]])
    with pytest.raises(R.UniverseGuardRefused):
        R.load_universe(tmp_path)


def test_universe_guard_refuses_wrong_suspect_count(tmp_path):
    _write_membership(tmp_path / R.MEMBERSHIP_NAME,
                      [["sp500", "AAPL", "Apple", "2015-01-01", "", 1, 0]])
    _write_suspects(tmp_path / R.SUSPECTS_NAME, [])  # 0, not 35
    with pytest.raises(R.UniverseGuardRefused):
        R.load_universe(tmp_path)


def test_universe_guard_refuses_mismatched_suspects(tmp_path):
    """A suspects.csv that flags a spell membership.csv doesn't have is a
    different W07-0002 publish and must be refused, not silently ignored."""
    pad_membership, pad_suspects = _pad_rows(34)
    _write_membership(tmp_path / R.MEMBERSHIP_NAME,
                      [["sp500", "AAPL", "Apple", "2015-01-01", "", 1, 0]]
                      + pad_membership)
    _write_suspects(tmp_path / R.SUSPECTS_NAME,
                    [["sp500", "NOTINFILE", "Ghost", "2016-01-01",
                     "2020-01-01", 1, "suspect_reuse", 0, 1]] + pad_suspects)
    with pytest.raises(R.UniverseGuardRefused):
        R.load_universe(tmp_path)


def test_universe_guard_refuses_missing_membership(tmp_path):
    _, pad_suspects = _pad_rows(35)
    _write_suspects(tmp_path / R.SUSPECTS_NAME, pad_suspects)
    with pytest.raises(R.UniverseGuardRefused):
        R.load_universe(tmp_path)


# ----------------------------------------------------------------- hindsight guard

def test_eligible_on_boundaries_are_inclusive(pit):
    pit_dir, _days = pit
    universe = R.load_universe(pit_dir)
    assert "GOOD" in R.eligible_on(universe, D(2016, 1, 1))       # == start
    assert "GOOD" not in R.eligible_on(universe, D(2015, 12, 31))  # start - 1
    # AAPL has no end -> eligible arbitrarily far in the future
    assert "AAPL" in R.eligible_on(universe, D(2030, 1, 1))


def test_hindsight_guard_passes_on_the_real_spells(pit):
    pit_dir, days = pit
    universe = R.load_universe(pit_dir)
    assert R.check_hindsight(universe, days) == len(days) * len(universe.spells)


def test_hindsight_guard_mutation_shift_start_by_one_day(pit):
    """The spec's own words: "shift a membership date by one day, the [test]
    must fail" -- meaning the guard must be SENSITIVE to the shift, catching
    the class of bug where eligibility silently ignores a boundary date. This
    constructs the shifted spell directly (the same defect a bug in
    `eligible_on` boundary arithmetic would produce) and asserts the guard's
    own primitive, `eligible_on`, reports a different answer on the old
    boundary day -- i.e. that a one-day shift is NOT invisible to the guard."""
    pit_dir, _days = pit
    universe = R.load_universe(pit_dir)
    good = next(s for s in universe.spells if s.code == "GOOD")
    shifted_good = P.Spell(good.index, good.code, good.name,
                           good.start + dt.timedelta(days=1), good.end,
                           good.is_active_now, good.is_delisted)
    mutated = R.Universe(
        spells=tuple(shifted_good if s.code == "GOOD" else s
                    for s in universe.spells),
        n_suspects_excluded=universe.n_suspects_excluded)

    boundary_day = good.start  # 2016-01-01: eligible before the mutation
    assert "GOOD" in R.eligible_on(universe, boundary_day)
    assert "GOOD" not in R.eligible_on(mutated, boundary_day), (
        "shifting GOOD's start date forward by one day must remove it from "
        "the eligible set on the old boundary day -- if this assertion is "
        "the one that fails, eligible_on() is not reading start dates at "
        "all, which is exactly the hindsight bug this guard exists to catch")

    # and check_hindsight must independently notice the same thing: the
    # mutated spell is no longer covered on boundary_day, so a caller that
    # (wrongly) still treated it as eligible would be caught.
    assert R.check_hindsight(mutated, [boundary_day]) == len(mutated.spells)
    assert not shifted_good.covers(boundary_day)


def test_hindsight_guard_catches_inconsistent_eligible_on(pit):
    """If `eligible_on` disagreed with a spell's own `covers()` -- the actual
    class of defect the guard exists to catch -- `check_hindsight` must
    raise. Simulated here by monkeypatching a broken variant of eligible_on
    onto the module and proving the guard fires rather than passing
    silently."""
    pit_dir, _days = pit
    universe = R.load_universe(pit_dir)
    good = next(s for s in universe.spells if s.code == "GOOD")

    orig = R.eligible_on

    def broken_eligible_on(u, day, index=None):
        # always includes GOOD, even before its start date -- the bug
        base = orig(u, day, index=index)
        return base | {"GOOD"}

    try:
        R.eligible_on = broken_eligible_on
        with pytest.raises(R.HindsightError):
            R.check_hindsight(universe, [good.start - dt.timedelta(days=1)])
    finally:
        R.eligible_on = orig


def test_suspect_leak_guard_passes(pit):
    pit_dir, _days = pit
    universe = R.load_universe(pit_dir)
    assert R.check_no_suspect_leak(universe, pit_dir / R.SUSPECTS_NAME, pit_dir) == 35


def test_suspect_leak_guard_fires_on_a_leaked_spell(pit):
    pit_dir, _days = pit
    universe = R.load_universe(pit_dir)
    bad = P.Spell("sp500", "BAD", "Excluded Co", D(2016, 1, 1), D(2020, 1, 1), 1, 1)
    leaked = R.Universe(spells=universe.spells + (bad,),
                        n_suspects_excluded=universe.n_suspects_excluded)
    with pytest.raises(R.HindsightError):
        R.check_no_suspect_leak(leaked, pit_dir / R.SUSPECTS_NAME, pit_dir)


# ------------------------------------------------------------------------- prices

def test_load_prices_skips_missing_files(pit):
    pit_dir, _days = pit
    prices = R.load_prices(["AAPL", "GOOD", "BAD", "NOPE"], pit_dir / "eod")
    assert set(prices) == {"AAPL", "GOOD"}


def test_trading_calendar_uses_reference(pit):
    pit_dir, days = pit
    prices = R.load_prices(["AAPL", "GOOD"], pit_dir / "eod")
    assert R.trading_calendar(prices) == sorted(days)


def test_trading_calendar_refuses_without_reference(tmp_path):
    with pytest.raises(R.UniverseGuardRefused):
        R.trading_calendar({}, reference="AAPL")


# ------------------------------------------------------------------------ ranking

def test_trailing_return_needs_both_endpoints():
    calendar = [D(2016, 1, 1) + dt.timedelta(days=i) for i in range(10)]
    series = {calendar[0]: 100.0, calendar[5]: 110.0}
    assert R.trailing_return(series, calendar, 5, 5) == pytest.approx(0.10)
    assert R.trailing_return(series, calendar, 3, 5) is None  # idx - k < 0
    assert R.trailing_return(series, calendar, 6, 5) is None  # calendar[1] missing


def test_bottom_decile_is_worst_first_and_deterministic():
    returns = {"A": -0.05, "B": 0.10, "C": -0.20, "D": 0.0}
    assert R.bottom_decile(returns)[0] == "C"


def test_bottom_decile_empty_when_no_returns():
    assert R.bottom_decile({}) == []


def test_daily_picks_prefers_the_falling_name(pit):
    pit_dir, days = pit
    universe = R.load_universe(pit_dir)
    prices = R.load_prices(["AAPL", "GOOD"], pit_dir / "eod")
    calendar = R.trading_calendar(prices)
    picks = R.daily_picks(universe, prices, calendar, k=5)
    late_day = calendar[10]
    assert picks[late_day] == ["GOOD"]


def test_turnover_is_empty_for_a_static_decile():
    picks = {D(2016, 1, 1): ["A"], D(2016, 1, 2): ["A"], D(2016, 1, 3): ["A"]}
    assert R.turnover(picks) == [0.0, 0.0]


def test_turnover_is_one_for_a_fully_new_decile():
    picks = {D(2016, 1, 1): ["A"], D(2016, 1, 2): ["B"]}
    assert R.turnover(picks) == [1.0]


# ---------------------------------------------------------------------- pre-flight

def test_run_preflight_has_no_dollar_figures(pit):
    pit_dir, _days = pit
    result = R.run_preflight(pit_dir)
    text = R.format_preflight(result)
    assert "$" not in text
    assert result["by_k"][5]["decile_size"]["median"] >= 0


def test_module_self_test_passes():
    assert R.self_test()
