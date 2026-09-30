#!/usr/bin/env python3
"""CHARTMARK-v1 G6: seen-window parity. Counts only, no P&L. The engine runs on the TradingView CL1! 1H bars Ben marked
(w15_0032_cl1_1h_bars_indicators.csv) and its entries are set beside Ben's 14 marked entry lines and the entry levels he
stated in his fire notes. Reported as-is; 'seen -- not evidence'."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from strategy.chartmark import engine as E
from strategy.chartmark import spec as S
from strategy.chartmark.data import indicators, load_seen_frame

OUT = Path(r"D:\Trading\Claude outputs")
# (fire bar NY, level Ben stated) from his notes in the "Candidate fires" sheet
STATED = [("2025-09-10 11:00", 63.50), ("2025-10-27 10:00", 61.65), ("2025-11-04 11:00", 60.65),
          ("2025-11-06 04:00", 60.00), ("2026-01-09 09:00", 58.53)]


def ben_marks(xlsx) -> list[tuple[str, pd.Timestamp, float]]:
    import openpyxl
    ws = openpyxl.load_workbook(xlsx, data_only=True)["Your 14 marks"]
    out = []
    for r in ws.iter_rows(min_row=2, values_only=True):
        if r[0]:
            out.append((r[0], pd.Timestamp(r[1].split(" ", 1)[1]), float(r[2])))
    return out


def run(csv, xlsx, log=print) -> str:
    fr = load_seen_frame(csv)
    ind = indicators(fr)
    trades, cnt = E.simulate(fr, ind, S.BASE)
    ny = fr.ny.tz_localize(None)
    ent = [(ny[t.entry_j], t.entry_px, t.entry_j) for t in trades]
    lines = [f"CHARTMARK-v1 G6 seen-window parity (TradingView CL1! bars, seen -- not evidence). Engine BASE fills: {len(trades)}, "
             f"orders {cnt['orders']}. Counts only, no P&L.", "", "Ben's 14 marked entries (bar within 1 bar, price within 2 ticks):"]
    hit = 0
    for name, when, line in ben_marks(xlsx):
        best = min(ent, key=lambda e: abs((e[0] - when) / pd.Timedelta(hours=1))) if ent else None
        if best is None:
            lines.append(f"  {name} {when}: no engine entries"); continue
        db = (best[0] - when) / pd.Timedelta(hours=1)
        dp = (best[1] - line) / S.TICK
        ok = abs(db) <= 1 and abs(dp) <= 2
        hit += ok
        lines.append(f"  {name:4s} Ben {when:%a %d %b %H:%M} @ {line:7.2f} | nearest engine entry {best[0]:%d %b %H:%M} @ {best[1]:7.2f} "
                     f"({db:+.0f} bars, {dp:+.0f} ticks) {'MATCH' if ok else '-'}")
    lines.append(f"  matched within 1 bar and 2 ticks: {hit} of 14")
    lines += ["", "Levels Ben stated in his notes (engine entry within 2 bars of the fire bar, price within 2 ticks):"]
    h2 = 0
    for when, level in STATED:
        w = pd.Timestamp(when)
        near = [e for e in ent if abs((e[0] - w) / pd.Timedelta(hours=1)) <= 2]
        if near:
            b = min(near, key=lambda e: abs(e[1] - level))
            dp = (b[1] - level) / S.TICK
            ok = abs(dp) <= 2
            h2 += ok
            lines.append(f"  {when} stated {level:.2f} | engine {b[0]:%d %b %H:%M} @ {b[1]:.2f} ({dp:+.0f} ticks) {'MATCH' if ok else '-'}")
        else:
            lines.append(f"  {when} stated {level:.2f} | no engine entry within 2 bars")
    lines.append(f"  matched: {h2} of {len(STATED)}")
    txt = "\n".join(lines) + "\n"
    log(txt)
    return txt


if __name__ == "__main__":
    run(OUT / "w15_0032_cl1_1h_bars_indicators.csv", OUT / "w15_0032_candidate_fires_review.xlsx")
