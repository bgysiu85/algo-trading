#!/usr/bin/env python3
"""
IBKR Flex trade-report parser: real executions -> symbol-date pairs and P/L.

    python -m common.flex TradeZella.csv                      # summary only
    python -m common.flex TradeZella.csv --pairs out.json     # pair list
    python -m common.flex TradeZella.csv --summary out.csv    # per symbol-day
    python -m common.flex TradeZella.csv --tz-report          # offset evidence

WHY THIS EXISTS
---------------
Every pair list in this project so far -- var/state/traded_pairs.json, all 407
of them -- was assembled in HINDSIGHT. PROGRAM_INDEX section 4 names that as the
one bias no amount of drop-top-N or bootstrapping can remove, and says the only
fix is "forward testing on contemporaneous scanner picks".

An IBKR Flex trade report is the closest thing available to that. The names in
it were chosen in real time on information that existed at the time, and the
fills are real fills at real prices with real commissions. It is evidence of a
different KIND from a backtest, not merely more of the same.

So this module is deliberately dumb: it extracts what IBKR actually reported and
computes nothing that IBKR did not already compute. FifoPnlRealized is IB's own
realised P/L and is used as-is. Recomputing FIFO here would be inventing a
second answer to a question the broker has already answered, and the two would
diverge silently on partial fills.

THE TIMEZONE TRAP, AND WHY THE OFFSET IS MEASURED RATHER THAN SET
-----------------------------------------------------------------
Flex reports DateTime in the ACCOUNT'S configured report timezone, not ET and
not UTC. On the first file processed here that was UTC+10 (Australian eastern,
winter), which puts a 04:00 ET pre-market fill at 18:00 the same day and a
10:00 ET fill at 00:01 the NEXT day. 109 of 4,692 rows had a DateTime date one
day ahead of TradeDate for exactly that reason.

Two consequences, both of which produce a plausible wrong answer rather than an
error:

  1. Pairing on DateTime[:10] silently mis-dates every fill after 14:00 ET.
     PAIR ON TradeDate -- IBKR sets it to the session date already.
  2. Bucketing into PRE / RTH / POST on the raw clock puts the entire
     pre-market block in the previous evening.

Australia and the US change DST on different dates, so the offset is 13, 14, 15
or 16 hours depending on the month, and a hardcoded constant is wrong for part
of any multi-month report. measure_offsets() therefore SOLVES for the offset per
row: the offset that both reproduces TradeDate and lands the fill inside the
04:00-20:00 ET session. Rows where more than one candidate fits (or none) are
reported rather than guessed at, because a report that cannot be placed on the
clock cannot be block-split, and block-splitting before the headline is a
standing requirement here.

WHAT THIS MODULE DOES NOT DO
----------------------------
It does not judge the trading. Comparing these fills against a strategy's
backtest on the same symbol-days is a separate question with its own confounds
-- above all that a discretionary trader chose both the name AND the moment,
while the strategy is only given the name. That belongs in its own module with
its own write-up, not here.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics as st
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

from common.report_io import emit

# The session this project trades, in ET. Used only to disambiguate the report
# timezone -- nothing is filtered by it.
ET = ZoneInfo("America/New_York")
SESSION_START_MIN = 4 * 60        # 04:00 ET
SESSION_END_MIN = 20 * 60         # 20:00 ET

# Candidate timezones for the DateTime column. Real IANA zones, not fixed hour
# offsets: a full-year report crosses four DST changes (US and Australia move on
# different dates), so the ET offset genuinely varies between 13 and 16 hours
# and NO single constant explains every row. The first version of this module
# used fixed offsets and left 86 of 18,482 rows unresolved for exactly that
# reason -- all of them clustered around the changeovers.
CANDIDATE_ZONES = (
    "Australia/Sydney",       # AEST/AEDT -- DST
    "Australia/Brisbane",     # AEST year-round -- no DST
    "Australia/Adelaide",
    "Australia/Perth",
    "America/New_York",       # report already in ET
    "UTC",
)

# PROGRAM_INDEX section 1: every strategy enforces this band. Executions outside
# it are kept and FLAGGED, never dropped -- the point of a real trade log is to
# show what was actually traded, including what the strategies would refuse.
PRICE_MIN, PRICE_MAX = 2.0, 20.0

REQUIRED_COLUMNS = (
    "Symbol", "TradeDate", "DateTime", "Quantity", "TradePrice",
    "IBCommission", "FifoPnlRealized", "Buy/Sell", "AssetClass",
    "LevelOfDetail", "TradeID",
)


@dataclass
class Execution:
    symbol: str
    trade_date: str          # ET session date, as IBKR reports it
    dt_raw: datetime         # in the report's own timezone
    qty: float               # signed: + buy, - sell
    price: float
    commission: float        # IBKR sign convention: negative = you paid
    fifo_pnl: float
    side: str
    trade_id: str = ""       # IBKR's unique execution id -- the de-dup key
    time_known: bool = True          # False when Flex stamped a date with no time
    et_minute: int | None = None     # minutes past ET midnight, once resolved
    offset_hours: int | None = None


@dataclass
class SymbolDay:
    symbol: str
    date: str
    executions: int = 0
    shares: float = 0.0
    gross_pnl: float = 0.0
    commission: float = 0.0
    prices: list[float] = field(default_factory=list)
    # Largest long position held during the day, in shares. This is what the
    # account actually had to fund, and it is the only honest way to size a
    # strategy against these trades: comparing a flat 100 shares against a day
    # that ran 2,000 measures position size, not decisions.
    max_position: int = 0

    # Bought and sold sides kept apart, with the NOTIONAL rather than a running
    # average price.
    #
    # An average of averages is wrong whenever the fills are unequal, and these
    # fills are wildly unequal -- a day can be 31 executions from 100 to 5,000
    # shares. Keeping sum(qty * price) and dividing once at the end is exact;
    # keeping a mean and updating it is not, and the error is invisible because
    # the number it produces is always plausible.
    #
    # `shares` above stays the total transacted (buys + sells), because
    # everything downstream already reads it that way.
    buy_shares: float = 0.0
    sell_shares: float = 0.0
    buy_notional: float = 0.0
    sell_notional: float = 0.0

    @property
    def avg_buy_price(self) -> float | None:
        """None, not 0.0 -- a day with no buys has no average buy price, and a
        zero would average into any summary as though it were a real one."""
        return self.buy_notional / self.buy_shares if self.buy_shares else None

    @property
    def avg_sell_price(self) -> float | None:
        return (self.sell_notional / self.sell_shares
                if self.sell_shares else None)

    @property
    def net_pnl(self) -> float:
        # IB reports commission as a negative number already.
        return self.gross_pnl + self.commission

    @property
    def in_band(self) -> bool:
        return all(PRICE_MIN <= p <= PRICE_MAX for p in self.prices)


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------

def _parse_dt(s: str) -> tuple[datetime, bool]:
    """Flex usually stamps 'YYYY-MM-DD HH:MM:SS', but not always.

    Three of 18,482 rows in the full-year report carried a bare date with no
    time -- all of them partial executions (Notes/Codes 'P') on the same fill.
    They are real trades with real P/L, so dropping them would understate the
    result, and inventing a time for them would put a fabricated fill in a
    session block. They load with time_known=False, count in every P/L figure,
    and are excluded from the clock-based analysis only.
    """
    for fmt, timed in (("%Y-%m-%d %H:%M:%S", True),
                       ("%Y-%m-%d;%H:%M:%S", True),
                       ("%Y%m%d;%H%M%S", True),
                       ("%Y-%m-%d", False)):
        try:
            return datetime.strptime(s, fmt), timed
        except ValueError:
            continue
    raise ValueError(f"unparseable Flex DateTime: {s!r}")


def load_many(paths, *, stocks_only: bool = True) -> list[Execution]:
    """Load several Flex exports and de-duplicate.

    Flex caps one query at about twelve months, so a longer history arrives as
    two or more exports with an overlapping window. Concatenating them naively
    double-counts every execution in the overlap -- and the overlap is not
    visible in the totals, it just makes them bigger.

    De-duplication is on IBKR's TradeID, which is unique per execution. It is
    NOT on the field values. A first version keyed on (symbol, date, timestamp,
    qty, price, commission, pnl) and silently deleted 1,314 real fills from a
    single 18,482-row report: a large order routed as several identical child
    fills in the same second is ordinary, not a duplicate. The P/L moved by
    $3,360, nothing raised, and the total was simply smaller and still
    plausible. If TradeID is absent the load fails loudly rather than falling
    back to a value-based key.
    """
    seen, out = set(), []
    for p in ([paths] if isinstance(paths, (str, Path)) else paths):
        for e in load(p, stocks_only=stocks_only):
            if not e.trade_id:
                raise ValueError(
                    f"{p}: an execution has no TradeID, so exports cannot be "
                    "safely de-duplicated. Add TradeID to the Flex query.")
            if e.trade_id in seen:
                continue
            seen.add(e.trade_id)
            out.append(e)
    return out


def load(path: str | Path, *, stocks_only: bool = True) -> list[Execution]:
    """Read a Flex trade CSV. Keeps EXECUTION rows only.

    Flex can emit ORDER-level and EXECUTION-level rows in the same file; summing
    both double-counts everything. LevelOfDetail is the discriminator.
    """
    rows = list(csv.DictReader(open(path, newline="", encoding="utf-8-sig")))
    if not rows:
        raise ValueError(f"{path}: no rows")

    missing = [c for c in REQUIRED_COLUMNS if c not in rows[0]]
    if missing:
        raise ValueError(
            f"{path}: not an IBKR Flex trade report -- missing {missing}. "
            "The query needs the Trades section at EXECUTION level of detail.")

    out: list[Execution] = []
    for r in rows:
        if r["LevelOfDetail"] != "EXECUTION":
            continue
        if stocks_only and r["AssetClass"] != "STK":
            continue
        raw, timed = _parse_dt(r["DateTime"].strip())
        out.append(Execution(
            symbol=r["Symbol"].strip().upper(),
            trade_date=r["TradeDate"].strip(),
            dt_raw=raw,
            time_known=timed,
            qty=float(r["Quantity"]),
            price=float(r["TradePrice"]),
            commission=float(r["IBCommission"] or 0.0),
            fifo_pnl=float(r["FifoPnlRealized"] or 0.0),
            side=r["Buy/Sell"].strip().upper(),
            trade_id=(r.get("TradeID") or r.get("IBExecID")
                      or r.get("TransactionID") or "").strip(),
        ))
    if not out:
        raise ValueError(f"{path}: no EXECUTION-level stock rows found")
    return out


# --------------------------------------------------------------------------
# the timezone question
# --------------------------------------------------------------------------

def _to_et(ex: Execution, zone: str) -> datetime | None:
    """Read the naive stamp AS this zone's wall clock and convert to ET."""
    if not ex.time_known:
        return None
    try:
        return ex.dt_raw.replace(tzinfo=ZoneInfo(zone)).astimezone(ET)
    except Exception:
        return None


