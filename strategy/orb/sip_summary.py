#!/usr/bin/env python3
r"""One row per symbol-day: everything `REGISTERED_orb_sip.md` needs to choose.

    python -m strategy.orb.sip_summary --jobs 8
    python -m strategy.orb.sip_summary --start 2024-07-01 --end 2024-07-31

WHY A SUMMARY PASS AT ALL
-------------------------
The archive holds 555 whole-market RTH days, ~2.07M minute bars each, 34 GB.
Every decision the strategy makes before it trades -- the $5 open, the 14-day
average volume, ATR(14), the opening-range relative volume -- is a function of
a handful of numbers per symbol-day. Computing them once and writing them to a
small table means the universe, the ranking and every control are built from a
file that fits in memory, and the 34 GB is read exactly twice: here, and again
for the sessions that actually trade.

WHAT IS AND IS NOT IN A ROW
---------------------------
Opening-range figures are computed for BOTH registered lengths (5 primary, 15
secondary) in the same pass, because reading the archive twice to add a column
is how a "quick second look" turns into a different sample.

`ts_event` is the interval START (common/dbn_io.py), so the 5-minute opening
range is the bars stamped 09:30..09:34 inclusive and 09:35 is already outside
it. Getting this wrong shifts the range by a minute and the entry with it.

NO BAR EXISTS FOR A MINUTE WITH NO TRADE. A symbol that traded 40 minutes of
the session has 40 rows, not 390 with gaps. So `rth_bars` is a coverage
measure, `first_bar`/`last_bar` say where the session really started and
ended for that name, and `max_gap_min` is the halt proxy the registration
promised to count (section 3.6) rather than assume away.
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

ET = "America/New_York"
RTH_OPEN_MIN = 9 * 60 + 30
RTH_CLOSE_MIN = 16 * 60
WINDOW = "0930_1600"
OUT_DEFAULT = Path("var/cache/orb_sip/summary")
COLUMNS = ["symbol", "date", "open", "rth_high", "rth_low", "rth_close",
           "rth_volume", "rth_bars", "first_bar", "last_bar", "max_gap_min",
           "or5_open", "or5_high", "or5_low", "or5_close", "or5_volume",
           "or15_open", "or15_high", "or15_low", "or15_close", "or15_volume"]


def day_file(archive: Path, dataset: str, day: str) -> Path:
    return archive / dataset / "ohlcv-1m" / f"{day}_{WINDOW}.dbn.zst"


def sessions(archive: Path, dataset: str) -> list[str]:
    d = archive / dataset / "ohlcv-1m"
    return sorted(p.name[:10] for p in d.glob(f"*_{WINDOW}.dbn.zst"))


def summarise(df: pd.DataFrame, day: str) -> pd.DataFrame:
    """Per-symbol rows for one session's RTH minute bars.

    The frame is indexed on ts_event in UTC and carries open/high/low/close/
    volume/symbol, which is what `common.dbn_io.read_dbn` returns.
    """
    if df.empty:
        return pd.DataFrame(columns=COLUMNS)
    et = df.index.tz_convert(ET)
    minute = et.hour * 60 + et.minute
    keep = (et.strftime("%Y-%m-%d") == day) & (minute >= RTH_OPEN_MIN) & (minute < RTH_CLOSE_MIN)
    df = df[keep]
    if df.empty:
        return pd.DataFrame(columns=COLUMNS)
    minute = minute[keep]
    work = pd.DataFrame({
        "symbol": df["symbol"].to_numpy(),
        "minute": np.asarray(minute),
        "open": df["open"].to_numpy(float),
        "high": df["high"].to_numpy(float),
        "low": df["low"].to_numpy(float),
        "close": df["close"].to_numpy(float),
        "volume": df["volume"].to_numpy(float),
    }).sort_values(["symbol", "minute"], kind="stable")

    g = work.groupby("symbol", sort=True)
    out = pd.DataFrame({
        "open": g["open"].first(),
        "rth_high": g["high"].max(),
        "rth_low": g["low"].min(),
        "rth_close": g["close"].last(),
        "rth_volume": g["volume"].sum(),
        "rth_bars": g["close"].size(),
        "first_bar": g["minute"].first(),
        "last_bar": g["minute"].last(),
        # The largest run of consecutive traded-minute gaps, in minutes. A
        # halt shows up here; so does a name that simply does not trade every
        # minute, which is why the report states the share rather than
        # filtering on it.
        "max_gap_min": g["minute"].apply(lambda m: int(np.diff(m.to_numpy()).max() - 1)
                                         if len(m) > 1 else 0),
    })
    for n in (5, 15):
        w = work[work["minute"] < RTH_OPEN_MIN + n]
        gw = w.groupby("symbol", sort=True)
        part = pd.DataFrame({
            f"or{n}_open": gw["open"].first(),
            f"or{n}_high": gw["high"].max(),
            f"or{n}_low": gw["low"].min(),
            f"or{n}_close": gw["close"].last(),
            f"or{n}_volume": gw["volume"].sum(),
        })
        out = out.join(part, how="left")
    out = out.reset_index().rename(columns={"index": "symbol"})
    out.insert(1, "date", day)
    return out[COLUMNS]


def _one(args) -> tuple[str, int, str]:
    archive, dataset, day, out_dir = args
    from common.dbn_io import read_dbn
    dst = Path(out_dir) / f"{day}.csv.gz"
    src = day_file(Path(archive), dataset, day)
    try:
        rows = summarise(read_dbn(src), day)
    except Exception as e:  # noqa: BLE001 -- one bad file must not stop 555
        return day, 0, f"{type(e).__name__}: {e}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    rows.to_csv(dst, index=False, encoding="utf-8", compression="gzip")
    return day, len(rows), ""


def build(archive: Path, dataset: str, days: list[str], out_dir: Path,
          jobs: int, force: bool) -> dict:
    todo = [d for d in days if force or not (out_dir / f"{d}.csv.gz").exists()]
    stats = {"sessions": len(days), "already": len(days) - len(todo),
             "written": 0, "rows": 0, "failed": []}
    work = [(str(archive), dataset, d, str(out_dir)) for d in todo]
    t0 = time.perf_counter()
    if jobs > 1 and work:
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            results = list(ex.map(_one, work))
    else:
        results = [_one(w) for w in work]
    for i, (day, n, err) in enumerate(results, 1):
        if err:
            stats["failed"].append((day, err))
            continue
        stats["written"] += 1
        stats["rows"] += n
        if i % 25 == 0:
            el = time.perf_counter() - t0
            print(f"  {i}/{len(work)}  {el/60:.1f} min elapsed, "
                  f"~{el/i*(len(work)-i)/60:.1f} min left", flush=True)
    return stats


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default="XNAS.BASIC")
    p.add_argument("--out", default=str(OUT_DEFAULT))
    p.add_argument("--start")
    p.add_argument("--end")
    p.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    p.add_argument("--force", action="store_true",
                   help="rewrite sessions whose summary already exists")
    a = p.parse_args(argv)

    if a.archive:
        archive = Path(a.archive)
    else:
        from common.databento_fetch import default_archive
        archive = default_archive()
    days = sessions(archive, a.dataset)
    if a.start:
        days = [d for d in days if d >= a.start]
    if a.end:
        days = [d for d in days if d <= a.end]
    if not days:
        sys.exit(f"no {WINDOW} files under {archive/a.dataset}/ohlcv-1m")

    print(f"{len(days)} session(s) {days[0]} -> {days[-1]}, {a.jobs} job(s)")
    st = build(archive, a.dataset, days, Path(a.out), a.jobs, a.force)
    print(f"sessions {st['sessions']:,}  already on disk {st['already']:,}  "
          f"written {st['written']:,}  rows {st['rows']:,}")
    for day, err in st["failed"]:
        print(f"  FAILED {day}  {err}")
    return 1 if st["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
