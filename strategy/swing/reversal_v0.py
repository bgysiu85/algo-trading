#!/usr/bin/env python3
"""SWING-v0: cross-sectional short-term reversal, long-only, market-relative.
Board W07-0010. Spec: docs/research/REGISTERED_swing_v0.md (the "spec").

    python -m strategy.swing.reversal_v0 preflight
    python -m strategy.swing.reversal_v0 --self-test

WHAT THIS MODULE IS, AND IS NOT, RIGHT NOW
-------------------------------------------
This is the SIGNAL layer only: the point-in-time eligible universe (spec
section 2.1), the K-day trailing-return ranking and bottom-decile selection
(2.2, 2.3), and the two guards the spec requires before any backtest runs
(section 0):

  * the universe-file guard  -- refuses any membership file that is not the
                                 one W07-0002 published, less exactly the 35
                                 suspects.csv spells (the accepted G8 residual)
  * the hindsight guard      -- a name is eligible on day t only inside its
                                 own membership spell; nothing else

It does NOT yet place a trade. The entry-time buckets (2.3: open/midday/
close) and the exit rule (2.4) price fills from INTRADAY quotes, and the
only price data on disk here is daily EOD bars (var/swing_pit/eod/*.csv --
one row per session: open/high/low/close/adjusted_close/volume, no
time-of-day). Building bucket-specific fills is a second piece of work,
raised separately on the board once this signal layer and its pre-flight
are green (section 5 of the spec is explicitly "no P&L" and does not need
them).

WHY ADJUSTED CLOSE
-------------------
`adjusted_close` (splits and dividends folded in) is the ranking input,
not raw `close`: an unadjusted split would show up as a fake -50% "reversal"
candidate the day after it happens. This is a design choice this module
makes, not something the spec pins down, and is flagged in the pre-flight
report as a caveat.

WHY AAPL AS THE CALENDAR
-------------------------
There is no separate list of NYSE/Nasdaq session dates on disk. AAPL has
been in the S&P 500 for the whole 2016-05-10 -> 2026-09-23 window and has a
complete daily file, so its own dates stand in for the trading calendar.
If AAPL's file is ever missing, this refuses rather than guessing.

NO REPO IMPORTS outside strategy/swing/, matching pit_universe.py and
pit_validate.py -- standard library only, plus the sibling pit_universe
module.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from strategy.swing import pit_universe as P

DEFAULT_PIT_DIR = Path("var") / "swing_pit"
MEMBERSHIP_NAME = "membership.csv"
SUSPECTS_NAME = "suspects.csv"
EXPECTED_SUSPECT_COUNT = 35  # REGISTERED_swing_v0.md G8: the accepted residual
CALENDAR_REFERENCE = "AAPL"

K_VALUES = (5, 10)          # spec 2.2 -- K=5 deployed, K=10 a reported neighbour
N_VALUES = (5, 10, 20)      # spec 2.4 -- the N-ensemble
BUCKETS = ("open", "midday", "close")  # spec 2.3 -- not fillable from EOD data yet


class UniverseGuardRefused(SystemExit):
    """The universe-file guard: a SystemExit so a caller cannot swallow it as
    an ordinary exception and quietly run on the wrong file."""


class HindsightError(AssertionError):
    """The hindsight guard fired: a name was found eligible outside its own
    membership spell."""


# --------------------------------------------------------------------------
# the universe-file guard (spec section 0 "universe file guard")
# --------------------------------------------------------------------------

def spell_key(s: P.Spell) -> tuple:
    return (s.index, s.code, s.start, s.end)


def read_suspect_keys(path: Path) -> frozenset:
    if not path.exists():
        raise UniverseGuardRefused(
            f"{path} does not exist -- the G8 residual (the 35 suspect spells "
            "from W07-0002) cannot be excluded without it, and this study must "
            "not run against an unfiltered membership file.")
    keys = set()
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            keys.add((r["index"], r["code"],
                      P.to_date(r["start"]) if r.get("start") else None,
                      P.to_date(r["end"]) if r.get("end") else None))
    return frozenset(keys)


def check_universe_files(membership_path: Path, suspects_path: Path) -> None:
    """Refuses anything but the published membership.csv minus suspects.csv
    (spec section 0). Raises UniverseGuardRefused, never returns a partial
    pass."""
    if not membership_path.exists():
        raise UniverseGuardRefused(f"{membership_path} does not exist")
    suspects = read_suspect_keys(suspects_path)
    if len(suspects) != EXPECTED_SUSPECT_COUNT:
        raise UniverseGuardRefused(
            f"{suspects_path} flags {len(suspects)} spell(s), not the "
            f"published {EXPECTED_SUSPECT_COUNT} (REGISTERED_swing_v0.md G8) "
            "-- this is not the file pair W07-0002 published.")
    spells = P.read_membership(membership_path)
    spell_keys = {spell_key(s) for s in spells}
    missing = suspects - spell_keys
    if missing:
        raise UniverseGuardRefused(
            f"{len(missing)} suspect spell(s) from {suspects_path} are not "
            f"present in {membership_path} -- these two files were not "
            "published together and must not be combined.")


@dataclass(frozen=True)
class Universe:
    spells: tuple  # P.Spell, less exactly the suspects.csv spells
    n_suspects_excluded: int


def load_universe(pit_dir: Path = DEFAULT_PIT_DIR) -> Universe:
    """The one entry point every caller uses. Runs the universe-file guard
    first; only a file pair that passes it is ever read into a Universe."""
    membership_path = pit_dir / MEMBERSHIP_NAME
    suspects_path = pit_dir / SUSPECTS_NAME
    check_universe_files(membership_path, suspects_path)
    suspects = read_suspect_keys(suspects_path)
    spells = P.read_membership(membership_path)
    kept = tuple(s for s in spells if spell_key(s) not in suspects)
    return Universe(spells=kept, n_suspects_excluded=len(spells) - len(kept))


# --------------------------------------------------------------------------
# the hindsight guard (spec section 0 "hindsight guard")
# --------------------------------------------------------------------------

def eligible_on(universe: Universe, day: dt.date, index: str | None = None) -> set:
    """The ONE production implementation of "who is in the eligible set on
    day t". `Spell.covers` is inclusive of both `start` and `end`; nothing
    here reads any date other than `day` and the spell's own boundaries."""
    return {s.code for s in universe.spells
           if (index is None or s.index == index) and s.covers(day)}


