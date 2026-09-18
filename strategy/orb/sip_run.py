#!/usr/bin/env python3
r"""Every qualifying symbol-day, traded once per registered range length.

    python -m strategy.orb.sip_run --jobs 8
    python -m strategy.orb.sip_run --start 2024-07-01 --end 2026-04-30

WHAT THIS PRODUCES, AND WHY IT IS A LEDGER RATHER THAN A RESULT
---------------------------------------------------------------
One row per (symbol-day, range length) that produced a trade, carrying the
trade, its RVOL rank, and the alternative reading of amendment A. Nothing is
aggregated, nothing is selected, no friction is applied and no arm exists here.

That is deliberate. `REGISTERED_orb_sip.md` section 4 requires the top-20 arm,
the unfiltered arm, top-10 and top-40, a 2,000-draw random-20 control and
three friction levels. Every one of those is a SELECTION over the same trades,
so computing the trades once and selecting afterwards means the arms cannot
silently differ by anything except their selection -- and the random control
draws from exactly the population the real ranking drew from.

THE UNFILTERED ARM IS WHY EVERY QUALIFYING NAME IS TRADED. The paper's own
base case (no RVOL rank, Sharpe 0.48 against 2.81) is the control that says
whether the selection rule transferred, so ~1,263 names a session are
simulated, not 20.

TWO TAPES (amendment B): bars come from XNAS.ITCH, which agrees with the
consolidated daily high and low to the cent; the ranking in the universe table
came from XNAS.BASIC's volume. A run whose price dataset is not the registered
one is refused unless --anyway, and then the ledger says so in its provenance.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from strategy.orb import sip as S
from strategy.orb.sip_summary import day_file

UNIVERSE_DEFAULT = Path("var/state/orb_sip_universe.csv.gz")
OUT_DEFAULT = Path("var/cache/orb_sip/trades")
PRICE_DATASET = "XNAS.ITCH"
RANGES = (5, 15)
HOLDOUT_FROM = "2026-05-01"          # section 4, locked

UNIVERSE_COLS = ["symbol", "date", "open", "atr14", "advol14", "rvol5", "rank5",
                 "eligible5", "rvol15", "rank15", "eligible15", "qualifies"]
LEDGER_COLS = [
    "date", "symbol", "range", "side", "rvol", "rank", "eligible", "atr",
    "entry_min", "entry_px", "exit_min", "exit_px", "exit_reason", "r",
    "bars_held", "gapped_entry", "or_high", "or_low",
    # amendment A's other reading, on the same entry
    "alt_exit_min", "alt_exit_px", "alt_exit_reason",
]


def load_universe(path: Path, start: str | None, end: str | None) -> pd.DataFrame:
    df = pd.read_csv(path, usecols=UNIVERSE_COLS, encoding="utf-8")
    df = df[df["qualifies"].astype(bool)]
    if start:
        df = df[df["date"] >= start]
    if end:
        df = df[df["date"] <= end]
    return df


def trade_session(bars: pd.DataFrame, univ: pd.DataFrame, day: str) -> tuple[list, dict]:
    """Every qualifying name on one session, both range lengths.

    `bars` is that session's RTH minute frame (UTC index, symbol column);
    `univ` is the session's qualifying rows from the universe table.
    """
    et = bars.index.tz_convert("America/New_York")
    work = pd.DataFrame({
        "symbol": bars["symbol"].to_numpy(),
        "minute": (et.hour * 60 + et.minute).to_numpy(),
        "open": bars["open"].to_numpy(float),
        "high": bars["high"].to_numpy(float),
        "low": bars["low"].to_numpy(float),
        "close": bars["close"].to_numpy(float),
    }).sort_values(["symbol", "minute"], kind="stable")
    want = set(univ["symbol"])
    work = work[work["symbol"].isin(want)]
    groups = {s: g for s, g in work.groupby("symbol", sort=False)}

    rows, status = [], {}
    for u in univ.itertuples(index=False):
        g = groups.get(u.symbol)
        if g is None:
            status["NO_BARS"] = status.get("NO_BARS", 0) + 1
            continue
        minute = g["minute"].to_numpy()
        o, h, l, c = (g[k].to_numpy() for k in ("open", "high", "low", "close"))
        for n in RANGES:
            t, why = S.trade_symbol_day(u.symbol, day, minute, o, h, l, c,
                                        u.atr14, n)
            key = f"{n}:{why}"
            status[key] = status.get(key, 0) + 1
            if t is None:
                continue
            alt, _ = S.trade_symbol_day(u.symbol, day, minute, o, h, l, c,
                                        u.atr14, n, stop_on_entry_bar=False)
            rvol = u.rvol5 if n == 5 else u.rvol15
            rank = u.rank5 if n == 5 else u.rank15
            elig = u.eligible5 if n == 5 else u.eligible15
            trigger = t.or_high if t.side == S.LONG else t.or_low
            rows.append((
                day, u.symbol, n, t.side, rvol, rank, bool(elig), u.atr14,
                t.entry_min, t.entry_px, t.exit_min, t.exit_px, t.exit_reason,
                t.r, t.bars_held, bool(abs(t.entry_px - trigger) > 1e-9),
                t.or_high, t.or_low,
                alt.exit_min, alt.exit_px, alt.exit_reason,
            ))
    return rows, status


def _one(args):
    archive, dataset, day, univ_pickle, out_dir = args
    from common.dbn_io import read_dbn
    univ = pd.read_pickle(univ_pickle) if isinstance(univ_pickle, str) else univ_pickle
    univ = univ[univ["date"] == day]
    dst = Path(out_dir) / f"{day}.csv.gz"
    try:
        bars = read_dbn(day_file(Path(archive), dataset, day))
        rows, status = trade_session(bars, univ, day)
    except Exception as e:  # noqa: BLE001
        return day, 0, {}, f"{type(e).__name__}: {e}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=LEDGER_COLS).to_csv(
        dst, index=False, encoding="utf-8", compression="gzip")
    return day, len(rows), status, ""


def build(archive: Path, dataset: str, univ: pd.DataFrame, out_dir: Path,
          jobs: int, force: bool, tmp: Path) -> dict:
    days = sorted(univ["date"].unique())
    todo = [d for d in days if force or not (out_dir / f"{d}.csv.gz").exists()]
    stats = {"sessions": len(days), "already": len(days) - len(todo),
             "trades": 0, "status": {}, "failed": []}
    if not todo:
        return stats
    tmp.parent.mkdir(parents=True, exist_ok=True)
    univ[univ["date"].isin(todo)].to_pickle(tmp)
    work = [(str(archive), dataset, d, str(tmp), str(out_dir)) for d in todo]
    t0 = time.perf_counter()
    if jobs > 1:
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            results = ex.map(_one, work)
            done = []
            for i, r in enumerate(results, 1):
                done.append(r)
                if i % 25 == 0:
                    el = time.perf_counter() - t0
                    print(f"  {i}/{len(work)}  {el/60:.1f} min elapsed, "
                          f"~{el/i*(len(work)-i)/60:.1f} min left", flush=True)
    else:
        done = [_one(w) for w in work]
    for day, n, status, err in done:
        if err:
            stats["failed"].append((day, err))
            continue
        stats["trades"] += n
        for k, v in status.items():
            stats["status"][k] = stats["status"].get(k, 0) + v
    return stats


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default=PRICE_DATASET,
                   help="PRICE dataset (amendment B: %(default)s)")
    p.add_argument("--universe", default=str(UNIVERSE_DEFAULT))
    p.add_argument("--out", default=str(OUT_DEFAULT))
    p.add_argument("--start")
    p.add_argument("--end")
    p.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    p.add_argument("--force", action="store_true")
    p.add_argument("--spend-holdout", action="store_true",
                   help="include sessions from " + HOLDOUT_FROM +
                        " (section 4: locked, spent once, only after a pass)")
    p.add_argument("--anyway", action="store_true",
                   help="run on a price dataset other than the registered one")
    a = p.parse_args(argv)

    if a.dataset != PRICE_DATASET and not a.anyway:
        sys.exit(f"REFUSING TO RUN: prices are registered on {PRICE_DATASET} "
                 f"(amendment B) and this run asked for {a.dataset}.\n"
                 "XNAS.BASIC's RTH minute bars carry off-exchange prints that "
                 "are not the session's range:\n"
                 "AAPL 2024-09-12 printed a 209.27 low against a true 219.82, "
                 "and 11.3% of liquid names\n"
                 "that session had a low more than 0.5% below consolidated. "
                 "Pass --anyway to run regardless.")

    if a.archive:
        archive = Path(a.archive)
    else:
        from common.databento_fetch import default_archive
        archive = default_archive()

    univ = load_universe(Path(a.universe), a.start, a.end)
    if not a.spend_holdout:
        before = univ["date"].nunique()
        univ = univ[univ["date"] < HOLDOUT_FROM]
        print(f"holdout: {before - univ['date'].nunique()} session(s) from "
              f"{HOLDOUT_FROM} withheld (section 4)")
    if univ.empty:
        sys.exit("no qualifying symbol-days in that range")

    print(f"{univ['date'].nunique()} session(s), "
          f"{len(univ):,} qualifying symbol-days, {len(RANGES)} range lengths, "
          f"{a.jobs} job(s)")
    st = build(archive, a.dataset, univ, Path(a.out), a.jobs, a.force,
               Path(a.out).parent / "_universe.pkl")
    print(f"sessions {st['sessions']:,}  already on disk {st['already']:,}  "
          f"trades written {st['trades']:,}")
    for k in sorted(st["status"]):
        print(f"  {k:<22} {st['status'][k]:,}")
    for day, err in st["failed"]:
        print(f"  FAILED {day}  {err}")
    return 1 if st["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
