#!/usr/bin/env python3
"""G1 -- the ES/NQ 1-minute data read-back gate. W16-0003 subitem 2,
REGISTERED_w16_session_baselines.md sec 0 (gate G1) and sec 6.1.

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.w16.readback

NO INDICATOR, NO SIGNAL, NO P&L HAPPENS HERE (sec 6.1: "no indicator, signal
or P&L"). This module only answers one question, per root (ES, NQ): can the
1-minute bars this study is about to trade on be trusted? It rebuilds a
daily close from the fetched `<ROOT>.v.0` 1-minute bars, on UTC calendar
days, and compares it against the `<ROOT>.v.0` `ohlcv-1d` bought alongside it
(`strategy.w16.fetch`) for exactly this check. Sec 0's stop rule: below 99%
agreement, the study stops until the mismatch is explained -- enforced here
by the exit code, not by printing a warning.

WHY THE DAILY COMPARISON IS ON UTC CALENDAR DAYS
--------------------------------------------------
Same convention as HTF-Ben's G1 (`strategy.htf.readback`, Amendment B,
2026-09-25): the owned `ohlcv-1d` archive is stamped on naive UTC calendar
days (`common/dbn_io.py`), not on any wall-clock session, so the rebuild has
to use the same grid to be a like-for-like comparison rather than a
convention mismatch dressed up as a data fault.

WHY THIS REUSES strategy.htf.readback's utc_daily / utc_roll_days /
daily_agreement
-------------------------------------------------------------------
Those three are generic pandas over a bar frame with an `open/high/low/
close/volume` OHLCV shape plus a "which contract is this bar on" id column
and a tz-aware UTC index -- nothing in them is CL-specific, and HTF-Ben's own
G1 already found and fixed the UTC-vs-session bug they exist to avoid
repeating. This module adapts to their column name (`held_id`) rather than
forking a second copy that could drift out of step with that fix.

WHAT'S DIFFERENT FROM HTF-Ben's G1, AND WHY
---------------------------------------------
HTF-Ben's session is CME's own 18:00-17:00 Globex day. This study's session
is the 09:30-16:00 America/New_York regular-trading-hours window the three
baselines are registered against (REGISTERED sec 2), so bars-per-session and
the >5-minute gap check are computed on that window, in wall-clock ET, on
whichever calendar dates a 1-minute bar actually falls in it -- the read-back
gate answers "is the data there and internally consistent", not "which days
does the exchange calendar say should exist"; the exact XNYS trading-day
list (excluding a Globex-only session, matching an early close, etc.) is the
engine's job (REGISTERED sec 2 "days that don't count"; W16-0003 subitem 3),
run once the data itself has passed this gate.
"""
from __future__ import annotations

import argparse
import json
from datetime import time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from strategy.htf.readback import daily_agreement, utc_daily, utc_roll_days

ET = ZoneInfo("America/New_York")
RTH_START = dtime(9, 30)
RTH_END = dtime(16, 0)
TOLERANCE_USD = 0.05
PASS_PCT = 0.99
GAP_MINUTES = 5
ROOTS = ("ES", "NQ")


