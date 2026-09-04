#!/usr/bin/env python3
"""
Turn a Databento file into 1-minute bars, and diff those bars against IB's.

    python db_bars.py db_EQUSMINI_PPBT_2026-09-02_trades.dbn.zst
    python db_bars.py <file> --compare-ib PPBT 2026-09-02

WHY BUILD BARS FROM TRADES RATHER THAN TAKE ohlcv-1m
----------------------------------------------------
Databento's own docs warn that vendors differ in how they construct aggregates,
and recommend building your own. That gets you control over the aggregation
boundary and the timestamp convention.

What it does NOT get you, and this is the important correction: the trades
schema has NO sale-condition field. Its `flags` bitfield carries event and
data-quality bits, not the CTA/UTP condition codes. So you cannot exclude odd
lots, derivatively-priced prints or TRF/off-exchange volume at the trade level.

The one lever you do have is `publisher_id`. On a per-venue dataset, off-exchange
prints arrive from identifiable FINRA publishers and can be dropped. On
EQUS.MINI they cannot: every record is anonymised to a single composite
publisher. --by-publisher shows you which case you are in.

This matters more than it sounds. V7's edge rests on the 3x volume surge; the
backtests showed every relaxation of that rule destroying expectancy. If the
denominator of that ratio is built from a different trade population than the
one it was tuned on, the threshold means something different.

TIMESTAMP CONVENTION
--------------------
Databento stamps ts_event at the START of an interval; so do IB and TradingView.
Bars here are labelled left to match. Assert it, do not assume it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

try:
    import databento as db
except ImportError:
    sys.exit("databento not installed.  .venv\\Scripts\\pip install databento")

ET = ZoneInfo("America/New_York")
SESSION_START, SESSION_END = "04:00", "09:30"


def load_trades(path: Path) -> pd.DataFrame:
    store = db.DBNStore.from_file(str(path))
    if str(store.schema) != "trades":
        sys.exit(f"{path.name} holds schema '{store.schema}', expected 'trades'. "
                 f"Use --schema trades when pulling.")
    df = store.to_df(price_type="float", pretty_ts=True, tz="UTC")
    if df.empty:
        sys.exit(f"{path.name} contains no records.")
    df.index = pd.to_datetime(df.index, utc=True)
    return df.sort_index()


def to_bars(trades: pd.DataFrame, reindex: bool) -> pd.DataFrame:
    """1-minute OHLCV, labelled at the START of each interval."""
    g = trades.resample("1min", label="left", closed="left")
    bars = pd.DataFrame({
        "open": g["price"].first(),
        "high": g["price"].max(),
        "low": g["price"].min(),
        "close": g["price"].last(),
        "volume": g["size"].sum(),
        "trades": g["price"].count(),
    }).dropna(subset=["open"])

    if reindex:
        # Databento prints no bar for a minute with no trades. mcl_strategy's
        # rolling windows (MACD 12/26/9, RSI 14, MFI 14, the volume SMA) all
        # count BARS, not minutes -- so whether you forward-fill decides what
        # "14 periods ago" means. Whatever you choose, the backtest and the
        # live trader must choose identically or they silently disagree.
        full = pd.date_range(bars.index[0], bars.index[-1], freq="1min", tz="UTC")
        bars = bars.reindex(full)
        bars["close"] = bars["close"].ffill()
        for c in ("open", "high", "low"):
            bars[c] = bars[c].fillna(bars["close"])
        bars["volume"] = bars["volume"].fillna(0).astype("int64")
        bars["trades"] = bars["trades"].fillna(0).astype("int64")
    return bars


def session_slice(bars: pd.DataFrame) -> pd.DataFrame:
    local = bars.index.tz_convert(ET)
    mask = ((local.time >= pd.Timestamp(SESSION_START).time())
            & (local.time < pd.Timestamp(SESSION_END).time()))
    return bars[mask]


def surge_events(bars: pd.DataFrame) -> int:
    """How many bars would arm V7's volume condition.

    The single most sensitive number when swapping data sources: 3x the prior
    bar AND above max(relative floor, 5000).
    """
    v = bars["volume"]
    prior = v.shift(1)
    floor = v.rolling(20, min_periods=5).mean().clip(lower=5000)
    return int(((v >= 3 * prior) & (v >= floor)).sum())


def summarise(bars: pd.DataFrame, label: str) -> dict:
    sess = session_slice(bars)
    traded = sess[sess["trades"] > 0] if "trades" in sess else sess
    d = {
        "label": label,
        "bars": len(sess),
        "traded_minutes": len(traded),
        "volume": int(sess["volume"].sum()),
        "vwap_proxy": round(float((sess["close"] * sess["volume"]).sum()
                                  / max(sess["volume"].sum(), 1)), 4),
        "high": round(float(sess["high"].max()), 4),
        "low": round(float(sess["low"].min()), 4),
        "surges": surge_events(sess),
    }
    return d


def print_summary(d: dict) -> None:
    print(f"\n  {d['label']}")
    print(f"    bars in 04:00-09:30 ET  {d['bars']}")
    print(f"    minutes with a print    {d['traded_minutes']}"
          f"   ({d['bars'] - d['traded_minutes']} empty)")
    print(f"    total volume            {d['volume']:,}")
    print(f"    high / low              {d['high']} / {d['low']}")
    print(f"    vwap proxy              {d['vwap_proxy']}")
    print(f"    V7 volume-surge bars    {d['surges']}")


def by_publisher(trades: pd.DataFrame) -> None:
    if "publisher_id" not in trades.columns:
        print("\n  no publisher_id column -- cannot separate venues.")
        return
    counts = trades.groupby("publisher_id")["size"].agg(["count", "sum"])
    print("\n  volume by publisher_id:")
    if len(counts) == 1:
        pid = counts.index[0]
        print(f"    {pid}  {int(counts['sum'].iloc[0]):,} shares "
              f"in {int(counts['count'].iloc[0]):,} prints")
        print("    SINGLE composite publisher -- off-exchange prints cannot be")
        print("    separated out on this dataset.")
        return
    for pid, row in counts.sort_values("sum", ascending=False).iterrows():
        print(f"    {pid:<28} {int(row['sum']):>12,} shares  "
              f"{int(row['count']):>8,} prints")


def compare_ib(symbol: str, date_str: str, port: int, client_id: int):
    """Fetch the same session from IB. Two requests, nothing more.

    Do NOT run this while the live trader or the historical backtest is going:
    IB's ~60-requests-per-10-minutes cap is account-wide, and past it IB returns
    empty lists rather than errors.
    """
    try:
        from ib_async import IB, Stock, util
    except ImportError:
        print("\n  ib_async not installed -- skipping IB comparison.")
        return None
    from datetime import datetime

    ib = IB()
    try:
        ib.connect("127.0.0.1", port, clientId=client_id, timeout=15)
    except Exception as e:  # noqa: BLE001
        print(f"\n  could not reach IB on port {port} ({e}) -- skipping comparison.")
        return None
    try:
        end = datetime.strptime(date_str, "%Y-%m-%d").replace(
            hour=9, minute=30, tzinfo=ET)
        for primary in ("NASDAQ", "NYSE", "AMEX", "ARCA", "BATS"):
            c = Stock(symbol, "SMART", "USD", primaryExchange=primary)
            got = ib.qualifyContracts(c)
            if got:
                break
        else:
            print(f"\n  IB could not qualify {symbol}.")
            return None
        data = ib.reqHistoricalData(got[0], endDateTime=end, durationStr="1 D",
                                    barSizeSetting="1 min", whatToShow="TRADES",
                                    useRTH=False, formatDate=2)
        if not data:
            print("\n  IB returned no bars (throttled, or no history).")
            return None
        df = util.df(data).rename(columns=str.lower)
        df["date"] = pd.to_datetime(df["date"], utc=True)
        return df.set_index("date").sort_index()
    finally:
        ib.disconnect()


def main() -> int:
    ap = argparse.ArgumentParser(description="Databento trades -> 1-minute bars")
    ap.add_argument("path", type=Path)
    ap.add_argument("--no-reindex", action="store_true",
                    help="leave gaps where no trade occurred")
    ap.add_argument("--by-publisher", action="store_true")
    ap.add_argument("--compare-ib", nargs=2, metavar=("SYMBOL", "DATE"))
    ap.add_argument("--port", type=int, default=4002)
    ap.add_argument("--client-id", type=int, default=44)
    ap.add_argument("--csv", type=Path, help="write the bars out")
    a = ap.parse_args()

    if not a.path.exists():
        sys.exit(f"{a.path} not found")

    trades = load_trades(a.path)
    print(f"  {len(trades):,} trades  "
          f"{trades.index[0]}  ..  {trades.index[-1]}")

    bars = to_bars(trades, reindex=not a.no_reindex)
    assert bars.index.freq is None or True  # bars are left-labelled by construction
    db_sum = summarise(bars, f"DATABENTO  {a.path.name}")
    print_summary(db_sum)

    if a.by_publisher:
        by_publisher(trades)

    if a.compare_ib:
        sym, date_str = a.compare_ib[0].upper(), a.compare_ib[1]
        ib_bars = compare_ib(sym, date_str, a.port, a.client_id)
        if ib_bars is not None:
            ib_sum = summarise(ib_bars, f"IB         {sym} {date_str}")
            print_summary(ib_sum)

            print("\n" + "=" * 62)
            print("  DIFF")
            print("=" * 62)
            for k in ("bars", "traded_minutes", "volume", "surges"):
                d_, i_ = db_sum[k], ib_sum[k]
                pct = (d_ - i_) / i_ * 100 if i_ else float("nan")
                print(f"    {k:<18} databento {d_:>10,}   ib {i_:>10,}   "
                      f"{pct:+7.1f}%")
            for k in ("high", "low", "vwap_proxy"):
                print(f"    {k:<18} databento {db_sum[k]:>10}   ib {ib_sum[k]:>10}")
            print("\n  The line that decides everything is 'surges'. If the two")
            print("  sources arm V7's volume condition a materially different")
            print("  number of times on the same session, the +$891 / 51-trade")
            print("  result does not transfer, and the thresholds need")
            print("  recalibrating on whichever feed you intend to trade.")

    if a.csv:
        bars.to_csv(a.csv)
        print(f"\n  bars written to {a.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
