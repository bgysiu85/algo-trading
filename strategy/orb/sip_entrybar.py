#!/usr/bin/env python3
r"""Did the stop trade before or after the entry, inside the entry minute?

    python -m strategy.orb.sip_entrybar pairs     # the symbol-days to price
    python -m strategy.orb.sip_entrybar resolve --jobs 8

THE QUESTION, AND WHY IT IS THE ONLY ONE LEFT
----------------------------------------------
`orb_sip_RESULT_20260918.md`: the strategy reads -0.350R a trade if the
protective stop can be hit during the minute the position was opened in, and
+0.055R if it cannot. 39.9% of top-20 trades are in that state, and those
trades average -1.35R under the pessimistic reading. A one-minute bar records
a low and a high but not their order, so the backtest has to assume one.

One-second bars remove the assumption. Inside the entry minute they say, for
each trade, whether the stop price traded BEFORE the entry trigger (in which
case no position existed yet and the stop could not have fired) or AFTER it
(in which case it did).

RESOLVED, TRADE BY TRADE -- not a third global assumption. Each of these
symbol-days gets its own answer and the ledger is re-read with it.

WHAT THIS CANNOT DO
-------------------
It cannot make the strategy pass. The optimistic reading already fails
criterion 2 (bootstrap 0.834 against a 0.95 bar) and criterion 7, and this
study changes neither. It decides which figure is the honest one to record,
and it is registered as amendment E before the data is bought.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from strategy.orb import sip as S
from strategy.orb import sip_report as P

TRADES_DEFAULT = Path("var/cache/orb_sip/trades")
PAIRS_DEFAULT = Path("var/state/orb_sip_entrybar_pairs.json")
OUT_DEFAULT = Path("var/cache/orb_sip/entrybar_resolved.csv.gz")
DATASET = "XNAS.ITCH"
SCHEMA = "ohlcv-1s"
RANGE_MINUTES = 5
TOP_N = 20

BEFORE = "stop_first"      # the low preceded the entry: no position yet
AFTER = "entry_first"      # the entry preceded the low: the stop fired
SAME = "same_second"       # both inside one second: unresolved, counted
NO_DATA = "no_seconds"


def entry_bar_stops(ledger: pd.DataFrame) -> pd.DataFrame:
    """The top-20 trades whose stop was touched in the entry minute."""
    d = ledger[(ledger["range"] == RANGE_MINUTES) & (ledger["rank"].le(TOP_N))]
    return d[(d["exit_reason"] == "stop") & (d["exit_min"] == d["entry_min"])]


def write_pairs(rows: pd.DataFrame, out: Path) -> int:
    pairs = (rows[["symbol", "date"]].drop_duplicates()
             .sort_values(["date", "symbol"]).to_dict("records"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(pairs, indent=1), encoding="utf-8")
    return len(pairs)


def classify(sec: pd.DataFrame, side: int, trigger: float, stop_frac_r: float):
    """One trade, one entry minute of 1-second bars.

    Returns (verdict, entry_px, exit_px_or_None). The entry fills at the first
    second that reaches the trigger, gapping through if that second opened
    beyond it -- the same fill model as the minute engine, one resolution
    down. The stop is then placed off that fill and only seconds AT OR AFTER
    the entry second can hit it.
    """
    if sec.empty:
        return NO_DATA, float("nan"), None
    o = sec["open"].to_numpy(float); h = sec["high"].to_numpy(float)
    l = sec["low"].to_numpy(float)
    reach = (h >= trigger) if side == S.LONG else (l <= trigger)
    if not reach.any():
        return NO_DATA, float("nan"), None
    i = int(np.argmax(reach))
    entry_px = max(trigger, o[i]) if side == S.LONG else min(trigger, o[i])
    stop_px = entry_px - side * stop_frac_r

    before = ((l[:i] <= stop_px) if side == S.LONG else (h[:i] >= stop_px))
    hit = ((l[i:] <= stop_px) if side == S.LONG else (h[i:] >= stop_px))
    if hit.any():
        j = i + int(np.argmax(hit))
        exit_px = (min(stop_px, o[j]) if side == S.LONG and j > i
                   else max(stop_px, o[j]) if side == S.SHORT and j > i
                   else stop_px)
        verdict = SAME if j == i else AFTER
        return verdict, entry_px, float(exit_px)
    return (BEFORE if before.any() else BEFORE), entry_px, None


def _one(args):
    archive, day, rows_json = args
    from common.dbn_io import read_dbn
    rows = pd.read_json(rows_json, orient="records")
    src = Path(archive) / DATASET / SCHEMA / f"{day}.dbn.zst"
    if not src.exists():
        return [(r.symbol, day, NO_DATA, np.nan, np.nan) for r in rows.itertuples()]
    bars = read_dbn(src)
    et = bars.index.tz_convert("America/New_York")
    minute = (et.hour * 60 + et.minute).to_numpy()
    out = []
    for r in rows.itertuples():
        m = (bars["symbol"].to_numpy() == r.symbol) & (minute == r.entry_min)
        verdict, entry_px, exit_px = classify(
            bars[m][["open", "high", "low", "close"]], int(r.side),
            r.or_high if r.side == S.LONG else r.or_low, float(r.r))
        out.append((r.symbol, day, verdict, entry_px,
                    np.nan if exit_px is None else exit_px))
    return out


def resolve(ledger: pd.DataFrame, archive: Path, jobs: int, tmp: Path) -> pd.DataFrame:
    rows = entry_bar_stops(ledger)
    tmp.mkdir(parents=True, exist_ok=True)
    work = []
    for day, g in rows.groupby("date", sort=True):
        f = tmp / f"{day}.json"
        g[["symbol", "side", "entry_min", "or_high", "or_low", "r"]].to_json(
            f, orient="records")
        work.append((str(archive), day, str(f)))
    if jobs > 1:
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            parts = list(ex.map(_one, work))
    else:
        parts = [_one(w) for w in work]
    flat = [x for part in parts for x in part]
    return pd.DataFrame(flat, columns=["symbol", "date", "verdict",
                                       "sec_entry_px", "sec_exit_px"])


def counts(res: pd.DataFrame) -> dict:
    n = len(res)
    c = res["verdict"].value_counts().to_dict()
    return {"trades": n,
            "entry_first": c.get(AFTER, 0),
            "stop_first": c.get(BEFORE, 0),
            "same_second": c.get(SAME, 0),
            "no_seconds": c.get(NO_DATA, 0),
            "share_entry_first": c.get(AFTER, 0) / n if n else 0.0}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("action", choices=("pairs", "resolve"))
    p.add_argument("--trades", default=str(TRADES_DEFAULT))
    p.add_argument("--pairs", default=str(PAIRS_DEFAULT))
    p.add_argument("--archive", default=None)
    p.add_argument("--out", default=str(OUT_DEFAULT))
    p.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    a = p.parse_args(argv)

    ledger = P.load_ledger(Path(a.trades))
    rows = entry_bar_stops(ledger)
    if a.action == "pairs":
        n = write_pairs(rows, Path(a.pairs))
        print(f"{len(rows):,} entry-minute stops in the top-{TOP_N} "
              f"{RANGE_MINUTES}-minute arm")
        print(f"{n:,} distinct symbol-days -> {a.pairs}")
        print("Price them (spends nothing):")
        print(f"  python -m common.databento_fetch --pairs {a.pairs} "
              f"--dataset {DATASET} --schemas {SCHEMA} --lookback 0 "
              "--max-cost 0.01 --report var\\reports\\price_1s_orb.txt")
        return 0

    if a.archive:
        archive = Path(a.archive)
    else:
        from common.databento_fetch import default_archive
        archive = default_archive()
    res = resolve(ledger, archive, a.jobs, Path(a.out).parent / "_entrybar")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    res.to_csv(a.out, index=False, encoding="utf-8", compression="gzip")
    c = counts(res)
    print(f"resolved {c['trades']:,} entry-minute stops")
    for k in ("entry_first", "stop_first", "same_second", "no_seconds"):
        print(f"  {k:<14} {c[k]:>7,}  {c[k]/max(c['trades'],1):6.1%}")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
