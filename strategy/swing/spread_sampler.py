#!/usr/bin/env python3
"""Record the real IBKR bid/ask for a candidate swing universe. Collector only.

    python -m strategy.swing.spread_sampler
    python -m strategy.swing.spread_sampler --universe my_names.txt --interval 30
    python -m strategy.swing.spread_sampler --self-test   (no IB connection needed)

WHY THIS EXISTS
---------------
`swing_preflight_20260914.md` G2 requires the cost of a round trip to be
MEASURED for the candidate universe, not assumed. Three routes were considered
and two of them are closed:

  * PUBLIC DATA. The SEC stopped publishing spread and depth after December
    2013. Its current market-structure files carry the right decile breakdown
    and no spread column. Quoting "SEC DERA" for a 2026 large-cap spread means
    quoting 13-year-old numbers.
  * THE TOOLING ALREADY ON DISK. `common/friction_quotes.py` prices Ben's own
    Flex fills and takes a trade report as input, so it can only measure a
    universe he has already traded. `common/quote_fill.py` is the same shape
    one level over -- it runs off the traded-pairs file.
  * THE DATABENTO ARCHIVE is scoped to the small-cap screened universe. Large
    cap tcbbo is not on disk, and retrieval is what Databento bills for.

So this measures the quote directly, live, at the venue Ben actually trades.
It is current, it is free, and it is his own execution venue rather than a
market-wide average that includes wholesaler flow he does not receive.

THIS SCRIPT DOES NOT ANALYSE. It writes raw observations and nothing else.
`spread_report.py` turns the CSV into a distribution. Keeping the collector
dumb means a bug in the analysis never costs a session of data.

READ-ONLY, AND ENFORCED THE SAME WAY THE REPO ENFORCES IT
----------------------------------------------------------
No order is ever placed -- there is no order code in this file. Beyond that it
carries the project's standing guards, because a rule that lives only in prose
gets broken by the first convenient exception:

  * PORT ALLOWLIST. 7497 (TWS paper) and 4002 (Gateway paper) accepted. 7496
    and 4001 are rejected BY NAME with an explanation, not silently.
  * DU-PREFIX CHECK. managedAccounts() must return a DU account or the script
    exits before requesting anything.

FOUR THINGS THAT WOULD MAKE THIS WRONG, AND WHAT IS DONE ABOUT EACH
--------------------------------------------------------------------
1. DELAYED DATA LOOKS LIKE LIVE DATA. This is the dangerous one. If the market
   data subscription sits on the live account and is not shared to paper, IB
   serves delayed quotes -- which still populate bid and ask, and would produce
   a spread distribution that is precise and measures nothing. So marketDataType
   is recorded ON EVERY ROW (1=live, 2=frozen, 3=delayed, 4=delayed-frozen) and
   the report REFUSES to pool anything that is not 1. A control whose output is
   indistinguishable from the failure it detects is not a control.

2. MARKET DATA LINES ARE FINITE. A standard account carries roughly 100
   simultaneous lines. Requesting more silently starves the tail of the
   universe. So the universe is subscribed in batches of --lines, and where it
   does not fit in one batch the batches ROTATE with a settle delay -- each name
   is then sampled every (batches x interval) seconds rather than every
   interval, which the report states rather than hides.

3. A TICKER THAT HAS NOT UPDATED YET IS NOT A ZERO SPREAD. Freshly subscribed
   tickers read nan for a second or two. Rows where bid or ask is missing or
   non-positive are written with the raw values intact and excluded by the
   report, which counts them -- rather than dropped here, where the loss would
   be invisible.

4. A CRASH FOUR HOURS IN SHOULD NOT COST FOUR HOURS. Every row is flushed as it
   is written. The file is opened in append mode, so re-running after a
   disconnect continues the same session rather than truncating it.

NO REPO IMPORTS, DELIBERATELY
------------------------------
This module imports nothing from `common/`. It runs while a session may be
live, possibly from the production tree, and a collector that cannot start
because something unrelated is mid-edit is a collector that loses a session.
The same reason it does not use `common.report_io`: it emits no colour at all,
so the ANSI-must-never-reach-a-txt rule is satisfied by construction rather
than by remembering to.

OPERATIONAL NOTES
-----------------
  * Requires `ib_async` (pinned at 2.1.0 in the repo's requirements).
  * US regular trading hours are 09:30-16:00 ET, which is 23:30-06:00 AEST in
    northern summer and 01:30-08:00 AEDT once both sides have shifted. The
    default window is RTH in ET and is converted for you.
  * Ctrl-C exits cleanly and leaves a valid CSV.
"""
from __future__ import annotations

