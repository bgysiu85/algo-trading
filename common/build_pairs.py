#!/usr/bin/env python3
"""
Build traded_pairs.json from broker exports.

    python build_pairs.py --ibkr "FY26 IBKR.csv" --tradezero "FY26 TradeZero.csv"

TIMEZONE — the thing that matters here
--------------------------------------
IBKR's Flex export writes DateTime in the LOCAL TIME OF THE ACCOUNT, which for
this account is Australia/Sydney. Treating those as US Eastern is wrong twice:

  * the hours are meaningless (fills appear at 18:00-02:00)
  * ~11% of fills fall on the PREVIOUS Eastern date, because Sydney 00:00-02:59
    is the previous day 09:00-11:59 in New York

Converting properly puts 98% of fills inside 04:00-09:29 ET, which is exactly
the strategy's pre-market window. Before conversion, 30% of the symbol/date
pairs were wrong (76 on the wrong session, 52 sessions missed entirely).

TradeZero is a US broker and its Exec Time is already Eastern, so its T/D is
used as-is.

DST is handled by zoneinfo: the Sydney/New York offset varies between 14 and 16
hours across the year, so a fixed offset would reintroduce the same class of bug.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

SYDNEY = ZoneInfo("Australia/Sydney")
EASTERN = ZoneInfo("America/New_York")


def ibkr_pairs(path: Path, account_tz: ZoneInfo) -> tuple[set, int]:
    df = pd.read_csv(path)
    has_time = df["DateTime"].astype(str).str.contains(";")
    dropped = int((~has_time).sum())
    df = df[has_time].copy()

    def to_eastern(s: str) -> datetime:
        d, t = s.split(";")
        naive = datetime.strptime(d + t, "%Y-%m-%d%H%M%S")
        return naive.replace(tzinfo=account_tz).astimezone(EASTERN)

    et = df["DateTime"].astype(str).map(to_eastern)
    return set(zip(df["Symbol"].astype(str).str.upper(),
                   et.dt.strftime("%Y-%m-%d"))), dropped


def tradezero_pairs(path: Path) -> set:
    df = pd.read_csv(path)
    d = pd.to_datetime(df["T/D"], format="%m/%d/%Y").dt.strftime("%Y-%m-%d")
    return set(zip(df["Symbol"].astype(str).str.upper(), d))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ibkr", type=Path)
    ap.add_argument("--tradezero", type=Path)
    ap.add_argument("--out", type=Path, default=Path("traded_pairs.json"))
    ap.add_argument("--ibkr-tz", default="Australia/Sydney",
                    help="timezone IBKR wrote its DateTime in (default Sydney)")
    a = ap.parse_args()

    pairs: set = set()
    if a.ibkr and a.ibkr.exists():
        p, dropped = ibkr_pairs(a.ibkr, ZoneInfo(a.ibkr_tz))
        print(f"IBKR       {len(p):>4} pairs   ({dropped} rows had no time component)")
        pairs |= p
    if a.tradezero and a.tradezero.exists():
        p = tradezero_pairs(a.tradezero)
        print(f"TradeZero  {len(p):>4} pairs   (already Eastern)")
        pairs |= p

    # US equities only: drop forex (AUD.USD) and anything non-alphabetic
    clean = sorted(x for x in pairs if x[0].isalpha() and "." not in x[0])
    print(f"dropped {len(pairs) - len(clean)} non-equity symbols")

    a.out.write_text(json.dumps(
        [{"symbol": s, "date": d} for s, d in clean], indent=0))
    print(f"\nwrote {len(clean)} pairs to {a.out}")
    by_year = collections.Counter(d[:4] for _, d in clean)
    print("by year:", dict(sorted(by_year.items())))
    print("range  :", min(d for _, d in clean), "..", max(d for _, d in clean))
    return 0


if __name__ == "__main__":
    sys.exit(main())
