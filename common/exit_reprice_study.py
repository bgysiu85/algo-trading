#!/usr/bin/env python3
"""W02-0018 -- would a wider retry ladder have caught a collapsing exit higher.

    python -m common.exit_reprice_study
    python -m common.exit_reprice_study --archive E:\Databento --fills-dir var/fills

Registered in docs/research/REGISTERED_w02_0018_exit_reprice.md (PRE-RUN,
committed 6f75fd2 before this file existed). Reads data already fetched
(Databento XNAS.ITCH mbp-1, $0 -- inside the free window) and the paper fill
logs already on disk. Makes no network call and spends nothing.

METHOD (verbatim from the registration)
----------------------------------------
Every NO_FILL_ABANDONED SELL episode in var/fills/mcl_fills_*.csv from
2026-09-16 through 2026-09-28, excluding 2026-09-16 itself (496 rows, all
MEDS -- the known "MEDS ghost" abandon-path bug, not real repricing). For
each episode, walk the mbp-1 book tick by tick and compare three retry
rules, using the SAME retry timestamps the live trader actually used (only
the limit price each retry sends is counterfactual):

  ACTUAL   -- limit = bid - 0.2%   (today's LIMIT_CROSS_BPS=20 rule; this is
              exactly what the live trader sent -- replayed here as a check
              that the replay engine reproduces the real fill before trusting
              its counterfactuals)
  B1       -- limit = bid - 1% on every retry
  B2       -- limit = bid - 1% on the first retry, bid - 2% from the second on

A simulated limit fills at the first book tick, within that retry's window
(up to the next retry's timestamp, or a 10s cap after the last one), where
bid_px_00 >= limit AND bid_sz_00 >= 100 (the live order size). Fill price is
the limit itself -- never better. No fill within the window scores UNFILLED
for that ladder on that retry; the next retry (if any) is still tried.
"""
from __future__ import annotations

import argparse
import glob
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from common.dbn_io import read_dbn

REGISTERED = "docs/research/REGISTERED_w02_0018_exit_reprice.md"
ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
EXCLUDE_DAYS = {"20260916"}          # MEDS ghost bug -- see REGISTERED S1
MIN_SIZE = 100                        # the live order's own size
POST_TERMINAL_CAP_S = 10              # window after the last retry
LADDERS = {
    "actual": None,                   # uses limit_sent as recorded
    "B1_flat_1pct": [0.01],
    "B2_1_then_2pct": [0.01, 0.02],
}


def load_episodes(fills_dir: str) -> list:
    """Every NO_FILL_ABANDONED SELL row, grouped into episodes, with the
    terminal (FILLED/PARTIAL_FILL/CANCELLED/REJECTED) row's price and time."""
    files = sorted(glob.glob(os.path.join(fills_dir, "mcl_fills_*.csv")))
    rows = []
    for f in files:
        day = os.path.basename(f).split("_")[-1].replace(".csv", "")
        if day < "20260916" or day in EXCLUDE_DAYS:
            continue
        df = pd.read_csv(f)
        df = df[df["action"] == "SELL"].copy()
        if df.empty:
            continue
        df["ts_et"] = pd.to_datetime(df["ts_et"])
        df["day"] = day
        rows.append(df)
    if not rows:
        return []
    all_rows = pd.concat(rows, ignore_index=True)

    episodes = []
    eid = 0
    for (day, strategy, symbol), g in all_rows.groupby(["day", "strategy", "symbol"],
                                                        sort=False):
        g = g.sort_values("ts_et").reset_index(drop=True)
        cur = None
        for _, row in g.iterrows():
            if row["status"] == "NO_FILL_ABANDONED":
                if cur is None:
                    eid += 1
                    cur = {"episode_id": eid, "day": day, "strategy": strategy,
                           "symbol": symbol, "reason": row["reason"], "retries": []}
                cur["retries"].append(row)
            elif cur is not None:
                cur["terminal_status"] = row["status"]
                cur["terminal_ts"] = row["ts_et"]
                cur["terminal_fill"] = row.get("fill_price")
                # The order that actually filled (or was cancelled/rejected)
                # is itself a priced attempt, sent fresh after the last
                # abandon -- its own limit_sent belongs in the retry ladder,
                # not just the abandons that preceded it. Without this the
                # "actual" replay only ever tests abandoned limits and can
                # never reproduce the real fill.
                if row["status"] in ("FILLED", "PARTIAL_FILL") and pd.notna(row.get("limit_sent")):
                    cur["retries"].append(row)
                episodes.append(cur)
                cur = None
        if cur is not None:
            cur["terminal_status"] = "UNRESOLVED_EOF"
            cur["terminal_ts"] = cur["retries"][-1]["ts_et"] + pd.Timedelta(seconds=30)
            cur["terminal_fill"] = None
            episodes.append(cur)
    return episodes


