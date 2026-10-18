#!/usr/bin/env python3
"""MNQ swing size: top-15 biggest 30-min and 1-hour bars over the past ~30 days.
Read-only (history only, no orders). Needs IB Gateway/TWS paper running.

  Set-Location D:\\Trading
  .\\.venv\\Scripts\\python.exe tools\\mnq_swing.py

A 'swing' = one bar's full range (high minus low), in index points. MNQ = $2 per point.
Bars are the continuous front-month contract, all hours (RTH + overnight).
"""
import os
import sys
import pandas as pd
from ib_async import IB, ContFuture

OUT = os.environ.get("W15_OUT", r"D:\Trading\Claude outputs")
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4002   # 4002 Gateway paper; use 7497 for TWS paper
PT = 2.0   # MNQ $ per point
TOP = 15


def money(x):
    return f"${x:,.0f}"


ib = IB()
ib.connect("127.0.0.1", PORT, clientId=77, timeout=20)
c = ib.qualifyContracts(ContFuture("MNQ", "CME"))[0]
lines = [f"MNQ swing study - generated {pd.Timestamp.now().date()} - contract {c.localSymbol or 'MNQ cont'} - $2/point"]
for label, size in (("30 min", "30 mins"), ("1 hour", "1 hour")):
    bars = ib.reqHistoricalData(c, endDateTime="", durationStr="30 D", barSizeSetting=size,
                                whatToShow="TRADES", useRTH=False, formatDate=2)
    d = pd.DataFrame([{"t": b.date, "o": b.open, "h": b.high, "l": b.low, "c": b.close} for b in bars])
    d["range"] = d.h - d.l
    top = d.nlargest(TOP, "range")
    lines += ["", f"=== {label} bars: {len(d)} bars, {d.t.min()} to {d.t.max()} ===",
              f"All bars   : mean range {d.range.mean():.1f} pts ({money(d.range.mean()*PT)}), median {d.range.median():.1f}",
              f"Top {TOP}    : mean range {top.range.mean():.1f} pts ({money(top.range.mean()*PT)}), "
              f"min {top.range.min():.1f}, max {top.range.max():.1f} pts ({money(top.range.max()*PT)})",
              f"Top {TOP} mean move open->close (absolute): {(top.c-top.o).abs().mean():.1f} pts",
              "", "  bar start (UTC)          range pts   $/contract   open->close"]
    for r in top.sort_values("range", ascending=False).itertuples():
        lines.append(f"  {str(r.t):<24}{r.range:>9.1f}{money(r.range*PT):>13}{r.c-r.o:>+13.1f}")
ib.disconnect()
txt = "\n".join(lines)
print(txt)
os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, "mnq_swing_30d.txt"), "w", encoding="utf-8") as f:
    f.write(txt + "\n")
print("\nSaved:", os.path.join(OUT, "mnq_swing_30d.txt"))