def check_hindsight(universe: Universe, days: Iterable) -> int:
    """Re-derive eligibility for every (day, spell) pair from the spell's own
    boundaries, independently of `eligible_on`, and assert the two agree.
    Raises HindsightError with the first disagreement; returns the number of
    (day, spell) pairs checked otherwise.

    This is the guard the spec's mutation test targets: shifting any spell's
    `start` or `end` by one day changes what `eligible_on` returns for the
    days adjacent to the boundary, which is exactly what
    tests/strategy/test_swing_reversal_v0.py asserts by constructing a
    shifted copy of a spell and checking the eligible set actually moves.
    """
    checked = 0
    for day in days:
        elig = eligible_on(universe, day)
        covering_codes = set()
        for s in universe.spells:
            before_start = s.start is not None and day < s.start
            after_end = s.end is not None and day > s.end
            should_be_in = not before_start and not after_end
            is_in = s.code in elig
            # A code can have more than one spell; only flag a code that is
            # eligible with NO covering spell, or ineligible despite THIS
            # spell covering it (covers() itself is re-checked, not trusted).
            if should_be_in and not s.covers(day):
                raise HindsightError(
                    f"{s.code}: day {day} is inside {s.start}->{s.end} but "
                    "Spell.covers() says no")
            if not should_be_in and s.covers(day):
                raise HindsightError(
                    f"{s.code}: day {day} is outside {s.start}->{s.end} but "
                    "Spell.covers() says yes")
            if s.covers(day) and not is_in:
                raise HindsightError(
                    f"{s.code}: eligible under its own spell on {day} but "
                    "missing from eligible_on()'s result")
            if s.covers(day):
                covering_codes.add(s.code)
            checked += 1
        # the reverse direction: nothing in the computed eligible set may
        # lack a covering spell on this day -- this is what catches a bug
        # (or a monkeypatch) that ADDS a name to eligible_on()'s result
        # without a membership spell to justify it.
        extra = elig - covering_codes
        if extra:
            raise HindsightError(
                f"day {day}: {sorted(extra)} appear eligible with no "
                "membership spell covering this day")
    return checked