def local_naive_et(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """A tz-aware (UTC or other) index -> naive America/New_York wall clock."""
    if idx.tz is None:
        raise ValueError("index must be tz-aware")
    return idx.tz_convert(ET).tz_localize(None)


def _with_held_id(df: pd.DataFrame) -> pd.DataFrame:
    """Adapt a raw 1-minute frame (instrument_id column, from read_dbn) to the
    `held_id` name strategy.htf.readback's utc_daily/utc_roll_days expect."""
    if "held_id" in df.columns:
        return df
    if "instrument_id" in df.columns:
        return df.rename(columns={"instrument_id": "held_id"})
    raise KeyError("expected an 'instrument_id' or 'held_id' column")


def rth_mask(naive_et: pd.DatetimeIndex) -> np.ndarray:
    t = naive_et.time
    return (t >= RTH_START) & (t < RTH_END)


def bars_per_session(df_1m: pd.DataFrame) -> dict:
    """RTH-only 1-minute bars, grouped by ET calendar date."""
    if df_1m.empty:
        return {"n_sessions": 0, "total_rth_bars": 0, "median": 0, "min": 0,
                "max": 0, "first_session": None, "last_session": None}
    naive = local_naive_et(df_1m.index)
    in_rth = naive[rth_mask(naive)]
    if len(in_rth) == 0:
        return {"n_sessions": 0, "total_rth_bars": 0, "median": 0, "min": 0,
                "max": 0, "first_session": None, "last_session": None}
    counts = pd.Series(1, index=in_rth.normalize()).groupby(level=0).sum()
    return {"n_sessions": int(len(counts)), "total_rth_bars": int(counts.sum()),
            "median": float(counts.median()), "min": int(counts.min()),
            "max": int(counts.max()), "first_session": str(counts.index.min().date()),
            "last_session": str(counts.index.max().date())}


def gaps_over(df_1m: pd.DataFrame, minutes: int = GAP_MINUTES) -> list[dict]:
    """Runs of missing minutes longer than `minutes` INSIDE the 09:30-16:00 ET
    window of a session -- a gap at the session's own open or close is not
    "inside" it and is not reported here."""
    if df_1m.empty:
        return []
    naive = local_naive_et(df_1m.index)
    mask = rth_mask(naive)
    if not mask.any():
        return []
    ts = pd.Series(naive[mask]).sort_values()
    session = ts.dt.normalize()
    out = []
    for s, g in ts.groupby(session, sort=True):
        g = g.sort_values().to_numpy()
        if len(g) < 2:
            continue
        deltas = (g[1:] - g[:-1]) / np.timedelta64(1, "m")
        bad = np.where(deltas > minutes)[0]
        for i in bad:
            out.append({"session": str(pd.Timestamp(s).date()),
                        "from": str(pd.Timestamp(g[i])),
                        "to": str(pd.Timestamp(g[i + 1])),
                        "gap_minutes": float(deltas[i])})
    return out


def roll_sessions(df_1m: pd.DataFrame) -> list[dict]:
    """ET calendar dates on which the held instrument_id changes from the
    immediately preceding 1-minute bar (a roll landing mid-session, the
    volume-led `v.0` map switching to the new front month)."""
    d = _with_held_id(df_1m).sort_index() if not df_1m.empty else df_1m
    if d.empty:
        return []
    change = d["held_id"] != d["held_id"].shift(1)
    change.iloc[0] = False
    if not change.any():
        return []
    naive = local_naive_et(d.index)
    out = []
    for i in np.where(change.to_numpy())[0]:
        out.append({"session": str(naive[i].date()),
                    "from_id": int(d["held_id"].iloc[i - 1]),
                    "to_id": int(d["held_id"].iloc[i])})
    return out


def owned_daily(ohlcv1d_path, root: str) -> pd.DataFrame:
    """The `<root>.v.0` daily bar bought alongside the 1-minute file
    (`strategy.w16.fetch`), read the same way HTF-Ben's G1 reads its owned
    daily archive (`common.dbn_io.read_dbn`)."""
    from common.dbn_io import read_dbn
    raw = read_dbn(ohlcv1d_path)
    sym = f"{root}.v.0"
    d = raw[raw["symbol"] == sym].copy() if "symbol" in raw.columns else raw.copy()
    d["date"] = (d.index.tz_convert(None) if d.index.tz is not None else d.index).normalize().date
    d = d.drop_duplicates("date", keep="first").sort_values("date")
    cols = [c for c in ("date", "open", "high", "low", "close", "volume") if c in d.columns]
    return d[cols].reset_index(drop=True)


def run(df_1m: pd.DataFrame, owned_1d: pd.DataFrame, *, gap_minutes: int = GAP_MINUTES,
        tol: float = TOLERANCE_USD, pass_pct: float = PASS_PCT) -> dict:
    """The whole gate for one root: coverage stats plus the UTC-day close
    comparison. Never raises on a failed comparison -- a failed G1 is itself
    the finding to report (sec 0's "stops until explained" is enforced by
    main()'s exit code)."""
    d = _with_held_id(df_1m) if not df_1m.empty else df_1m
    utc_rebuilt = utc_daily(d)
    roll_days = utc_roll_days(d)
    agree = daily_agreement(utc_rebuilt, owned_1d, tol=tol, roll_days=roll_days)
    return {
        "bars_per_session": bars_per_session(df_1m),
        "gaps_over_5min": gaps_over(df_1m, minutes=gap_minutes),
        "roll_sessions": roll_sessions(df_1m),
        "daily_agreement": agree,
        "passed": agree["n_compared"] > 0 and agree["pct_within_tol"] >= pass_pct,
        "pass_threshold_pct": pass_pct,
    }


def _load(archive: Path, root: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    from common.dbn_io import read_dbn
    from strategy.w16.fetch import ARCHIVE_SUBDIR
    from common.tsmom_data_price import DATASET

    base = Path(archive) / DATASET / ARCHIVE_SUBDIR
    m1_path = base / "ohlcv-1m" / f"{root}.dbn.zst"
    d1_path = base / "ohlcv-1d" / f"{root}.dbn.zst"
    if not m1_path.exists():
        raise SystemExit(f"missing {m1_path} -- run strategy.w16.fetch --confirm first")
    if not d1_path.exists():
        raise SystemExit(f"missing {d1_path} -- run strategy.w16.fetch --confirm first")
    df_1m = read_dbn(m1_path)
    if "symbol" in df_1m.columns:
        df_1m = df_1m[df_1m["symbol"] == f"{root}.v.0"].copy()
    owned_1d = owned_daily(d1_path, root)
    return df_1m, owned_1d


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="G1: ES/NQ 1-minute bar read-back gate.")
    ap.add_argument("--archive", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None,
                    help="write the full JSON report here as well as stdout")
    a = ap.parse_args(argv)

    from common.tsmom_fetch import default_archive
    archive = a.archive or default_archive()

    reports, all_passed = {}, True
    for root in ROOTS:
        df_1m, owned_1d = _load(archive, root)
        report = run(df_1m, owned_1d)
        reports[root] = report
        all_passed = all_passed and report["passed"]

        bps, ag = report["bars_per_session"], report["daily_agreement"]
        print(f"=== {root} ===")
        print(f"RTH bars: {bps['total_rth_bars']} over {bps['n_sessions']} sessions "
              f"({bps['first_session']} .. {bps['last_session']}), "
              f"median {bps['median']:.0f}/session, range [{bps['min']}, {bps['max']}]")
        print(f"gaps >{GAP_MINUTES}min inside 09:30-16:00 ET: {len(report['gaps_over_5min'])}")
        print(f"roll sessions: {len(report['roll_sessions'])}")
        print(f"daily agreement (UTC calendar days): {ag['n_within_tol']}/{ag['n_compared']} "
              f"({ag['pct_within_tol']:.4%}) within ${ag['tolerance_usd']}")
        print(f"dates only in 1-min rebuild: {ag['n_only_in_1h_rebuild']}")
        print(f"dates only in owned 1D: {ag['n_only_in_owned_1d']}")
        for m in ag["misses"][:10]:
            roll = "  [roll day]" if m["is_roll_day"] else ""
            print(f"  miss {m['date']}  1min={m['close_1h']:.2f}  1D={m['close_1d']:.2f}  "
                  f"diff=${m['diff']:.2f}{roll}")
        print(f"{'PASSED' if report['passed'] else 'FAILED'} "
              f"({ag['pct_within_tol']:.4%} vs {report['pass_threshold_pct']:.0%} needed)\n")

    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(reports, indent=2, default=str), encoding="utf-8")
        print(f"full report: {a.out}")

    if all_passed:
        print("G1 PASSED for ES and NQ.")
        return 0
    print("G1 FAILED for at least one root -- REGISTERED_w16_session_baselines.md "
          "sec 0: the study stops until this is explained.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
