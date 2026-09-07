#!/usr/bin/env python3
"""One row per trading day: what Ben did, and what each strategy would have.

    python -m common.day_compare --summary var/reports/flex_symbol_days_all.csv \
        --strategy mcl mc5 vw9_5m --out var/reports/day_compare.csv

WHY THIS READS ARTEFACTS AND NOT STRATEGIES
--------------------------------------------
common/manual_vs_strategy.py runs MCL inline. That works for one strategy and
stops working for three: each has its own bar window, its own kwargs and its
own idea of a session, and a module that imports all of them ends up
re-implementing common/backtest.py badly. So this reads what the engine already
wrote -- backtest_trades_<strategy>.csv for the fills and
backtest_state_<strategy>.json for the coverage -- and joins.

The consequence worth knowing: this module cannot produce a number the engine
did not. If a strategy's column is empty, the run is the thing to look at.

AVERAGES ARE SHARE-WEIGHTED, ACROSS TRADES AS WELL AS WITHIN THEM
------------------------------------------------------------------
A day is not a trade. In the shipped MCL run, 66% of symbol-days hold more than
one trade -- up to ten -- and the entry prices inside one day spread by a
median of 18% and a maximum of 90%.

So every average here is sum(qty * price) / sum(qty), the same rule
common/flex.py applies to real fills.

Be precise about where that rule EARNS its keep, though, because the two sides
of this sheet are not alike:

  * On Ben's fills it changes the number, often a lot. The fills are unequal --
    a day can be 31 executions from 100 to 5,000 shares -- and 100 shares at $2
    plus 900 at $9 averages to $8.30, where the mean of the two prices is
    $5.50. Only one of those is what the account paid.

  * On a strategy's trades it currently coincides with the plain mean, because
    every trade in a day is the same size: size_for() is pinned at MAX_SHARES
    across the whole $2-20 band, and --size-from fixes one quantity per
    symbol-day. Verified on the shipped MCL run -- weighted and unweighted
    agree to four decimals on all 217 days.

It is written weighted anyway. The moment a size varies inside a day -- a
partial fill, a per-trade risk model, a max_position_shares cap that bites --
the unweighted number becomes wrong silently, and this is not a place where
anything would notice.

WHY IT IS SAFE TO TAKE entry_price AS THE BUY PRICE OF A TRADE
---------------------------------------------------------------
A Trade record carries entry_price, exit_price and qty -- not the fills. That
is only the whole story while a trade is ONE buy and ONE sell, which is true
because scale-out, pyramiding and scale-up are all off in the engine's default
call. It stops being true the moment a scaled run is exported, and the failure
would be silent: entry_price would quietly become "the first of several buys"
and still print as an average.

single_round_trip() checks it per row, and a row that fails is reported with
its prices BLANK and counted, rather than averaged. See --strict.

STATUS IS NOT A NUMBER
-----------------------
An empty strategy block has four different meanings and they must not collapse
into a zero:

    TRADED      the strategy traded; the figures are real
    NO TRADES   the strategy saw the session and declined -- a real zero
    NO BARS     the session could not be evaluated at all
    NO SIZE     no position to match, so no comparable run was made
    NOT RUN     the pair is not in this strategy's state file

Only NO TRADES is a zero. The other three are absences, and a spreadsheet that
writes 0.00 for them makes a strategy that could not be tested look like one
that broke even.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Statuses the engine records in backtest_state_<strategy>.json, mapped to what
# they mean for a row here. Anything unrecognised becomes NO BARS, which is the
# conservative direction: it reports the day as untested rather than as flat.
STATE_STATUS = {
    "OK": "TRADED",             # refined to NO TRADES when the day has none
    "NO_DATA": "NO BARS",
    "NOT_QUALIFIED": "NO BARS",
    "NO_SIZE": "NO SIZE",
}

BLANK_STATUSES = ("NO BARS", "NO SIZE", "NOT RUN", "SCALED")


@dataclass
class Block:
    """One source's figures for one symbol-day."""
    status: str = "NOT RUN"
    trades: int = 0
    buy_shares: float = 0.0
    sell_shares: float = 0.0
    buy_notional: float = 0.0
    sell_notional: float = 0.0
    cost: float = 0.0
    gross: float = 0.0
    net: float = 0.0
    # Ben's side only: the raw fill count. `trades` is round trips on BOTH
    # sides so the column compares like with like; this sits beside it because
    # 31 fills and 3 round trips are both true and both worth seeing.
    fills: int | None = None

    @property
    def avg_buy_price(self) -> float | None:
        return self.buy_notional / self.buy_shares if self.buy_shares else None

    @property
    def avg_sell_price(self) -> float | None:
        return (self.sell_notional / self.sell_shares
                if self.sell_shares else None)

    @property
    def has_figures(self) -> bool:
        return self.status not in BLANK_STATUSES