import argparse
import csv
import signal
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------- guards ----

# Same allowlist the live trader enforces (brokers/ibkr/trader.py PAPER_PORTS /
# LIVE_PORTS). The DEFAULT is 4002 to match trader.py and run_paper.ps1, which
# is what actually runs here -- the first version of this module defaulted to
# 7497 because it is first in this dict, and the run died on
# ConnectionRefusedError with nothing listening. A default that disagrees with
# the rest of the repo is a paper cut every single time.
PORTS_ALLOWED = {7497: "TWS paper", 4002: "IB Gateway paper"}
PORTS_REFUSED = {
    7496: "TWS LIVE",
    4001: "IB Gateway LIVE",
}

# The 36 names the pre-flight measured move sizes on, plus SPY. Using the same
# universe means the numerator (move size) and the denominator (spread) are
# measured on identical names, which is the only way the ratio in section 4 of
# the pre-flight becomes a measurement rather than two unrelated numbers.
DEFAULT_UNIVERSE = [
    # MEGA
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL",
    "JPM", "XOM", "JNJ", "WMT", "PG", "UNH",
    # LARGE
    "AMD", "CRM", "NFLX", "CAT", "GS", "SCHW",
    "PFE", "GILD", "NEE", "DUK", "FDX", "MRVL",
    # MID
    "ETSY", "ROKU", "WYNN", "ALB", "MOS", "ALK",
    "CLF", "AA", "BEN", "SJM", "KMX", "HAL",
    # reference
    "SPY",
]

FIELDS = [
    "ts_utc", "symbol", "bid", "ask", "bid_size", "ask_size",
    "last", "volume", "md_type", "batch",
]

_stop = False


def _sigint(_sig, _frm):
    global _stop
    _stop = True
    print("\n[stop] finishing the current tick and closing the file cleanly...")


# ------------------------------------------------------------- session ----

RTH_OPEN_MIN = 9 * 60 + 30       # 09:30 ET
RTH_CLOSE_MIN = 16 * 60          # 16:00 ET


def _et(dt_utc: datetime) -> datetime:
    """ET wall clock. UTC-4 in summer, UTC-5 in winter, derived from the date."""
    y = dt_utc.year
    mar = datetime(y, 3, 1, tzinfo=timezone.utc)
    dst_start = mar + timedelta(days=(6 - mar.weekday()) % 7 + 7, hours=7)
    nov = datetime(y, 11, 1, tzinfo=timezone.utc)
    dst_end = nov + timedelta(days=(6 - nov.weekday()) % 7, hours=6)
    return dt_utc + timedelta(hours=-4 if dst_start <= dt_utc < dst_end else -5)


def rth_overlap_minutes(start_utc: datetime, minutes: float) -> int:
    """How many minutes of a planned run land inside US regular hours.

    Weekends count as closed. Holidays do not -- this is a planning aid, not a
    calendar, and it says so rather than pretending otherwise.
    """
    if minutes <= 0:
        minutes = 24 * 60          # open-ended run: judge the next 24h
    covered = 0
    for m in range(int(minutes)):
        et = _et(start_utc + timedelta(minutes=m))
        if et.weekday() >= 5:                      # Sat/Sun
            continue
        mins = et.hour * 60 + et.minute
        if RTH_OPEN_MIN <= mins < RTH_CLOSE_MIN:
            covered += 1
    return covered


