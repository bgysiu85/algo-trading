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
        need = {"buy_shares", "sell_shares", "avg_buy_price", "avg_sell_price"}
        missing = need - set(rd.fieldnames or [])
        if missing:
            sys.exit(f"{path} is an older summary without {sorted(missing)}. "
                     "Regenerate it: python -m common.flex ... --summary <path>")
        for r in rd:
            bs = float(r["buy_shares"] or 0)
            ss = float(r["sell_shares"] or 0)
            out[(r["symbol"], r["date"])] = Block(
                status="TRADED",
                trades=int(r["executions"]),
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


# --- output ----------------------------------------------------------------

FIELDS = ("trades", "buy_shares", "sell_shares", "avg_buy_price",
          "avg_sell_price", "cost", "gross", "net")


def header(names: list[str]) -> list[str]:
    cols = ["symbol", "date"]
    for src in ["mine"] + names:
        cols.append(f"{src}_status")
        cols += [f"{src}_{f}" for f in FIELDS]
    return cols


def cells(b: Block) -> list:
    """One block's values. An absence is empty, never zero -- see the module
    docstring: 0.00 turns a day that could not be tested into a break-even."""
    if not b.has_figures:
        return [""] * len(FIELDS)
    return [b.trades, round(b.buy_shares), round(b.sell_shares),
            "" if b.avg_buy_price is None else round(b.avg_buy_price, 4),
            "" if b.avg_sell_price is None else round(b.avg_sell_price, 4),
            round(b.cost, 2), round(b.gross, 2), round(b.net, 2)]


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