def et_to_utc(ts) -> pd.Timestamp:
    return pd.Timestamp(ts).tz_localize(ET).tz_convert(UTC)


def book_for(archive: str, day: str, symbol: str) -> pd.DataFrame:
    path = Path(archive) / "XNAS.ITCH" / "mbp-1" / f"{day[:4]}-{day[4:6]}-{day[6:]}.dbn.zst"
    if not path.exists():
        return pd.DataFrame()
    df = read_dbn(path)
    df = df[df["symbol"] == symbol]
    return df[["bid_px_00", "ask_px_00", "bid_sz_00", "ask_sz_00"]].sort_index()


def simulate_fill(book: pd.DataFrame, window_start_utc, window_end_utc, limit: float):
    """First tick in (start, end] with bid >= limit and displayed size >= MIN_SIZE.
    Returns (fill_price, fill_ts) or (None, None)."""
    w = book.loc[(book.index > window_start_utc) & (book.index <= window_end_utc)]
    ok = w[(w["bid_px_00"] >= limit) & (w["bid_sz_00"] >= MIN_SIZE)]
    if ok.empty:
        return None, None
    return round(limit, 4), ok.index[0]


def run_ladder(book: pd.DataFrame, episode: dict, ladder_pcts) -> dict:
    retries = episode["retries"]
    n = len(retries)
    for i, row in enumerate(retries):
        retry_ts = et_to_utc(row["ts_et"])
        window_end = (et_to_utc(retries[i + 1]["ts_et"]) if i + 1 < n
                      else et_to_utc(episode["terminal_ts"])
                      + pd.Timedelta(seconds=POST_TERMINAL_CAP_S))
        if ladder_pcts is None:
            limit = float(row["limit_sent"])
        else:
            step = ladder_pcts[min(i, len(ladder_pcts) - 1)]
            bid = float(row["bid"])
            limit = round(bid * (1 - step), 4)
        price, ts = simulate_fill(book, retry_ts, window_end, limit)
        if price is not None:
            return {"filled": True, "price": price, "fill_ts": ts,
                     "on_retry": i + 1, "limit_used": limit}
    return {"filled": False, "price": None, "fill_ts": None,
             "on_retry": None, "limit_used": None}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", default=os.environ.get("DATABENTO_ARCHIVE", "E:/Databento"))
    ap.add_argument("--fills-dir", default="var/fills")
    ap.add_argument("--out", default="var/reports/w02_0018_exit_reprice.csv")
    ap.add_argument("--raw-out", default="Claude outputs/w02_0018_exit_reprice_20260928.txt")
    a = ap.parse_args(argv)

    episodes = load_episodes(a.fills_dir)
    print(f"{len(episodes)} episodes loaded (2026-09-16 excluded)")

    books: dict = {}
    results = []
    for ep in episodes:
        key = (ep["day"], ep["symbol"])
        if key not in books:
            books[key] = book_for(a.archive, ep["day"], ep["symbol"])
        book = books[key]
        row = {"episode_id": ep["episode_id"], "day": ep["day"],
               "strategy": ep["strategy"], "symbol": ep["symbol"],
               "n_retries": len(ep["retries"]),
               "terminal_status": ep["terminal_status"],
               "actual_fill": ep["terminal_fill"]}
        if book.empty:
            row["book_rows"] = 0
            for name in LADDERS:
                row[f"{name}_filled"] = None
                row[f"{name}_price"] = None
                row[f"{name}_on_retry"] = None
            results.append(row)
            print(f"  {ep['day']} {ep['strategy']} {ep['symbol']}: NO BOOK DATA -- skipped")
            continue
        row["book_rows"] = len(book)
        for name, pcts in LADDERS.items():
            r = run_ladder(book, ep, pcts)
            row[f"{name}_filled"] = r["filled"]
            row[f"{name}_price"] = r["price"]
            row[f"{name}_on_retry"] = r["on_retry"]
        results.append(row)

    out = pd.DataFrame(results)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(a.out, index=False)
    print(f"\nwritten: {a.out}  ({len(out)} rows)")

    # --- validation: does the replay reproduce the real fill? ---
    val = out.dropna(subset=["actual_fill", "actual_filled"])
    val = val[val["actual_filled"] == True]  # noqa: E712
    if not val.empty:
        diff = (val["actual_price"] - val["actual_fill"]).abs()
        print(f"\nVALIDATION (replay 'actual' vs real fill_price), n={len(val)}:")
        print(f"  matched within $0.01: {(diff <= 0.01).sum()} / {len(val)}")
        print(f"  max abs diff: {diff.max():.4f}")
        bad = val[diff > 0.01]
        if not bad.empty:
            print("  mismatches:")
            print(bad[["day", "strategy", "symbol", "actual_price", "actual_fill"]]
                  .to_string(index=False))

    Path(a.raw_out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.raw_out, "w", encoding="utf-8") as f:
        f.write(out.to_string(index=False))
    print(f"raw report: {a.raw_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