def session_banner(start_utc: datetime, minutes: float) -> tuple[list[str], bool]:
    """Lines to print before collecting, and whether to warn.

    The first real run of this collector was started at 11:02 AEST and left for
    13 hours. Under 5% of its rows landed inside US regular hours, and the
    pooled spread came out at 34.27 bps against the honest 8.00 -- a figure
    that passed the G2 gate and measured the overnight book. Finding that out
    afterwards costs a session; saying it here costs a line.
    """
    et = _et(start_utc)
    planned = int(minutes) if minutes > 0 else 24 * 60
    covered = rth_overlap_minutes(start_utc, minutes)
    pct = 100.0 * covered / planned if planned else 0.0

    lines = [
        f"[session] ET now {et:%Y-%m-%d %H:%M} ({et:%a}); "
        f"US regular hours are 09:30-16:00 ET",
        f"[session] this run covers {covered} of {planned} planned minutes "
        f"inside regular hours ({pct:.0f}%)",
    ]
    warn = pct < 50.0
    if warn:
        lines += [
            "",
            "  *** WARNING: most of this run falls OUTSIDE US regular hours. ***",
            "  *** The overnight and pre-market book is several times wider,  ***",
            "  *** and spread_report defaults to --session rth, so those rows ***",
            "  *** will be collected and then excluded.                       ***",
            "  *** Start closer to the open, or pass --minutes to end at it.  ***",
            "",
        ]
    lines.append("[session] holidays are not modelled; weekends are")
    return lines, warn



def seconds_until_open(now_utc: datetime) -> float:
    """Seconds until the next US regular-hours open. 0 when already inside.

    Weekends skip to Monday. Holidays are NOT modelled -- on a holiday this
    returns 0 all day and the collector will sit there recording a shut market,
    which the report then excludes as a session with no usable rows. That is a
    wasted night, not a wrong number, and the banner says so.
    """
    et = _et(now_utc)
    mins = et.hour * 60 + et.minute + et.second / 60.0
    if et.weekday() < 5 and RTH_OPEN_MIN <= mins < RTH_CLOSE_MIN:
        return 0.0
    ahead = 0
    while True:
        cand = et + timedelta(days=ahead)
        if cand.weekday() < 5:
            open_at = cand.replace(hour=9, minute=30, second=0, microsecond=0)
            if open_at > et:
                return (open_at - et).total_seconds()
        ahead += 1
        if ahead > 7:                                    # unreachable in practice
            raise RuntimeError("no market open found within a week")


class Outages:
    """Every stretch the socket was down, so a hole in the CSV is explained.

    Without this a disconnect is invisible after the fact: the rows simply stop
    and resume, and nothing distinguishes "Gateway restarted" from "the market
    was quiet". The first real run had two holes -- 134.6 and 10.7 minutes --
    and it took an after-the-fact timestamp diff to find them.
    """

    def __init__(self):
        self.events: list[tuple[str, str, float]] = []

    def record(self, start_utc: datetime, end_utc: datetime) -> None:
        self.events.append((
            start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            end_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            (end_utc - start_utc).total_seconds(),
        ))

    def total_seconds(self) -> float:
        return sum(e[2] for e in self.events)

    def summary(self) -> list[str]:
        if not self.events:
            return ["[outages] none -- the connection held for the whole run"]
        out = [f"[outages] {len(self.events)} disconnection(s), "
               f"{self.total_seconds()/60:.1f} min total. NO rows were written "
               f"while down."]
        for a, b, secs in self.events:
            out.append(f"    {a} -> {b}   ({secs/60:.1f} min)")
        return out


# ------------------------------------------------------------- universe ----

def load_universe(path: str | None) -> list[str]:
    if not path:
        return list(DEFAULT_UNIVERSE)
    p = Path(path)
    if not p.exists():
        sys.exit(f"universe file not found: {p}")
    out: list[str] = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        s = raw.split("#", 1)[0].strip().upper()
        if s:
            out.extend(t.strip() for t in s.split(",") if t.strip())
    if not out:
        sys.exit(f"universe file is empty: {p}")
    seen: set[str] = set()
    uniq = [s for s in out if not (s in seen or seen.add(s))]
    if len(uniq) != len(out):
        print(f"[universe] dropped {len(out) - len(uniq)} duplicate symbol(s)")
    return uniq