def single_round_trip(row: dict) -> bool:
    """Is this trade one buy and one sell, so entry/exit ARE the averages?

    The scaling columns are optional: MC5 has no scaling mechanic at all and
    emits none of them, and older CSVs predate them. Absent columns mean the
    strategy could not have scaled, so absence reads as True -- but a PRESENT
    column that disagrees is believed.
    """
    def num(name, default=None):
        v = row.get(name)
        if v in (None, ""):
            return default
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    if num("cycles", 0.0) != 0.0 or num("adds", 0.0) != 0.0:
        return False
    qty = num("qty")
    traded = num("shares_traded")
    if qty is not None and traded is not None and traded != 2 * qty:
        return False
    return True


def read_trades(path: Path) -> tuple[dict, list]:
    """{(symbol, date): Block} from a backtest_trades CSV, plus the rows whose
    prices cannot be trusted as averages."""
    out: dict[tuple[str, str], Block] = {}
    scaled: list[tuple[str, str]] = []
    if not path.exists():
        return out, scaled
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            key = (r["symbol"], r["date"])
            b = out.setdefault(key, Block(status="TRADED"))
            qty = float(r["qty"])
            b.trades += 1
            b.gross += float(r["gross"])
            b.cost += float(r["commission"])
            b.net += float(r["net"])
            if single_round_trip(r):
                b.buy_shares += qty
                b.sell_shares += qty
                b.buy_notional += qty * float(r["entry_price"])
                b.sell_notional += qty * float(r["exit_price"])
            else:
                # P/L is still exact -- the strategy computed it from the fills
                # it actually made. Only the PRICES are unknowable from this
                # row, so only they are withheld.
                b.status = "SCALED"
                scaled.append(key)
    return out, scaled