def check_no_suspect_leak(universe: Universe, suspects_path: Path,
                          pit_dir: Path = DEFAULT_PIT_DIR) -> int:
    """None of the 35 excluded G8 residual spells may ever appear in
    `universe.spells` (spec section 0, section 3 item 8: "the 35 excluded G8
    residual spells never entering a signal"). Returns the count checked."""
    suspects = read_suspect_keys(suspects_path)
    kept_keys = {spell_key(s) for s in universe.spells}
    leaked = suspects & kept_keys
    if leaked:
        raise HindsightError(f"{len(leaked)} suspect spell(s) leaked into the "
                             f"eligible universe: {sorted(leaked)[:5]}")
    return len(suspects)


# --------------------------------------------------------------------------
# prices and the trading calendar
# --------------------------------------------------------------------------

def load_prices(codes: Iterable, eod_dir: Path) -> dict:
    """code -> {date: adjusted_close}. A code with no file, or an unreadable
    file, is simply absent from the result -- it is treated the same as "no
    price on this day" everywhere downstream, never as an error."""
    out: dict = {}
    for code in codes:
        path = eod_dir / f"{P.file_stem(code)}.csv"
        if not path.exists():
            continue
        series: dict = {}
        with path.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                d = P.to_date(r.get("date"))
                if d is None:
                    continue
                try:
                    px = float(r["adjusted_close"])
                except (TypeError, ValueError, KeyError):
                    continue
                if px > 0:
                    series[d] = px
        if series:
            out[code] = series
    return out


def trading_calendar(prices: dict, reference: str = CALENDAR_REFERENCE) -> list:
    if reference not in prices or not prices[reference]:
        raise UniverseGuardRefused(
            f"no usable price file for the calendar reference {reference!r} "
            "-- refusing to guess a trading calendar from a partial universe.")
    return sorted(prices[reference].keys())


# --------------------------------------------------------------------------
# the ranking signal (spec section 2.2) and bottom-decile selection
# (spec section 2.3)
# --------------------------------------------------------------------------

def trailing_return(series: dict, calendar: list, idx: int, k: int):
    """Cumulative simple return over the K trading days ending at the close
    of calendar[idx]: px[t] / px[t-k] - 1. None if either endpoint has no
    price (the name did not trade, or has no file) or there is no t-k."""
    if idx - k < 0:
        return None
    p_now = series.get(calendar[idx])
    p_then = series.get(calendar[idx - k])
    if p_now is None or p_then is None or p_then == 0:
        return None
    return p_now / p_then - 1.0


def bottom_decile(returns: dict) -> list:
    """The bottom decile (biggest recent losers) among names with a computed
    trailing return, worst-first, ties broken by code for determinism. A
    day with fewer than 10 names in `returns` still returns whatever the
    decile contains (spec section 2.3) -- callers report the count, they do
    not widen it."""
    if not returns:
        return []
    ordered = sorted(returns.items(), key=lambda kv: (kv[1], kv[0]))
    decile_n = max(1, round(len(ordered) / 10))
    return [code for code, _ in ordered[:decile_n]]


def daily_picks(universe: Universe, prices: dict, calendar: list, k: int,
                index: str | None = None) -> dict:
    """day -> bottom-decile codes, for every day with at least one eligible
    name that has a computed K-day trailing return. The hindsight guard
    (`check_hindsight`) must be run over the same `universe` and the same
    `calendar` before any of this is treated as a result."""
    out: dict = {}
    for idx, day in enumerate(calendar):
        elig = eligible_on(universe, day, index=index)
        rets = {}
        for code in elig:
            series = prices.get(code)
            if series is None:
                continue
            r = trailing_return(series, calendar, idx, k)
            if r is not None:
                rets[code] = r
        out[day] = bottom_decile(rets)
    return out


