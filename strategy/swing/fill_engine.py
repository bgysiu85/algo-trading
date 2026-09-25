#!/usr/bin/env python3
"""W07-0012 subitem 5 (part 2 of 2): bucket entry/exit pricing and the N-day
same-bucket exit for SWING-v0's daily picks (`docs/research/REGISTERED_swing_v0.md`
S2.3-S2.4), point-in-time, off the EODHD intraday pull (`intraday_pull.py`,
part 1).

    python -m strategy.swing.fill_engine run --bucket midday --n 5 --k 5
    python -m strategy.swing.fill_engine --self-test

WHAT THIS MODULE IS, AND IS NOT
-----------------------------------
This turns `reversal_v0.py`'s daily picks (a set of codes per signal day) into
priced TRADES: one row per (code, signal day) with the actual entry date,
exit date, entry/exit bucket price, and the raw simple return -- nothing
else. It does NOT compute costs, market-relative scoring, the bootstrap, the
random-decile control, or the K x N x bucket grid report -- those are spec
S3's job, raised separately as W07-0012 subitem 6 (`README.md`'s own
next-step note). This module's contract ends at "here is what would have
filled, and at what price"; subitem 6 turns that into the registered study.

WHEN ENTRY HAPPENS -- THE PART A NAIVE READING GETS WRONG
--------------------------------------------------------------
`daily_picks(...)[day]` is the bottom decile computed from the K-day trailing
return ENDING AT `day`'s close (spec S2.2) -- the signal is known only once
that close prints. Spec S2.3: "the signal is known at the previous close, and
the order is placed at a fixed clock time the next session." So a pick on
signal day `day` enters at the chosen bucket on the VERY NEXT trading day in
the calendar, never on `day` itself -- entering on `day` would price the fill
from data that was not vet knowable until after the market had already moved
on it (this module cannot see day t's own close before it happens, but
naively reusing `picks[day]` as if it were tradeable ON `day` would be
exactly the same class of bug the hindsight guard in `reversal_v0.py` exists
to catch on the universe side, just moved to the fill side).

Exit: exactly N trading days after entry (calendar index arithmetic, not
calendar days), at the SAME bucket (spec S2.4) -- an `open` entry exits at
`open`, N sessions later, never a different bucket.

THE NO-LOOK-AHEAD GUARD (mutation-tested)
---------------------------------------------
`check_no_lookahead` re-derives, independently of `build_trades`, that every
trade's entry index is EXACTLY the signal index + 1 (never the same day,
never skipped further ahead) and that the exit index is EXACTLY the entry
index + N (never a different N, never a different bucket's calendar
position). `tests/strategy/test_swing_fill_engine.py` mutates a trade's entry
date back onto its own signal day and asserts the guard raises -- the same
"shift a date, the test must fail" discipline `reversal_v0.py`'s hindsight
guard and `alpaca_coverage_probe.py` both use.

UNFILLABLE TRADES ARE COUNTED, NEVER DROPPED SILENTLY
-----------------------------------------------------------
A pick with no next trading session (signal day is the last day in the
calendar), no session N days later, or a MISSING/absent bucket price at
either end is recorded as an `Unfilled` row with a reason, not quietly
excluded from the trade list -- spec S3 item 8 requires every count reported,
and a fill engine that just drops what it cannot price would understate the
real coverage gap the whole W07-0012 line exists to measure.

NO REPO IMPORTS BEYOND THE PACKAGE ITSELF
---------------------------------------------
Same convention as the rest of `strategy/swing/`: standard library only, plus
`pit_universe` and `reversal_v0`, siblings in this package. Reads
`intraday_pull.py`'s own `OBS_FIELDS`/output shape rather than re-defining it.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from strategy.swing import intraday_pull as I
from strategy.swing import pit_universe as P
from strategy.swing import reversal_v0 as R

DEFAULT_PIT_DIR = Path("var") / "swing_pit"
INTRADAY_SUBDIR = I.INTRADAY_SUBDIR


class LookaheadError(AssertionError):
    """The no-look-ahead guard fired: a trade's entry or exit index does not
    match what spec S2.3/S2.4 requires."""


# --------------------------------------------------------------------------
# reading intraday_pull.py's own output
# --------------------------------------------------------------------------

def load_intraday_store(codes: Iterable[str], intraday_dir: Path) -> dict:
    """code -> {(date, bucket): (price|None, status)}. A code with no
    intraday/<code>.csv is simply absent -- every bucket for it reads as
    "no file", the same as a MISSING status, never an error (mirrors
    `reversal_v0.load_prices`'s own "absent means no price" convention)."""
    out: dict = {}
    for code in codes:
        path = intraday_dir / f"{P.file_stem(code)}.csv"
        if not path.exists():
            continue
        store: dict = {}
        with path.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                d = P.to_date(r.get("date"))
                bucket = r.get("bucket")
                if d is None or not bucket:
                    continue
                status = r.get("status") or "MISSING"
                price = None
                if status != "MISSING":
                    try:
                        price = float(r["price"])
                    except (TypeError, ValueError, KeyError):
                        status = "MISSING"
                store[(d, bucket)] = (price, status)
        if store:
            out[code] = store
    return out


def bucket_price(store: dict, code: str, day: dt.date, bucket: str
                 ) -> tuple[float | None, str]:
    per_code = store.get(code)
    if per_code is None:
        return None, "NO_FILE"
    return per_code.get((day, bucket), (None, "NO_ROW"))


# --------------------------------------------------------------------------
# trade construction (spec S2.3 entry timing, S2.4 exit)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Trade:
    code: str
    signal_date: dt.date
    entry_date: dt.date
    exit_date: dt.date
    bucket: str
    n: int
    entry_price: float
    exit_price: float
    entry_status: str
    exit_status: str

    @property
    def ret(self) -> float:
        return self.exit_price / self.entry_price - 1.0

    def row(self) -> list:
        return [self.code, self.signal_date.isoformat(), self.entry_date.isoformat(),
                self.exit_date.isoformat(), self.bucket, self.n,
                round(self.entry_price, 4), round(self.exit_price, 4),
                self.entry_status, self.exit_status, round(self.ret, 6)]


TRADE_FIELDS = ["code", "signal_date", "entry_date", "exit_date", "bucket",
                "n", "entry_price", "exit_price", "entry_status",
                "exit_status", "ret"]


@dataclass(frozen=True)
class Unfilled:
    code: str
    signal_date: dt.date
    bucket: str
    n: int
    reason: str

    def row(self) -> list:
        return [self.code, self.signal_date.isoformat(), self.bucket, self.n,
                self.reason]


UNFILLED_FIELDS = ["code", "signal_date", "bucket", "n", "reason"]


def build_trades(picks: dict, calendar: list, store: dict, bucket: str, n: int
                 ) -> tuple[list[Trade], list[Unfilled]]:
    """`picks` is `reversal_v0.daily_picks(...)`'s own output: signal_date ->
    list of codes. Entry is the calendar index right after the signal day
    (spec S2.3); exit is exactly `n` trading days after entry, same bucket
    (spec S2.4). Every pick becomes either one Trade or one Unfilled row --
    no pick silently disappears."""
    index_of = {d: idx for idx, d in enumerate(calendar)}
    trades: list[Trade] = []
    unfilled: list[Unfilled] = []
    for signal_date, codes in picks.items():
        signal_idx = index_of.get(signal_date)
        if signal_idx is None or not codes:
            continue
        entry_idx = signal_idx + 1
        if entry_idx >= len(calendar):
            for code in codes:
                unfilled.append(Unfilled(code, signal_date, bucket, n,
                                         "no_next_session"))
            continue
        exit_idx = entry_idx + n
        entry_date = calendar[entry_idx]
        if exit_idx >= len(calendar):
            for code in codes:
                unfilled.append(Unfilled(code, signal_date, bucket, n,
                                         "insufficient_calendar_for_exit"))
            continue
        exit_date = calendar[exit_idx]
        for code in codes:
            entry_px, entry_status = bucket_price(store, code, entry_date, bucket)
            if entry_px is None:
                unfilled.append(Unfilled(code, signal_date, bucket, n,
                                         f"entry_price_{entry_status.lower()}"))
                continue
            exit_px, exit_status = bucket_price(store, code, exit_date, bucket)
            if exit_px is None:
                unfilled.append(Unfilled(code, signal_date, bucket, n,
                                         f"exit_price_{exit_status.lower()}"))
                continue
            trades.append(Trade(code, signal_date, entry_date, exit_date,
                                bucket, n, entry_px, exit_px, entry_status,
                                exit_status))
    return trades, unfilled


# --------------------------------------------------------------------------
# the no-look-ahead guard (mutation-tested)
# --------------------------------------------------------------------------

def check_no_lookahead(trades: list[Trade], calendar: list, n: int) -> int:
    """Re-derives, from `calendar` alone (never trusting the Trade's own
    labelling), that entry_idx == signal_idx + 1 and exit_idx == entry_idx +
    n for every trade. Raises LookaheadError on the first violation; returns
    the number of trades checked otherwise."""
    index_of = {d: idx for idx, d in enumerate(calendar)}
    checked = 0
    for t in trades:
        signal_idx = index_of.get(t.signal_date)
        entry_idx = index_of.get(t.entry_date)
        exit_idx = index_of.get(t.exit_date)
        if signal_idx is None or entry_idx is None or exit_idx is None:
            raise LookaheadError(
                f"{t.code}: signal/entry/exit date not found in the supplied "
                "calendar -- a trade must only ever reference real sessions")
        if entry_idx != signal_idx + 1:
            raise LookaheadError(
                f"{t.code}: signal {t.signal_date} -> entry {t.entry_date} is "
                f"{entry_idx - signal_idx} session(s) apart, not exactly 1 -- "
                "spec S2.3 requires entry on the very next session, never the "
                "signal day itself and never a later one")
        if exit_idx - entry_idx != n:
            raise LookaheadError(
                f"{t.code}: entry {t.entry_date} -> exit {t.exit_date} is "
                f"{exit_idx - entry_idx} session(s), not the registered N={n} "
                "-- spec S2.4 requires exactly N trading days, same bucket")
        checked += 1
    return checked


# --------------------------------------------------------------------------
# summary (fill-rate only -- NOT the S3 report; that is subitem 6)
# --------------------------------------------------------------------------

def summarize(trades: list[Trade], unfilled: list[Unfilled]) -> dict:
    n_picks = len(trades) + len(unfilled)
    reasons: dict[str, int] = {}
    for u in unfilled:
        reasons[u.reason] = reasons.get(u.reason, 0) + 1
    return {
        "picks": n_picks,
        "filled": len(trades),
        "unfilled": len(unfilled),
        "fill_rate_pct": round(100 * len(trades) / n_picks, 2) if n_picks else None,
        "unfilled_by_reason": dict(sorted(reasons.items(), key=lambda kv: -kv[1])),
    }


def write_trades_csv(path: Path, trades: list[Trade]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(TRADE_FIELDS)
        for t in trades:
            w.writerow(t.row())


def write_unfilled_csv(path: Path, unfilled: list[Unfilled]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(UNFILLED_FIELDS)
        for u in unfilled:
            w.writerow(u.row())


# --------------------------------------------------------------------------
# self-test (offline, synthetic data -- no network, no real var/swing_pit)
# --------------------------------------------------------------------------

def self_test() -> list[str]:
    calendar = [dt.date(2026, 1, 5) + dt.timedelta(days=i) for i in range(10)]
    # picks: AAA and BBB picked on calendar[2]; CCC picked on the LAST day
    # (no next session -> must be unfilled, not silently dropped)
    picks = {
        calendar[2]: ["AAA", "BBB"],
        calendar[-1]: ["CCC"],
    }
    store = {
        "AAA": {(calendar[3], "midday"): (10.0, "HIT"),
               (calendar[5], "midday"): (11.0, "HIT")},   # entry idx3, exit idx3+2=5
        "BBB": {(calendar[3], "midday"): (20.0, "HIT")},   # exit price missing
        # CCC: no file at all
    }

    trades, unfilled = build_trades(picks, calendar, store, bucket="midday", n=2)
    assert len(trades) == 1 and trades[0].code == "AAA", trades
    assert trades[0].entry_date == calendar[3] and trades[0].exit_date == calendar[5]
    assert abs(trades[0].ret - (11.0 / 10.0 - 1.0)) < 1e-9

    reasons = {u.code: u.reason for u in unfilled}
    assert reasons["BBB"] == "exit_price_no_row", reasons
    assert reasons["CCC"] == "no_next_session", reasons

    n_checked = check_no_lookahead(trades, calendar, n=2)
    assert n_checked == 1

    summary = summarize(trades, unfilled)
    assert summary["picks"] == 3 and summary["filled"] == 1 and summary["unfilled"] == 2

    # the mutation test: force a trade's entry back onto its own signal day
    # (the exact bug class spec S2.3's "next session, never the signal day
    # itself" rule exists to rule out) -- the guard must catch it
    bad = Trade("AAA", calendar[2], calendar[2], calendar[4], "midday", 2,
               10.0, 11.0, "HIT", "HIT")
    try:
        check_no_lookahead([bad], calendar, n=2)
    except LookaheadError:
        pass
    else:
        raise AssertionError(
            "check_no_lookahead did not catch an entry dated on its own "
            "signal day -- the mutation test the no-look-ahead guard "
            "requires would not catch this")

    # a second mutation: right entry, wrong N (exit too early)
    bad_n = Trade("AAA", calendar[2], calendar[3], calendar[4], "midday", 2,
                 10.0, 11.0, "HIT", "HIT")
    try:
        check_no_lookahead([bad_n], calendar, n=2)
    except LookaheadError:
        pass
    else:
        raise AssertionError(
            "check_no_lookahead did not catch an exit one session short of "
            "the registered N")

    return ["self-test passed: entry priced on the session after the signal "
           "(never the signal day itself), exit exactly N sessions later at "
           "the same bucket, unfillable picks counted with a reason instead "
           "of dropped, and the no-look-ahead guard's two required mutation "
           "checks (same-day entry, short-N exit) both caught"]


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("stage", nargs="?", choices=["run"])
    p.add_argument("--pit-dir", type=Path, default=DEFAULT_PIT_DIR)
    p.add_argument("--bucket", choices=R.BUCKETS, default="midday")
    p.add_argument("--n", type=int, default=5)
    p.add_argument("--k", type=int, default=5)
    p.add_argument("--index", choices=["sp400", "sp500"], default=None)
    p.add_argument("--out-dir", type=Path, default=Path("var") / "swing_pit" / "trades")
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args(argv)

    if a.self_test:
        for line in self_test():
            print(line)
        return 0
    if a.stage != "run":
        p.error("choose a stage: run")

    try:
        universe = R.load_universe(a.pit_dir)
    except (R.UniverseGuardRefused, R.HindsightError) as e:
        print(f"STOPPED: {e}", file=sys.stderr)
        return 2

    all_codes = sorted({s.code for s in universe.spells})
    prices = R.load_prices(all_codes, a.pit_dir / "eod")
    calendar = R.trading_calendar(prices)
    picks = R.daily_picks(universe, prices, calendar, a.k, index=a.index)
    store = load_intraday_store(all_codes, a.pit_dir / INTRADAY_SUBDIR)

    trades, unfilled = build_trades(picks, calendar, store, a.bucket, a.n)
    check_no_lookahead(trades, calendar, a.n)

    tag = f"k{a.k}_{a.bucket}_n{a.n}"
    trades_path = a.out_dir / f"trades_{tag}.csv"
    unfilled_path = a.out_dir / f"unfilled_{tag}.csv"
    write_trades_csv(trades_path, trades)
    write_unfilled_csv(unfilled_path, unfilled)

    summary = summarize(trades, unfilled)
    print(f"K={a.k} bucket={a.bucket} N={a.n}: {summary['picks']} picks, "
         f"{summary['filled']} filled ({summary['fill_rate_pct']}%), "
         f"{summary['unfilled']} unfilled")
    if summary["unfilled_by_reason"]:
        print("unfilled by reason:")
        for reason, n in summary["unfilled_by_reason"].items():
            print(f"  {reason}: {n}")
    print(f"written to {trades_path} and {unfilled_path}")
    print("This is raw fill pricing only -- no costs, no market-relative "
         "scoring, no bootstrap. Subitem 6 (the S3 report layer) turns this "
         "into the registered study.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
