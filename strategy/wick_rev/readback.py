#!/usr/bin/env python3
"""G1a read-back of the owned NQ 1-minute and CL 1-hour files (no spend). REGISTERED sec 7."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from strategy.wick_rev import bars as B


def describe(df: pd.DataFrame, name: str, gap_minutes: int) -> str:
    if df.empty:
        return f"{name}: EMPTY"
    idx = df.index
    yrs = pd.Series(1, index=idx.year).groupby(level=0).sum()
    dt = np.diff(idx.asi8) / 6e10                                         # minutes between bars
    long_gaps = dt[dt > gap_minutes]
    held = df["held_id"].to_numpy()
    rolls = int((held[1:] != held[:-1]).sum())
    sess = B.session_dates(df)
    lines = [f"{name}: first {idx[0]}  last {idx[-1]}  bars {len(df)}",
             f"  first session {sess.min().date()}  last session {sess.max().date()}  held-contract changes {rolls}",
             "  bars per year: " + ", ".join(f"{y}:{n}" for y, n in yrs.items()),
             f"  gaps longer than {gap_minutes} min: {len(long_gaps)} (longest {long_gaps.max() if len(long_gaps) else 0:.0f} min; "
             f"weekends / holidays / the 17:00-18:00 break are included)"]
    return "\n".join(lines)


def run(archive: Path, mcl30_path: Path) -> str:
    from strategy.wick_rev import run as RUN
    parts = ["G1a READ-BACK - owned files only, no spend, no wick ratio or reversal read", ""]
    parts.append(describe(RUN.load_nq_1m(archive), "NQ.v.0 ohlcv-1m (MNQ source)", 60 * 4))
    parts.append("")
    parts.append(describe(RUN.load_cl_1h(archive), "CL.c.0 ohlcv-1h (MCL 1H / 4H source)", 60 * 4))
    parts.append("")
    m = RUN.load_mcl_30m(mcl30_path)
    parts.append(describe(m, "MCL 30m (IBKR, sub 3a)", 60 * 4) if m is not None else "MCL 30m (IBKR): no file yet (sub 3a)")
    return "\n".join(parts)