def turnover(picks: dict) -> list:
    """Day-to-day churn of the bottom decile: fraction of the union of two
    consecutive days' decile membership that is NOT shared, for every pair
    of consecutive days where both deciles are non-empty."""
    days = sorted(picks)
    out = []
    for prev, cur in zip(days, days[1:]):
        a, b = set(picks[prev]), set(picks[cur])
        union = a | b
        if not union:
            continue
        out.append(len(a ^ b) / len(union))
    return out


# --------------------------------------------------------------------------
# pre-flight (spec section 5): no P&L, training side only
# --------------------------------------------------------------------------

def run_preflight(pit_dir: Path = DEFAULT_PIT_DIR, index: str | None = None,
                  hindsight_sample: int = 40) -> dict:
    universe = load_universe(pit_dir)
    all_codes = sorted({s.code for s in universe.spells})
    prices = load_prices(all_codes, pit_dir / "eod")
    calendar = trading_calendar(prices)

    # hindsight guard, sampled (every day would be slow and adds nothing
    # past a few hundred spot checks against every spell -- see section 0
    # and the mutation test, which exercises the boundary logic directly
    # rather than by brute force over the whole calendar)
    import random
    rng = random.Random(20260925)
    sample_days = calendar if len(calendar) <= hindsight_sample else \
        sorted(rng.sample(calendar, hindsight_sample))
    n_hindsight_checked = check_hindsight(universe, sample_days)
    n_suspects_checked = check_no_suspect_leak(
        universe, pit_dir / SUSPECTS_NAME, pit_dir)

    result: dict = {
        "pit_dir": str(pit_dir),
        "window": [calendar[0].isoformat(), calendar[-1].isoformat()],
        "n_sessions": len(calendar),
        "n_codes_with_prices": len(prices),
        "guards": {
            "universe_file_guard": "passed at load (see load_universe)",
            "hindsight_guard": f"passed, {n_hindsight_checked} (day, spell) "
                               f"pairs checked over {len(sample_days)} sampled days",
            "suspect_leak_guard": f"passed, {n_suspects_checked} suspect "
                                  "spells confirmed absent from the eligible universe",
        },
        "by_k": {},
    }

    thin_threshold = 5  # spec section 5's stop-rule check: <5 names in the decile
    for k in K_VALUES:
        picks = daily_picks(universe, prices, calendar, k, index=index)
        elig_sizes = [len(eligible_on(universe, d, index=index)) for d in calendar]
        decile_sizes = [len(v) for v in picks.values()]
        n_thin = sum(1 for n in decile_sizes if 0 < n < thin_threshold)
        n_no_trade = sum(1 for n in decile_sizes if n == 0)
        churn = turnover(picks)
        result["by_k"][k] = {
            "eligible_universe_size": {
                "min": min(elig_sizes), "median": statistics.median(elig_sizes),
                "max": max(elig_sizes),
            },
            "decile_size": {
                "min": min(decile_sizes), "median": statistics.median(decile_sizes),
                "max": max(decile_sizes),
            },
            "n_days_decile_lt_5": n_thin,
            "pct_days_decile_lt_5": round(100 * n_thin / len(decile_sizes), 2),
            "n_no_trade_days": n_no_trade,
            "turnover": {
                "min": round(min(churn), 4) if churn else None,
                "median": round(statistics.median(churn), 4) if churn else None,
                "max": round(max(churn), 4) if churn else None,
            },
        }

    # the pre-registered stop rule (spec section 5, last paragraph)
    finding = []
    for k, row in result["by_k"].items():
        if row["pct_days_decile_lt_5"] > 10.0:
            finding.append(
                f"K={k}: the point-in-time universe is too thin for a decile "
                f"rule on more than 10% of trading days "
                f"({row['pct_days_decile_lt_5']}%). Per spec section 5, this "
                "is reported as a finding, not worked around by widening the "
                "decile after seeing the number.")
    result["stop_rule_finding"] = finding or (
        "not triggered: the bottom decile has at least 5 names on more than "
        "90% of trading days, for every K")
    result["caveats"] = [
        "Ranking uses adjusted_close (splits and dividends folded in), a "
        "design choice this module makes -- see the module docstring.",
        f"The trading calendar is {CALENDAR_REFERENCE}'s own session dates, "
        "not an independent exchange calendar.",
        "This pre-flight does not price any trade: the entry-time bucket "
        "(2.3) and the N-day exit (2.4) need intraday quotes this module "
        "does not yet load. No P&L number appears anywhere in this report.",
    ]
    return result


