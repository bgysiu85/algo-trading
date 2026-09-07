#!/usr/bin/env python3
"""Dollar volume per symbol-day, for the compounding simulation's liquidity cap.

    python -m common.day_dollar_volume --pairs var/state/flex_pairs_all.json \
        --out var/reports/day_dollar_volume.csv

WHY IT NEEDS ITS OWN MODULE
----------------------------
common/compound_sim.py caps a position at a share of the day's dollar volume,
and without that cap a compounding account grows into share counts these $2-20
names could never have printed. But the simulator reads trade CSVs and knows
nothing about market volume, and common/screen.py's feature table is over a
gigabyte. So this extracts the one column that is needed, for the few hundred
symbol-days that are wanted, and writes a small file.

CONSOLIDATED, NOT EQUS.MINI
----------------------------
EQUS.SUMMARY by default. Measured in claude/consolidated_volume_gap.md:
EQUS.MINI sees a MEDIAN 4.7% of the consolidated tape, and the shortfall varies
several-fold between symbols. Capping a position at 1% of EQUS.MINI's volume
would therefore cap it at roughly 0.05% of the real tape, on a factor that
changes per name -- a liquidity limit that is wrong by an unknown multiple is
worse than none, because it looks like a measurement.

close x volume, not a VWAP. The daily bar carries no volume-weighted price, and
a session's close is within a few percent of its VWAP on names that move enough
to be screened. The cap is a coarse instrument -- 1% of a day's turnover -- and
does not deserve a precision the input cannot support.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from common.databento_fetch import default_archive


def wanted(paths) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for p in paths:
        for row in json.load(open(p)):
            out.add((row["symbol"], row["date"]))
    return out


def build(archive: Path, dataset: str, keys: set) -> list[dict]:
    from common.dbn_io import daily_frame

    df = daily_frame(archive, dataset)
    if df.empty:
        sys.exit(f"no ohlcv-1d bars under {archive}/{dataset}/")
    df = df[["symbol", "date", "close", "volume"]].copy()
    df["dollar_volume"] = df["close"] * df["volume"]
    want = {(s, d) for s, d in keys}
    hit = df[[(s, d) in want for s, d in zip(df["symbol"], df["date"])]]
    return [{"symbol": r.symbol, "date": r.date,
             "close": round(float(r.close), 4),
             "volume": int(r.volume),
             "dollar_volume": round(float(r.dollar_volume), 2)}
            for r in hit.itertuples()]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Dollar volume per symbol-day")
    ap.add_argument("--pairs", nargs="+", required=True)
    ap.add_argument("--archive", default=str(default_archive()))
    ap.add_argument("--dataset", default="EQUS.SUMMARY",
                    help="consolidated by default -- EQUS.MINI sees a median "
                         "4.7%% of the tape and would cap at a wrong multiple")
    ap.add_argument("--out", default="var/reports/day_dollar_volume.csv")
    a = ap.parse_args(argv)

    keys = wanted(a.pairs)
    rows = build(Path(a.archive), a.dataset, keys)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["symbol", "date", "close", "volume",
                                           "dollar_volume"])
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["symbol"], r["date"])))

    missing = len(keys) - len(rows)
    print(f"wrote {a.out}  ({len(rows):,} of {len(keys):,} symbol-days)")
    if missing:
        # NOT silently zero. compound_sim treats an absent figure as "no cap
        # known" and leaves the position uncapped, which is the conservative
        # direction for a liquidity limit -- but the count has to be visible or
        # a mostly-empty file reads as a mostly-uncapped run for no stated
        # reason.
        print(f"MISSING: {missing:,} symbol-day(s) have no daily bar in "
              f"{a.dataset}. Those positions run UNCAPPED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
