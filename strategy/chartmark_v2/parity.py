#!/usr/bin/env python3
"""CHARTMARK-v2 G6: seen-window parity (Amendments 1.3, 2.2, 3.4). Counts and levels only -- no P&L.
The engine runs on the TradingView CL1! 1H bars Ben traded (w15_0032_cl1_1h_bars_indicators.csv). 'seen -- not evidence'."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from strategy.chartmark.data import indicators, load_seen_frame
from strategy.chartmark_v2 import engine as E
from strategy.chartmark_v2 import spec as S

OUT = Path(__file__).resolve().parents[2] / "Claude outputs"
CSV = "w15_0032_cl1_1h_bars_indicators.csv"


def _idx(ny, stamp: str) -> int:
    """Index of the last bar whose open is at or before `stamp` (a flat start at that bar's close)."""
    return int(np.where(ny <= pd.Timestamp(stamp))[0][-1])


def checks(csv_path, p: S.Params = S.K1) -> list[dict]:
    """Each check: name, expected, got, ok."""
    fr = load_seen_frame(csv_path)
    ind = indicators(fr)
    pre = E.precompute(fr, ind)
    ny = fr.ny.tz_localize(None)
    out = []

    def fills(start_close: str):
        tr, _ = E.simulate(fr, ind, p, start=_idx(ny, start_close), pre=pre)
        return tr

    def add(name, expected, got, ok):
        out.append(dict(name=name, expected=expected, got=got, ok=bool(ok)))

    prev = "on" if p.prev_high else "off"
    # 28 Aug: flat at the close of 11:00 -> fill in the 12:00 bar
    tr = fills("2026-08-28 11:00")
    t0 = tr[0] if tr else None
    lvl28 = 83.30 if p.prev_high else 83.27
    add(f"28 Aug, flat at 11:00 close, prev-high {prev}: first fill is the 12:00 bar",
        "2026-08-28 12:00", None if t0 is None else str(ny[t0.entry_j]), t0 is not None and ny[t0.entry_j] == pd.Timestamp("2026-08-28 12:00"))
    if t0 is not None:
        add(f"28 Aug: level within 2 ticks of {lvl28:.2f} (Ben ~83.35)", lvl28, round(t0.level, 2),
            abs(t0.level - lvl28) <= 2 * S.TICK + 1e-9)
        xs = [t for t in tr if ny[t.exit_j] == pd.Timestamp("2026-09-02 08:00")]
        add("28 Aug: the position exits at the 2 Sep 08:00 open 89.11", 89.11, round(t0.exit_px, 2),
            ny[t0.exit_j] == pd.Timestamp("2026-09-02 08:00") and abs(t0.exit_px - 89.11) < 1e-6 and t0.reason == "EMA21")
    # 1 Sep: flat at 03:00 close -> fill in the 04:00 bar at 87.69 (+-2 ticks)
    tr = fills("2026-09-01 03:00")
    t1 = tr[0] if tr else None
    add("1 Sep, flat at 03:00 close: first fill is the 04:00 bar", "2026-09-01 04:00",
        None if t1 is None else str(ny[t1.entry_j]), t1 is not None and ny[t1.entry_j] == pd.Timestamp("2026-09-01 04:00"))
    if t1 is not None:
        add("1 Sep: level within 2 ticks of 87.69", 87.69, round(t1.level, 2), abs(t1.level - 87.69) <= 2 * S.TICK + 1e-9)
        # Amendment 1.3 + Amendment 5: the 04:00 bar opened below the level (86.95 < 87.69), EMA9 was not falling at the 03:00 close,
        # and the bar closed at 88.04 (> the 87.09 backstop), so the fill-bar low is not counted and the trade runs to 89.11.
        add("1 Sep: exits at the 2 Sep 08:00 open 89.11 (Amendments 1.3 + 5)", 89.11, f"{t1.reason} @ {t1.exit_px:.2f}",
            ny[t1.exit_j] == pd.Timestamp("2026-09-02 08:00") and abs(t1.exit_px - 89.11) < 1e-6 and t1.reason == "EMA21")
        tn = E.simulate(fr, ind, replace(p, backstop=50.0), start=_idx(ny, "2026-09-01 03:00"), pre=pre)[0][0]
        add("1 Sep: EMA21 exit machinery alone (backstop neutralised) exits at the 2 Sep 08:00 open 89.11", 89.11,
            f"{tn.reason} @ {tn.exit_px:.2f} on {ny[tn.exit_j]}",
            ny[tn.exit_j] == pd.Timestamp("2026-09-02 08:00") and abs(tn.exit_px - 89.11) < 1e-6 and tn.reason == "EMA21")
    # 1 Sep 00:00 must not fill (level 87.25 > high 87.09): flat at 31 Aug 23:00 close
    tr = fills("2026-08-31 23:00")
    first = tr[0] if tr else None
    add("1 Sep 00:00 bar does not fill (flat at 31 Aug 23:00 close)", "not 2026-09-01 00:00",
        None if first is None else str(ny[first.entry_j]), first is None or ny[first.entry_j] != pd.Timestamp("2026-09-01 00:00"))
    # no fill 30 Aug 18:00 -> 31 Aug 23:59, both flat-start and whole year
    a, b = pd.Timestamp("2026-08-30 18:00"), pd.Timestamp("2026-08-31 23:59")
    for label, trs in (("flat at the last close before 30 Aug 18:00", fills("2026-08-30 17:00")),
                       ("whole seen year", E.simulate(fr, ind, p, pre=pre)[0])):
        bad = [str(ny[t.entry_j]) for t in trs if a <= ny[t.entry_j] <= b]
        add(f"No fill 30 Aug 18:00 -> 31 Aug 23:59 ({label})", "none", bad or "none", not bad)
    return out


def report(csv_path=None) -> tuple[str, bool]:
    csv_path = csv_path or OUT / CSV
    lines = ["CHARTMARK-v2 G6 seen-window parity (TradingView CL1! bars; seen -- not evidence). No P&L.", ""]
    ok_all = True
    for name, p in (("K1 (prev-high on, theta 0.05) -- the registered base", S.K1), ("K3 (prev-high off, theta 0.05)", S.K3)):
        lines.append(f"== {name}")
        for c in checks(csv_path, p):
            ok_all &= c["ok"]
            lines.append(f"  [{'PASS' if c['ok'] else 'FAIL'}] {c['name']}: expected {c['expected']}, got {c['got']}")
        lines.append("")
    lines.append("G6 " + ("PASSES" if ok_all else "NOT CLEARED: see the FAIL lines"))
    return "\n".join(lines) + "\n", ok_all


if __name__ == "__main__":
    txt, ok = report()
    print(txt)
    raise SystemExit(0 if ok else 1)