def format_preflight(result: dict) -> str:
    L = [f"SWING-v0 signal-layer pre-flight (spec section 5) -- "
        f"{result['window'][0]} to {result['window'][1]}, "
        f"{result['n_sessions']} sessions, "
        f"{result['n_codes_with_prices']} codes with usable prices", ""]
    L.append("GUARDS")
    for name, msg in result["guards"].items():
        L.append(f"  {name}: {msg}")
    L.append("")
    for k, row in result["by_k"].items():
        L.append(f"K = {k}")
        e = row["eligible_universe_size"]
        L.append(f"  eligible universe size   min {e['min']}  "
                 f"median {e['median']}  max {e['max']}")
        d = row["decile_size"]
        L.append(f"  bottom-decile size       min {d['min']}  "
                 f"median {d['median']}  max {d['max']}")
        L.append(f"  days with decile < 5 names: {row['n_days_decile_lt_5']} "
                 f"({row['pct_days_decile_lt_5']}%)")
        L.append(f"  no-trade days (decile empty): {row['n_no_trade_days']}")
        t = row["turnover"]
        L.append(f"  day-to-day decile turnover   min {t['min']}  "
                 f"median {t['median']}  max {t['max']}")
        L.append("")
    L.append("STOP-RULE CHECK (spec section 5)")
    finding = result["stop_rule_finding"]
    if isinstance(finding, list):
        for line in finding:
            L.append(f"  {line}")
    else:
        L.append(f"  {finding}")
    L.append("")
    L.append("CAVEATS")
    for c in result["caveats"]:
        L.append(f"  - {c}")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------
# self-test (offline, synthetic data -- exercises every guard and the
# ranking path without touching var/swing_pit/)
# --------------------------------------------------------------------------

