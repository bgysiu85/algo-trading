#!/usr/bin/env python3
"""CHARTMARK-S v2 G6 (sec 5): seen-window fidelity to Ben's marks, counts only, no P&L. The engine (BASE) runs on the TradingView
CL1! 1H bars (w15_0032_cl1_1h_bars_indicators.csv, 2025-09-08 -> 2026-09-29). Of the last 30 v1 trades Ben marked (sheet
w15_0032_chartmark_short_last30_check.xlsx): the engine must take NONE of the 8 he rejected for "EMA9 above EMA21, not falling"
and MUST fill at the two he wanted. A mismatch is a fidelity finding reported to Ben before any P&L; the rule is never adjusted
to make it pass. Seen -- not evidence. Interpretations: spec K6."""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from strategy.chartmark_s2 import engine as E
from strategy.chartmark_s2 import spec as S
from strategy.chartmark_s2.data import indicators, load_seen_frame

OUT = Path(os.environ.get("CHARTMARK_OUT", r"D:\Trading\Claude outputs"))
YEAR = 2026
REJECTED = ("08 Sep 08:00", "08 Sep 22:00", "09 Sep 00:00", "09 Sep 13:00", "09 Sep 20:00", "10 Sep 19:00", "10 Sep 21:00", "14 Sep 01:00")
ACCEPT_1 = ("09 Sep 22:00", 96.25, 0.02)        # registered: within 2 ticks
ACCEPT_2 = ("11 Sep 01:00", 102.09, 0.25)       # registered "near"; fixed at 0.25 in spec K6 before any run


def _ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(f"{s} {YEAR}")


def fills_near(ny, trades, when: pd.Timestamp, bars: int = 1) -> list:
    return [t for t in trades if abs((ny[t.entry_j] - when) / pd.Timedelta(hours=1)) <= bars]


def run(csv, log=print, *, simulate=None, params=None, name="CHARTMARK-S v2") -> tuple[str, bool]:
    fr = load_seen_frame(csv)
    ind = indicators(fr)
    trades, cnt = (simulate or E.simulate)(fr, ind, params or S.BASE)
    ny = fr.ny.tz_localize(None)
    L = [f"{name} G6 seen-window fidelity (TradingView CL1! bars, seen -- not evidence). Counts only, no P&L.", "",
         f"engine BASE on the seen window: {len(trades)} fills (Tier A {sum(t.tier == 1 for t in trades)}, "
         f"Tier B {sum(t.tier == 2 for t in trades)}); orders {cnt['orders']}", "",
         "Ben's 8 rejected entries (\"EMA9 above EMA21, not falling\") -- the engine must NOT fill within 1 bar:"]
    ok = True
    for s in REJECTED:
        near = fills_near(ny, trades, _ts(s))
        good = not near
        ok &= good
        L.append(f"  {s}: " + ("no fill within 1 bar  OK" if good else
                               "FILL " + ", ".join(f"{ny[t.entry_j]:%d %b %H:%M} @ {t.entry_px:.2f} (tier {'AB'[t.tier - 1]})" for t in near) + "  MISMATCH"))
    L += ["", "Ben's 2 wanted entries -- the engine MUST fill (within 1 bar, price tolerance from spec K6):"]
    for s, px, tol in (ACCEPT_1, ACCEPT_2):
        near = fills_near(ny, trades, _ts(s))
        hit = [t for t in near if abs(t.entry_px - px) <= tol]
        good = bool(hit)
        ok &= good
        L.append(f"  {s} near {px:.2f} (tol {tol:.2f}): " + (
            "  ".join(f"{ny[t.entry_j]:%d %b %H:%M} @ {t.entry_px:.2f} tier {'AB'[t.tier - 1]}" for t in hit) + "  OK" if good else
            ("fills " + ", ".join(f"{ny[t.entry_j]:%d %b %H:%M} @ {t.entry_px:.2f}" for t in near) if near else "no fill within 1 bar") + "  MISMATCH"))
    L += ["", f"G6 fidelity: {'PASS' if ok else 'FAIL -- report to Ben as a fidelity finding before any P&L; do not adjust the rule'}",
          "", "Every engine fill from 08 Sep to 30 Sep 2026 (for Ben's eye; counts only):"]
    for t in trades:
        if pd.Timestamp("2026-09-08") <= ny[t.entry_j] <= pd.Timestamp("2026-09-30"):
            L.append(f"  {ny[t.entry_j]:%a %d %b %H:%M} @ {t.entry_px:.2f}  tier {'AB'[t.tier - 1]}  ({t.reason}, {t.exit_j - t.entry_j} bars)")
    txt = "\n".join(L) + "\n"
    log(txt)
    return txt, ok


if __name__ == "__main__":
    run(OUT / "w15_0032_cl1_1h_bars_indicators.csv")