def check_port(port: int) -> None:
    if port in PORTS_REFUSED:
        sys.exit(
            f"\nREFUSED: port {port} is {PORTS_REFUSED[port]}.\n"
            f"This project's standing rule is that tooling connects to the paper\n"
            f"environment only. Allowed ports: "
            + ", ".join(f"{p} ({n})" for p, n in PORTS_ALLOWED.items())
            + "\n"
        )
    if port not in PORTS_ALLOWED:
        sys.exit(
            f"\nREFUSED: port {port} is not on the allowlist.\n"
            f"Allowed ports: "
            + ", ".join(f"{p} ({n})" for p, n in PORTS_ALLOWED.items())
            + "\n"
        )


# ----------------------------------------------------------- self-test ----

def self_test() -> int:
    """Everything that does not need IB. Run this before the session, not during."""
    ok = True

    u = load_universe(None)
    print(f"[self-test] default universe: {len(u)} symbols, first 5 {u[:5]}")
    if len(u) != 37:
        print("  FAIL expected 37 symbols"); ok = False

    for bad in (7496, 4001, 1234):
        try:
            check_port(bad)
            print(f"  FAIL port {bad} was accepted"); ok = False
        except SystemExit as e:
            label = "by name" if bad in PORTS_REFUSED else "not on allowlist"
            print(f"[self-test] port {bad} refused ({label}) OK")
            if bad in PORTS_REFUSED and PORTS_REFUSED[bad] not in str(e):
                print("  FAIL refusal did not name the port"); ok = False
    for good in PORTS_ALLOWED:
        try:
            check_port(good)
            print(f"[self-test] port {good} accepted OK")
        except SystemExit:
            print(f"  FAIL port {good} was refused"); ok = False

    tmp = Path(tempfile.mkdtemp(prefix="swing_selftest_")) / "sample.csv"
    try:
        w = Writer(tmp)
        w.write_row({
            "ts_utc": "2026-09-14T13:30:00Z", "symbol": "TEST",
            "bid": 10.01, "ask": 10.03, "bid_size": 300, "ask_size": 500,
            "last": 10.02, "volume": 12345, "md_type": 1, "batch": 0,
        })
        w.close()
        rows = list(csv.DictReader(tmp.open(encoding="utf-8")))
        if len(rows) == 1 and rows[0]["symbol"] == "TEST":
            print("[self-test] CSV write/readback OK")
        else:
            print("  FAIL csv readback"); ok = False
    finally:
        tmp.unlink(missing_ok=True)
        tmp.parent.rmdir()

    for accts, want_ok in ((["DUM215828"], True), (["DU111", "DU222"], True),
                           (["U1234567"], False), ([], False),
                           (["DUM1", "U9"], False)):
        try:
            check_accounts(accts)
            got_ok = True
        except SystemExit:
            got_ok = False
        if got_ok != want_ok:
            print(f"  FAIL account guard on {accts}"); ok = False
    print("[self-test] DU-prefix account guard OK")

    # 2026-09-17 was a Thursday. 01:02Z is 21:02 ET the previous day -- shut.
    _, warn = session_banner(datetime(2026, 9, 17, 1, 2, tzinfo=timezone.utc), 390)
    if not warn:
        print("  FAIL an overnight start did not warn"); ok = False
    # 13:30Z is 09:30 ET, the open
    _, warn = session_banner(datetime(2026, 9, 17, 13, 30, tzinfo=timezone.utc), 390)
    if warn:
        print("  FAIL a run starting at the open warned anyway"); ok = False
    cov = rth_overlap_minutes(datetime(2026, 9, 17, 13, 30, tzinfo=timezone.utc), 390)
    if cov != 390:
        print(f"  FAIL open-to-close overlap was {cov}, expected 390"); ok = False
    print("[self-test] session banner OK")

    if seconds_until_open(datetime(2026, 9, 17, 13, 30, tzinfo=timezone.utc)) != 0:
        print("  FAIL inside RTH should be 0"); ok = False
    fri = seconds_until_open(datetime(2026, 9, 18, 21, 0, tzinfo=timezone.utc))
    if abs(fri - 64.5 * 3600) > 1:
        print(f"  FAIL Friday evening should reach Monday, got {fri/3600:.2f}h")
        ok = False
    o = Outages()
    if o.total_seconds() != 0 or "none" not in o.summary()[0]:
        print("  FAIL empty outages"); ok = False
    o.record(datetime(2026, 9, 17, 1, 44, tzinfo=timezone.utc),
             datetime(2026, 9, 17, 3, 59, tzinfo=timezone.utc))
    if abs(o.total_seconds() - 135 * 60) > 1:
        print("  FAIL outage duration"); ok = False
    print("[self-test] wait-for-open and outage accounting OK")

    b = batches(list(range(37)), 45)
    if len(b) != 1:
        print("  FAIL 37 symbols in 45 lines should be one batch"); ok = False
    b = batches(list(range(100)), 45)
    if len(b) != 3 or sum(len(x) for x in b) != 100:
        print("  FAIL batching lost symbols"); ok = False
    print("[self-test] batching OK")

    print("\n[self-test] PASS" if ok else "\n[self-test] FAILED")
    return 0 if ok else 1