def self_test() -> list:
    import tempfile

    def write_membership(path, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(P.MEMBERSHIP_FIELDS)
            for r in rows:
                w.writerow(r)

    def write_suspects(path, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["index", "code", "name", "start", "end", "is_delisted",
                       "verdict", "in_window_rows", "expected_rows"])
            for r in rows:
                w.writerow(r)

    def write_prices(path, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["date", "open", "high", "low", "close",
                       "adjusted_close", "volume"])
            for d, px in rows:
                w.writerow([d, px, px, px, px, px, 1000])

    pad_membership = [["sp500", f"PAD{i}", "pad", "2016-01-01",
                       "2020-01-01", 1, 1]
                      for i in range(EXPECTED_SUSPECT_COUNT - 1)]
    pad_suspects = [["sp500", f"PAD{i}", "pad", "2016-01-01",
                     "2020-01-01", 1, "suspect_reuse", 0, 1]
                    for i in range(EXPECTED_SUSPECT_COUNT - 1)]

    with tempfile.TemporaryDirectory() as t:
        pit = Path(t)
        write_membership(pit / MEMBERSHIP_NAME, [
            ["sp500", "AAPL", "Apple", "2015-01-01", "", 1, 0],
            ["sp500", "GOOD", "Good Co", "2016-01-01", "", 1, 0],
            ["sp500", "BAD", "Excluded Co", "2016-01-01", "2020-01-01", 1, 1],
        ] + pad_membership)
        write_suspects(pit / SUSPECTS_NAME,
                       [["sp500", "BAD", "Excluded Co", "2016-01-01",
                         "2020-01-01", 1, "suspect_reuse", 0, 100]]
                       + pad_suspects)
        days = [dt.date(2016, 1, 4) + dt.timedelta(days=i) for i in range(30)]
        write_prices(pit / "eod" / "AAPL.csv", [(d, 100 + i) for i, d in enumerate(days)])
        write_prices(pit / "eod" / "GOOD.csv", [(d, 50 - i * 0.5) for i, d in enumerate(days)])
        # no price file for BAD -- and BAD is excluded anyway

        universe = load_universe(pit)
        assert universe.n_suspects_excluded == EXPECTED_SUSPECT_COUNT, \
            universe.n_suspects_excluded
        assert {s.code for s in universe.spells} == {"AAPL", "GOOD"}, universe.spells

        check_hindsight(universe, days)
        check_no_suspect_leak(universe, pit / SUSPECTS_NAME, pit)

        prices = load_prices(["AAPL", "GOOD"], pit / "eod")
        calendar = trading_calendar(prices)
        assert calendar == sorted(days)

        picks = daily_picks(universe, prices, calendar, k=5)
        # GOOD falls every day, AAPL rises every day -- GOOD must always be
        # the (only) name in the bottom decile once both have a K=5 return
        late = calendar[10]
        assert picks[late] == ["GOOD"], picks[late]

        # the universe-file guard: wrong suspect count refuses
        bad_pit = Path(t) / "bad"
        write_membership(bad_pit / MEMBERSHIP_NAME, [
            ["sp500", "AAPL", "Apple", "2015-01-01", "", 1, 0]])
        write_suspects(bad_pit / SUSPECTS_NAME, [])
        try:
            load_universe(bad_pit)
        except UniverseGuardRefused:
            pass
        else:
            raise AssertionError("universe-file guard did not refuse a "
                                 "0-suspect file")

        # the hindsight guard: shifting a spell's start must move eligibility
        shifted = Universe(
            spells=tuple(P.Spell(s.index, s.code, s.name,
                                 s.start + dt.timedelta(days=1) if s.code == "GOOD" else s.start,
                                 s.end, s.is_active_now, s.is_delisted)
                        for s in universe.spells),
            n_suspects_excluded=universe.n_suspects_excluded)
        boundary_day = universe.spells[[s.code for s in universe.spells].index("GOOD")].start
        before = "GOOD" in eligible_on(universe, boundary_day)
        after = "GOOD" in eligible_on(shifted, boundary_day)
        assert before and not after, (
            "shifting GOOD's start date by one day did not change its "
            "eligibility on the old boundary day -- the mutation test the "
            "spec's hindsight guard requires would not catch this")

    return ["self-test passed: universe-file guard, hindsight guard "
           "(including the required one-day-shift mutation check), "
           "suspect-leak guard, and the K=5 bottom-decile ranking all "
           "behaved as specified"]


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("stage", nargs="?", choices=["preflight"])
    p.add_argument("--pit-dir", type=Path, default=DEFAULT_PIT_DIR)
    p.add_argument("--index", choices=["sp400", "sp500"], default=None)
    p.add_argument("--out", type=Path,
                  default=Path("claude") / "raw" / "w07_0010_preflight.txt")
    p.add_argument("--json-out", type=Path,
                  default=Path("var") / "swing_pit" / "reversal_v0_preflight.json")
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args(argv)

    if a.self_test:
        for line in self_test():
            print(line)
        return 0
    if a.stage != "preflight":
        p.error("choose a stage: preflight")

    try:
        result = run_preflight(a.pit_dir, index=a.index)
    except (UniverseGuardRefused, HindsightError) as e:
        print(f"STOPPED: {e}", file=sys.stderr)
        return 2
    text = format_preflight(result)
    print(text)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(text, encoding="utf-8")
    a.json_out.parent.mkdir(parents=True, exist_ok=True)
    a.json_out.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"written to {a.out} and {a.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
