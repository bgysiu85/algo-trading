#!/usr/bin/env python3
r"""G1 (W05-0003, `docs/research/REGISTERED_10sec.md`) — the symbol-days the
10-second engine needs, whole day, and the price of pulling them.

    python -m strategy.orb.tensec_pairs pairs

WHAT THIS IS, AND WHY IT IS NOT `sip_entrybar.py --action pairs`
------------------------------------------------------------------
`orb_sip_entrybar_pairs.json` (already on disk, 2,888 symbol-days) covers only
the ENTRY MINUTE of the 39.9% of top-20 trades whose stop was touched inside
it (amendment E). REGISTERED_10sec.md's B0/T1/T2 engine runs on 1-second bars
for the WHOLE SESSION, every symbol-day of the primary cell — the confirmation
trigger can fire any time from 09:35 to 15:59, not just in the entry minute.
So this writes a new, wider pair list and the two are UNIONed by
`common.databento_fetch` automatically (it takes `--pairs` twice); nothing
already captured for the entry-minute study is re-bought.

Primary cell, unchanged from `docs/research/REGISTERED_orb_sip.md` section 2:
5-minute opening range, top 20 by RVOL, outside the locked holdout
(2026-05-01 on) — the same 7,239 trades / 446 sessions / 1,990 symbols
REGISTERED_10sec.md section 2 cites. `sip_report.load_ledger` already drops
the holdout by default; nothing here reads it.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from strategy.orb import sip_report as P

TRADES_DEFAULT = Path("var/cache/orb_sip/trades")
PAIRS_DEFAULT = Path("var/state/orb_tensec_pairs.json")
ENTRYBAR_PAIRS = Path("var/state/orb_sip_entrybar_pairs.json")
DATASET = "XNAS.ITCH"
SCHEMA = "ohlcv-1s"
RANGE_MINUTES = 5
TOP_N = 20


def primary_cell(ledger: pd.DataFrame) -> pd.DataFrame:
    return ledger[(ledger["range"] == RANGE_MINUTES) & (ledger["rank"].le(TOP_N))]


def write_pairs(rows: pd.DataFrame, out: Path) -> int:
    pairs = (rows[["symbol", "date"]].drop_duplicates()
             .sort_values(["date", "symbol"]).to_dict("records"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(pairs, indent=1), encoding="utf-8")
    return len(pairs)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("action", choices=("pairs",))
    p.add_argument("--trades", default=str(TRADES_DEFAULT))
    p.add_argument("--out", default=str(PAIRS_DEFAULT))
    a = p.parse_args(argv)

    ledger = P.load_ledger(Path(a.trades))
    cell = primary_cell(ledger)
    all_days = cell[["symbol", "date"]].drop_duplicates()
    n = write_pairs(all_days, Path(a.out))

    print(f"primary cell: {len(cell):,} trades, {cell['date'].nunique():,} "
          f"sessions, {cell['symbol'].nunique():,} symbols")
    print(f"{n:,} distinct symbol-days (whole day) -> {a.out}")
    if ENTRYBAR_PAIRS.exists():
        have = {(r["symbol"], r["date"])
                for r in json.loads(ENTRYBAR_PAIRS.read_text(encoding="utf-8"))}
        need = set(map(tuple, all_days.itertuples(index=False, name=None)))
        print(f"{len(have & need):,} already captured for the entry-minute "
              f"study ({ENTRYBAR_PAIRS}); {len(need - have):,} net-new")
    print("\nPrice it (spends nothing without --confirm):")
    print(f"  python -m common.databento_fetch --pairs {a.out} "
          f"--dataset {DATASET} --schemas {SCHEMA} --lookback 0 "
          f"--max-cost 1.00 --report var\\reports\\price_1s_10sec.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
