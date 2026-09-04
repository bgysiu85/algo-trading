#!/usr/bin/env python3
"""
Dump what YOUR IB Gateway's market scanner can actually do.

    .\.venv\Scripts\python.exe scan_params.py

Scan codes and filter tags depend on your own market-data subscriptions, so the
only reliable answer comes from your Gateway. Reads only — places no orders,
requests no market data. Safe to run while the trader is going (own client id).

Writes the full parameter XML to scanner_parameters.xml (it is several MB) and
prints the parts relevant to the MCL screen:
    $2-20 price · RVOL >= 5x · float < 20m · top-2 pre-market gainer
"""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    from ib_async import IB
except ImportError:
    sys.exit("ib_async not installed.  Run:  pip install ib_async")

PAPER_PORTS = {4002: "IB Gateway paper", 7497: "TWS paper"}
LIVE_PORTS = {4001: "IB Gateway LIVE", 7496: "TWS LIVE"}
HOST, CLIENT_ID = "127.0.0.1", 88

OUT = Path("scanner_parameters.xml")

# What we care about for this strategy
CODE_HINTS = ("GAIN", "LOSE", "VOLUME", "ACTIVE", "HOT", "PREMARKET", "PRE_MARKET",
              "OPEN_GAP", "GAP", "RANGE")
FILTER_HINTS = ("price", "volume", "float", "changeperc", "marketcap", "shares",
                "outstanding", "gap", "trades")


def main() -> int:
    for port in (4002, 7497):
        ib = IB()
        try:
            print(f"connecting {HOST}:{port} ({PAPER_PORTS[port]}) ...",
                  end=" ", flush=True)
            ib.connect(HOST, port, clientId=CLIENT_ID, timeout=8)
            print("OK")
            break
        except Exception as e:  # noqa: BLE001
            print(f"no ({type(e).__name__})")
            ib = None
    else:
        print("\nCould not connect on either paper port. Is Gateway running?")
        print(f"(ports {sorted(LIVE_PORTS)} are LIVE and are not tried)")
        return 1

    print("requesting scanner parameters (this can take ~10s and is several MB)...")
    xml = ib.reqScannerParameters()
    OUT.write_text(xml, encoding="utf-8")
    print(f"saved {len(xml):,} bytes to {OUT.resolve()}\n")

    root = ET.fromstring(xml)

    # ---- scan codes ------------------------------------------------------
    codes = sorted({el.findtext("scanCode") or "" for el in root.iter("ScanType")}
                   - {""})
    print(f"=== {len(codes)} scan codes available ===")
    hits = [c for c in codes if any(h in c.upper() for h in CODE_HINTS)]
    print(f"--- {len(hits)} relevant to gainers / volume / gaps ---")
    for c in hits:
        print(f"  {c}")

    # explicit check for anything pre-market aware
    pre = [c for c in codes if "PRE" in c.upper() or "OPEN" in c.upper()]
    print(f"\n--- pre-market / open related ({len(pre)}) ---")
    print("  " + ("\n  ".join(pre) if pre else
                  "(none — scanner is likely regular-hours only)"))

    # ---- filter tags -----------------------------------------------------
    tags = sorted({el.findtext("AbstractField/code") or el.findtext("code") or ""
                   for el in root.iter("RangeFilter")} - {""})
    if not tags:  # schema varies by version; fall back to a broad sweep
        tags = sorted({t.text for t in root.iter("code") if t.text})

    print(f"\n=== {len(tags)} filter tags available ===")
    rel = [t for t in tags if any(h in t.lower() for h in FILTER_HINTS)]
    print(f"--- {len(rel)} relevant to price / volume / float / market cap ---")
    for t in rel:
        print(f"  {t}")

    # ---- the specific questions -----------------------------------------
    print("\n=== verdict for the MCL screen ===")
    def has(word):
        return [t for t in tags if word in t.lower()]

    for label, word in (("float", "float"),
                        ("shares outstanding", "outstanding"),
                        ("price", "price"),
                        ("volume", "volume"),
                        ("change %", "changeperc"),
                        ("market cap", "marketcap")):
        found = has(word)
        mark = "YES" if found else "NO "
        print(f"  [{mark}] {label:20s} {', '.join(found[:6]) if found else '—'}")

    print("\nFull XML saved for reference. Send it back if you want the exact")
    print("ScannerSubscription built for the $2-20 / RVOL / gainer screen.")

    ib.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