def check_accounts(accounts: list[str]) -> None:
    """Every account must carry the DU paper prefix. Lifted out of run() so a
    test can exercise it without an IB connection -- a guard that is only
    reachable through a live socket is a guard nothing ever tests."""
    if not accounts or not all(a.startswith("DU") for a in accounts):
        raise SystemExit(
            f"REFUSED: managedAccounts() returned {accounts}.\n"
            "Every account must carry the DU paper prefix before this script "
            "requests anything.")


def batches(items: list, size: int) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]


# -------------------------------------------------------------- writer ----

class Writer:
    """Append-mode, header-once, flush-every-row."""

    def __init__(self, path: Path):
        self.path = path
        new = not path.exists() or path.stat().st_size == 0
        path.parent.mkdir(parents=True, exist_ok=True)
        self.fh = path.open("a", newline="", encoding="utf-8")
        self.w = csv.DictWriter(self.fh, fieldnames=FIELDS)
        if new:
            self.w.writeheader()
            self.fh.flush()
        self.n = 0

    def write_row(self, row: dict) -> None:
        self.w.writerow(row)
        self.fh.flush()
        self.n += 1

    def close(self) -> None:
        self.fh.close()


# --------------------------------------------------------------- sample ----

def _num(x):
    """IB serves nan for 'not yet known'. Keep it out of the CSV as empty."""
    try:
        if x is None:
            return ""
        f = float(x)
        if f != f:            # nan
            return ""
        if f < 0:             # IB uses -1 for 'no size'
            return ""
        return f
    except (TypeError, ValueError):
        return ""


