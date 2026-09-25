#!/usr/bin/env python3
"""G1 -- the CL 1-hour data read-back gate. W15-0004, REGISTERED_htf_ben_v0.md
sec 0 (gate G1) and sec 5.1 (Amendment B, 2026-09-25).

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.htf.readback

NO INDICATOR, NO SIGNAL, NO P&L HAPPENS HERE (sec 5.1). This module only
answers one question: can the 1-hour bars this study is about to trade on be
trusted? It rebuilds a daily close from the fetched CL.c.0 1-hour bars and
compares it against the daily close the project already owns (GLBX.MDP3
ohlcv-1d, bought and read back independently months ago for TSMOM/TL-v0).
Sec 0's stop rule: below 99% agreement within $0.05, the study stops until
the mismatch is explained -- this module enforces that by its exit code,
not by printing a warning.

AMENDMENT B (2026-09-25) -- COMPARE ON UTC CALENDAR DAYS, NOT THE ET SESSION
-----------------------------------------------------------------------------
G1 as first written compared daily closes rebuilt on the 18:00-17:00 New
York session (strategy.htf.bars.daily) against the owned ohlcv-1d close, and
got 45.58% agreement: a convention mismatch, not a data fault. The owned
ohlcv-1d archive is stamped on naive UTC calendar days
(common/dbn_io.py's daily_frame docstring: "daily bars are stamped at UTC
midnight"), not the 18:00 ET session this study trades on. So the primary,
gating comparison here re-aggregates the raw 1-hour bars on UTC calendar
days (ts_event in [D 00:00, D+1 00:00) UTC; close = close of the last bar
in the day) -- like for like. The 18:00 New York session grid is still
built and reported (bars.daily), but only as a reported-only figure; it is
verified by the bars-module tests (DST crossings, the 16:00/14:00 last
bars, an early close), not by this gate, and does not affect "passed".

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


def coverage(df_1h: pd.DataFrame, *, gap_hours: int = 3) -> dict:
    """W15-0004 step 7 checkpoint 10. REGISTERED sec 3 item 11: "Coverage in
    the same pass: bars per year, gaps, roll dates, first and last bar" --
    every one of those is already exactly what this gate (G1) computes for
    its own one-time report (bars_per_year, gaps_over, roll_sessions), so
    this is a thin re-assembly for report.py to call on every run's own
    1-hour archive, NOT a second read-back gate: it does not touch the
    owned ohlcv-1d comparison (that stays G1's one-time job, run() above,
    not something every backtest pass repeats)."""
    return {
        "bars_per_year": bars_per_year(df_1h),
        "gaps_over_3h": gaps_over(df_1h, hours=gap_hours),
        "roll_sessions": roll_sessions(df_1h),
    }


def utc_daily(df_1h: pd.DataFrame) -> pd.DataFrame:
    """CL.c.0 1-hour bars (tz-aware UTC index; open/high/low/close/volume/
    held_id columns, e.g. from bars.split_held) re-aggregated on UTC
    CALENDAR days -- Amendment B, 2026-09-25. ts_event in
    [D 00:00, D+1 00:00) UTC. OHLC = first open, max high, min low, last
    close, summed volume; held_id = the LAST source bar's (a roll inside the
    day is reflected honestly, matching bars.resample's convention).

    This is deliberately NOT the 18:00 New York session grid (bars.daily):
    the owned ohlcv-1d archive is itself stamped on naive UTC calendar days
    (common/dbn_io.py), so this is the like-for-like comparison for G1.
    """
    cols = ["date", "open", "high", "low", "close", "volume", "held_id"]
    if df_1h.empty:
        return pd.DataFrame(columns=cols)
    d = df_1h.sort_index().copy()
    d["date"] = d.index.tz_convert("UTC").normalize().date
    g = d.groupby("date", sort=True)
    out = pd.DataFrame({
        "open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
        "close": g["close"].last(), "volume": g["volume"].sum(),
        "held_id": g["held_id"].last(),
    }).reset_index()
    return out[cols]


def utc_roll_days(df_1h: pd.DataFrame) -> set:
    """UTC calendar dates on which held_id changed from the immediately
    preceding 1-hour bar (roll happened at or during that day) -- used to
    flag whether a G1 miss coincides with a roll, not to explain it away."""
    if df_1h.empty:
        return set()
    d = df_1h.sort_index()
    change = d["held_id"] != d["held_id"].shift(1)
    change.iloc[0] = False
    if not change.any():
        return set()
    dates = d.index.tz_convert("UTC").normalize().date
    return {dates[i] for i in np.where(change.to_numpy())[0]}


def owned_daily(ohlcv1d_path) -> pd.DataFrame:
    """The project's already-owned daily CL.c.0 OHLCV, independently pulled
    and read back for TSMOM/TL-v0 (common/tl_v0_data.py's front_month_series
    does the same "c.0 IS the held contract" read for CL). Stamped at UTC
    midnight (common/dbn_io.py's daily_frame docstring)."""
    from common.dbn_io import read_dbn
    raw = read_dbn(ohlcv1d_path)
    d = raw[raw["symbol"] == "CL.c.0"].copy()
    d["date"] = (d.index.tz_convert(None) if d.index.tz is not None else d.index).normalize().date
    d = d.drop_duplicates("date", keep="first").sort_values("date")
    cols = [c for c in ("date", "open", "high", "low", "close", "volume") if c in d.columns]
    return d[cols].reset_index(drop=True)


def owned_daily_close(ohlcv1d_path) -> pd.DataFrame:
    """Back-compat thin wrapper: owned_daily's date/close columns only."""
    return owned_daily(ohlcv1d_path)[["date", "close"]]


def daily_agreement(rebuilt: pd.DataFrame, owned: pd.DataFrame, *,
                    tol: float = TOLERANCE_USD, roll_days: set | None = None) -> dict:
    """rebuilt: a date/OHLCV frame (utc_daily(...) or bars.daily(...) output).
    owned: owned_daily(...) (or owned_daily_close(...)) output. Compared on
    the intersection of dates only -- a date present in one but not the
    other is reported separately, not silently dropped from the denominator.

    High, low and volume are reported alongside the close comparison when
    both frames carry them (volume is expected to match exactly); only the
    close difference decides "passed". `roll_days`, when given, flags each
    miss with whether its date fell on a roll (Amendment B: "whether it is
    a roll day"), purely informational -- a roll-day miss still counts
    against the 99% threshold.
    """
    have_ohlc = {"open", "high", "low", "volume"} <= set(rebuilt.columns) and \
                {"open", "high", "low", "volume"} <= set(owned.columns)
    r_cols = {"close": "close_1h"}
    o_cols = {"close": "close_1d"}
    if have_ohlc:
        r_cols.update({"open": "open_1h", "high": "high_1h", "low": "low_1h",
                       "volume": "volume_1h"})
        o_cols.update({"open": "open_1d", "high": "high_1d", "low": "low_1d",
                       "volume": "volume_1d"})
    r = rebuilt[["date", *r_cols.keys()]].rename(columns=r_cols)
    o = owned[["date", *o_cols.keys()]].rename(columns=o_cols)
    m = r.merge(o, on="date", how="outer", indicator=True)
    both = m[m["_merge"] == "both"].copy()
    only_1h = sorted(str(d) for d in m.loc[m["_merge"] == "left_only", "date"])
    only_1d = sorted(str(d) for d in m.loc[m["_merge"] == "right_only", "date"])
    both["diff"] = (both["close_1h"] - both["close_1d"]).abs()
    n = len(both)
    within = int((both["diff"] <= tol).sum())
    misses = both[both["diff"] > tol].sort_values("diff", ascending=False)
    roll_days = roll_days or set()

    def _miss(row) -> dict:
        m = {"date": str(row.date), "close_1h": float(row.close_1h),
             "close_1d": float(row.close_1d), "diff": float(row.diff),
             "is_roll_day": row.date in roll_days}
        if have_ohlc:
            m.update({
                "high_1h": float(row.high_1h), "high_1d": float(row.high_1d),
                "low_1h": float(row.low_1h), "low_1d": float(row.low_1d),
                "volume_1h": float(row.volume_1h), "volume_1d": float(row.volume_1d),
                "volume_matches": bool(np.isclose(row.volume_1h, row.volume_1d)),
            })
        return m

    return {
        "n_compared": n,
        "n_within_tol": within,
        "pct_within_tol": (within / n) if n else 0.0,
        "tolerance_usd": tol,
        "n_only_in_1h_rebuild": len(only_1h), "only_in_1h_rebuild": only_1h[:20],
        "n_only_in_owned_1d": len(only_1d), "only_in_owned_1d": only_1d[:20],
        "misses": [_miss(row) for row in misses.itertuples()],
    }


def run(archive_1h, ohlcv1d_path, *, gap_hours: int = 3, tol: float = TOLERANCE_USD,
        pass_pct: float = PASS_PCT) -> dict:
    """The whole gate: load, rebuild, compare, report. Returns a dict with
    "passed": bool -- never raises on a failed comparison, since a failed G1
    is itself the finding to report (sec 0's "stops until the mismatch is
    explained" is enforced by main()'s exit code, not by an exception here).

    "passed" is decided by the UTC-calendar-day comparison only (Amendment
    B). The 18:00 New York session-grid comparison is still computed and
    returned, under "daily_agreement_session_grid_reported_only" -- it does
    not gate anything, it is there so a divergence between the two
    conventions stays visible.
    """
    df_1h = B.load_1h(archive_1h)
    settle_mask = B.settlement_bar_mask(df_1h)
    session_daily = B.daily(df_1h)
    utc_rebuilt = utc_daily(df_1h)
    roll_days = utc_roll_days(df_1h)
    owned = owned_daily(ohlcv1d_path)
    agree = daily_agreement(utc_rebuilt, owned, tol=tol, roll_days=roll_days)
    agree_session_grid = daily_agreement(session_daily, owned, tol=tol, roll_days=roll_days)
    report = {
        "coverage": bars_per_year(df_1h),
        "settlement_bars_excluded": {
            "n": int(settle_mask.sum()),
            "note": ("a recurring ts_event==17:00 print in CL.c.0 (found "
                     "here, not documented anywhere upstream): interval "
                     "[17:00,18:00), after the 18:00-17:00 session this "
                     "study trades on, so bars.py excludes it from the "
                     "ET session grid; the UTC-day gate below includes it, "
                     "like any other bar, since it is a real Databento "
                     "print and the owned ohlcv-1d archive is not built on "
                     "the ET session either"),
        },
        "gaps_over_3h": gaps_over(df_1h, hours=gap_hours),
        "roll_sessions": roll_sessions(df_1h),
        "daily_agreement": agree,
        "daily_agreement_session_grid_reported_only": agree_session_grid,
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
    ag_sg = report["daily_agreement_session_grid_reported_only"]
    print(f"G1 -- CL 1-hour read-back (Amendment B: UTC calendar days)\n"
          f"bars: {report['coverage']['n_total']} total, "
          f"{report['coverage']['first']} .. {report['coverage']['last']}\n"
          f"by year: {report['coverage']['by_year']}\n"
          f"settlement bars (17:00 print), excluded from the ET session grid only: "
          f"{report['settlement_bars_excluded']['n']}\n"
          f"gaps >3h inside a session: {len(report['gaps_over_3h'])}\n"
          f"roll sessions: {len(report['roll_sessions'])}\n"
          f"daily agreement (UTC calendar days, GATING): {ag['n_within_tol']}/{ag['n_compared']} "
          f"({ag['pct_within_tol']:.4%}) within ${ag['tolerance_usd']}\n"
          f"dates only in 1H rebuild: {ag['n_only_in_1h_rebuild']}\n"
          f"dates only in owned 1D: {ag['n_only_in_owned_1d']}\n"
          f"daily agreement (18:00 ET session grid, reported only): "
          f"{ag_sg['n_within_tol']}/{ag_sg['n_compared']} ({ag_sg['pct_within_tol']:.4%})\n"
          f"misses, UTC days (worst 10 of {len(ag['misses'])}):")
    for m in ag["misses"][:10]:
        roll = "  [roll day]" if m["is_roll_day"] else ""
        print(f"  {m['date']}  1H={m['close_1h']:.2f}  1D={m['close_1d']:.2f}  "
              f"diff=${m['diff']:.2f}{roll}")

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
