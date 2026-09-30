#!/usr/bin/env python3
"""CHARTMARK-S v1 G6: seen-window parity, counts only, no P&L. The engine runs on the TradingView CL1! 1H bars Ben marked
(w15_0032_cl1_1h_bars_indicators.csv, 2025-09-08 -> 2026-09-29) and must reproduce the registered reference:
651 trades, first fill 2025-09-10 16:00 at 63.73, exits P0 542 / P1 108 / backstop 1, and the five listed trades.
Ben's 15 short entries are then set beside the engine's (entry within 1 bar). Seen -- not evidence."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import pandas as pd

from strategy.chartmark_s import engine as E
from strategy.chartmark_s import spec as S
from strategy.chartmark_s.data import indicators, load_seen_frame

import os
OUT = Path(os.environ.get("CHARTMARK_OUT", r"D:\Trading\Claude outputs"))
REF_N, REF_EXITS = 651, {"P0": 542, "P1": 108, "S": 1}
REF_FIVE = [("2025-09-10 16:00", 63.73, "2025-09-10 18:00", 63.80, "P0"), ("2025-09-10 20:00", 63.74, "2025-09-10 21:00", 63.72, "P0"),
            ("2025-09-10 22:00", 63.60, "2025-09-11 02:00", 63.62, "P0"), ("2025-09-11 06:00", 63.27, "2025-09-12 04:00", 62.09, "P1"),
            ("2025-09-12 12:00", 63.20, "2025-09-14 20:00", 62.71, "P1")]


def run(csv, marks_csv, log=print) -> tuple[str, bool]:
    fr = load_seen_frame(csv)
    ind = indicators(fr)
    trades, cnt = E.simulate(fr, ind, S.BASE)
    ny = fr.ny.tz_localize(None)
    ex = dict(Counter(t.reason for t in trades))
    ok_n, ok_ex = len(trades) == REF_N, ex == REF_EXITS
    L = ["CHARTMARK-S v1 G6 seen-window parity (TradingView CL1! bars, seen -- not evidence). Counts only, no P&L.", "",
         f"trades {len(trades)} (registered {REF_N}) {'OK' if ok_n else 'MISMATCH'}",
         f"exits {ex} (registered {REF_EXITS}) {'OK' if ok_ex else 'MISMATCH'}",
         f"orders {cnt['orders']} fills {cnt['fills']} cancels {cnt['ctx_cancels']} timeouts {cnt['timeouts']} re-entries {cnt['reentries']} "
         f"gap fills {cnt['gap_fills']} same-bar backstop touches {cnt['same_bar']}", "", "first five trades:"]
    ok5 = True
    for t, r in zip(trades[:5], REF_FIVE):
        got = (f"{ny[t.entry_j]:%Y-%m-%d %H:%M}", round(t.entry_px, 2), f"{ny[t.exit_j]:%Y-%m-%d %H:%M}", round(t.exit_px, 2), t.reason)
        good = got == r
        ok5 &= good
        L.append(f"  engine {got}  registered {r}  {'OK' if good else 'MISMATCH'}")
    ok = ok_n and ok_ex and ok5 and f"{ny[trades[0].entry_j]:%Y-%m-%d %H:%M}" == "2025-09-10 16:00"
    L += ["", f"G6 parity: {'PASS' if ok else 'FAIL'}", "", "Ben's 15 short entries vs the engine (entry within 1 bar; counts only):"]
    m = pd.read_csv(marks_csv)
    ent = [(ny[t.entry_j], t.entry_px) for t in trades]
    hit = 0
    for _, r in m.iterrows():
        when = pd.Timestamp(r["e_dt"])
        near = [e for e in ent if abs((e[0] - when) / pd.Timedelta(hours=1)) <= 1]
        hit += bool(near)
        L.append(f"  #{int(r['n']):>2} Ben {when:%d %b %H:%M} @ {r['e_px']:.2f} | engine "
                 + (", ".join(f"{e[0]:%d %b %H:%M} @ {e[1]:.2f}" for e in near) if near else "no entry within 1 bar"))
    L.append(f"  engine has an entry within 1 bar of {hit} of {len(m)} of Ben's entries")
    txt = "\n".join(L) + "\n"
    log(txt)
    return txt, ok


if __name__ == "__main__":
    run(OUT / "w15_0032_cl1_1h_bars_indicators.csv", OUT / "w15_0032_short_marks_v3.csv")