def run(args) -> int:
    try:
        from ib_async import IB, Stock
    except ImportError:
        sys.exit(
            "ib_async is not installed in this interpreter.\n"
            "  pip install ib_async==2.1.0\n"
        )

    check_port(args.port)
    symbols = load_universe(args.universe)
    out = Path(args.out)

    ib = IB()
    print(f"[connect] {args.host}:{args.port} clientId={args.client_id}")
    ib.connect(args.host, args.port, clientId=args.client_id, timeout=20)

    accounts = ib.managedAccounts()
    print(f"[connect] accounts: {accounts}")
    try:
        check_accounts(accounts)
    except SystemExit:
        ib.disconnect()
        raise

    # 1 = live. Anything else and the spread is not the spread.
    ib.reqMarketDataType(1)

    print(f"[qualify] {len(symbols)} symbols...")
    contracts, unqualified = [], []
    for s in symbols:
        c = Stock(s, "SMART", "USD")
        try:
            q = ib.qualifyContracts(c)
            if q:
                contracts.append(q[0])
            else:
                unqualified.append(s)
        except Exception as e:                       # noqa: BLE001
            unqualified.append(f"{s} ({type(e).__name__})")
        ib.sleep(0.05)                               # qualification is paced too
    if unqualified:
        print(f"[qualify] NOT qualified ({len(unqualified)}): {unqualified}")
    if not contracts:
        ib.disconnect()
        sys.exit("no contracts qualified; nothing to sample")
    print(f"[qualify] {len(contracts)} qualified")

    groups = batches(contracts, args.lines)
    rotating = len(groups) > 1
    if rotating:
        eff = args.interval * len(groups)
        print(f"[lines] {len(contracts)} symbols exceed --lines {args.lines}: "
              f"{len(groups)} rotating batches, so each name is sampled every "
              f"~{eff}s, not every {args.interval}s")
    else:
        print(f"[lines] all {len(contracts)} symbols fit in one batch")

    writer = Writer(out)
    print(f"[out] {out.resolve()}  (append mode, flushed per row)")
    for line in session_banner(datetime.now(timezone.utc), args.minutes)[0]:
        print(line)
    print(f"[run] interval {args.interval}s, duration "
          f"{'until Ctrl-C' if args.minutes <= 0 else str(args.minutes) + ' min'}")
    print("[run] Ctrl-C to stop\n")

    signal.signal(signal.SIGINT, _sigint)

    if args.wait_for_open:
        wait = seconds_until_open(datetime.now(timezone.utc))
        if wait <= 0:
            print("[wait] regular hours are already open; collecting now")
        else:
            print(f"[wait] sleeping {wait/3600:.2f} h until the next 09:30 ET open "
                  f"(Ctrl-C to abort)")
            waited = 0.0
            while waited < wait and not _stop:
                chunk = min(60.0, wait - waited)
                time.sleep(chunk)
                waited += chunk
                left = (wait - waited) / 60.0
                if int(waited) % 900 < 60:            # a line every ~15 min
                    print(f"[wait] {left:6.1f} min until the open", flush=True)
            if _stop:
                writer.close()
                ib.disconnect()
                print("[wait] aborted before the open; nothing collected")
                return 0
            print("[wait] open reached; collecting")

    # the clock starts when collection does, not when the process did
    started = time.time()
    deadline = started + args.minutes * 60 if args.minutes > 0 else None
    subscribed: list = []
    tick = 0
    md_seen: dict[int, int] = {}
    outages = Outages()
    down_since: datetime | None = None
    skipped_ticks = 0

    try:
        if not rotating:
            subscribed = [ib.reqMktData(c, "", False, False) for c in groups[0]]
            ib.sleep(args.settle)

        while not _stop:
            if deadline and time.time() > deadline:
                print("[run] duration reached")
                break

            # THE GUARD. A dropped socket does not clear the ticker objects --
            # they keep their last bid and ask forever. Writing those with a
            # fresh timestamp records a stale quote as a live one, which is
            # indistinguishable from real data afterwards. So: write nothing
            # while down, and account for the hole.
            if not ib.isConnected():
                if down_since is None:
                    down_since = datetime.now(timezone.utc)
                    print(f"\n  *** DISCONNECTED at {down_since:%H:%M:%S}Z. "
                          "Writing nothing until the socket is back. ***")
                    print("  *** Most likely IB Gateway's daily restart. "
                          "Configure -> Settings -> Lock and Exit. ***")
                subscribed = []
                try:
                    ib.connect(args.host, args.port,
                               clientId=args.client_id, timeout=15)
                except Exception as e:                   # noqa: BLE001
                    print(f"  [reconnect] failed ({type(e).__name__}); "
                          f"retrying in {args.interval:.0f}s", flush=True)
                    skipped_ticks += 1
                    time.sleep(max(5.0, args.interval))
                    continue
                back = datetime.now(timezone.utc)
                outages.record(down_since, back)
                print(f"  *** RECONNECTED at {back:%H:%M:%S}Z after "
                      f"{(back - down_since).total_seconds()/60:.1f} min ***\n")
                down_since = None
                ib.reqMarketDataType(1)
                if not rotating:
                    subscribed = [ib.reqMktData(c, "", False, False)
                                  for c in groups[0]]
                    ib.sleep(args.settle)

            gi = tick % len(groups)
            if rotating:
                for t in subscribed:
                    ib.cancelMktData(t.contract)
                subscribed = [ib.reqMktData(c, "", False, False) for c in groups[gi]]
                ib.sleep(args.settle)

            if not ib.isConnected():        # dropped during the settle above
                skipped_ticks += 1
                continue

            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            wrote = 0
            for t in subscribed:
                mdt = getattr(t, "marketDataType", None)
                mdt = int(mdt) if mdt is not None else ""
                if isinstance(mdt, int):
                    md_seen[mdt] = md_seen.get(mdt, 0) + 1
                writer.write_row({
                    "ts_utc": ts,
                    "symbol": t.contract.symbol,
                    "bid": _num(t.bid),
                    "ask": _num(t.ask),
                    "bid_size": _num(t.bidSize),
                    "ask_size": _num(t.askSize),
                    "last": _num(t.last),
                    "volume": _num(t.volume),
                    "md_type": mdt,
                    "batch": gi,
                })
                wrote += 1

            tick += 1
            mins = (time.time() - started) / 60.0
            print(f"[tick {tick:>5}] {ts}  batch {gi}  rows {wrote:>3}  "
                  f"total {writer.n:>7}  elapsed {mins:6.1f} min", flush=True)

            if tick == 1 and md_seen and set(md_seen) != {1}:
                print("\n  *** WARNING: market data type is not 1 (live). ***")
                print(f"  *** seen: {md_seen}  "
                      "(1=live 2=frozen 3=delayed 4=delayed-frozen) ***")
                print("  *** Delayed quotes still populate bid and ask, and would "
                      "produce a\n      spread distribution that is precise and "
                      "measures nothing.")
                print("  *** Most likely cause: the market data subscription sits "
                      "on the live\n      account and is not shared to paper. "
                      "spread_report.py will refuse\n      to pool these rows.\n")

            ib.sleep(max(0.0, args.interval - (args.settle if rotating else 0)))

    finally:
        for t in subscribed:
            try:
                ib.cancelMktData(t.contract)
            except Exception:                        # noqa: BLE001
                pass
        writer.close()
        ib.disconnect()
        if down_since is not None:                   # still down when we stopped
            outages.record(down_since, datetime.now(timezone.utc))
        mins = (time.time() - started) / 60.0
        print(f"\n[done] {writer.n} rows over {tick} ticks, {mins:.1f} min")
        print(f"[done] {out.resolve()}")
        print(f"[done] market data types seen: {md_seen or 'none'}")
        for line in outages.summary():
            print(line)
        if skipped_ticks:
            print(f"[done] {skipped_ticks} tick(s) skipped while disconnected")
        side = out.with_suffix(out.suffix + ".outages.txt")
        side.write_text("\n".join(outages.summary()) + "\n", encoding="utf-8")
        print(f"[done] outage log: {side.resolve()}")
        print("\nNext:  python -m strategy.swing.spread_report " + str(out))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Record real IBKR bid/ask for a swing candidate universe")
    ap.add_argument("--universe", default=None,
                    help="text file of symbols, one or comma-separated per line "
                         "(default: the 36 pre-flight names + SPY)")
    ap.add_argument("--out", default="var/reports/spread_samples.csv")
    ap.add_argument("--interval", type=float, default=30.0,
                    help="seconds between samples (default 30)")
    ap.add_argument("--minutes", type=float, default=0,
                    help="stop after N minutes; 0 = run until Ctrl-C (default)")
    ap.add_argument("--lines", type=int, default=45,
                    help="max simultaneous market data lines (default 45)")
    ap.add_argument("--settle", type=float, default=3.0,
                    help="seconds to wait after subscribing before reading "
                         "(default 3)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=4002,
                    help="4002 IB Gateway paper (default) or 7497 TWS paper. "
                         "Live ports are refused by name.")
    ap.add_argument("--client-id", type=int, default=71)
    ap.add_argument("--wait-for-open", action="store_true",
                    help="sleep until the next 09:30 ET open before collecting, "
                         "so --minutes counts from the open rather than from "
                         "whenever the command was typed. Holidays are not "
                         "modelled.")
    ap.add_argument("--self-test", action="store_true",
                    help="run the offline checks and exit; no IB connection")
    a = ap.parse_args(argv)

    if a.self_test:
        return self_test()
    return run(a)


if __name__ == "__main__":
    raise SystemExit(main())
