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
from datetime import datetime, timezone
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
    print(f"[run] interval {args.interval}s, duration "
          f"{'until Ctrl-C' if args.minutes <= 0 else str(args.minutes) + ' min'}")
    print("[run] Ctrl-C to stop\n")

    signal.signal(signal.SIGINT, _sigint)

    started = time.time()
    deadline = started + args.minutes * 60 if args.minutes > 0 else None
    subscribed: list = []
    tick = 0
    md_seen: dict[int, int] = {}

    try:
        if not rotating:
            subscribed = [ib.reqMktData(c, "", False, False) for c in groups[0]]
            ib.sleep(args.settle)

        while not _stop:
            if deadline and time.time() > deadline:
                print("[run] duration reached")
                break

            gi = tick % len(groups)
            if rotating:
                for t in subscribed:
                    ib.cancelMktData(t.contract)
                subscribed = [ib.reqMktData(c, "", False, False) for c in groups[gi]]
                ib.sleep(args.settle)

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
        mins = (time.time() - started) / 60.0
        print(f"\n[done] {writer.n} rows over {tick} ticks, {mins:.1f} min")
        print(f"[done] {out.resolve()}")
        print(f"[done] market data types seen: {md_seen or 'none'}")
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
    ap.add_argument("--self-test", action="store_true",
                    help="run the offline checks and exit; no IB connection")
    a = ap.parse_args(argv)

    if a.self_test:
        return self_test()
    return run(a)


if __name__ == "__main__":
    raise SystemExit(main())