def read_state(path: Path) -> dict[tuple[str, str], str]:
    """{(symbol, date): status} from backtest_state_<strategy>.json."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    out = {}
    for key, rec in (data.get("done") or {}).items():
        sym, _, day = key.partition("|")
        if day:
            out[(sym, day)] = STATE_STATUS.get(rec.get("status"), "NO BARS")
    return out


def strategy_blocks(reports: Path, states: Path, name: str):
    """Blocks for every symbol-day the engine has an opinion about."""
    trades, scaled = read_trades(reports / f"backtest_trades_{name}.csv")
    state = read_state(states / f"backtest_state_{name}.json")
    out: dict[tuple[str, str], Block] = {}
    for key, status in state.items():
        b = trades.get(key)
        if b is not None:
            # A SCALED row keeps its own status; otherwise the state file's
            # verdict and the presence of trades agree by construction.
            out[key] = b
        else:
            # OK with no trades is the one real zero: the strategy saw the
            # session and declined.
            out[key] = Block(status="NO TRADES" if status == "TRADED" else status)
    # Trades with no state entry should not happen, but if they do the trades
    # are the evidence and the state file is the thing that is stale.
    for key, b in trades.items():
        out.setdefault(key, b)
    return out, scaled


def read_summary(path: Path) -> dict[tuple[str, str], Block]:
    """Ben's own day, from a flex --summary CSV.

    commission arrives as IBKR's NEGATIVE-is-paid convention and is flipped to
    a positive cost here, so every cost column in the output means the same
    thing and 'gross minus cost' is one subtraction everywhere.
    """
    out: dict[tuple[str, str], Block] = {}
    with open(path, newline="") as fh:
        rd = csv.DictReader(fh)
        need = {"buy_shares", "sell_shares", "avg_buy_price", "avg_sell_price",
                "round_trips"}
        missing = need - set(rd.fieldnames or [])
        if missing:
            sys.exit(f"{path} is an older summary without {sorted(missing)}. "
                     "Regenerate it: python -m common.flex ... --summary <path>")
        for r in rd:
            bs = float(r["buy_shares"] or 0)
            ss = float(r["sell_shares"] or 0)
            out[(r["symbol"], r["date"])] = Block(
                status="TRADED",
                # round_trips, NOT executions. A strategy's trade count is
                # round trips; executions are fills. A day of 31 fills can be
                # 3 decisions, and putting the two in one column would compare
                # an order-slicing habit against a decision count.
                trades=int(r["round_trips"]),
                fills=int(r["executions"]),
                buy_shares=bs, sell_shares=ss,
                buy_notional=bs * float(r["avg_buy_price"] or 0),
                sell_notional=ss * float(r["avg_sell_price"] or 0),
                cost=-float(r["commission"]),
                gross=float(r["gross_pnl"]),
                net=float(r["net_pnl"]))
    return out


def build(summary: Path, reports: Path, states: Path, names: list[str]):
    mine = read_summary(summary)
    strat = {}
    scaled_any = {}
    for n in names:
        strat[n], sc = strategy_blocks(reports, states, n)
        if sc:
            scaled_any[n] = sc
    rows = []
    for key in sorted(mine):
        rows.append({"symbol": key[0], "date": key[1], "mine": mine[key],
                     **{n: strat[n].get(key, Block()) for n in names}})
    return rows, scaled_any


# --- summaries -------------------------------------------------------------
#
# WHY MONTH AND WEEKDAY COME FROM DAYS, AND THE CLOCK FROM TRADES
# ----------------------------------------------------------------
# A day on which a strategy declined every setup is a REAL zero and belongs in
# a monthly total and in that weekday's total -- it is one of the days the
# strategy was given and did nothing with. It belongs in no 30-minute bucket at
# all, because there is no entry to place. So month and weekday aggregate the
# day blocks (zeros included, day counts honest) and the clock aggregates the
# individual positions.
#
# The consequence to keep hold of: the clock sheet's totals will be the same
# money as the monthly sheet's, but its counts are TRADES, not days.

BLOCK_MINUTES = 30


@dataclass
class Cell:
    """An aggregated bucket for one source."""
    days: int = 0            # or trades, on the clock sheet
    trades: int = 0
    gross: float = 0.0
    cost: float = 0.0
    net: float = 0.0

    def add(self, gross, cost, net, trades=0):
        self.days += 1
        self.trades += trades
        self.gross += gross
        self.cost += cost
        self.net += net


WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
            "Saturday", "Sunday"]


def by_month(rows, sources) -> dict:
    return _by_day_key(rows, sources, lambda d: d[:7])


def by_weekday(rows, sources) -> dict:
    from datetime import date as _d
    return _by_day_key(
        rows, sources,
        lambda s: WEEKDAYS[_d.fromisoformat(s).weekday()])


def _by_day_key(rows, sources, key) -> dict:
    """{bucket: {source: Cell}} over the DAY blocks.

    Each source is counted over the days IT could be evaluated on. That is what
    was asked for, and it is the version that is easiest to misread: a month
    where a strategy saw 12 days sits beside one where Ben traded 40, in
    adjacent columns, looking comparable. So `days` is carried on every cell
    and the writer is expected to show it.
    """
    out: dict[str, dict[str, Cell]] = {}
    for r in rows:
        k = key(r["date"])
        bucket = out.setdefault(k, {s: Cell() for s in sources})
        for src in sources:
            b = r[src]
            if b.has_figures:
                bucket[src].add(b.gross, b.cost, b.net, b.trades)
    return dict(sorted(out.items()))


def block_label(minute: int) -> str:
    start = (minute // BLOCK_MINUTES) * BLOCK_MINUTES
    end = start + BLOCK_MINUTES
    return f"{start//60:02d}:{start%60:02d}-{end//60:02d}:{end%60:02d}"


def by_entry_block(units: dict, sources) -> dict:
    """{block: {source: Cell}} over individual POSITIONS, keyed on ENTRY.

    Entry, not exit: the question a time-of-day sheet is asked is "which part
    of the morning do I take setups worth taking", and that is a decision that
    can be made again tomorrow. Where the money was booked is a different
    question and it does not tell you when you chose to be there.

    A unit with no resolved entry time is counted under NO TIME rather than
    dropped or floored to midnight -- 00:00 would pile them into one bucket,
    and the most conspicuous bucket on the sheet.
    """
    out: dict[str, dict[str, Cell]] = {}
    for src in sources:
        for u in units.get(src, []):
            k = "NO TIME" if u["minute"] is None else block_label(u["minute"])
            bucket = out.setdefault(k, {s: Cell() for s in sources})
            bucket[src].add(u["gross"], u["cost"], u["net"], 1)
    # NO TIME sorts last, where it reads as a footnote rather than as 00:00.
    keys = sorted(k for k in out if k != "NO TIME")
    return {k: out[k] for k in keys + (["NO TIME"] if "NO TIME" in out else [])}


def restrict_units(units: dict, rows) -> tuple[dict, dict]:
    """Keep only the positions that fall on a symbol-day the sheet has a row
    for. Returns (kept, dropped-per-source).

    The row set is Ben's traded history, and it is the spine of the whole
    comparison: a strategy trade on a day he did not trade has nothing to be
    compared against. But a strategy's own artefacts can outlive a pair list --
    the shipped MCL run held 6 trades on 3 symbol-days that no longer appear in
    the flex summary at all.

    Left in, those trades sat in the clock sheet and not in the monthly sheet,
    so the two disagreed by $102.67 on a workbook whose every individual cell
    was correct. Dropped silently, the same $102.67 vanishes with no record.
    So they are dropped AND counted, and the caller is expected to say so.
    """
    keys = {(r["symbol"], r["date"]) for r in rows}
    kept, dropped = {}, {}
    for src, us in units.items():
        keep = [u for u in us if (u["symbol"], u["date"]) in keys]
        lost = [u for u in us if (u["symbol"], u["date"]) not in keys]
        kept[src] = keep
        if lost:
            dropped[src] = lost
    return kept, dropped


ET = "America/New_York"


def _et_minute(stamp: str) -> int | None:
    """Minutes past ET midnight from a strategy's entry_time.

    The engine writes these in UTC ('2026-06-01 08:22:00+00:00'). Bucketing
    that as-is would put an 04:22 ET pre-market entry in the 08:00 block and
    shift every bucket by four or five hours -- and the sheet would look
    entirely reasonable, just describing a market that opens at 13:30.
    """
    import pandas as pd
    try:
        ts = pd.Timestamp(stamp)
    except (ValueError, TypeError):
        return None
    if ts.tzinfo is None:
        return None
    local = ts.tz_convert(ET)
    return local.hour * 60 + local.minute


def strategy_units(path: Path) -> list[dict]:
    """One dict per strategy trade, with its ENTRY time in ET minutes."""
    out = []
    if not path.exists():
        return out
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            out.append({"symbol": r["symbol"], "date": r["date"],
                        "minute": _et_minute(r.get("entry_time", "")),
                        "gross": float(r["gross"]),
                        "cost": float(r["commission"]),
                        "net": float(r["net"])})
    return out


def my_units(path: Path) -> list[dict]:
    """One dict per round trip, from a flex --round-trips CSV."""
    out = []
    if not path.exists():
        return out
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            t = r.get("entry_et") or ""
            minute = None
            if ":" in t:
                hh, _, mm = t.partition(":")
                minute = int(hh) * 60 + int(mm)
            cost = -float(r["commission"])      # IBKR negative-is-paid
            out.append({"symbol": r["symbol"], "date": r["date"],
                        "minute": minute, "gross": float(r["gross_pnl"]),
                        "cost": cost, "net": float(r["net_pnl"])})
    return out


# --- output ----------------------------------------------------------------

FIELDS = ("trades", "buy_shares", "sell_shares", "avg_buy_price",
          "avg_sell_price", "cost", "gross", "net")


def header(names: list[str]) -> list[str]:
    cols = ["symbol", "date"]
    for src in ["mine"] + names:
        cols.append(f"{src}_status")
        if src == "mine":
            cols.append("mine_fills")
        cols += [f"{src}_{f}" for f in FIELDS]
    return cols


def cells(b: Block, raw: bool = False) -> list:
    """One block's values. An absence is empty, never zero -- see the module
    docstring: 0.00 turns a day that could not be tested into a break-even.

    raw=True skips the display rounding. A spreadsheet must store the exact
    value and round in the number FORMAT, because its own monthly totals are
    SUMIFS over these cells: sum 587 values each rounded to the cent and the
    month is a few cents off the truth, on a sheet that shows both. Rounding
    for the eye belongs at the point of display, and in a workbook that point
    is the format string, not the cell.
    """
    if not b.has_figures:
        return [""] * len(FIELDS)
    r = (lambda v, n=2: v) if raw else round
    return [b.trades, round(b.buy_shares), round(b.sell_shares),
            "" if b.avg_buy_price is None else r(b.avg_buy_price, 4),
            "" if b.avg_sell_price is None else r(b.avg_sell_price, 4),
            r(b.cost, 2), r(b.gross, 2), r(b.net, 2)]


def write_csv(rows, names, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header(names))
        for r in rows:
            line = [r["symbol"], r["date"]]
            for src in ["mine"] + names:
                b = r[src]
                line.append(b.status)
                if src == "mine":
                    line.append("" if b.fills is None else b.fills)
                line += cells(b)
            w.writerow(line)


def coverage(rows, names) -> list[str]:
    out = ["COVERAGE", "",
           f"  symbol-days            {len(rows):,}", ""]
    width = max(len(n) for n in names) if names else 8
    out.append(f"  {'strategy':<{width}}  {'TRADED':>7} {'NO TRADES':>10} "
               f"{'NO BARS':>8} {'NO SIZE':>8} {'NOT RUN':>8} {'SCALED':>7}")
    for n in names:
        c = {s: 0 for s in ("TRADED", "NO TRADES", "NO BARS", "NO SIZE",
                            "NOT RUN", "SCALED")}
        for r in rows:
            c[r[n].status] = c.get(r[n].status, 0) + 1
        out.append(f"  {n:<{width}}  {c['TRADED']:>7} {c['NO TRADES']:>10} "
                   f"{c['NO BARS']:>8} {c['NO SIZE']:>8} {c['NOT RUN']:>8} "
                   f"{c['SCALED']:>7}")
    out += ["",
            "  Only NO TRADES is a zero: the strategy saw the session and",
            "  declined. NO BARS / NO SIZE / NOT RUN are days that could not",
            "  be tested, and their cells are EMPTY. Totalling a column over",
            "  a strategy with many of them compares a subset against the",
            "  whole of Ben's history."]
    return out


def totals(rows, names) -> list[str]:
    out = ["", "TOTALS OVER THE DAYS EACH SOURCE COULD BE EVALUATED ON", "",
           f"  {'source':<10} {'days':>6} {'trades':>7} {'gross':>13} "
           f"{'cost':>10} {'net':>13}", "  " + "-" * 62]
    for src in ["mine"] + names:
        ev = [r[src] for r in rows if r[src].has_figures]
        out.append(f"  {src:<10} {len(ev):>6} {sum(b.trades for b in ev):>7} "
                   f"{sum(b.gross for b in ev):>13,.2f} "
                   f"{sum(b.cost for b in ev):>10,.2f} "
                   f"{sum(b.net for b in ev):>13,.2f}")
    out += ["",
            "  These are NOT like-for-like unless the day counts match. A",
            "  strategy evaluated on 217 of 587 days is not outperforming",
            "  anything; it is a different sample."]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Per-day comparison, me vs strategies")
    ap.add_argument("--summary", default="var/reports/flex_symbol_days_all.csv")
    ap.add_argument("--strategy", nargs="+", default=["mcl", "mc5", "vw9_5m"])
    ap.add_argument("--reports", default="var/reports")
    ap.add_argument("--states", default="var/state")
    ap.add_argument("--out", default="var/reports/day_compare.csv")
    ap.add_argument("--report", default="var/reports/day_compare.txt")
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero if any trade was not a single round "
                         "trip, rather than blanking its prices and going on")
    a = ap.parse_args(argv)

    rows, scaled = build(Path(a.summary), Path(a.reports), Path(a.states),
                         a.strategy)
    write_csv(rows, a.strategy, Path(a.out))

    lines = coverage(rows, a.strategy) + totals(rows, a.strategy)
    if scaled:
        lines += ["", "TRADES THAT WERE NOT SINGLE ROUND TRIPS", ""]
        for n, keys in scaled.items():
            lines.append(f"  {n}: {len(keys)} row(s), e.g. {keys[:3]}")
        lines += ["",
                  "  entry_price is the FIRST buy on these, not the average,",
                  "  so the price columns are blank. The P/L is still exact."]
    from common.report_io import emit
    emit("\n".join(lines), a.report, header="common.day_compare")
    print(f"\nwrote {a.out}  ({len(rows):,} symbol-days)")
    if scaled and a.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
