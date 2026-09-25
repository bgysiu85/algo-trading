#!/usr/bin/env python3
"""G1 -- the CL 1-hour data read-back gate. W15-0004, REGISTERED_htf_ben_v0.md
sec 0 (gate G1) and sec 5.1.

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.htf.readback

NO INDICATOR, NO SIGNAL, NO P&L HAPPENS HERE (sec 5.1). This module only
answers one question: can the 1-hour bars this study is about to trade on be
trusted? It rebuilds a daily close from the fetched CL.c.0 1-hour bars
(strategy/htf/bars.daily) and compares it against the daily close the
project already owns (GLBX.MDP3 ohlcv-1d, bought and read back independently
months ago for TSMOM/TL-v0). Sec 0's stop rule: below 99% agreement within
$0.05, the study stops until the mismatch is explained -- this module
enforces that by its exit code, not by printing a warning.

It also reports (sec 5.1): bars per year, first/last bar, hours missing
inside a session (>3 in a row, excluding the 17:00-18:00 break/weekends --
which never appear as "missing" in the first place, since a session's own
1-hour bars are indexed 0..22 and only span the session), and roll sessions
(a held_id change between consecutive 1-hour bars, from bars.split_held).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from strategy.htf import bars as B

TOLERANCE_USD = 0.05
PASS_PCT = 0.99


def bars_per_year(df_1h: pd.DataFrame) -> dict:
    """{year: n_bars} over the held (CL.c.0) 1-hour bars, plus first/last."""
    if df_1h.empty:
        return {"by_year": {}, "first": None, "last": None, "n_total": 0}
    idx = df_1h.index
    years = idx.year
    by_year = pd.Series(1, index=years).groupby(level=0).sum().to_dict()
    return {"by_year": {int(y): int(n) for y, n in sorted(by_year.items())},
            "first": idx.min().isoformat(), "last": idx.max().isoformat(),
            "n_total": int(len(df_1h))}


def gaps_over(df_1h: pd.DataFrame, hours: int = 3) -> list[dict]:
    """Sessions with a run of missing hours inside them longer than `hours`,
    from the elapsed-since-open sequence (bars.py's own bucketing), not from
    wall-clock deltas across the 17:00-18:00 break or a weekend -- neither of
    those is a "gap inside a session", they are the session boundary."""
    if df_1h.empty:
        return []
    naive = B.local_naive(df_1h.index)
    sess = B.session_of(naive)
    open_naive = B.session_open_naive(sess)
    elapsed = ((naive - open_naive) / pd.Timedelta(hours=1)).to_numpy()
    d = pd.DataFrame({"session": sess.date, "elapsed": elapsed}).sort_values(
        ["session", "elapsed"])
    out = []
    for s, g in d.groupby("session", sort=True):
        e = g["elapsed"].to_numpy()
        prev = np.r_[-1.0, e[:-1]]          # session opens at elapsed 0, so a
        gap = e - prev - 1                  # gap before the first bar counts
        bad = np.where(gap > hours)[0]
        for i in bad:
            out.append({"session": str(s), "from_elapsed": float(prev[i] + 1),
                        "to_elapsed": float(e[i]), "gap_hours": float(gap[i])})
    return out


def roll_sessions(df_1h: pd.DataFrame) -> list[dict]:
    """Sessions in which held_id (CL.c.0's instrument_id) changes from the
    prior bar -- i.e. the roll happened intraday, mid-session."""
    if df_1h.empty:
        return []
    d = df_1h.sort_index()
    change = d["held_id"] != d["held_id"].shift(1)
    change.iloc[0] = False
    if not change.any():
        return []
    naive = B.local_naive(d.index)
    sess = B.session_of(naive)
    out = []
    for i in np.where(change.to_numpy())[0]:
        out.append({"session": str(sess[i].date()),
                    "from_id": int(d["held_id"].iloc[i - 1]),
                    "to_id": int(d["held_id"].iloc[i]),
                    "gap_usd": float(d["close"].iloc[i] - d["close"].iloc[i - 1])})
    return out


def owned_daily_close(ohlcv1d_path) -> pd.DataFrame:
    """The project's already-owned daily CL.c.0 close, independently pulled
    and read back for TSMOM/TL-v0 (common/tl_v0_data.py's front_month_series
    does the same "c.0 IS the held contract" read for CL)."""
    from common.dbn_io import read_dbn
    raw = read_dbn(ohlcv1d_path)
    d = raw[raw["symbol"] == "CL.c.0"].copy()
    d["date"] = (d.index.tz_convert(None) if d.index.tz is not None else d.index).normalize().date
    d = d.drop_duplicates("date", keep="first").sort_values("date")
    return d[["date", "close"]].reset_index(drop=True)


def daily_agreement(rebuilt: pd.DataFrame, owned: pd.DataFrame,
                    tol: float = TOLERANCE_USD) -> dict:
    """rebuilt: strategy.htf.bars.daily(...) output (has 'date','close').
    owned: owned_daily_close(...) output. Compared on the intersection of
    dates only -- a date present in one but not the other is reported
    separately, not silently dropped from the denominator."""
    r = rebuilt[["date", "close"]].rename(columns={"close": "close_1h"})
    o = owned.rename(columns={"close": "close_1d"})
    m = r.merge(o, on="date", how="outer", indicator=True)
    both = m[m["_merge"] == "both"].copy()
    only_1h = sorted(str(d) for d in m.loc[m["_merge"] == "left_only", "date"])
    only_1d = sorted(str(d) for d in m.loc[m["_merge"] == "right_only", "date"])
    both["diff"] = (both["close_1h"] - both["close_1d"]).abs()
    n = len(both)
    within = int((both["diff"] <= tol).sum())
    misses = both[both["diff"] > tol].sort_values("diff", ascending=False)
    return {
        "n_compared": n,
        "n_within_tol": within,
        "pct_within_tol": (within / n) if n else 0.0,
        "tolerance_usd": tol,
        "n_only_in_1h_rebuild": len(only_1h), "only_in_1h_rebuild": only_1h[:20],
        "n_only_in_owned_1d": len(only_1d), "only_in_owned_1d": only_1d[:20],
        "misses": [{"date": str(row.date), "close_1h": float(row.close_1h),
                    "close_1d": float(row.close_1d), "diff": float(row.diff)}
                   for row in misses.itertuples()],
    }


def run(archive_1h, ohlcv1d_path, *, gap_hours: int = 3, tol: float = TOLERANCE_USD,
        pass_pct: float = PASS_PCT) -> dict:
    """The whole gate: load, rebuild, compare, report. Returns a dict with
    "passed": bool -- never raises on a failed comparison, since a failed G1
    is itself the finding to report (sec 0's "stops until the mismatch is
    explained" is enforced by main()'s exit code, not by an exception here)."""
    df_1h = B.load_1h(archive_1h)
    settle_mask = B.settlement_bar_mask(df_1h)
    daily = B.daily(df_1h)
    owned = owned_daily_close(ohlcv1d_path)
    agree = daily_agreement(daily, owned, tol=tol)
    report = {
        "coverage": bars_per_year(df_1h),
        "settlement_bars_excluded": {
            "n": int(settle_mask.sum()),
            "note": ("a recurring ts_event==17:00 print in CL.c.0 (found "
                     "here, not documented anywhere upstream): interval "
                     "[17:00,18:00), after the 18:00-17:00 session this "
                     "study trades on, so bars.py excludes it from every "
                     "grid rather than treating it as a 24th intraday bar"),
        },
        "gaps_over_3h": gaps_over(df_1h, hours=gap_hours),
        "roll_sessions": roll_sessions(df_1h),
        "daily_agreement": agree,
        "passed": agree["n_compared"] > 0 and agree["pct_within_tol"] >= pass_pct,
        "pass_threshold_pct": pass_pct,
    }
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="G1: CL 1-hour bar read-back gate.")
    ap.add_argument("--archive", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None,
                    help="write the full JSON report here as well as stdout")
    a = ap.parse_args(argv)

    from common.tsmom_fetch import default_archive
    from common.tsmom_data_price import DATASET
    archive = a.archive or default_archive()
    ohlcv1d = Path(archive) / DATASET / "ohlcv-1d" / "CL.dbn.zst"

    report = run(archive, ohlcv1d)
    ag = report["daily_agreement"]
    print(f"G1 -- CL 1-hour read-back\n"
          f"bars: {report['coverage']['n_total']} total, "
          f"{report['coverage']['first']} .. {report['coverage']['last']}\n"
          f"by year: {report['coverage']['by_year']}\n"
          f"settlement bars excluded (17:00 print): "
          f"{report['settlement_bars_excluded']['n']}\n"
          f"gaps >3h inside a session: {len(report['gaps_over_3h'])}\n"
          f"roll sessions: {len(report['roll_sessions'])}\n"
          f"daily agreement: {ag['n_within_tol']}/{ag['n_compared']} "
          f"({ag['pct_within_tol']:.4%}) within ${ag['tolerance_usd']}\n"
          f"dates only in 1H rebuild: {ag['n_only_in_1h_rebuild']}\n"
          f"dates only in owned 1D: {ag['n_only_in_owned_1d']}\n"
          f"misses (worst 10 of {len(ag['misses'])}):")
    for m in ag["misses"][:10]:
        print(f"  {m['date']}  1H={m['close_1h']:.2f}  1D={m['close_1d']:.2f}  "
              f"diff=${m['diff']:.2f}")

    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"\nfull report: {a.out}")

    if report["passed"]:
        print(f"\nG1 PASSED ({ag['pct_within_tol']:.4%} >= "
              f"{report['pass_threshold_pct']:.0%})")
        return 0
    print(f"\nG1 FAILED -- below {report['pass_threshold_pct']:.0%} agreement. "
          "REGISTERED_htf_ben_v0.md sec 0: the study stops until this is explained.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
