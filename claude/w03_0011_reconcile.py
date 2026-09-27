#!/usr/bin/env python3
from __future__ import annotations
import csv, sys
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
sys.path.insert(0, ".")
from common.entry_gates import load_quote_window, TOLERANCE_S

ET = ZoneInfo("America/New_York")
DATES = ["20260910", "20260911", "20260914", "20260915"]

def live_rows(dates):
    out = []
    for d in dates:
        fn = f"var/fills/mcl_fills_{d}.csv"
        day = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        with open(fn, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row["action"] != "BUY" or row["reason"] != "entry_signal":
                    continue
                try:
                    bid = float(row["bid"]); ask = float(row["ask"])
                except (TypeError, ValueError):
                    continue
                if not (bid > 0 and ask > 0 and ask >= bid):
                    continue
                row["_day"] = day; row["_bid"] = bid; row["_ask"] = ask
                out.append(row)
    return out

def main():
    archive = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(r"E:\Databento")
    rows = live_rows(DATES)
    print(f"live BUY entry_signal rows across {DATES}: {len(rows)}")
    results = []
    no_quote = 0
    for row in rows:
        day = row["_day"]; symbol = row["symbol"]
        ts_et = pd.Timestamp(row["ts_et"]).tz_localize(ET)
        ts_utc = ts_et.tz_convert("UTC")
        quotes = load_quote_window(archive, day, symbol)
        if quotes.empty:
            no_quote += 1; bt_spread = np.nan
        else:
            q = quotes.copy()
            q["mid"] = (q["bid"] + q["ask"]) / 2.0
            q["spread_pct"] = (q["ask"] - q["bid"]) / q["mid"]
            idx = q["ts"].searchsorted(ts_utc, side="right") - 1
            if idx < 0:
                bt_spread = np.nan
            else:
                delta = (ts_utc - q["ts"].iloc[idx]).total_seconds()
                bt_spread = (q["spread_pct"].iloc[idx] * 100.0 if delta <= TOLERANCE_S else np.nan)
                if delta > TOLERANCE_S:
                    no_quote += 1
        live_bid, live_ask = row["_bid"], row["_ask"]
        live_mid = (live_bid + live_ask) / 2.0
        live_spread_mid_pct = (live_ask - live_bid) / live_mid * 100.0
        logged_spread_pct = float(row["spread_pct"]) if row["spread_pct"] not in ("", None) else np.nan
        results.append(dict(day=day, symbol=symbol, strategy=row["strategy"],
                             ts_et=row["ts_et"], status=row["status"],
                             live_bid=live_bid, live_ask=live_ask,
                             live_spread_mid_pct=live_spread_mid_pct,
                             logged_spread_pct=logged_spread_pct,
                             bt_spread_pct=bt_spread))
    df = pd.DataFrame(results)
    df["diff_bt_minus_live"] = df["bt_spread_pct"] - df["live_spread_mid_pct"]
    out_csv = "var/reports/w03_0011_reconcile.csv"
    df.to_csv(out_csv, index=False)
    have_bt = df.dropna(subset=["bt_spread_pct"])
    print(f"\nrows with a cbbo-1s quote inside {TOLERANCE_S}s of the live entry: {len(have_bt)} / {len(df)} ({no_quote} NO_QUOTE)")
    print("\n--- live IB spread (mid-based, recomputed) ---")
    print(df["live_spread_mid_pct"].describe())
    print("\n--- live logged spread_pct column (ask-based, as-written) ---")
    print(df["logged_spread_pct"].describe())
    if not have_bt.empty:
        print("\n--- backtest cbbo-1s spread, matched rows only ---")
        print(have_bt["bt_spread_pct"].describe())
        print("\n--- diff (backtest - live mid-based), matched rows ---")
        print(have_bt["diff_bt_minus_live"].describe())
        print(f"\nbacktest >= 2.0% threshold: {(have_bt['bt_spread_pct'] >= 2.0).sum()} / {len(have_bt)}")
        print(f"live mid  >= 2.0% threshold: {(have_bt['live_spread_mid_pct'] >= 2.0).sum()} / {len(have_bt)}")
        print("\nworst 15 by |diff|:")
        print(have_bt.reindex(have_bt["diff_bt_minus_live"].abs().sort_values(ascending=False).index)
              [["day","symbol","ts_et","live_bid","live_ask","live_spread_mid_pct","bt_spread_pct","diff_bt_minus_live"]]
              .head(15).to_string(index=False))
    print(f"\nwrote {out_csv}")

if __name__ == "__main__":
    main()
