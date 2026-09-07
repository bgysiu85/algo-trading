#!/usr/bin/env python3
"""
Databento connectivity, entitlement and COST probe.

    .\\.venv\\Scripts\\python.exe db_check.py                 # free: auth + catalogue
    .\\.venv\\Scripts\\python.exe db_check.py --quote PPBT 2026-09-02
    .\\.venv\\Scripts\\python.exe db_check.py --pull  PPBT 2026-09-02

Everything except --pull is free. get_cost() and get_record_count() are
metadata calls: they price a query without buying it. Nothing here spends
credit unless you pass --pull, and --pull refuses to run without showing you
the cost and getting a yes.

Reads DATABENTO_API_KEY through secrets_util (see that file for why
credentials resolve once at startup and never again).
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from common.databento_fetch import require_databento

db = require_databento()

from common import secrets_util as S

ET = ZoneInfo("America/New_York")
KEY_VAR = "DATABENTO_API_KEY"

# The pre-market window MCL actually trades. Everything here is scoped to it,
# because that is where the coverage question lives -- a dataset can look
# complete at 10:00 and be threadbare at 05:00.
SESSION_START = "04:00"
SESSION_END = "09:30"

# Candidates, cheapest first. Which of these you are entitled to is exactly
# what this script is here to discover.
CANDIDATES = ["EQUS.MINI", "EQUS.SUMMARY", "EQUS.BASIC", "EQUS.PLUS",
              "EQUS.ALL", "EQUS.MAX", "XNAS.ITCH", "XNYS.PILLAR", "IEXG.TOPS"]


def et_window(date_str: str) -> tuple[datetime, datetime]:
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    sh, sm = map(int, SESSION_START.split(":"))
    eh, em = map(int, SESSION_END.split(":"))
    return (datetime(d.year, d.month, d.day, sh, sm, tzinfo=ET),
            datetime(d.year, d.month, d.day, eh, em, tzinfo=ET))


def catalogue(client) -> list[str]:
    print("=" * 70)
    print("  ENTITLEMENTS")
    print("=" * 70)
    try:
        available = client.metadata.list_datasets()
    except Exception as e:  # noqa: BLE001
        sys.exit(f"could not list datasets -- is the API key valid?\n  {e}")

    equity = [d for d in available if d.split(".")[0] in
              ("EQUS", "XNAS", "XNYS", "IEXG", "ARCX", "BATS", "DBEQ")]
    print(f"  {len(available)} datasets visible, {len(equity)} US-equity relevant\n")
    for name in CANDIDATES:
        mark = "yes" if name in available else " - "
        print(f"    [{mark}] {name}")
    extra = sorted(set(equity) - set(CANDIDATES))
    for name in extra:
        print(f"    [yes] {name}   (not in candidate list)")
    return [d for d in equity if d in available]


def describe(client, dataset: str) -> None:
    print(f"\n  --- {dataset} ---")
    try:
        schemas = client.metadata.list_schemas(dataset)
        print(f"    schemas : {', '.join(schemas)}")
    except Exception as e:  # noqa: BLE001
        print(f"    schemas : unavailable ({type(e).__name__})")
        return
    try:
        rng = client.metadata.get_dataset_range(dataset)
        print(f"    history : {rng.get('start', '?')}  ..  {rng.get('end', '?')}")
    except Exception as e:  # noqa: BLE001
        print(f"    history : unavailable ({type(e).__name__})")

    # Does it carry what MCL needs?
    need = {"trades": "raw prints (build your own bars)",
            "ohlcv-1m": "ready-made 1-minute bars",
            "tbbo": "BBO at each trade -- fill realism",
            "mbp-1": "full top-of-book",
            "bbo-1s": "sampled top-of-book",
            "definition": "symbology / tick size"}
    have = set(schemas)
    for s, why in need.items():
        print(f"      [{'x' if s in have else ' '}] {s:11} {why}")


def price_query(client, dataset: str, symbol: str, date_str: str,
                schema: str) -> tuple[float, int]:
    """Cost in USD and record count for one symbol over one pre-market window."""
    start, end = et_window(date_str)
    cost = client.metadata.get_cost(
        dataset=dataset, start=start, end=end, symbols=[symbol], schema=schema)
    count = client.metadata.get_record_count(
        dataset=dataset, start=start, end=end, symbols=[symbol], schema=schema)
    return float(cost), int(count)


def quote(client, datasets: list[str], symbol: str, date_str: str) -> None:
    print("\n" + "=" * 70)
    print(f"  COST TO PULL {symbol} on {date_str}, {SESSION_START}-{SESSION_END} ET")
    print("=" * 70)
    print("  (metadata only -- this costs nothing)\n")
    print(f"  {'dataset':<14} {'schema':<11} {'records':>9}  {'USD':>10}")
    print("  " + "-" * 48)
    for ds in datasets:
        try:
            schemas = set(client.metadata.list_schemas(ds))
        except Exception:  # noqa: BLE001
            continue
        for sc in ("trades", "ohlcv-1m", "tbbo"):
            if sc not in schemas:
                continue
            try:
                cost, count = price_query(client, ds, symbol, date_str, sc)
            except Exception as e:  # noqa: BLE001
                print(f"  {ds:<14} {sc:<11} {'-':>9}  {type(e).__name__}")
                continue
            zero = "   <- NO DATA" if count == 0 else ""
            print(f"  {ds:<14} {sc:<11} {count:>9,}  {cost:>10.4f}{zero}")
    print("\n  A record count of 0 in the pre-market window means that dataset")
    print("  does not see this name before 09:30 -- which is disqualifying")
    print("  for MCL no matter how cheap it is.")


def pull(client, dataset: str, symbol: str, date_str: str, schema: str,
         out_dir: Path, assume_yes: bool) -> int:
    start, end = et_window(date_str)
    cost, count = price_query(client, dataset, symbol, date_str, schema)
    print(f"\n  {dataset} {schema} {symbol} {date_str}")
    print(f"  {count:,} records, ${cost:.4f}")
    if count == 0:
        print("  nothing to download.")
        return 1
    if not assume_yes:
        if input("  proceed? [y/N] ").strip().lower() not in ("y", "yes"):
            print("  cancelled.")
            return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"db_{dataset.replace('.', '')}_{symbol}_{date_str}_{schema}.dbn.zst"
    client.timeseries.get_range(
        dataset=dataset, start=start, end=end, symbols=[symbol],
        schema=schema, stype_in="raw_symbol", path=str(out))
    print(f"  written to {out.name}  ({out.stat().st_size:,} bytes)")
    print(f"  next:  python db_bars.py {out.name}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Databento connectivity and cost probe")
    ap.add_argument("--quote", nargs=2, metavar=("SYMBOL", "DATE"),
                    help="price a pre-market pull across every entitled dataset")
    ap.add_argument("--pull", nargs=2, metavar=("SYMBOL", "DATE"),
                    help="actually download (asks first)")
    ap.add_argument("--dataset", default="EQUS.MINI", help="dataset for --pull")
    ap.add_argument("--schema", default="trades", help="schema for --pull")
    ap.add_argument("--out-dir", default="var/databento")
    ap.add_argument("--yes", action="store_true", help="skip the cost confirmation")
    a = ap.parse_args()

    S.preload({KEY_VAR: "Databento API key"})
    print(S.report())
    print()

    client = db.Historical(key=S.get(KEY_VAR))
    entitled = catalogue(client)
    for ds in entitled[:6]:
        describe(client, ds)

    if a.quote:
        quote(client, entitled, a.quote[0].upper(), a.quote[1])
    if a.pull:
        return pull(client, a.dataset, a.pull[0].upper(), a.pull[1],
                    a.schema, Path(a.out_dir), a.yes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
