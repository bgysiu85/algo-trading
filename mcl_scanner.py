#!/usr/bin/env python3
"""
MCL scanner -- feeds watchlist.txt from IB's market scanner.

    .\\.venv\\Scripts\\python.exe mcl_scanner.py --preview   # show, write nothing
    .\\.venv\\Scripts\\python.exe mcl_scanner.py             # run and keep it fresh

Runs alongside mcl_paper_trader.py on its own client id. Places no orders.
The trader re-reads watchlist.txt every 5 seconds, so anything written here is
picked up without a restart.

SELECTION IS STICKY
-------------------
Once a symbol qualifies it stays on the list for the rest of the session. The
strategy's premise is "today's movers", not "this minute's movers" -- a name that
qualifies at 04:05 and would trigger an entry at 04:20 must not vanish at 04:10
because it slipped to third place. --no-sticky turns this off.

The trader handles removal safely anyway: a retired symbol stops taking NEW
entries but an open position is still managed through to its exit.

SCAN CONFIG IS PROVISIONAL
--------------------------
SCAN_CODE and the filters below are a best guess until scan_params.py has been
run against your Gateway. IB's available scan codes and filter tags depend on
your own market-data subscriptions. Run scan_params.py first and adjust.

FLOAT FILTERING - CORRECTED 2026-09-04
--------------------------------------
An earlier version of this file claimed IB has no float filter. That was wrong.
scanner_parameters.xml declares floatSharesAbove and floatSharesBelow, so the
float < 20m criterion CAN be pushed into the scan itself rather than applied by
hand afterwards. Both are wired below.

Also confirmed present: changePercAbove/Below, volumeAbove, avgVolumeAbove,
marketCapAbove1e6/Below1e6, haltedIs. 527 scan codes in total, and
STK.US.MAJOR, STK.US.MINOR, STK.NASDAQ.SCM (Nasdaq Small Cap Market) are all
valid locations.

STILL UNVERIFIED: whether TOP_PERC_GAIN computes anything before 09:30. IB's
percent-gain scans are defined against the previous close, which should work in
the pre-market, but this has never actually been run against a live Gateway.
--preview is how to find out, and it writes nothing.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from ib_async import IB, ScannerSubscription, TagValue
except ImportError:
    sys.exit("ib_async not installed.  Run:  pip install ib_async")

ET = ZoneInfo("America/New_York")

PAPER_PORTS = {4002: "IB Gateway paper", 7497: "TWS paper"}
LIVE_PORTS = {4001: "IB Gateway LIVE", 7496: "TWS LIVE"}
HOST = "127.0.0.1"
CLIENT_ID = 55                      # trader uses 17, viewer 77, params dump 88

# ---- the screen ----------------------------------------------------------
SCAN_CODE = "TOP_PERC_GAIN"         # verified present in scanner_parameters.xml
# STK.US.MAJOR excludes OTC/pink. STK.NASDAQ.SCM (Nasdaq Small Cap Market) is
# narrower and closer to the strategy's universe -- worth comparing with
# --preview before committing to either.
LOCATION = "STK.US.MAJOR"
PRICE_MIN, PRICE_MAX = 2.0, 20.0
MIN_VOLUME = 100_000                # previous-day volume floor, a coarse cut

# Pushed into the scan as TagValues. All three tag names verified against
# scanner_parameters.xml -- an unknown tag makes IB reject the WHOLE scan
# rather than ignore that one filter, so they are not guesses.
FLOAT_MAX = 20_000_000              # floatSharesBelow -- the < 20m criterion
CHANGE_PERC_MIN = 5.0               # floor on the move; the scan ranks, this cuts
USE_FLOAT_FILTER = True             # set False if your data subscription lacks it
TOP_N = 3                           # how many of the scan's top names to take
MAX_ROWS = 50                       # IB's hard cap per scan

# Sticky selection accumulates all session, so the list only grows. The trader
# fetches bars once per minute per symbol and IB refuses beyond 60 history
# requests per 10 minutes ACROSS ALL CONTRACTS -- so the watchlist has to be
# capped or it will quietly break the strategy it is feeding.
MAX_WATCHLIST = 6

LOG = logging.getLogger("scanner")

HEADER = """\
# MCL watchlist -- WRITTEN BY mcl_scanner.py. Hand edits will be overwritten.
# Pin names that must always be included in watchlist_pinned.txt instead.
#
# Screen: ${PRICE_MIN}-${PRICE_MAX} price, top-{TOP_N} gainer, scan {SCAN_CODE}
# Selection is sticky: once a name qualifies it stays for the session.
"""


def read_pinned(path: Path) -> list[str]:
    """One symbol per line; blank lines and comments ignored, INCLUDING trailing
    ones -- watchlist_blocked.txt stores `JLHL  # reason`, so a parser that keeps
    the comment silently fails to match the symbol."""
    if not path.exists():
        return []
    out = []
    for ln in path.read_text().splitlines():
        s = ln.split("#", 1)[0].strip().upper()
        if s and s not in out:
            out.append(s)
    return out


def render(selected: dict[str, str], pinned: list[str], top_n: int = TOP_N) -> str:
    """selected: symbol -> the ET timestamp and reason it was added."""
    lines = [
        "# MCL watchlist -- WRITTEN BY mcl_scanner.py.",
        "# Hand edits are overwritten; pin names in watchlist_pinned.txt instead.",
        "#",
        f"# Screen: ${PRICE_MIN:.0f}-${PRICE_MAX:.0f}, top-{top_n} by {SCAN_CODE}",
        "# Selection is sticky: a name that qualifies stays for the session.",
        f"# Last refreshed {datetime.now(ET):%Y-%m-%d %H:%M:%S} ET",
        "",
    ]
    if pinned:
        lines.append("# --- pinned ---")
        lines += pinned
        lines.append("")
    if selected:
        lines.append("# --- from scanner ---")
        for sym, why in selected.items():
            lines.append(f"{sym}  # {why}")
    else:
        lines.append("# (scanner has returned no qualifying names yet)")
    lines.append("")
    return "\n".join(lines)


async def scan_once(ib: IB) -> list[str]:
    sub = ScannerSubscription(
        instrument="STK",
        locationCode=LOCATION,
        scanCode=SCAN_CODE,
        abovePrice=PRICE_MIN,
        belowPrice=PRICE_MAX,
        aboveVolume=MIN_VOLUME,
        numberOfRows=MAX_ROWS,
    )
    # Filters IB cannot express in the subscription fields go here as tags.
    # Every name below appears in scanner_parameters.xml. An unknown tag makes
    # IB reject the WHOLE scan rather than ignore that filter, which is why
    # the float filter is behind a switch: if your market-data subscription
    # does not carry float data the scan fails outright, and turning it off is
    # the difference between a working scan and no watchlist at all.
    tags = [TagValue("changePercAbove", str(CHANGE_PERC_MIN))]
    if USE_FLOAT_FILTER:
        tags.append(TagValue("floatSharesBelow", str(FLOAT_MAX)))
    LOG.info("scan %s @ %s  price %.2f-%.2f  vol>%s  tags=%s",
             SCAN_CODE, LOCATION, PRICE_MIN, PRICE_MAX, f"{MIN_VOLUME:,}",
             {t.tag: t.value for t in tags})
    try:
        rows = await ib.reqScannerDataAsync(sub, [], tags)
    except Exception as e:  # noqa: BLE001
        LOG.error("scan failed: %s", e)
        LOG.error("  >> If this mentions an unknown tag or scan code, run "
                  "scan_params.py and correct SCAN_CODE / tags.")
        if USE_FLOAT_FILTER and tags:
            LOG.warning("  >> retrying once WITHOUT the float filter, in case "
                        "your data subscription does not carry float data")
            try:
                rows = await ib.reqScannerDataAsync(
                    sub, [], [TagValue("changePercAbove", str(CHANGE_PERC_MIN))])
                LOG.warning("  >> that worked. Set USE_FLOAT_FILTER = False and "
                            "apply the float cut yourself.")
                return [r.contractDetails.contract.symbol for r in rows]
            except Exception as e2:  # noqa: BLE001
                LOG.error("  >> still failed without it: %s", e2)
        return []

    syms = []
    for r in rows:
        c = getattr(r, "contractDetails", None)
        c = getattr(c, "contract", None) if c else None
        if c is not None and c.symbol and c.symbol not in syms:
            syms.append(c.symbol)
    return syms


async def main_async(args) -> int:
    if args.port in LIVE_PORTS:
        print(f"REFUSING: port {args.port} is {LIVE_PORTS[args.port]}.")
        return 1
    if args.port not in PAPER_PORTS:
        print(f"REFUSING: port {args.port} is not a known paper port.")
        return 1

    wl = Path(args.watchlist)
    pinned_path = wl.with_name("watchlist_pinned.txt")

    ib = IB()
    try:
        await ib.connectAsync(HOST, args.port, clientId=CLIENT_ID, timeout=10)
    except Exception as e:  # noqa: BLE001
        print(f"Could not connect to {HOST}:{args.port} -- {type(e).__name__}: {e}")
        return 1
    LOG.info("connected on %d (%s), accounts %s",
             args.port, PAPER_PORTS[args.port], ib.managedAccounts())

    selected: dict[str, str] = {}
    try:
        while True:
            found = await scan_once(ib)
            top = found[:args.top]
            now = f"{datetime.now(ET):%H:%M:%S} ET"

            if not args.sticky:
                selected = {}

            pinned = read_pinned(pinned_path)
            # Names IB refuses to open a position in -- the trader writes these
            # after a rejection. Re-adding one just burns signals again.
            blocked = set(read_pinned(wl.with_name("watchlist_blocked.txt")))
            budget = max(0, args.max_symbols - len(pinned))

            added, skipped = [], []
            for rank, sym in enumerate(top, 1):
                if sym in selected or sym in pinned:
                    continue
                if sym in blocked:
                    LOG.info("skipping %s -- on watchlist_blocked.txt", sym)
                    continue
                if len(selected) >= budget:
                    skipped.append(sym)
                    continue
                selected[sym] = f"added {now}, rank {rank} of {SCAN_CODE}"
                added.append(sym)

            if skipped:
                LOG.warning("watchlist full at %d (%d pinned) -- not adding %s. "
                            "Raise --max-symbols only if you accept the risk of "
                            "IB throttling bar requests.",
                            args.max_symbols, len(pinned), ", ".join(skipped))

            if found:
                LOG.info("scan returned %d, top %d: %s%s", len(found), args.top,
                         ", ".join(top) or "(none)",
                         f"  NEW: {', '.join(added)}" if added else "")
            else:
                LOG.warning("scan returned nothing -- check SCAN_CODE and whether "
                            "this scan works pre-market")

            text = render(selected, pinned, args.top)
            if args.preview:
                print("\n" + "-" * 60)
                print(text.rstrip())
                print("-" * 60)
                print("(preview -- nothing written)")
                break
            if not wl.exists() or wl.read_text() != text:
                wl.write_text(text)
                LOG.info("wrote %s (%d symbols)", wl, len(selected))

            await asyncio.sleep(args.interval)
    except (KeyboardInterrupt, asyncio.CancelledError):
        LOG.info("stopping")
    finally:
        ib.disconnect()
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Feed watchlist.txt from IB's scanner")
    p.add_argument("--watchlist", default="watchlist.txt")
    p.add_argument("--port", type=int, default=4002)
    p.add_argument("--interval", type=int, default=60,
                   help="seconds between scans (default 60)")
    p.add_argument("--top", type=int, default=TOP_N,
                   help=f"take the top N names from each scan (default {TOP_N})")
    p.add_argument("--max-symbols", type=int, default=MAX_WATCHLIST,
                   help=f"cap on the total watchlist (default {MAX_WATCHLIST}). "
                        "Sticky selection only grows, and the trader's bar "
                        "requests hit IB's pacing limit beyond ~6 symbols.")
    p.add_argument("--preview", action="store_true",
                   help="scan once, print what would be written, write nothing")
    p.add_argument("--no-sticky", dest="sticky", action="store_false",
                   help="let names drop off when they leave the top N "
                        "(default is to keep them for the session)")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s",
                        datefmt="%H:%M:%S")
    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
