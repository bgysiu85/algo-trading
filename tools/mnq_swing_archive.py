#!/usr/bin/env python3
"""MNQ swing size from the owned NQ 1-minute archive (no IBKR, no spend, no orders).
NQ and MNQ move the same index points; MNQ = $2/point.

  Set-Location D:\\Trading
  .\\.venv\\Scripts\\python.exe tools\\mnq_swing_archive.py

Takes the last 30 calendar days present in the file, rebuilds 30-min and 1-hour bars (UTC clock
boundaries, all hours), ranks bars by high-low range, and reports the top 15 of each.
"""
import os
import pandas as pd
from common.dbn_io import read_dbn
from common.tsmom_fetch import default_archive
from common.tsmom_data_price import DATASET
from strategy.w16.fetch import ARCHIVE_SUBDIR

OUT = os.environ.get("W15_OUT", r"D:\Trading\Claude outputs")
PT, TOP = 2.0, 15
path = default_archive() / DATASET / ARCHIVE_SUBDIR / "ohlcv-1m" / "NQ.dbn.zst"
m = read_dbn(path)
m = m[["open", "high", "low", "close"]].astype(float).sort_index()
end = m.index.max()
m = m[m.index > end - pd.Timedelta(days=30)]
# continuous-contract roll guard: a 1-minute close-to-open jump over 150 points is a roll seam, not a move
seam = (m.open - m.close.shift()).abs() > 150
money = lambda x: f"${x:,.0f}"
lines = [f"MNQ swing study from NQ 1m archive - data {m.index.min():%Y-%m-%d %H:%M} to {end:%Y-%m-%d %H:%M} UTC "
         f"- $2/point - roll seams flagged: {int(seam.sum())}"]
if (pd.Timestamp.now(tz='UTC') - end).days > 5:
    lines.append(f"NOTE: archive ends {end:%Y-%m-%d}; this is the latest month IT holds, not the past month.")
for label, rule in (("30 min", "30min"), ("1 hour", "1h")):
    d = m.resample(rule).agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    s = seam.resample(rule).max().reindex(d.index).fillna(False)
    d = d[~s]
    d["range"] = d.high - d.low
    top = d.nlargest(TOP, "range")
    lines += ["", f"=== {label} bars: {len(d)} bars ===",
              f"All bars : mean range {d.range.mean():.1f} pts ({money(d.range.mean()*PT)}), median {d.range.median():.1f}",
              f"Top {TOP}   : mean range {top.range.mean():.1f} pts ({money(top.range.mean()*PT)}), "
              f"min {top.range.min():.1f}, max {top.range.max():.1f} pts ({money(top.range.max()*PT)})",
              f"Top {TOP} mean |open->close| : {(top.close-top.open).abs().mean():.1f} pts",
              "", "  bar start (UTC)          range pts   $/contract   open->close"]
    for t, r in top.iterrows():
        lines.append(f"  {t:%Y-%m-%d %H:%M}        {r.range:>9.1f}{money(r.range*PT):>13}{r.close-r.open:>+13.1f}")
txt = "\n".join(lines)
print(txt)
os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, "mnq_swing_30d.txt"), "w", encoding="utf-8") as f:
    f.write(txt + "\n")
print("\nSaved:", os.path.join(OUT, "mnq_swing_30d.txt"))
