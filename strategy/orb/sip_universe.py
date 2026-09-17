#!/usr/bin/env python3
r"""The qualifying set and the Relative Volume ranking, point in time.

    python -m strategy.orb.sip_universe                      # writes the table
    python -m strategy.orb.sip_universe --report var/reports/orb_sip_universe.txt

`docs/research/REGISTERED_orb_sip.md` section 2 fixes every rule below and this
module adds no judgement. Where the two disagree the registration wins.

    open > $5.00                      today's 09:30 bar open
    mean(daily volume, prior 14) >= 1,000,000        EQUS.SUMMARY, CONSOLIDATED
    ATR(14) > $0.50                   prior 14 sessions, RTH bars only
    RVOL = OR volume / mean(OR volume, prior 14) >= 1.00
    rank by RVOL descending, ties by symbol ascending, take the top 20

EVERYTHING EXCEPT THE OPEN AND TODAY'S OR VOLUME IS FROM PRIOR SESSIONS, and
that is the whole point. `orb_pit_RESULT_20260917.md` closed the last strategy
because its universe was selected with the day's own bar: the profitable group
was the names that needed the whole session to be knowable. Here the windows
are shifted by one session in code (`.shift(1)`), and a test fails if today's
value can reach its own average.

WHY THE CONSOLIDATED FEED FOR ONE FILTER AND THE MINUTE TAPE FOR THE OTHERS
---------------------------------------------------------------------------
The liquidity filter is a statement about the market, so it reads consolidated
volume (EQUS.SUMMARY). ATR and the opening range are statements about the bars
the strategy will actually trade, so they read the same XNAS.BASIC RTH minute
bars the engine reads. Mixing those the other way -- an ATR from whole-feed
daily bars, which include extended hours -- would widen every stop by the
overnight range, which is the defect `prior_close_defect_CONFIRMED_20260912.md`
found in another divisor.

A NAME WITH NO 09:30 BAR IS NOT IN THE UNIVERSE. Its "open" would be whatever
minute it first printed, which on a thin name is 09:47. Counted, not guessed.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SUMMARY_DEFAULT = Path("var/cache/orb_sip/summary")
DVOL_CACHE = Path("var/cache/orb_sip/daily_volume.csv.gz")
OUT_DEFAULT = Path("var/state/orb_sip_universe.csv.gz")

LOOKBACK = 14
MIN_OPEN = 5.00
MIN_AVG_VOLUME = 1_000_000.0
MIN_ATR = 0.50
MIN_RVOL = 1.00
TOP_N = 20
# Section 3.5: the $2-20 band is replaced here by the paper's floor plus a
# guard against an unadjusted corporate action. A 1-for-10 reverse split prints
# as a 10x overnight move on a raw tape and would otherwise enter the universe
# as the day's most active name.
GUARD_LO, GUARD_HI = 0.2, 5.0
RTH_OPEN_MIN = 9 * 60 + 30

SUMMARY_COLS = ["symbol", "date", "open", "first_bar", "rth_high", "rth_low",
                "rth_close", "or5_volume", "or15_volume"]


def load_summaries(summary_dir: Path, start: str | None = None,
                   end: str | None = None) -> pd.DataFrame:
    files = sorted(summary_dir.glob("*.csv.gz"))
    if start:
        files = [f for f in files if f.name[:10] >= start]
    if end:
        files = [f for f in files if f.name[:10] <= end]
    if not files:
        raise FileNotFoundError(f"no summaries under {summary_dir}")
    parts = [pd.read_csv(f, usecols=SUMMARY_COLS, encoding="utf-8") for f in files]
    return pd.concat(parts, ignore_index=True)


def load_daily_volume(archive: Path, dataset: str, cache: Path,
                      force: bool = False) -> pd.DataFrame:
    """Consolidated daily volume per symbol-day, cached after the first read."""
    if cache.exists() and not force:
        return pd.read_csv(cache, encoding="utf-8")
    from common.dbn_io import read_dbn
    rows = []
    for f in sorted((archive / dataset / "ohlcv-1d").glob("*.dbn.zst")):
        df = read_dbn(f)
        if df.empty:
            continue
        rows.append(pd.DataFrame({
            "symbol": df["symbol"].to_numpy(),
            "date": df.index.tz_convert("America/New_York").strftime("%Y-%m-%d"),
            "day_volume": df["volume"].to_numpy(float)}))
    out = pd.concat(rows, ignore_index=True).drop_duplicates(["symbol", "date"])
    cache.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(cache, index=False, encoding="utf-8", compression="gzip")
    return out


def _prior_mean(df: pd.DataFrame, col: str, n: int = LOOKBACK) -> pd.Series:
    """Mean of the PRIOR n values of `col` within each symbol.

    `shift(1)` before `rolling` is the point-in-time step. Without it the
    average contains the very value being ranked against it, which on a
    volume spike day pulls the denominator up and the ratio down -- a
    look-ahead that makes the strategy look worse, and is a look-ahead
    either way.
    """
    s = df.groupby("symbol", sort=False)[col]
    return s.transform(lambda x: x.shift(1).rolling(n, min_periods=n).mean())


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df.groupby("symbol", sort=False)["rth_close"].shift(1)
    a = df["rth_high"] - df["rth_low"]
    b = (df["rth_high"] - prev_close).abs()
    c = (df["rth_low"] - prev_close).abs()
    return pd.concat([a, b, c], axis=1).max(axis=1)


def build_universe(summ: pd.DataFrame, dvol: pd.DataFrame) -> pd.DataFrame:
    """One row per symbol-day with every filter and both rankings."""
    df = summ.merge(dvol, on=["symbol", "date"], how="left")
    df = df.sort_values(["symbol", "date"], kind="stable").reset_index(drop=True)

    df["tr"] = true_range(df)
    df["atr14"] = _prior_mean(df, "tr")
    df["advol14"] = _prior_mean(df, "day_volume")
    df["prior_close"] = df.groupby("symbol", sort=False)["rth_close"].shift(1)
    for n in (5, 15):
        df[f"avg_or{n}"] = _prior_mean(df, f"or{n}_volume")
        df[f"rvol{n}"] = df[f"or{n}_volume"] / df[f"avg_or{n}"]

    ratio = df["open"] / df["prior_close"]
    df["has_open"] = df["first_bar"] == RTH_OPEN_MIN
    df["guard_ok"] = ratio.between(GUARD_LO, GUARD_HI) & df["prior_close"].gt(0)
    df["qualifies"] = (
        df["has_open"]
        & df["open"].gt(MIN_OPEN)
        & df["advol14"].ge(MIN_AVG_VOLUME)
        & df["atr14"].gt(MIN_ATR)
        & df["guard_ok"].fillna(False)
    )
    for n in (5, 15):
        ok = df["qualifies"] & df[f"rvol{n}"].ge(MIN_RVOL)
        df[f"eligible{n}"] = ok
        # Ties by symbol ascending, fixed in the registration so the tie rule
        # can never become a choice made after seeing a result.
        order = df[ok].sort_values([f"rvol{n}", "symbol"],
                                   ascending=[False, True], kind="stable")
        rank = order.groupby("date", sort=False).cumcount() + 1
        df[f"rank{n}"] = pd.Series(rank, index=order.index).reindex(df.index)
    return df


def counts(df: pd.DataFrame) -> dict:
    sessions = df["date"].nunique()
    q = df[df["qualifies"]]
    per_session = q.groupby("date").size()
    e5 = df[df["eligible5"]].groupby("date").size()
    top = df[df["rank5"].le(TOP_N)]
    return {
        "symbol_days": len(df),
        "sessions": sessions,
        "no_0930_bar": int((~df["has_open"]).sum()),
        "guard_refused": int((df["has_open"] & ~df["guard_ok"].fillna(False)).sum()),
        "qualify": int(len(q)),
        "qualify_per_session_median": float(per_session.median()) if len(per_session) else 0.0,
        "eligible5": int(df["eligible5"].sum()),
        "eligible5_per_session_median": float(e5.median()) if len(e5) else 0.0,
        "sessions_short_of_top_n": int((e5 < TOP_N).sum()),
        "top20_symbol_days": int(len(top)),
        "rvol5_top20_median": float(top["rvol5"].median()) if len(top) else 0.0,
    }


def render(c: dict, summary_dir: Path, dataset: str, first: str, last: str) -> list[str]:
    return [
        "ORB STOCKS IN PLAY -- THE QUALIFYING SET AND THE RVOL RANKING", "",
        f"  summaries        {summary_dir}",
        f"  daily volume     {dataset} ohlcv-1d (CONSOLIDATED)",
        f"  sessions         {c['sessions']:,}  {first} -> {last}",
        f"  symbol-days read {c['symbol_days']:,}", "",
        "  REGISTERED FILTERS (section 2), every window from PRIOR sessions",
        f"    open > ${MIN_OPEN:.2f}   avg volume(14) >= {MIN_AVG_VOLUME:,.0f}   "
        f"ATR(14) > ${MIN_ATR:.2f}   RVOL >= {MIN_RVOL:.2f}   top {TOP_N}", "",
        f"  no 09:30 bar, excluded      {c['no_0930_bar']:,}",
        f"  adjustment guard refused    {c['guard_refused']:,}   "
        f"(open outside {GUARD_LO}x-{GUARD_HI}x the prior RTH close)",
        f"  qualifying symbol-days      {c['qualify']:,}   "
        f"median {c['qualify_per_session_median']:.0f} a session",
        f"  of those, RVOL >= 1         {c['eligible5']:,}   "
        f"median {c['eligible5_per_session_median']:.0f} a session",
        f"  sessions with fewer than {TOP_N} eligible names  "
        f"{c['sessions_short_of_top_n']:,}",
        f"  top-{TOP_N} symbol-days         {c['top20_symbol_days']:,}   "
        f"median RVOL {c['rvol5_top20_median']:.2f}", "",
        "  Nothing here is a trade or a P/L. The engine reads this table.", "",
    ]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--summaries", default=str(SUMMARY_DEFAULT))
    p.add_argument("--archive", default=None)
    p.add_argument("--daily-dataset", default="EQUS.SUMMARY")
    p.add_argument("--dvol-cache", default=str(DVOL_CACHE))
    p.add_argument("--refresh-dvol", action="store_true")
    p.add_argument("--start")
    p.add_argument("--end")
    p.add_argument("--out", default=str(OUT_DEFAULT))
    p.add_argument("--report", default="var/reports/orb_sip_universe.txt")
    a = p.parse_args(argv)

    if a.archive:
        archive = Path(a.archive)
    else:
        from common.databento_fetch import default_archive
        archive = default_archive()

    summ = load_summaries(Path(a.summaries), a.start, a.end)
    dvol = load_daily_volume(archive, a.daily_dataset, Path(a.dvol_cache),
                             a.refresh_dvol)
    df = build_universe(summ, dvol)
    keep = ["symbol", "date", "open", "prior_close", "atr14", "advol14",
            "or5_volume", "avg_or5", "rvol5", "rank5", "eligible5",
            "or15_volume", "avg_or15", "rvol15", "rank15", "eligible15",
            "qualifies", "has_open", "guard_ok"]
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df[keep].to_csv(out, index=False, encoding="utf-8", compression="gzip")

    from common.report_io import emit
    c = counts(df)
    emit("\n".join(render(c, Path(a.summaries), a.daily_dataset,
                          df["date"].min(), df["date"].max())),
         a.report,
         header=f"strategy.orb.sip_universe  rows={len(df):,}  out={out}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