def _fits(ex: Execution, zone: str) -> bool:
    """Does this zone reproduce TradeDate AND land the fill in the ET session?"""
    et = _to_et(ex, zone)
    if et is None or et.strftime("%Y-%m-%d") != ex.trade_date:
        return False
    return SESSION_START_MIN <= et.hour * 60 + et.minute <= SESSION_END_MIN


def score_offsets(execs: list[Execution]) -> dict[str, int]:
    """How many rows each candidate zone explains. This is the evidence."""
    return {z: sum(1 for e in execs if _fits(e, z)) for z in CANDIDATE_ZONES}


def measure_offsets(execs: list[Execution], *, force: str | None = None) -> dict:
    """Resolve the report timezone and stamp ET minutes onto each row.

    Two things make this harder than it looks, and both produce a plausible
    wrong answer rather than an error.

    FIRST, a single fill rarely pins the zone. A fill stamped 18:00 on its own
    TradeDate is 05:00 ET under a +13 zone and 04:00 ET under a +14 one, and
    both are inside the session on the right date. Only rows that cross midnight
    (a 10:00 ET fill stamped 00:01 the next day) discriminate, and there are few.

    SECOND -- and this is why zones rather than hour offsets -- the US and
    Australia change DST on different dates, so over a full year the true ET
    offset moves between 13 and 16 hours. A constant cannot be right for all of
    it. Scoring real IANA zones lets the zone database handle the changeovers,
    which is what took the unresolved count on the full-year report from 86 to
    whatever it now reports.

    Zones that explain equally many rows are reported as ambiguous rather than
    silently collapsed; --tz overrides.
    """
    scores = score_offsets(execs)
    best = max(scores.values())
    fitting = [z for z in CANDIDATE_ZONES if scores[z] == best]
    chosen = force if force is not None else fitting[0]

    resolved = 0
    for e in execs:
        et = _to_et(e, chosen)
        if et is None or not _fits(e, chosen):
            e.et_minute, e.offset_hours = None, None
            continue
        e.et_minute = et.hour * 60 + et.minute
        e.offset_hours = int((e.dt_raw - et.replace(tzinfo=None)).total_seconds() // 3600)
        resolved += 1

    et_minutes = [e.et_minute for e in execs if e.et_minute is not None]
    return {
        "scores": scores,
        "chosen": chosen,
        "forced": force is not None,
        "equally_good": fitting,
        "ambiguous": len(fitting) > 1,
        "resolved": resolved,
        "unresolved": len(execs) - resolved,
        "earliest_et": min(et_minutes) if et_minutes else None,
        "latest_et": max(et_minutes) if et_minutes else None,
        "no_time_stamped": sum(1 for e in execs if not e.time_known),
        "date_mismatches": sum(
            1 for e in execs if e.dt_raw.strftime("%Y-%m-%d") != e.trade_date),
    }


def block(et_minute: int | None) -> str:
    if et_minute is None:
        return "UNKNOWN"
    if et_minute < 9 * 60 + 30:
        return "PRE"
    if et_minute < 16 * 60:
        return "RTH"
    return "POST"


# --------------------------------------------------------------------------
# the two things callers actually want
# --------------------------------------------------------------------------

def pairs(execs: list[Execution]) -> list[dict]:
    """Symbol-date pairs in var/state/traded_pairs.json format, sorted.

    Pairs on TradeDate. See the module docstring for why DateTime is wrong.
    """
    seen = sorted({(e.symbol, e.trade_date) for e in execs})
    return [{"symbol": s, "date": d} for s, d in seen]


def _px(v) -> str:
    """A missing average price is written as empty, never as 0.

    A 0.00 in an average-price column reads as a real price and averages into
    any downstream summary as one. Empty is the only value that cannot be
    mistaken for a measurement.
    """
    return "" if v is None else f"{v:.4f}"


def symbol_days(execs: list[Execution]) -> dict[tuple[str, str], SymbolDay]:
    grouped: dict[tuple[str, str], list[Execution]] = defaultdict(list)
    for e in execs:
        grouped[(e.symbol, e.trade_date)].append(e)

    out: dict[tuple[str, str], SymbolDay] = {}
    for k, rows in grouped.items():
        sd = out[k] = SymbolDay(symbol=k[0], date=k[1])
        # Walk the fills in time order to find the peak position. Rows with no
        # stamped time sort first; they are three fills in the whole history and
        # cannot change a peak by more than their own size.
        pos = 0.0
        for e in sorted(rows, key=lambda x: (x.time_known, x.dt_raw)):
            sd.executions += 1
            sd.shares += abs(e.qty)
            sd.gross_pnl += e.fifo_pnl
            sd.commission += e.commission
            sd.prices.append(abs(e.price))
            # Side comes from the SIGN of qty, not from e.side. Both are
            # present and they agree today, but the sign is what every other
            # number here is derived from (shares, max_position), so deriving
            # this from the string would let the two drift apart silently.
            if e.qty > 0:
                sd.buy_shares += e.qty
                sd.buy_notional += e.qty * abs(e.price)
            elif e.qty < 0:
                sd.sell_shares += -e.qty
                sd.sell_notional += -e.qty * abs(e.price)
            pos += e.qty
            sd.max_position = max(sd.max_position, int(round(pos)))
    return out


def new_against(pair_list: list[dict], existing_path: str | Path) -> list[dict]:
    """The pairs not already in an existing pair file."""
    have = {(p["symbol"], p["date"])
            for p in json.load(open(existing_path))}
    return [p for p in pair_list if (p["symbol"], p["date"]) not in have]


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------

def _drop_top(values: list[float], n: int) -> float:
    return sum(sorted(values, reverse=True)[n:])


def report(execs: list[Execution], tz: dict) -> str:
    sd = symbol_days(execs)
    nets = [s.net_pnl for s in sd.values()]
    dates = sorted({e.trade_date for e in execs})
    lines = []
    A = lines.append

    A(f"executions          {len(execs):,}")
    A(f"symbol-days         {len(sd):,}")
    A(f"symbols             {len({e.symbol for e in execs}):,}")
    A(f"sessions            {len(dates)}   {dates[0]} -> {dates[-1]}")

    def hhmm(m):
        return "n/a" if m is None else f"{m//60:02d}:{m%60:02d}"

    A("")
    A("REPORT TIMEZONE " + ("(FORCED)" if tz["forced"] else "(measured)"))
    for z, n in sorted(tz["scores"].items(), key=lambda kv: -kv[1]):
        A(f"    {z:<20} explains {n:>7,} of {len(execs):,}")
    A(f"  chosen            {tz['chosen']}"
      + ("  <-- overridden" if tz["forced"] else ""))
    if tz["ambiguous"]:
        A(f"  AMBIGUOUS         {tz['equally_good']} explain the same rows;")
        A( "                    took the first. Override with --tz.")
    A(f"  resolved          {tz['resolved']:,} of {tz['resolved']+tz['unresolved']:,}")
    if tz["no_time_stamped"]:
        A(f"  no time stamped   {tz['no_time_stamped']:,}  (date-only fills; "
          "in the P/L, out of the block split)")
    if tz["unresolved"]:
        A(f"  UNRESOLVED        {tz['unresolved']:,}  <-- excluded from the block split")
    A(f"  implied ET span   {hhmm(tz['earliest_et'])} .. {hhmm(tz['latest_et'])}")
    A(f"  DateTime date != TradeDate in {tz['date_mismatches']:,} rows "
      "(expected, and the reason pairing uses TradeDate)")

    blocks = Counter(block(e.et_minute) for e in execs)
    A("")
    A("EXECUTIONS BY ET BLOCK")
    for b in ("PRE", "RTH", "POST", "UNKNOWN"):
        if blocks.get(b):
            A(f"  {b:<8} {blocks[b]:>6,}  ({100*blocks[b]/len(execs):.0f}%)")

    gross = sum(e.fifo_pnl for e in execs)
    comm = sum(e.commission for e in execs)
    A("")
    A("REALISED P/L (IBKR's own FIFO figures)")
    A(f"  gross             ${gross:>12,.2f}")
    A(f"  commission        ${comm:>12,.2f}")
    A(f"  net               ${gross+comm:>12,.2f}")

    wins = sum(1 for v in nets if v > 0)
    A("")
    A("PER SYMBOL-DAY")
    A(f"  profitable        {wins} of {len(nets)}  ({100*wins/len(nets):.0f}%)")
    A(f"  median            ${st.median(nets):>12,.2f}")
    A(f"  mean              ${sum(nets)/len(nets):>12,.2f}")
    A(f"  best / worst      ${max(nets):,.2f} / ${min(nets):,.2f}")
    for n in (1, 3, 5):
        A(f"  drop-top-{n}        ${_drop_top(nets, n):>12,.2f}")

    ex_counts = sorted(s.executions for s in sd.values())
    A("")
    A("TRADE FREQUENCY  (the commission driver)")
    A(f"  executions/symbol-day   median {st.median(ex_counts):.0f}"
      f"   p90 {ex_counts[int(0.9*len(ex_counts))]}   max {max(ex_counts)}")
    A(f"  commission per execution  ${abs(comm)/len(execs):.2f}")

    out_of_band = [s for s in sd.values() if not s.in_band]
    A("")
    A(f"PRICE BAND (${PRICE_MIN:.0f}-${PRICE_MAX:.0f})")
    A(f"  symbol-days with any fill outside the band: {len(out_of_band)} of {len(sd)}")
    A("  (kept and flagged, not dropped -- the strategies would refuse these)")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("csv", nargs="+",
                    help="IBKR Flex trade report(s), EXECUTION level. Several "
                         "may be given: Flex caps a single query at ~12 months, "
                         "so a longer history arrives as overlapping exports. "
                         "Executions are de-duplicated across files.")
    ap.add_argument("--pairs", metavar="OUT.json",
                    help="write the symbol-date pairs")
    ap.add_argument("--summary", metavar="OUT.csv",
                    help="write per-symbol-day P/L")
    ap.add_argument("--against", metavar="EXISTING.json",
                    default="var/state/traded_pairs.json",
                    help="report which pairs are new against this file")
    ap.add_argument("--out", metavar="OUT.txt",
                    default="var/reports/flex_report.txt",
                    help="save the report as UTF-8 (default: %(default)s)")
    ap.add_argument("--tz-report", action="store_true",
                    help="print the per-offset evidence and exit")
    ap.add_argument("--tz", default=None, metavar="ZONE",
                    help="force the report timezone, e.g. Australia/Sydney "
                         "(skips the measurement; see --tz-report first)")
    a = ap.parse_args(argv)

    execs = load_many(a.csv)
    tz = measure_offsets(execs, force=a.tz)

    if a.tz_report:
        print(json.dumps(tz, indent=2))
        return 0

    emit(report(execs, tz), a.out, header="common.flex")

    pl = pairs(execs)
    try:
        new = new_against(pl, a.against)
        print(f"\nAGAINST {a.against}")
        print(f"  pairs in this report   {len(pl)}")
        print(f"  already present        {len(pl)-len(new)}")
        print(f"  NEW                    {len(new)}")
    except FileNotFoundError:
        pass

    if a.pairs:
        Path(a.pairs).parent.mkdir(parents=True, exist_ok=True)
        json.dump(pl, open(a.pairs, "w"), indent=1)
        print(f"\nwrote {a.pairs}  ({len(pl)} pairs)")

    if a.summary:
        sd = symbol_days(execs)
        Path(a.summary).parent.mkdir(parents=True, exist_ok=True)
        with open(a.summary, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["symbol", "date", "executions", "shares",
                        "buy_shares", "sell_shares", "avg_buy_price",
                        "avg_sell_price", "max_position", "gross_pnl",
                        "commission", "net_pnl", "in_band"])
            for k in sorted(sd):
                s = sd[k]
                w.writerow([s.symbol, s.date, s.executions, round(s.shares),
                            round(s.buy_shares), round(s.sell_shares),
                            _px(s.avg_buy_price), _px(s.avg_sell_price),
                            s.max_position,
                            round(s.gross_pnl, 2), round(s.commission, 2),
                            round(s.net_pnl, 2), int(s.in_band)])
        print(f"wrote {a.summary}  ({len(sd)} symbol-days)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
